"""FAT12/16/32 deleted-file recovery.

When a file is deleted on a FAT filesystem, the directory entry is only
marked deleted (first byte of the filename set to 0xE5) and the cluster
chain in the FAT table is freed. The directory entry itself, and usually
the file's data clusters, are left untouched until something writes over
them, so for a recently deleted file with no writes since it is normally
possible to recover:
  - the short (8.3) filename
  - the file size
  - the starting cluster

Because the FAT chain is gone, we can't know for certain which clusters
belonged to a fragmented file, so this module uses the same heuristic as
most consumer recovery tools: assume the file's data lives in one
contiguous run of clusters starting at the recorded start cluster. This
works well for files that weren't fragmented (the common case for photos/
videos written once by a camera or phone) and can fail for files that
were fragmented on write.

Long filenames (VFAT LFN entries) are not reconstructed in this version;
recovered names are the short 8.3 name.
"""

import os
import struct
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class DeletedEntry:
    name: str
    size: int
    start_cluster: int
    dir_offset: int


@dataclass
class BootSector:
    bytes_per_sector: int
    sectors_per_cluster: int
    reserved_sectors: int
    num_fats: int
    root_entries: int  # FAT12/16 only
    total_sectors: int
    fat_size: int  # sectors per FAT
    fat_type: str  # "FAT12" | "FAT16" | "FAT32"
    root_cluster: int  # FAT32 only
    fat_start: int
    cluster_heap_start: int  # byte offset of cluster #2

    def cluster_to_offset(self, cluster: int) -> int:
        cluster_size = self.bytes_per_sector * self.sectors_per_cluster
        return self.cluster_heap_start + (cluster - 2) * cluster_size

    @property
    def cluster_size(self) -> int:
        return self.bytes_per_sector * self.sectors_per_cluster


_VALID_BYTES_PER_SECTOR = {512, 1024, 2048, 4096}
_VALID_SECTORS_PER_CLUSTER = {1, 2, 4, 8, 16, 32, 64, 128}


def parse_boot_sector(fh) -> Optional[BootSector]:
    """Parse a FAT boot sector at the START of `fh`.

    `fh` must already be positioned at the volume, not at the start of a
    raw disk with a partition table ahead of it. See
    find_fat_or_ntfs_offset() in cli.py for locating that offset.
    """
    fh.seek(0)
    boot = fh.read(512)
    if len(boot) < 512:
        return None
    if boot[510:512] != b"\x55\xAA":
        return None
    # A real x86 boot sector starts with a short jump instruction
    # (0xEB xx 0x90, or 0xE9 xx xx). Without this check, other 512-byte
    # sectors that happen to end in 0x55AA (an MBR partition table, for
    # instance) can be misread as a FAT boot sector and produce garbage.
    if boot[0] not in (0xEB, 0xE9):
        return None

    bytes_per_sector = struct.unpack("<H", boot[11:13])[0]
    sectors_per_cluster = boot[13]
    reserved_sectors = struct.unpack("<H", boot[14:16])[0]
    num_fats = boot[16]
    root_entries = struct.unpack("<H", boot[17:19])[0]
    total_sectors_16 = struct.unpack("<H", boot[19:21])[0]
    fat_size_16 = struct.unpack("<H", boot[22:24])[0]
    total_sectors_32 = struct.unpack("<I", boot[32:36])[0]
    fat_size_32 = struct.unpack("<I", boot[36:40])[0]
    root_cluster = struct.unpack("<I", boot[44:48])[0] if fat_size_16 == 0 else 0

    if bytes_per_sector not in _VALID_BYTES_PER_SECTOR:
        return None
    if sectors_per_cluster not in _VALID_SECTORS_PER_CLUSTER:
        return None
    if reserved_sectors == 0 or num_fats not in (1, 2):
        return None

    total_sectors = total_sectors_16 or total_sectors_32
    fat_size = fat_size_16 or fat_size_32

    root_dir_sectors = ((root_entries * 32) + (bytes_per_sector - 1)) // bytes_per_sector
    data_start_sector = reserved_sectors + (num_fats * fat_size) + root_dir_sectors
    total_clusters = (total_sectors - data_start_sector) // sectors_per_cluster if sectors_per_cluster else 0

    if fat_size_16 == 0:
        # Only FAT32 stores the FAT size in the 32-bit field; this is a
        # more reliable signal than the cluster-count heuristic, which
        # misclassifies very small (below-spec-minimum) FAT32 volumes
        # sometimes produced by formatting tools for tiny test/USB media.
        fat_type = "FAT32"
    elif total_clusters < 4085:
        fat_type = "FAT12"
    else:
        fat_type = "FAT16"

    fat_start = reserved_sectors * bytes_per_sector
    cluster_heap_start = data_start_sector * bytes_per_sector

    return BootSector(
        bytes_per_sector=bytes_per_sector,
        sectors_per_cluster=sectors_per_cluster,
        reserved_sectors=reserved_sectors,
        num_fats=num_fats,
        root_entries=root_entries,
        total_sectors=total_sectors,
        fat_size=fat_size,
        fat_type=fat_type,
        root_cluster=root_cluster,
        fat_start=fat_start,
        cluster_heap_start=cluster_heap_start,
    )


