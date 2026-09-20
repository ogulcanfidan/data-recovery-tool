"""Signature-based carving engine.

Works even when the filesystem is gone (quick-formatted drive, corrupted
partition table) because it uses no filesystem metadata at all: it scans
raw bytes for known magic numbers and extracts what sits between a
recognized start and a recognized end, or up to a size cap when the
format has no end marker.

Two passes, favouring simplicity over raw speed:
  1. scan_headers(), one sequential pass, collects every candidate
     header offset in the source.
  2. carve_candidates() seeks back to each candidate and reads forward
     until a footer, a size cap, or the next candidate's start, writing
     the bytes to a file.
"""

import os
import struct
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from .filesystems import fat as _fat
from .signatures import (
    FORMAT_ALIASES,
    HEADER_BACK_OFFSET,
    MAX_FOOTER_LEN,
    MAX_HEADER_LEN,
    SIGNATURES,
    Signature,
)
from .utils import get_source_size, open_source

BLOCK_SIZE = 8 * 1024 * 1024  # 8MB read chunks for the header scan pass
CARVE_CHUNK = 1 * 1024 * 1024  # 1MB read chunks while extracting a file
EOCD_MARKER = b"PK\x05\x06"  # ZIP end-of-central-directory record

# Formats that state their own length in their own data: BMP's header
# size field, MP4's box chain, PE's section table, RIFF's chunk size,
# SQLite's page_size * page_count, 7z's next-header pointer. These must
# not fall back to the "stop where the next candidate starts" bound in
# carve_candidates_fh. `list-formats` also reports them differently, so
# both callers read this one definition.
SELF_DESCRIBING_FORMATS = frozenset({"BMP", "MP4", "EXE", "RIFF", "SQLite", "7ZIP"})
# First read size when looking for a ZIP's end-of-central-directory
# record; doubles up to CARVE_CHUNK. See _find_zip_eocd.
EOCD_FIRST_CHUNK = 64 * 1024

ProgressCB = Optional[Callable[[int, int], None]]


@dataclass
class Candidate:
    offset: int
    signature: Signature


@dataclass
class RecoveredFile:
    path: str
    offset: int
    size: int
    format: str
    truncated: bool  # True if we hit a cap rather than a real footer/EOF


def _signatures_for(formats: Optional[List[str]]) -> List[Signature]:
    if not formats:
        return SIGNATURES
    wanted = {f.lower() for f in formats}
    # "avi"/"wav" map to the shared RIFF signature, "docx"/"xlsx"/"pptx"
    # to ZIP, "heic"/"heif"/"mov" to MP4. See FORMAT_ALIASES.
    wanted_canonical = {FORMAT_ALIASES[f] for f in wanted if f in FORMAT_ALIASES}
    return [
        s
        for s in SIGNATURES
        if s.name.lower() in wanted or s.ext.lower() in wanted or s.name in wanted_canonical
    ]


