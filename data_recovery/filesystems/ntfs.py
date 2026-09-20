"""NTFS deleted-file recovery via direct MFT (Master File Table) parsing.

When a file is deleted on NTFS, its MFT record is flagged "not in use".
The record itself, holding the filename, the size and the data-run map
pointing at the file's clusters, usually survives until that MFT slot is
reused. Unlike FAT, this means fragmented files are often recoverable,
because the real cluster map is still in the MFT record.

This is a best-effort, from-scratch implementation of the pieces needed
for recovery (not a full NTFS driver): boot sector, MFT record fixups,
attribute parsing for $FILE_NAME and $DATA, and data-run decoding.
"""

import os
import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

ATTR_STANDARD_INFORMATION = 0x10
ATTR_FILE_NAME = 0x30
ATTR_DATA = 0x80
ATTR_END = 0xFFFFFFFF

FLAG_IN_USE = 0x0001
FLAG_DIRECTORY = 0x0002


@dataclass
class NtfsBoot:
    bytes_per_sector: int
    sectors_per_cluster: int
    mft_lcn: int
    mft_record_size: int
    total_sectors: int

    @property
    def cluster_size(self) -> int:
        return self.bytes_per_sector * self.sectors_per_cluster

    def cluster_offset(self, lcn: int) -> int:
        return lcn * self.cluster_size


@dataclass
class NtfsDeletedEntry:
    record_num: int
    name: str
    size: int
    data_runs: List[Tuple[Optional[int], int]]  # (lcn or None if sparse, run_length_in_clusters)


def parse_boot_sector(fh) -> Optional[NtfsBoot]:
    fh.seek(0)
    boot = fh.read(512)
    if len(boot) < 512:
        return None
    if boot[3:11] != b"NTFS    ":
        return None

    bytes_per_sector = struct.unpack("<H", boot[11:13])[0]
    sectors_per_cluster = boot[13]
    total_sectors = struct.unpack("<Q", boot[40:48])[0]
    mft_lcn = struct.unpack("<Q", boot[48:56])[0]
    clusters_per_mft_record = struct.unpack("<b", boot[64:65])[0]

    if bytes_per_sector == 0 or sectors_per_cluster == 0:
        return None

    cluster_size = bytes_per_sector * sectors_per_cluster
    if clusters_per_mft_record < 0:
        mft_record_size = 1 << (-clusters_per_mft_record)
    else:
        mft_record_size = clusters_per_mft_record * cluster_size

    if mft_record_size <= 0 or mft_record_size > 65536:
        return None

    return NtfsBoot(
        bytes_per_sector=bytes_per_sector,
        sectors_per_cluster=sectors_per_cluster,
        mft_lcn=mft_lcn,
        mft_record_size=mft_record_size,
        total_sectors=total_sectors,
    )


def _apply_fixup(record: bytes, sector_size: int) -> Optional[bytes]:
    if len(record) < 8 or record[0:4] != b"FILE":
        return None
    record = bytearray(record)
    usa_offset = struct.unpack("<H", record[4:6])[0]
    usa_count = struct.unpack("<H", record[6:8])[0]
    if usa_count == 0:
        return bytes(record)

    usa = record[usa_offset : usa_offset + usa_count * 2]
    if len(usa) < usa_count * 2:
        return bytes(record)

    for i in range(1, usa_count):
        sector_end = i * sector_size
        if sector_end + 2 > len(record):
            break
        original = usa[i * 2 : i * 2 + 2]
        record[sector_end - 2 : sector_end] = original

    return bytes(record)


def parse_data_runs(run_bytes: bytes) -> List[Tuple[Optional[int], int]]:
    runs: List[Tuple[Optional[int], int]] = []
    pos = 0
    current_lcn = 0
    while pos < len(run_bytes):
        header = run_bytes[pos]
        if header == 0:
            break
        length_size = header & 0x0F
        offset_size = (header >> 4) & 0x0F
        pos += 1
        if pos + length_size > len(run_bytes):
            break
        length_bytes = run_bytes[pos : pos + length_size]
        run_length = int.from_bytes(length_bytes, "little", signed=False)
        pos += length_size

        if offset_size == 0:
            # sparse run: no LCN change, no physical clusters
            runs.append((None, run_length))
            continue

        if pos + offset_size > len(run_bytes):
            break
        offset_bytes = run_bytes[pos : pos + offset_size]
        lcn_delta = int.from_bytes(offset_bytes, "little", signed=True)
        pos += offset_size
        current_lcn += lcn_delta
        runs.append((current_lcn, run_length))

    return runs


def _parse_attributes(record: bytes):
    attr_offset = struct.unpack("<H", record[20:22])[0]
    flags = struct.unpack("<H", record[22:24])[0]
    attrs = []
    pos = attr_offset
    while pos + 8 <= len(record):
        attr_type = struct.unpack("<I", record[pos : pos + 4])[0]
        if attr_type == ATTR_END or attr_type == 0:
            break
        attr_len = struct.unpack("<I", record[pos + 4 : pos + 8])[0]
        if attr_len <= 0 or pos + attr_len > len(record) + 8:
            break
        non_resident = record[pos + 8]
        attrs.append({"type": attr_type, "non_resident": non_resident, "offset": pos, "len": attr_len})
        pos += attr_len
    return flags, attrs


def _read_filename(record: bytes, attr: dict) -> Optional[str]:
    base = attr["offset"]
    if attr["non_resident"]:
        return None
    content_len = struct.unpack("<I", record[base + 16 : base + 20])[0]
    content_off = struct.unpack("<H", record[base + 20 : base + 22])[0]
    content = record[base + content_off : base + content_off + content_len]
    if len(content) < 0x42:
        return None
    name_len_chars = content[0x40]
    namespace = content[0x41]
    name_bytes = content[0x42 : 0x42 + name_len_chars * 2]
    try:
        name = name_bytes.decode("utf-16-le", errors="replace")
    except Exception:
        return None
    return name, namespace