def _parse_dir_entries(raw: bytes, base_offset: int) -> List[DeletedEntry]:
    entries = []
    for i in range(0, len(raw) - 31, 32):
        rec = raw[i : i + 32]
        first = rec[0]
        attr = rec[11]
        if attr == 0x0F:
            continue  # LFN entry, skip (not reconstructing long names)
        if first != 0xE5:
            continue
        if attr & 0x08:
            continue  # volume label
        raw_name = rec[1:8]
        ext = rec[8:11]
        try:
            name_part = raw_name.decode("ascii", errors="replace").rstrip()
            ext_part = ext.decode("ascii", errors="replace").rstrip()
        except Exception:
            continue
        display_name = "_" + name_part
        if ext_part:
            display_name += "." + ext_part
        start_hi = struct.unpack("<H", rec[20:22])[0]
        start_lo = struct.unpack("<H", rec[26:28])[0]
        start_cluster = (start_hi << 16) | start_lo
        size = struct.unpack("<I", rec[28:32])[0]
        if size == 0 and start_cluster == 0:
            continue
        entries.append(
            DeletedEntry(
                name=display_name,
                size=size,
                start_cluster=start_cluster,
                dir_offset=base_offset + i,
            )
        )
    return entries


_VALID_NTRES = {0x00, 0x08, 0x10, 0x18}
_VALID_NAME_SPECIALS = {
    0x21, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29,
    0x2D, 0x40, 0x5E, 0x5F, 0x60, 0x7B, 0x7D, 0x7E,
}


def _valid_short_name_bytes(name_bytes: bytes) -> bool:
    for c in name_bytes:
        if c == 0x20 or (0x30 <= c <= 0x39) or (0x41 <= c <= 0x5A):
            continue
        if c in _VALID_NAME_SPECIALS or c >= 0x80:
            continue
        return False
    return True


def _valid_fat_date(date: int) -> bool:
    if date == 0:
        return True
    month = (date >> 5) & 0x0F
    day = date & 0x1F
    return 1 <= month <= 12 and 1 <= day <= 31


def _looks_like_orphan_entry(rec: bytes) -> bool:
    """Broader structural check than _parse_dir_entries's: this also
    accepts entries that are NOT individually marked deleted (first byte
    != 0xE5). That matters because the interesting case for orphan
    scanning is a whole directory cluster that a quick format made
    unreachable from the now-empty live root, even though none of its own
    entries were ever marked deleted. The filenames inside are intact,
    just no longer linked from anywhere walkable.

    A directory-entry-shaped 32-byte record has several independent
    fields that must all line up (name charset, reserved attribute bits,
    a small set of legal NTRes values, three separately plausible FAT
    dates). Matching all of them by coincidence in unrelated binary data
    is very unlikely, the same reasoning as the BMP and PE validators.
    """
    first = rec[0]
    if first == 0x00:
        return False
    attr = rec[11]
    if attr == 0x0F:
        return False  # LFN entry, not reconstructed in this version
    if attr & 0xC0:
        return False  # reserved bits must be zero
    if attr & 0x08:
        return False  # volume label
    name_bytes = rec[1:11] if first == 0xE5 else rec[0:11]
    if not _valid_short_name_bytes(name_bytes):
        return False
    if rec[12] not in _VALID_NTRES:
        return False
    if rec[13] > 199:
        return False
    crt_date, access_date = struct.unpack("<HH", rec[16:20])
    wrt_date = struct.unpack("<H", rec[24:26])[0]
    if not (_valid_fat_date(crt_date) and _valid_fat_date(access_date) and _valid_fat_date(wrt_date)):
        return False
    return True


