"""Finds a FAT or NTFS volume inside a source that might be a single
partition already (offset 0 == volume start) or a whole raw disk with a
partition table ahead of the volume (MBR or GPT).
"""

from typing import Optional, Tuple

from .filesystems import fat, ntfs
from .utils import OffsetView, find_partitions


def find_filesystem(fh) -> Tuple[object, Optional[str], object, Optional[int]]:
    """Returns (view, kind, boot, partition_offset).

    `view` is the file-like object to pass to the rest of the fat/ntfs
    functions (either `fh` itself, or an OffsetView windowed onto the
    partition that was found). `kind` is "ntfs", "fat", or None if
    nothing recognizable was found. `partition_offset` is None when the
    filesystem was found directly at the start of the source (the common
    case when `fh` is already a single partition/volume), otherwise the
    byte offset where the matching partition starts on the raw disk.
    """
    boot_ntfs = ntfs.parse_boot_sector(fh)
    if boot_ntfs:
        return fh, "ntfs", boot_ntfs, None

    boot_fat = fat.parse_boot_sector(fh)
    if boot_fat:
        return fh, "fat", boot_fat, None

    for part in find_partitions(fh):
        view = OffsetView(fh, part.offset, part.size)

        boot_ntfs = ntfs.parse_boot_sector(view)
        if boot_ntfs:
            return view, "ntfs", boot_ntfs, part.offset

        boot_fat = fat.parse_boot_sector(view)
        if boot_fat:
            return view, "fat", boot_fat, part.offset

    return None, None, None, None
