"""Helpers for opening and reading raw sources: disk images, block devices,
and mounted volumes (including phones connected in file-transfer/MTP mode
that the OS exposes as a regular filesystem).
"""

import io
import os
import platform
import struct
import sys
from dataclasses import dataclass
from typing import BinaryIO, Iterator, List, Optional, Tuple


def human_size(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(n) < 1024.0:
            return f"{n:3.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"


def human_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}sa {minutes}dk"
    if minutes:
        return f"{minutes}dk {secs}sn"
    return f"{secs}sn"


def estimate_remaining(done: int, total: int, elapsed: float) -> Optional[str]:
    """Rough ETA string ("tahmini kalan: 12dk 30sn") from progress so far.

    Bytes/sec varies a lot in the first few seconds of a scan (disk
    caching, USB negotiation, etc.), so this is intentionally hidden
    until there's enough signal (>=2s elapsed and >=1% done) to avoid
    printing a wildly wrong number that then jumps around.
    """
    if total <= 0 or done <= 0 or elapsed < 2.0:
        return None
    fraction = done / total
    if fraction < 0.01:
        return None
    rate = done / elapsed
    if rate <= 0:
        return None
    remaining_bytes = total - done
    remaining_seconds = remaining_bytes / rate
    return human_duration(remaining_seconds)


def is_windows() -> bool:
    return platform.system() == "Windows"


def is_macos() -> bool:
    return platform.system() == "Darwin"


def is_linux() -> bool:
    return platform.system() == "Linux"


def list_block_devices() -> List[Tuple[str, str]]:
    """Best-effort listing of candidate raw devices/disks the user might
    want to scan. Returns list of (path, description).
    """
    results: List[Tuple[str, str]] = []
    if is_linux():
        base = "/sys/block"
        if os.path.isdir(base):
            for name in sorted(os.listdir(base)):
                dev_path = f"/dev/{name}"
                size_path = os.path.join(base, name, "size")
                size_str = ""
                try:
                    with open(size_path) as f:
                        sectors = int(f.read().strip())
                        size_str = human_size(sectors * 512)
                except Exception:
                    pass
                if os.path.exists(dev_path):
                    results.append((dev_path, f"{name} ({size_str})" if size_str else name))
    elif is_macos():
        try:
            import subprocess

            out = subprocess.run(["diskutil", "list"], capture_output=True, text=True, timeout=10)
            for line in out.stdout.splitlines():
                line = line.strip()
                if line.startswith("/dev/disk"):
                    results.append((line.split()[0], line))
        except Exception:
            pass
    elif is_windows():
        results.extend(_list_windows_disks_powershell())
        if not results:
            results.extend(_list_windows_disks_wmic())
    return results


def _list_windows_disks_powershell() -> List[Tuple[str, str]]:
    """Preferred method: PowerShell's Get-CimInstance. wmic is deprecated
    and removed entirely on newer Windows builds, so this is the reliable
    path there.
    """
    results: List[Tuple[str, str]] = []
    try:
        import json
        import subprocess

        cmd = (
            "Get-CimInstance Win32_DiskDrive | "
            "Select-Object DeviceID,Model,Size | ConvertTo-Json -Compress"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=15,
        )
        data = json.loads(out.stdout.strip()) if out.stdout.strip() else []
        if isinstance(data, dict):
            data = [data]
        for disk in data:
            device_id = disk.get("DeviceID", "")
            model = disk.get("Model", "")
            size = disk.get("Size")
            size_str = human_size(int(size)) if size else ""
            if device_id:
                desc = f"{model} ({size_str})" if size_str else model
                results.append((device_id, desc))
    except Exception:
        pass
    return results