def scan_headers_fh(
    fh,
    total_size: int,
    formats: Optional[List[str]] = None,
    block_size: int = BLOCK_SIZE,
    progress_cb: ProgressCB = None,
    boot_sector=None,
    orphan_sink: Optional[list] = None,
) -> List[Candidate]:
    """One sequential pass over an open source, collecting every known
    file-signature header. Returns candidates sorted by offset.

    Takes an open handle rather than opening one itself so the scan and
    extract passes can share it: opening a raw device handle is not free,
    and on Windows closing one and immediately reopening it can fail.

    `boot_sector` and `orphan_sink` are optional and only useful
    together. Given a parsed filesystems.fat.BootSector (with offsets
    made absolute to this `fh` when the filesystem sits inside a
    partition) and a list to append to, this pass also collects FAT
    directory-entry-shaped records found anywhere on disk rather than
    only those reachable by walking the live directory tree. That
    recovers original filenames from a subdirectory a quick format made
    unreachable, without a second full-disk read. See
    filesystems.fat.scan_orphan_entries_in_chunk.
    """
    sigs = _signatures_for(formats)
    overlap = MAX_HEADER_LEN - 1 if MAX_HEADER_LEN > 1 else 0
    # Directory entries are 32 bytes, so a record straddling a block
    # boundary needs 31 bytes of look-back to still be seen whole. Same
    # idea as the signature overlap above.
    orphan_overlap = 31 if (boot_sector is not None and orphan_sink is not None) else 0
    overlap = max(overlap, orphan_overlap)

    candidates: List[Candidate] = []
    pos = 0
    while True:
        read_start = max(0, pos - overlap)
        fh.seek(read_start)
        chunk = fh.read(block_size + overlap)
        if not chunk:
            break

        for sig in sigs:
            for header in sig.headers:
                search_from = 0
                while True:
                    idx = chunk.find(header, search_from)
                    if idx == -1:
                        break
                    abs_offset = read_start + idx
                    search_from = idx + 1
                    # Already considered on the previous iteration.
                    if abs_offset < pos:
                        continue
                    real_offset = abs_offset - HEADER_BACK_OFFSET.get(sig.name, 0)
                    if real_offset < 0:
                        continue
                    candidates.append(Candidate(real_offset, sig))

        if boot_sector is not None and orphan_sink is not None:
            orphan_sink.extend(
                _fat.scan_orphan_entries_in_chunk(chunk, read_start, pos, boot_sector, total_size)
            )

        advanced = len(chunk) - overlap if len(chunk) > overlap else len(chunk)
        if advanced <= 0:
            break
        pos += advanced
        if progress_cb and total_size:
            progress_cb(min(pos, total_size), total_size)
        if len(chunk) < block_size + overlap:
            break  # reached EOF

    candidates = _apply_validators(fh, candidates)
    candidates.sort(key=lambda c: c.offset)
    candidates = _dedupe_overlapping_same_signature(candidates)
    candidates = _dedupe_nested_zip_candidates(fh, candidates)
    return candidates


def _dedupe_overlapping_same_signature(candidates: List[Candidate]) -> List[Candidate]:
    """Collapse candidates of one signature that are really one match.

    When a signature lists several header patterns and one occurs a few
    bytes into a match of another, the same file yields two candidates a
    few bytes apart: HTML's "<!DOCTYPE html" is followed by its own
    "<html". Two distinct files of one type never start within
    header-length distance on real media, so a same-signature candidate
    starting before the previous one's header has finished is a repeat,
    not a second file.

    `candidates` must already be sorted by offset.
    """
    kept: List[Candidate] = []
    last_end_by_sig: dict = {}
    for c in candidates:
        prev_end = last_end_by_sig.get(c.signature.name)
        if prev_end is not None and c.offset < prev_end:
            continue
        kept.append(c)
        # Allow a few bytes past the header itself: "<!DOCTYPE html" is
        # followed by a closing ">" before "<html" begins, so the header
        # length alone is not quite enough margin.
        last_end_by_sig[c.signature.name] = c.offset + max(len(h) for h in c.signature.headers) + 8
    return kept


def _dedupe_nested_zip_candidates(fh, candidates: List[Candidate]) -> List[Candidate]:
    """Keep only the outermost archive of each ZIP-family candidate.

    A .docx/.xlsx/.pptx, or any multi-entry ZIP, stores one
    "PK\\x03\\x04" local-file header per contained file: one for
    "[Content_Types].xml", one for "word/document.xml", one per image.
    Each of those also matches ZIP's own header, so one Office document
    produces a dozen or more nested candidates, each a truncated tail
    slice of the same archive sharing its single end-of-central-directory
    footer.

    Walks the ZIP candidates in offset order and, for each one kept,
    finds its own footer to learn its span, then drops every other ZIP
    candidate inside that span.
    """
    zip_sig = next((s for s in SIGNATURES if s.name == "ZIP"), None)
    if zip_sig is None or not any(c.signature.name == "ZIP" for c in candidates):
        return candidates

    kept: List[Candidate] = []
    skip_until = -1
    # Bound the footer search: a multi-gigabyte zip with a missing or
    # corrupted EOCD would otherwise mean reading all of it to find
    # nothing.
    search_cap = min(zip_sig.max_size, 64 * 1024 * 1024)
    for c in candidates:
        if c.signature.name != "ZIP":
            kept.append(c)
            continue
        if c.offset < skip_until:
            continue
        kept.append(c)
        end = _find_zip_eocd(fh, c.offset, search_cap)
        if end is not None:
            skip_until = end + zip_sig.footer_extra
    return kept