def scan_orphan_entries_in_chunk(
    chunk: bytes,
    chunk_base_offset: int,
    min_offset: int,
    boot: BootSector,
    total_size: int,
) -> List[DeletedEntry]:
    """Look for FAT directory-entry-shaped 32-byte records anywhere in
    `chunk`, independent of the live directory tree.

    Intended to run inside carve's existing single sequential pass over
    the disk (see the boot_sector and orphan_sink parameters of
    carve.scan_headers_fh), not as a second full read.

    This recovers names that undelete's directory walk cannot. A quick
    format usually rewrites only the boot sector, the FAT tables and the
    root directory's first cluster, so an old subdirectory's own cluster,
    elsewhere in the data region with its entries intact, survives but is
    no longer reachable by walking the new empty root. The broader check
    also picks up ordinary 0xE5-prefixed deleted entries, as
    find_deleted_entries does.

    Directory entries are always 32-byte aligned relative to a sector
    boundary (every FAT sector size is a multiple of 32), so scanning
    every 32-byte offset relative to the start of the *disk* is safe
    regardless of where this chunk happens to fall, without needing to
    know cluster boundaries up front.
    """
    found: List[DeletedEntry] = []
    rem = chunk_base_offset % 32
    start_i = (32 - rem) % 32
    for i in range(start_i, len(chunk) - 31, 32):
        abs_offset = chunk_base_offset + i
        if abs_offset < min_offset:
            continue
        rec = chunk[i : i + 32]
        if not _looks_like_orphan_entry(rec):
            continue
        first = rec[0]
        raw_name = rec[1:8] if first == 0xE5 else rec[0:8]
        ext = rec[8:11]
        try:
            name_part = raw_name.decode("ascii").rstrip()
            ext_part = ext.decode("ascii").rstrip()
        except UnicodeDecodeError:
            continue
        if not name_part:
            continue
        display_name = ("_" if first == 0xE5 else "") + name_part
        if ext_part:
            display_name += "." + ext_part
        start_hi, _wrt, _wd, start_lo = struct.unpack("<HHHH", rec[20:28])
        start_cluster = (start_hi << 16) | start_lo
        size = struct.unpack("<I", rec[28:32])[0]
        if start_cluster < 2 or size == 0 or size > total_size:
            continue
        try:
            data_offset = boot.cluster_to_offset(start_cluster)
        except Exception:
            continue
        if not (0 <= data_offset < total_size):
            continue
        found.append(
            DeletedEntry(
                name=display_name,
                size=size,
                start_cluster=start_cluster,
                dir_offset=abs_offset,
            )
        )
    return found


def find_deleted_entries(fh, boot: BootSector) -> List[DeletedEntry]:
    """Scans the root directory (and, for FAT32, walks subdirectories) for
    deleted entries. FAT12/16 root directory is a fixed area; FAT32 root
    is just cluster chain starting at root_cluster like any directory.
    """
    entries: List[DeletedEntry] = []

    if boot.fat_type == "FAT32":
        visited = set()
        _walk_fat32_dir(fh, boot, boot.root_cluster, entries, visited)
    else:
        root_dir_offset = boot.fat_start + boot.num_fats * boot.fat_size * boot.bytes_per_sector
        root_dir_size = boot.root_entries * 32
        fh.seek(root_dir_offset)
        raw = fh.read(root_dir_size)
        entries.extend(_parse_dir_entries(raw, root_dir_offset))

    return entries


def _read_fat32_entry(fh, boot: BootSector, cluster: int) -> int:
    fat_offset = boot.fat_start + cluster * 4
    fh.seek(fat_offset)
    raw = fh.read(4)
    if len(raw) < 4:
        return 0x0FFFFFFF
    return struct.unpack("<I", raw)[0] & 0x0FFFFFFF


def _walk_fat32_dir(fh, boot: BootSector, cluster: int, entries: List[DeletedEntry], visited: set, depth: int = 0):
    if depth > 12 or cluster in visited or cluster < 2:
        return
    visited.add(cluster)

    chain = [cluster]
    cur = cluster
    for _ in range(4096):  # sane upper bound on directory size
        nxt = _read_fat32_entry(fh, boot, cur)
        if nxt >= 0x0FFFFFF8 or nxt == 0:
            break
        chain.append(nxt)
        cur = nxt

    subdirs = []
    for c in chain:
        offset = boot.cluster_to_offset(c)
        fh.seek(offset)
        raw = fh.read(boot.cluster_size)
        found = _parse_dir_entries(raw, offset)
        entries.extend(found)

        # also look for live (non-deleted) subdirectories to recurse into,
        # so we can find deleted files inside folders too
        for i in range(0, len(raw) - 31, 32):
            rec = raw[i : i + 32]
            first = rec[0]
            attr = rec[11]
            if first in (0x00, 0xE5) or attr == 0x0F:
                continue
            if attr & 0x10:  # directory
                name = rec[0:8].decode("ascii", errors="replace").rstrip()
                if name in (".", ".."):
                    continue
                start_hi = struct.unpack("<H", rec[20:22])[0]
                start_lo = struct.unpack("<H", rec[26:28])[0]
                sub_cluster = (start_hi << 16) | start_lo
                if sub_cluster >= 2:
                    subdirs.append(sub_cluster)

    for sc in subdirs:
        _walk_fat32_dir(fh, boot, sc, entries, visited, depth + 1)


def recover_entry(fh, boot: BootSector, entry: DeletedEntry, out_dir: str) -> Optional[str]:
    """Reads clusters starting at entry.start_cluster, contiguously, for
    entry.size bytes (heuristic: assumes no fragmentation) and writes the
    result to out_dir.
    """
    if entry.start_cluster < 2 or entry.size == 0:
        return None

    os.makedirs(out_dir, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in entry.name)
    out_path = os.path.join(out_dir, f"{entry.dir_offset:012x}_{safe_name}")

    offset = boot.cluster_to_offset(entry.start_cluster)
    fh.seek(offset)
    remaining = entry.size
    with open(out_path, "wb") as out_fh:
        while remaining > 0:
            chunk = fh.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            out_fh.write(chunk)
            remaining -= len(chunk)

    if os.path.getsize(out_path) == 0:
        os.remove(out_path)
        return None
    return out_path
