"""File signature ("magic number") database used for carving.

Each entry describes how to recognize the start (and, when possible, the
end) of a file type inside a raw stream of bytes with no filesystem
metadata to rely on. Same technique as PhotoRec / Scalpel.

Fields:
    name        human readable name
    ext         extension to give recovered files
    headers     list of possible byte-string headers (magic numbers)
    footers     optional list of byte-string footers/end markers. If a
                footer is present, carving reads until the footer is
                found (bounded by max_size). If footer is None, carving
                relies purely on max_size (or a size field embedded in
                the header for some formats, handled specially).
    max_size    hard cap in bytes to avoid runaway files when no footer
                is found (protects against pathological data)
    footer_extra
                extra bytes to include after the footer match itself
                (e.g. PNG's IEND chunk CRC is 4 bytes after the marker)
"""

import struct
from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class Signature:
    name: str
    ext: str
    headers: List[bytes]
    footers: Optional[List[bytes]] = None
    max_size: int = 200 * 1024 * 1024  # 200MB default cap
    footer_extra: int = 0
    # Optional structural sanity check, run once per candidate right after
    # the header match on `validate_peek` bytes read from the match
    # offset. Returning False drops the candidate.
    #
    # Needed for signatures whose header is short enough to match by
    # coincidence inside unrelated binary data (BMP's bare "BM", PE's
    # "MZ"). Unchecked, one large binary file yields thousands of bogus
    # candidates, and each one also truncates the real file via
    # carve_candidates_fh's next-candidate upper bound.
    validate: Optional[Callable[[bytes], bool]] = None
    validate_peek: int = 0


def _validate_bmp(peek: bytes, max_size: int = 50 * 1024 * 1024) -> bool:
    """Check that a "BM" match is followed by a plausible
    BITMAPFILEHEADER + DIB header.

    Two bytes alone match about once every 65KB of random data, so
    require:
      - a declared file size at least as large as a minimal BMP and not
        far beyond our own cap
      - a pixel-data offset inside that file size
      - a DIB header size equal to one of the values real encoders emit
        (BITMAPCOREHEADER, BITMAPINFOHEADER, BITMAPV2/3/4/5HEADER)

    The DIB size check alone rejects almost all coincidental matches,
    being 10 accepted values out of 2^32.
    """
    if len(peek) < 18:
        return False
    file_size = struct.unpack("<I", peek[2:6])[0]
    data_offset = struct.unpack("<I", peek[10:14])[0]
    dib_header_size = struct.unpack("<I", peek[14:18])[0]
    if not (54 <= file_size <= max_size):
        return False
    if not (14 <= data_offset < file_size):
        return False
    if dib_header_size not in (12, 16, 20, 24, 40, 52, 56, 64, 108, 124):
        return False
    return True


def _validate_jpeg(peek: bytes) -> bool:
    """Check that the byte after "\\xFF\\xD8\\xFF" is a real marker type.

    The 3-byte header is only "SOI plus the start of the next marker", so
    peek[3] (peek starts at the matched header) must be an actual marker
    type: APPn, DQT, SOFn, COM and so on are all >= 0xC0. Both 0x00 and
    0xFF are invalid here, and a coincidental match usually lands on an
    arbitrary byte.
    """
    if len(peek) < 4:
        return False
    marker = peek[3]
    return 0xC0 <= marker <= 0xFE


def _validate_id3(peek: bytes) -> bool:
    """Check the version bytes of an ID3v2 tag header.

    Layout is "ID3" + major + minor + flags, so with peek starting at the
    matched "ID3" the version bytes are peek[3:5]. Only ID3v2.2/2.3/2.4
    exist in practice, and 0xFF is invalid by spec. Text data containing
    "ID3" is rarely followed by a plausible version byte ("ID30" gives
    0x30).
    """
    if len(peek) < 5:
        return False
    major, minor = peek[3], peek[4]
    return major in (2, 3, 4) and minor != 0xFF


_PE_KNOWN_MACHINES = {
    0x014C, 0x0200, 0x8664, 0x01C0, 0x01C4, 0xAA64, 0x0160, 0x0162,
    0x0166, 0x0168, 0x0169, 0x0184, 0x01A2, 0x01A3, 0x01A4, 0x01A6,
    0x01A8, 0x01C2, 0x01D3, 0x01F0, 0x01F1, 0x0266, 0x0366, 0x0466,
    0x0520, 0x0CEF, 0x0EBC, 0x9041, 0xC0EE,
}


def _validate_pe(peek: bytes) -> bool:
    """Check that an "MZ" match has a real PE header behind it.

    Two bytes match about once every 65KB of random data, so require the
    DOS header's e_lfanew to point at a "PE\\0\\0" signature with a known
    machine type and a plausible section count.
    """
    if len(peek) < 64:
        return False
    if peek[:2] != b"MZ":
        return False
    e_lfanew = struct.unpack("<I", peek[0x3C:0x40])[0]
    if not (64 <= e_lfanew <= len(peek) - 24):
        return False
    if peek[e_lfanew : e_lfanew + 4] != b"PE\x00\x00":
        return False
    machine, num_sections = struct.unpack("<HH", peek[e_lfanew + 4 : e_lfanew + 8])
    if machine not in _PE_KNOWN_MACHINES:
        return False
    if not (0 < num_sections <= 96):
        return False
    return True