def _find_zip_eocd(fh, start: int, search_cap: int) -> Optional[int]:
    """Absolute offset just past the first end-of-central-directory
    record at or after `start`, or None if none appears within
    `search_cap` bytes.

    Reads forward in growing chunks and stops at the first hit rather
    than pulling `search_cap` bytes at once. Almost every archive on real
    media is a document well under a megabyte whose EOCD sits a few
    hundred bytes in, so a blind 64MB read per candidate cost orders of
    magnitude more I/O than needed: a card holding a few hundred Office
    documents turned one scan pass into tens of gigabytes of reads, slow
    enough on USB or SD media to look like a hang.

    EOCD_MARKER is 4 bytes, so consecutive chunks are joined by a 3-byte
    carry to catch a record straddling a chunk boundary, the same
    look-back the header scan uses for its overlap.
    """
    carry = b""
    searched = 0
    want = EOCD_FIRST_CHUNK
    fh.seek(start)
    while searched < search_cap:
        chunk = fh.read(min(want, search_cap - searched))
        if not chunk:
            return None
        haystack = carry + chunk
        base = start + searched - len(carry)  # absolute offset of haystack[0]
        idx = haystack.find(EOCD_MARKER)
        if idx != -1:
            return base + idx + len(EOCD_MARKER)
        searched += len(chunk)
        carry = haystack[-(len(EOCD_MARKER) - 1):]
        # Grow the read size. The first chunk settles almost every
        # archive; doubling keeps a genuinely large one from costing a
        # separate read per megabyte.
        want = min(want * 2, CARVE_CHUNK)
    return None


def _apply_validators(fh, candidates: List[Candidate]) -> List[Candidate]:
    """Drop candidates failing their signature's structural validator
    (see Signature.validate).

    One small read per candidate that has a validator, reusing the
    handle the scan already holds. This is what stops a weak signature
    like BMP's 2-byte "BM" from turning one large binary file (a video,
    a disk image, anything without frequent footers) into thousands of
    bogus candidates, each of which would also truncate the real file
    via carve_candidates_fh's next-candidate bound.
    """
    if not any(c.signature.validate for c in candidates):
        return candidates
    kept = []
    for c in candidates:
        sig = c.signature
        if sig.validate is None:
            kept.append(c)
            continue
        fh.seek(c.offset)
        peek = fh.read(sig.validate_peek)
        if sig.validate(peek):
            kept.append(c)
    return kept


def scan_headers(
    source_path: str,
    formats: Optional[List[str]] = None,
    block_size: int = BLOCK_SIZE,
    progress_cb: ProgressCB = None,
) -> List[Candidate]:
    """Open `source_path` and scan it in one shot.

    Prefer scan_headers_fh() when also calling carve_candidates_fh() on
    the same source, to avoid a redundant close and reopen.
    """
    with open_source(source_path) as fh:
        total_size = get_source_size(source_path, fh)
        return scan_headers_fh(fh, total_size, formats=formats, block_size=block_size, progress_cb=progress_cb)


def _bmp_declared_size(header_bytes: bytes) -> Optional[int]:
    # BMP file header: 'BM' + 4-byte little-endian total file size
    if len(header_bytes) >= 6 and header_bytes[:2] == b"BM":
        return struct.unpack("<I", header_bytes[2:6])[0]
    return None