def _read_data_runs(record: bytes, attr: dict) -> Tuple[List[Tuple[Optional[int], int]], int]:
    base = attr["offset"]
    if not attr["non_resident"]:
        content_len = struct.unpack("<I", record[base + 16 : base + 20])[0]
        return [], content_len  # resident data (tiny file), handled by caller separately
    real_size = struct.unpack("<Q", record[base + 48 : base + 56])[0]
    run_offset = struct.unpack("<H", record[base + 32 : base + 34])[0]
    run_bytes = record[base + run_offset : base + attr["len"]]
    runs = parse_data_runs(run_bytes)
    return runs, real_size


def _resident_data(record: bytes, attr: dict) -> bytes:
    base = attr["offset"]
    content_len = struct.unpack("<I", record[base + 16 : base + 20])[0]
    content_off = struct.unpack("<H", record[base + 20 : base + 22])[0]
    return record[base + content_off : base + content_off + content_len]


def _get_mft_data_runs(fh, ntfs: NtfsBoot) -> List[Tuple[Optional[int], int]]:
    fh.seek(ntfs.cluster_offset(ntfs.mft_lcn))
    raw = fh.read(ntfs.mft_record_size)
    fixed = _apply_fixup(raw, ntfs.bytes_per_sector)
    if not fixed:
        return [(ntfs.mft_lcn, 1)]  # fallback: treat as unreadable, caller will bound-check

    _, attrs = _parse_attributes(fixed)
    for attr in attrs:
        if attr["type"] == ATTR_DATA and attr["non_resident"]:
            runs, _ = _read_data_runs(fixed, attr)
            if runs:
                return runs
    return [(ntfs.mft_lcn, 1)]


def _iter_mft_record_offsets(ntfs: NtfsBoot, mft_runs: List[Tuple[Optional[int], int]]):
    records_per_cluster = max(1, ntfs.cluster_size // ntfs.mft_record_size)
    record_num = 0
    for lcn, run_len in mft_runs:
        if lcn is None:
            record_num += run_len * records_per_cluster
            continue
        total_records_in_run = run_len * records_per_cluster
        for i in range(total_records_in_run):
            byte_offset = ntfs.cluster_offset(lcn) + i * ntfs.mft_record_size
            yield record_num, byte_offset
            record_num += 1


def find_deleted_entries(fh, ntfs: NtfsBoot, max_records: int = 2_000_000) -> List[NtfsDeletedEntry]:
    mft_runs = _get_mft_data_runs(fh, ntfs)
    results: List[NtfsDeletedEntry] = []

    count = 0
    for record_num, byte_offset in _iter_mft_record_offsets(ntfs, mft_runs):
        count += 1
        if count > max_records:
            break
        fh.seek(byte_offset)
        raw = fh.read(ntfs.mft_record_size)
        if len(raw) < ntfs.mft_record_size or raw[0:4] != b"FILE":
            continue
        fixed = _apply_fixup(raw, ntfs.bytes_per_sector)
        if not fixed:
            continue

        flags, attrs = _parse_attributes(fixed)
        if flags & FLAG_IN_USE:
            continue  # still in use, not deleted
        if flags & FLAG_DIRECTORY:
            continue  # skip directories, we only recover file content

        name = None
        best_namespace = -1
        data_runs: List[Tuple[Optional[int], int]] = []
        resident_bytes = None
        size = 0

        for attr in attrs:
            if attr["type"] == ATTR_FILE_NAME:
                parsed = _read_filename(fixed, attr)
                if parsed:
                    cand_name, namespace = parsed
                    if namespace != 2 and namespace >= best_namespace:  # prefer non-DOS-only names
                        name = cand_name
                        best_namespace = namespace
                    elif name is None:
                        name = cand_name
            elif attr["type"] == ATTR_DATA:
                if attr["non_resident"]:
                    runs, real_size = _read_data_runs(fixed, attr)
                    if runs:
                        data_runs = runs
                        size = real_size
                else:
                    resident_bytes = _resident_data(fixed, attr)
                    size = len(resident_bytes)

        if not name:
            continue
        if not data_runs and resident_bytes is None:
            continue

        entry = NtfsDeletedEntry(record_num=record_num, name=name, size=size, data_runs=data_runs)
        entry._resident_bytes = resident_bytes  # type: ignore[attr-defined]
        results.append(entry)

    return results


def recover_entry(fh, ntfs: NtfsBoot, entry: NtfsDeletedEntry, out_dir: str) -> Optional[str]:
    os.makedirs(out_dir, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in entry.name) or f"file_{entry.record_num}"
    out_path = os.path.join(out_dir, f"{entry.record_num:010d}_{safe_name}")

    resident_bytes = getattr(entry, "_resident_bytes", None)
    if resident_bytes is not None:
        if not resident_bytes:
            return None
        with open(out_path, "wb") as out_fh:
            out_fh.write(resident_bytes)
        return out_path

    if not entry.data_runs or entry.size == 0:
        return None

    remaining = entry.size
    with open(out_path, "wb") as out_fh:
        for lcn, run_len in entry.data_runs:
            run_bytes = run_len * ntfs.cluster_size
            to_write = min(run_bytes, remaining)
            if to_write <= 0:
                break
            if lcn is None:
                out_fh.write(b"\x00" * to_write)
            else:
                fh.seek(ntfs.cluster_offset(lcn))
                chunk = fh.read(to_write)
                out_fh.write(chunk)
                if len(chunk) < to_write:
                    break
            remaining -= to_write

    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        if os.path.exists(out_path):
            os.remove(out_path)
        return None
    return out_path