def _list_windows_disks_wmic() -> List[Tuple[str, str]]:
    """Fallback for older Windows where wmic still exists."""
    results: List[Tuple[str, str]] = []
    try:
        import subprocess

        out = subprocess.run(
            ["wmic", "diskdrive", "get", "DeviceID,Model,Size"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in out.stdout.splitlines()[1:]:
            line = line.strip()
            if line:
                results.append((line.split()[0], line))
    except Exception:
        pass
    return results


def is_windows_device_path(path: str) -> bool:
    """True for \\\\.\\PhysicalDriveN and \\\\.\\X: style raw device paths."""
    return path.startswith("\\\\.\\") or path.startswith("\\\\?\\")


class AlignedFile:
    """Wraps a raw, unbuffered file handle so arbitrary byte-granular
    seek() and read() calls work on top of it.

    Windows refuses non-sector-aligned reads and seeks on raw device
    handles (\\\\.\\PhysicalDriveN, \\\\.\\X:), raising OSError
    (WinError 87, "the parameter is incorrect") for anything not aligned
    to the sector size. Nearly every read this tool performs can land on
    an unaligned boundary: carving at an arbitrary byte offset, FAT and
    NTFS structures that are not sector-sized. On Windows raw devices
    everything therefore goes through this wrapper, which rounds each
    request out to ALIGN-byte boundaries internally and returns only the
    bytes asked for.
    """

    ALIGN = 4096  # safe superset of both 512- and 4096-byte sector devices

    def __init__(self, raw_fh):
        self._fh = raw_fh
        self._pos = 0
        self._size = None  # lazily discovered, best-effort
        self._max_chunk = None  # largest single ReadFile() size known to work

    def _discover_size(self):
        if self._size is not None:
            return self._size
        try:
            self._fh.seek(0, io.SEEK_END)
            self._size = self._fh.tell()
            self._fh.seek(0)
        except OSError:
            self._size = 0
        return self._size

    def set_known_size(self, size: int) -> None:
        """Accept an exact device byte size from a caller that already
        knows it, such as a Windows ioctl that does not disturb the read
        position (see _windows_raw_disk_size), instead of falling back to
        _discover_size()'s SEEK_END probe.

        This also lets read() refuse to attempt anything past the real
        end of the device. Some raw-device drivers, including certain USB
        mass storage bridges, do not return a clean short read at
        end-of-device the way a normal file does; they raise
        ERROR_ACCESS_DENIED, which is indistinguishable from a genuine
        permissions failure. Knowing the boundary in advance means the
        request is never made.
        """
        if size and size > 0:
            self._size = size

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = self._discover_size() + offset
        else:
            raise ValueError(f"invalid whence: {whence}")
        return self._pos

    def tell(self) -> int:
        return self._pos

    def _read_span(self, start: int, length: int) -> bytes:
        """Read exactly the aligned [start, start+length) range from the
        raw handle, splitting into smaller ReadFile() calls if the driver
        rejects a large one.

        Some storage stacks, USB mass storage especially, cap a single
        raw ReadFile() at somewhere around 64KB to 1MB and reject
        anything larger. Some security products also throttle large
        sequential raw-disk reads. Both surface to Python as a plain
        PermissionError or OSError with no indication of the cause,
        looking identical to a genuine "not admin" error. Rather than
        guess a safe size up front, start with the whole span in one call
        and halve on failure until one succeeds, then reuse that size so
        later reads do not repeat the failures.
        """
        align = self.ALIGN
        pieces = []
        pos = start
        end = start + length
        chunk = self._max_chunk or length
        while pos < end:
            want = min(chunk, end - pos)
            self._fh.seek(pos)
            try:
                data = self._fh.read(want)
            except OSError as e:
                if chunk <= align:
                    # Add the offset and size of the failing read to the
                    # message. errno is preserved, so Python still maps
                    # this to the same exception subclass (PermissionError
                    # for EACCES, for instance).
                    raise OSError(
                        e.errno,
                        f"{e.strerror} (offset={pos}, size={want}, hedef aralik=[{start},{start + length}))",
                    ) from e
                chunk = max(align, chunk // 2)
                continue
            if self._max_chunk is None or chunk < self._max_chunk:
                self._max_chunk = chunk
            if not data:
                break
            pieces.append(data)
            pos += len(data)
            if len(data) < want:
                break  # short read, likely EOF
        return b"".join(pieces)

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = max(0, self._discover_size() - self._pos)
            if size == 0:
                return b""

        # When the device's real size is known (set_known_size(), or an
        # earlier _discover_size()), never attempt a read at or past it.
        # Some drivers raise ERROR_ACCESS_DENIED there instead of a clean
        # short read. This can only shrink `size`, so in-bounds reads are
        # unaffected.
        if self._size is not None:
            if self._pos >= self._size:
                return b""
            size = min(size, self._size - self._pos)

        align = self.ALIGN
        aligned_start = (self._pos // align) * align
        aligned_end = ((self._pos + size + align - 1) // align) * align

        # Clamp the aligned window too, so it cannot cross the real end
        # after rounding up. Instead of requesting bytes known not to
        # exist, settle for the last fully in-bounds block and drop the
        # remainder past it, at most ALIGN-1 bytes. Losing a few KB at the
        # very physical end of a multi-GB device does not affect
        # signature-based recovery.
        if self._size is not None and aligned_end > self._size:
            # Floor to the 512-byte sector size rather than the full
            # ALIGN. ALIGN is a conservative margin for general
            # offset/size alignment, but flooring the boundary to it would
            # discard an entire readable partial block whenever the
            # device's true size is not an ALIGN multiple, which is
            # common: device sizes are reliably 512-sector multiples but
            # not necessarily 4096-byte ones. 512 is also the minimum
            # sector size the MBR/GPT/FAT/NTFS parsing already assumes.
            sector = 512
            safe_end = (self._size // sector) * sector
            if safe_end > aligned_start:
                aligned_end = safe_end
            else:
                aligned_end = aligned_start  # nothing safely readable left

        if aligned_end <= aligned_start:
            return b""

        try:
            buf = self._read_span(aligned_start, aligned_end - aligned_start)
        except OSError:
            # Near the true end of the device the last aligned block can
            # overshoot its real size; retry with a smaller aligned window
            # before giving up.
            shrink = aligned_end - align
            if shrink <= aligned_start:
                return b""
            buf = self._read_span(aligned_start, shrink - aligned_start)

        start_in_buf = self._pos - aligned_start
        result = buf[start_in_buf : start_in_buf + size]
        self._pos += len(result)
        return result

    def close(self):
        self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def open_source(path: str) -> BinaryIO:
    """Open a raw device, disk image file, or any file/path for binary
    sequential reading. On Windows, raw physical drives/volumes need to be
    opened via \\\\.\\PhysicalDriveN or \\\\.\\X: syntax, which the caller
    passes directly; those are wrapped in AlignedFile since Windows
    requires sector-aligned I/O on them.
    """
    raw = open(path, "rb", buffering=0)
    if is_windows() and is_windows_device_path(path):
        return AlignedFile(raw)
    return raw


class OffsetView:
    """Presents a byte-range of an underlying seekable/readable file-like
    object as if it started at position 0. Used so filesystem parsers that
    assume "offset 0 == start of the volume" (true for a single partition)
    also work when the source is actually a whole raw disk with a
    partition table ahead of that volume.
    """

    def __init__(self, base_fh, offset: int, size: Optional[int] = None):
        self._fh = base_fh
        self._offset = offset
        self._size = size
        self._pos = 0

    def seek(self, pos: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = pos
        elif whence == 1:
            self._pos += pos
        elif whence == 2:
            if self._size is None:
                raise OSError("size unknown for SEEK_END on this view")
            self._pos = self._size + pos
        else:
            raise ValueError(f"invalid whence: {whence}")
        return self._pos

    def tell(self) -> int:
        return self._pos

    def read(self, size: int = -1) -> bytes:
        self._fh.seek(self._offset + self._pos)
        data = self._fh.read(size)
        self._pos += len(data)
        return data


@dataclass
class PartitionInfo:
    offset: int  # byte offset from the start of the raw disk
    size: int  # bytes
    type_desc: str


def find_mbr_partitions(fh) -> List[PartitionInfo]:
    """Reads the classic MBR partition table (offset 0x1BE, four 16-byte
    entries) from a whole-disk source and returns the ones that look real.
    Returns an empty list if this doesn't look like an MBR at all (e.g. a
    GPT protective MBR, a superfloppy with no partition table, or a source
    that's already a single volume rather than a whole disk).
    """
    fh.seek(0)
    sector0 = fh.read(512)
    if len(sector0) < 512 or sector0[510:512] != b"\x55\xAA":
        return []

    partitions: List[PartitionInfo] = []
    for i in range(4):
        entry = sector0[0x1BE + i * 16 : 0x1BE + (i + 1) * 16]
        part_type = entry[4]
        if part_type == 0:
            continue
        if part_type == 0xEE:
            return []  # GPT protective MBR; caller should try GPT instead
        lba_start = struct.unpack("<I", entry[8:12])[0]
        num_sectors = struct.unpack("<I", entry[12:16])[0]
        if lba_start == 0 or num_sectors == 0:
            continue
        partitions.append(
            PartitionInfo(
                offset=lba_start * 512,
                size=num_sectors * 512,
                type_desc=f"MBR type 0x{part_type:02x}",
            )
        )
    return partitions


def find_gpt_partitions(fh) -> List[PartitionInfo]:
    """Best-effort GPT partition table parser (partition entries starting
    at LBA 2, standard 128-byte entries, 512-byte logical sectors assumed).
    """
    fh.seek(512)
    gpt_header = fh.read(512)
    if len(gpt_header) < 512 or gpt_header[0:8] != b"EFI PART":
        return []

    entry_lba = struct.unpack("<Q", gpt_header[72:80])[0]
    num_entries = struct.unpack("<I", gpt_header[80:84])[0]
    entry_size = struct.unpack("<I", gpt_header[84:88])[0]
    if entry_size == 0 or num_entries == 0 or num_entries > 1024:
        return []

    fh.seek(entry_lba * 512)
    table = fh.read(num_entries * entry_size)

    partitions: List[PartitionInfo] = []
    for i in range(num_entries):
        entry = table[i * entry_size : (i + 1) * entry_size]
        if len(entry) < 40 or entry[0:16] == b"\x00" * 16:
            continue  # unused entry
        first_lba = struct.unpack("<Q", entry[32:40])[0]
        last_lba = struct.unpack("<Q", entry[40:48])[0]
        if last_lba < first_lba:
            continue
        partitions.append(
            PartitionInfo(
                offset=first_lba * 512,
                size=(last_lba - first_lba + 1) * 512,
                type_desc="GPT",
            )
        )
    return partitions


def find_partitions(fh) -> List[PartitionInfo]:
    parts = find_mbr_partitions(fh)
    if parts:
        return parts
    return find_gpt_partitions(fh)


def _windows_raw_disk_size(fh) -> Optional[int]:
    """Ask Windows for a raw device's exact byte length via
    IOCTL_DISK_GET_LENGTH_INFO, without touching the handle's read
    position at all.

    We used to get this by seeking to the end and back (like on
    Linux/macOS), but that turned out to actively break things on some
    USB storage controllers: seeking a whole-disk \\\\.\\PhysicalDriveN
    handle to SEEK_END and then back to 0 can leave the device in a state
    where the *next* large read is rejected with ERROR_ACCESS_DENIED --
    which looks exactly like a real permissions problem (and was being
    misreported as one) even though plain reads at the same offset/size
    work fine on a handle that was never seeked to the end. Querying the
    length via DeviceIoControl instead never moves the file pointer, so
    it can't trigger that.
    """
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        raw = fh._fh if isinstance(fh, AlignedFile) else fh
        handle = msvcrt.get_osfhandle(raw.fileno())

        class _GET_LENGTH_INFORMATION(ctypes.Structure):
            _fields_ = [("Length", ctypes.c_longlong)]

        IOCTL_DISK_GET_LENGTH_INFO = 0x0007405C
        info = _GET_LENGTH_INFORMATION()
        returned = wintypes.DWORD(0)
        ok = ctypes.windll.kernel32.DeviceIoControl(
            wintypes.HANDLE(handle),
            IOCTL_DISK_GET_LENGTH_INFO,
            None,
            0,
            ctypes.byref(info),
            ctypes.sizeof(info),
            ctypes.byref(returned),
            None,
        )
        if ok and info.Length > 0:
            return info.Length
    except Exception:
        pass
    return None


def get_source_size(path: str, fh: BinaryIO) -> int:
    """Try to determine the total size of the source in bytes. Falls back
    to seeking to the end for regular files/images; for raw block devices
    this usually works too on Linux/macOS. On Windows raw drives we
    deliberately avoid seeking to the end at all (see
    _windows_raw_disk_size's docstring) and use a dedicated ioctl instead;
    if that's unavailable we give up on a size rather than risk it, since
    every caller already treats 0/unknown gracefully.
    """
    if is_windows() and is_windows_device_path(path):
        size = _windows_raw_disk_size(fh)
        if size and isinstance(fh, AlignedFile):
            # Hand the exact size to the AlignedFile wrapper so later
            # reads refuse to cross the real end of the device. See
            # AlignedFile.set_known_size().
            fh.set_known_size(size)
        return size if size else 0
    try:
        size = os.path.getsize(path)
        if size > 0:
            return size
    except OSError:
        pass
    try:
        cur = fh.tell()
        fh.seek(0, io.SEEK_END)
        size = fh.tell()
        fh.seek(cur)
        return size
    except OSError:
        return 0


def iter_mounted_volumes() -> List[Tuple[str, str]]:
    """List currently mounted volumes/folders a user might point the tool
    at directly (e.g. a phone in file-transfer mode, or an already-mounted
    SD card) rather than a raw device path. Best-effort, informational.
    """
    results: List[Tuple[str, str]] = []
    if is_linux():
        for base in ("/media", "/run/media", "/mnt"):
            if os.path.isdir(base):
                for user in os.listdir(base):
                    p = os.path.join(base, user)
                    if os.path.isdir(p):
                        for name in os.listdir(p):
                            full = os.path.join(p, name)
                            if os.path.ismount(full) or os.path.isdir(full):
                                results.append((full, name))
    elif is_macos():
        base = "/Volumes"
        if os.path.isdir(base):
            for name in os.listdir(base):
                results.append((os.path.join(base, name), name))
    elif is_windows():
        import string

        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                results.append((drive, drive))
    return results