# Some common ISO-BMFF (MP4/MOV) top-level box types, used as a loose
# sanity check on the 4-byte type field while walking boxes below. An
# unknown type is not invalid, since vendors add their own, so the real
# check is "printable ASCII" and this set just covers the common case.
_MP4_KNOWN_BOX_TYPES = {
    b"ftyp", b"moov", b"mdat", b"free", b"skip", b"wide", b"pnot",
    b"PICT", b"moof", b"mfra", b"meta", b"meco", b"styp", b"sidx",
    b"ssix", b"prft", b"uuid", b"mvhd", b"trak", b"udta", b"mdta",
    b"emsg", b"jp2 ",
}


def _pe_declared_size(fh, start: int, cap: int) -> Optional[int]:
    """Length of a Windows PE (.exe/.dll) file from its own COFF section
    table, plus its certificate directory when signed.

    "MZ" is only 2 bytes, weaker even than BMP's "BM", so reading the
    real length here matters as much as it does there: the alternative is
    guessing from wherever an unrelated candidate happens to start next.

    Returns None when the data does not parse as a sane PE, leaving the
    caller to fall back to the next-candidate heuristic. Otherwise
    returns the total length spanned by the headers, the sections' raw
    data, and the certificate table if present.
    """
    try:
        fh.seek(start)
        head = fh.read(min(4096, cap))
        if len(head) < 64 or head[:2] != b"MZ":
            return None
        e_lfanew = struct.unpack("<I", head[0x3C:0x40])[0]
        if e_lfanew < 64 or e_lfanew + 24 > len(head):
            return None
        if head[e_lfanew : e_lfanew + 4] != b"PE\x00\x00":
            return None
        machine, num_sections, _ts, _psym, _nsym, size_opt, _chars = struct.unpack(
            "<HHIIIHH", head[e_lfanew + 4 : e_lfanew + 24]
        )
        if not (0 < num_sections <= 96):
            return None

        opt_start = e_lfanew + 24
        sec_start = opt_start + size_opt
        needed = sec_start + num_sections * 40
        if needed > len(head):
            fh.seek(start)
            head = fh.read(min(needed, cap))
            if needed > len(head):
                return None

        max_end = sec_start + num_sections * 40  # the headers themselves

        for i in range(num_sections):
            off = sec_start + i * 40
            size_raw, ptr_raw = struct.unpack("<II", head[off + 16 : off + 24])
            if ptr_raw:
                max_end = max(max_end, ptr_raw + size_raw)

        # The certificate table (the Authenticode signature on a signed
        # binary) sits after every section and, unlike every other data
        # directory, is addressed by a raw file offset rather than an
        # RVA, so looking only at sections under-counts it.
        if size_opt >= 2:
            magic = struct.unpack("<H", head[opt_start : opt_start + 2])[0]
            std_fields = 28 if magic == 0x10B else 24 if magic == 0x20B else None
            if std_fields is not None:
                win_fields = 68 if magic == 0x10B else 88
                dir_start = opt_start + std_fields + win_fields
                cert_dir = dir_start + 4 * 8  # IMAGE_DIRECTORY_ENTRY_SECURITY
                if cert_dir + 8 <= opt_start + size_opt and cert_dir + 8 <= len(head):
                    cert_off, cert_size = struct.unpack("<II", head[cert_dir : cert_dir + 8])
                    if cert_off:
                        max_end = max(max_end, cert_off + cert_size)

        if max_end <= 0 or max_end > cap:
            return None
        return max_end
    except (struct.error, IndexError):
        return None