SIGNATURES: List[Signature] = [
    Signature(
        "JPEG",
        "jpg",
        [b"\xFF\xD8\xFF"],
        [b"\xFF\xD9"],
        max_size=50 * 1024 * 1024,
        validate=_validate_jpeg,
        validate_peek=4,
    ),
    Signature(
        "PNG",
        "png",
        [b"\x89PNG\r\n\x1a\n"],
        [b"IEND"],
        max_size=100 * 1024 * 1024,
        footer_extra=4,  # trailing CRC32 after IEND
    ),
    Signature("GIF87a", "gif", [b"GIF87a"], [b"\x00\x3B"], max_size=50 * 1024 * 1024),
    Signature("GIF89a", "gif", [b"GIF89a"], [b"\x00\x3B"], max_size=50 * 1024 * 1024),
    Signature(
        "BMP",
        "bmp",
        [b"BM"],
        None,
        max_size=50 * 1024 * 1024,
        validate=_validate_bmp,
        validate_peek=18,
    ),
    Signature("TIFF-LE", "tiff", [b"II*\x00"], None, max_size=200 * 1024 * 1024),
    Signature("TIFF-BE", "tiff", [b"MM\x00*"], None, max_size=200 * 1024 * 1024),
    # Nearly every PDF writer puts a newline right after %%EOF.
    # footer_extra=1 keeps it, so the output matches the original
    # byte-for-byte instead of losing the last byte.
    Signature("PDF", "pdf", [b"%PDF-"], [b"%%EOF"], max_size=300 * 1024 * 1024, footer_extra=1),
    # ZIP-based containers (also covers docx/xlsx/pptx/apk/jar unless a more
    # specific match is layered on top later)
    Signature(
        "ZIP",
        "zip",
        [b"PK\x03\x04"],
        [b"PK\x05\x06"],
        max_size=1024 * 1024 * 1024,
        footer_extra=18,  # end-of-central-directory record tail
    ),
    Signature("RAR4", "rar", [b"Rar!\x1a\x07\x00"], None, max_size=1024 * 1024 * 1024),
    Signature("RAR5", "rar", [b"Rar!\x1a\x07\x01\x00"], None, max_size=1024 * 1024 * 1024),
    Signature("7ZIP", "7z", [b"7z\xBC\xAF\x27\x1C"], None, max_size=1024 * 1024 * 1024),
    # AVI and WAV are both RIFF containers sharing the same 4-byte "RIFF"
    # header. Listing them separately produced two candidates (and two
    # output files, one misnamed) at every match, so there is one entry
    # here and carve.py's _resolve_format_and_ext peeks the form type
    # after RIFF's declared size to name the output correctly.
    Signature("RIFF", "riff", [b"RIFF"], None, max_size=2 * 1024 * 1024 * 1024),
    Signature(
        "MP3-ID3",
        "mp3",
        [b"ID3"],
        None,
        max_size=200 * 1024 * 1024,
        validate=_validate_id3,
        validate_peek=5,
    ),
    Signature("MKV", "mkv", [b"\x1a\x45\xdf\xa3"], None, max_size=2 * 1024 * 1024 * 1024),
    Signature(
        "SQLite",
        "sqlite",
        [b"SQLite format 3\x00"],
        None,
        max_size=500 * 1024 * 1024,
    ),
    Signature("OLE-DOC", "doc", [b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"], None, max_size=100 * 1024 * 1024),
    Signature("HTML", "html", [b"<!DOCTYPE html", b"<html"], [b"</html>"], max_size=20 * 1024 * 1024),
    # MP4/MOV family: 'ftyp' box appears at offset 4, header handled specially in carve.py
    Signature("MP4", "mp4", [b"ftyp"], None, max_size=4 * 1024 * 1024 * 1024),
    # Windows PE executables/DLLs. True size comes from the section table
    # (plus the certificate directory when signed); see
    # carve.py's _pe_declared_size.
    Signature(
        "EXE",
        "exe",
        [b"MZ"],
        None,
        max_size=500 * 1024 * 1024,
        validate=_validate_pe,
        validate_peek=4096,
    ),
]

# Formats whose real header starts a few bytes before the matched marker
# (offset, in bytes, to step BACK from the match position to the true
# start of the file).
HEADER_BACK_OFFSET = {
    "MP4": 4,  # 4-byte size field precedes 'ftyp'
}

MAX_HEADER_LEN = max(len(h) for sig in SIGNATURES for h in sig.headers)
MAX_FOOTER_LEN = max((len(f) for sig in SIGNATURES if sig.footers for f in sig.footers), default=0)

# Extra names accepted by --formats that are not any Signature's own
# .name/.ext. At scan time these only need to select the right container
# signature: "avi"/"wav" the shared RIFF entry, and
# "docx"/"xlsx"/"pptx"/"heic"/"heif"/"mov" the ZIP or MP4 container they
# are built on. The actual format and extension are resolved per
# candidate in carve.py's _resolve_format_and_ext.
FORMAT_ALIASES = {
    "avi": "RIFF",
    "wav": "RIFF",
    "docx": "ZIP",
    "xlsx": "ZIP",
    "pptx": "ZIP",
    "heic": "MP4",
    "heif": "MP4",
    "avif": "MP4",
    "mov": "MP4",
}