def _sqlite_declared_size(peek: bytes) -> Optional[int]:
    """Exact length of a SQLite database from its header.

    The header states the page size and the page count ("in-header
    database size"), so the total is their product: no guessing from a
    neighbouring candidate, unlike most footerless formats.
    """
    if len(peek) < 32 or peek[:16] != b"SQLite format 3\x00":
        return None
    page_size = struct.unpack(">H", peek[16:18])[0]
    if page_size == 1:
        page_size = 65536  # 1 is SQLite's special-case encoding of 65536
    elif page_size < 512 or page_size > 32768 or (page_size & (page_size - 1)) != 0:
        return None
    page_count = struct.unpack(">I", peek[28:32])[0]
    if page_count <= 0:
        return None
    return page_size * page_count


def _7z_declared_size(peek: bytes) -> Optional[int]:
    """Exact length of a 7z archive from its signature header.

    The 32-byte header carries the offset and size of the archive's end
    header, so the total is 32 + NextHeaderOffset + NextHeaderSize.
    """
    if len(peek) < 32 or peek[:6] != b"7z\xBC\xAF\x27\x1C":
        return None
    next_header_offset, next_header_size = struct.unpack("<QQ", peek[12:28])
    total = 32 + next_header_offset + next_header_size
    return total if total > 32 else None


_RIFF_FORMS = {
    b"WAVE": ("WAV", "wav"),
    b"AVI ": ("AVI", "avi"),
}


def _riff_declared_size(peek: bytes) -> Optional[int]:
    """Exact length of a RIFF file from its own chunk-size field.

    The 4-byte size follows the 4-byte "RIFF" tag and covers everything
    after itself, so the total is that value plus the 8 bytes of tag and
    size.

    This doubles as a validity check. "RIFF" is only 4 bytes, the
    weakest remaining signature now that BMP and MZ have validators, so
    an implausible declared size is a useful sign the match was not a
    real RIFF header.
    """
    if len(peek) < 8:
        return None
    size = struct.unpack("<I", peek[4:8])[0]
    total = size + 8
    return total if total > 8 else None


_HEIF_BRANDS = {
    b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevm", b"hevs",
    b"mif1", b"msf1", b"avif", b"avis",
}


def _resolve_format_and_ext(sig: Signature, fh, start: int, window: int) -> Tuple[str, str]:
    """Resolve a candidate's real format and extension by peeking further
    into it.

    Some formats share a container with a very different file type:
    MP4's ISO-BMFF container is also how iPhones store HEIC photos, and
    a .docx/.xlsx/.pptx is a ZIP with a particular internal layout.
    Without this every HEIC photo would come back as .mp4 and every
    Office document as .zip, neither of them wrong exactly but neither
    recognizable.

    Falls back to the signature's own name and extension when nothing
    more specific matches, so a real video stays .mp4 and a plain
    archive stays .zip.
    """
    if sig.name == "MP4":
        fh.seek(start)
        peek = fh.read(min(16, window))
        if len(peek) >= 12 and peek[8:12] in _HEIF_BRANDS:
            return "HEIC", "heic"
        return sig.name, sig.ext
    if sig.name == "RIFF":
        fh.seek(start)
        peek = fh.read(min(12, window))
        if len(peek) >= 12 and peek[8:12] in _RIFF_FORMS:
            return _RIFF_FORMS[peek[8:12]]
        return sig.name, sig.ext
    if sig.name == "ZIP":
        fh.seek(start)
        peek = fh.read(min(4096, window))
        if b"word/document.xml" in peek or b"word/_rels/" in peek:
            return "DOCX", "docx"
        if b"xl/workbook.xml" in peek or b"xl/worksheets/" in peek:
            return "XLSX", "xlsx"
        if b"ppt/presentation.xml" in peek or b"ppt/slides/" in peek:
            return "PPTX", "pptx"
        return sig.name, sig.ext
    return sig.name, sig.ext


def _mp4_walk_size(fh, start: int, cap: int) -> Optional[int]:
    """Length of an MP4/MOV file by walking its own ISO-BMFF box headers
    (ftyp/moov/mdat/...) from `start`, each of which declares its size.

    MP4 has no footer, so without this the only bound available to
    carve_candidates_fh is "stop at the next candidate's offset". A large
    video is hundreds of megabytes of compressed binary data, well within
    range for another signature's header (JPEG's, ID3's) to appear by
    chance and pass its own validator, and one such coincidence anywhere
    inside truncates the video. Reading the box structure makes the
    length independent of what happens to match nearby.

    Returns None when the data is not a walkable box chain, leaving the
    caller to fall back to the next-candidate heuristic. Otherwise
    returns the length spanned by as many consecutive parseable boxes as
    could be read, stopping at `cap` or at a box claiming to run to EOF.
    """
    offset = start
    end_limit = start + cap
    saw_valid_box = False
    while offset < end_limit:
        fh.seek(offset)
        head = fh.read(16)
        if len(head) < 8:
            break
        size32 = struct.unpack(">I", head[0:4])[0]
        box_type = head[4:8]
        header_len = 8
        if size32 == 1:
            if len(head) < 16:
                break
            size = struct.unpack(">Q", head[8:16])[0]
            header_len = 16
        elif size32 == 0:
            # Size 0 means "extends to end of file", which the header
            # alone cannot resolve. Treat everything parsed so far as a
            # floor and let the caller apply the usual cap to this
            # open-ended final box.
            return (offset - start) if saw_valid_box else None
        else:
            size = size32
        if size < header_len:
            break
        looks_like_type = box_type in _MP4_KNOWN_BOX_TYPES or all(0x20 <= b <= 0x7E for b in box_type)
        if not looks_like_type:
            break
        saw_valid_box = True
        offset += size
    if not saw_valid_box:
        return None
    return offset - start


def carve_candidates_fh(
    fh,
    total_size: int,
    candidates: List[Candidate],
    out_dir: str,
    progress_cb: ProgressCB = None,
) -> List[RecoveredFile]:
    """Extract each candidate from an open source. See scan_headers_fh()
    for why this takes a handle rather than a path.
    """
    os.makedirs(out_dir, exist_ok=True)
    recovered: List[RecoveredFile] = []

    for i, cand in enumerate(candidates):
        sig = cand.signature
        start = cand.offset
        next_start = candidates[i + 1].offset if i + 1 < len(candidates) else None
        upper_bound = start + sig.max_size
        # Formats that declare their own size (BMP's header field, MP4's
        # box chain) must not use the next-candidate bound below.
        # Trusting "stop wherever another signature happens to match
        # next" is what let a coincidental match inside a large binary
        # file, usually a video, truncate it. Their real bound comes from
        # their own data further down.
        self_describing = sig.name in SELF_DESCRIBING_FORMATS
        # A format with its own footer may search past an unrelated
        # candidate starting inside it. A weak header, or a stray
        # footer-lookalike byte sequence, appearing by coincidence inside
        # this file's data is no reason to stop early and truncate before
        # the real footer.
        #
        # Formats with neither a footer nor a readable declared size
        # (RAR, MP3-ID3, MKV, OLE-DOC, TIFF) keep "stop at the next
        # candidate" as their only guard against running to max_size.
        if next_start is not None and next_start > start and not sig.footers and not self_describing:
            upper_bound = min(upper_bound, next_start)
        if total_size:
            upper_bound = min(upper_bound, total_size)

        window = upper_bound - start
        if window <= 0:
            continue

        fh.seek(start)
        header_peek = fh.read(min(64, window))

        declared_size = None
        if sig.name == "BMP":
            declared_size = _bmp_declared_size(header_peek)
            if declared_size and 0 < declared_size <= window:
                upper_bound = start + declared_size
                window = declared_size
        elif sig.name == "MP4":
            declared_size = _mp4_walk_size(fh, start, window)
            if declared_size and 0 < declared_size <= window:
                upper_bound = start + declared_size
                window = declared_size
            else:
                # No walkable box chain, so the start is corrupted or
                # overwritten. Fall back rather than run to a 4GB
                # max_size on garbage.
                if next_start is not None and next_start > start:
                    upper_bound = min(upper_bound, next_start)
                    window = upper_bound - start
        elif sig.name == "EXE":
            declared_size = _pe_declared_size(fh, start, window)
            if declared_size and 0 < declared_size <= window:
                upper_bound = start + declared_size
                window = declared_size
            else:
                # No sane section table, so the start is corrupted or
                # overwritten. Same fallback as MP4 above.
                if next_start is not None and next_start > start:
                    upper_bound = min(upper_bound, next_start)
                    window = upper_bound - start
        elif sig.name == "RIFF":
            declared_size = _riff_declared_size(header_peek)
            if declared_size and 0 < declared_size <= window:
                upper_bound = start + declared_size
                window = declared_size
            else:
                declared_size = None
                if next_start is not None and next_start > start:
                    upper_bound = min(upper_bound, next_start)
                    window = upper_bound - start
        elif sig.name == "SQLite":
            declared_size = _sqlite_declared_size(header_peek)
            if declared_size and 0 < declared_size <= window:
                upper_bound = start + declared_size
                window = declared_size
            else:
                declared_size = None
                if next_start is not None and next_start > start:
                    upper_bound = min(upper_bound, next_start)
                    window = upper_bound - start
        elif sig.name == "7ZIP":
            declared_size = _7z_declared_size(header_peek)
            if declared_size and 0 < declared_size <= window:
                upper_bound = start + declared_size
                window = declared_size
            else:
                declared_size = None
                if next_start is not None and next_start > start:
                    upper_bound = min(upper_bound, next_start)
                    window = upper_bound - start

        display_format, ext = _resolve_format_and_ext(sig, fh, start, window)
        out_name = f"recovered_{i:05d}_{start:012x}.{ext}"
        out_path = os.path.join(out_dir, out_name)

        fh.seek(start)
        written = 0
        truncated = True
        tail_carry = b""

        with open(out_path, "wb") as out_fh:
            remaining = window
            while remaining > 0:
                to_read = min(CARVE_CHUNK, remaining)
                data = fh.read(to_read)
                if not data:
                    break
                out_fh.write(data)
                written += len(data)
                remaining -= len(data)

                if sig.footers:
                    haystack = tail_carry + data
                    found_at = None
                    for footer in sig.footers:
                        idx = haystack.find(footer)
                        if idx != -1:
                            found_at = idx + len(footer) + sig.footer_extra
                            break
                    if found_at is not None:
                        # found_at is relative to haystack; trim what we
                        # already wrote past the footer.
                        excess = len(haystack) - found_at
                        if 0 < excess <= len(data):
                            out_fh.truncate(out_fh.tell() - excess)
                            written -= excess
                        truncated = False
                        break
                    tail_carry = data[-MAX_FOOTER_LEN:] if MAX_FOOTER_LEN else b""
                elif declared_size is not None:
                    truncated = False

            else:
                if not sig.footers:
                    truncated = declared_size is None

        if written <= 0:
            try:
                os.remove(out_path)
            except OSError:
                pass
            continue

        recovered.append(
            RecoveredFile(
                path=out_path,
                offset=start,
                size=written,
                format=display_format,
                truncated=truncated,
            )
        )
        if progress_cb:
            progress_cb(i + 1, len(candidates))

    return recovered


def carve_candidates(
    source_path: str,
    candidates: List[Candidate],
    out_dir: str,
    progress_cb: ProgressCB = None,
) -> List[RecoveredFile]:
    """Open `source_path` and extract in one shot.

    Prefer carve_candidates_fh() when also calling scan_headers_fh() on
    the same source, to avoid a redundant close and reopen, which can
    fail on Windows raw devices.
    """
    with open_source(source_path) as fh:
        total_size = get_source_size(source_path, fh)
        return carve_candidates_fh(fh, total_size, candidates, out_dir, progress_cb=progress_cb)
