#!/usr/bin/env python3
"""Self-contained sanity tests.

The carving test needs nothing but Python and always runs. The FAT/NTFS
undelete tests need the platform's own filesystem tools (mkfs.vfat +
mtools, or mkfs.ntfs + mount) to build a real test filesystem image, so
they're skipped with a clear message if those aren't installed --
that's expected on most machines and not a failure of this tool.
"""

import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data_recover.carve import carve_candidates, scan_headers, scan_headers_fh
from data_recover.filesystems import fat, ntfs
from data_recover.utils import AlignedFile, open_source

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"

results = []


def check(name, condition):
    results.append((name, condition))
    print(f"[{PASS if condition else FAIL}] {name}")


def skip(name, reason):
    print(f"[{SKIP}] {name} ({reason})")


def test_carving():
    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "carve.img")
        # Seeded, not os.urandom: with unseeded padding this test failed
        # roughly 1 run in 40, because ~2.6% of random 2000-byte payloads
        # happen to contain a stray FF D9, JPEG's end-of-image marker,
        # which correctly truncates the carve there and so fails the
        # byte-identity check. A real JPEG cannot do that: 0xFF inside
        # entropy-coded data is byte-stuffed as FF 00, so a bare FF D9 only
        # ever appears as the genuine EOI. Dropping 0xFF from the filler
        # models that rule, and the seed keeps every run identical.
        rng = random.Random(3)

        def filler(n):
            return bytes(rng.randrange(0x00, 0xFF) for _ in range(n))

        out = bytearray()
        out += filler(500)
        jpeg = bytes.fromhex("FFD8FFE000104A46494600010100000100010000") + filler(2000) + bytes.fromhex("FFD9")
        out += jpeg
        out += filler(300)

        def chunk(tag, data):
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

        png = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        png += chunk(b"IEND", b"")
        out += png
        out += filler(300)

        with open(img_path, "wb") as f:
            f.write(out)

        candidates = scan_headers(img_path)
        check("carving: iki dosya da tespit edildi", len(candidates) == 2)

        recovered = carve_candidates(img_path, candidates, os.path.join(tmp, "out"))
        check("carving: iki dosya da çıkarıldı", len(recovered) == 2)

        by_fmt = {r.format: r for r in recovered}
        if "JPEG" in by_fmt:
            data = open(by_fmt["JPEG"].path, "rb").read()
            check("carving: JPEG içerik birebir eşleşiyor", data == jpeg)
        if "PNG" in by_fmt:
            data = open(by_fmt["PNG"].path, "rb").read()
            check("carving: PNG içerik birebir eşleşiyor", data == png)


def test_bmp_false_positives_dont_shred_real_files():
    # A large binary blob, standing in for a footerless video, that by
    # chance contains many coincidental "BM" byte pairs. Without the BMP
    # structural validator every one of those became a candidate, which
    # both produced a flood of bogus "BMP" files and truncated the real
    # surrounding file at each one, since carve_candidates_fh bounds a
    # footerless format by the next candidate's offset whatever its type.
    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "video.img")
        # Seed chosen so the random "video" body leaves no false-positive
        # candidates after validation. The JPEG/ID3/BMP validators cut the
        # false-positive rate sharply but not to zero for such short
        # headers, so an unseeded run has a small chance of a coincidental
        # match that also passes validation and legitimately truncates the
        # MP4, exactly as a real neighbouring file would. That is an
        # inherent limit of signature-only carving on weak headers, not a
        # bug for this test to chase.
        rng = random.Random(1)

        mp4_header = struct.pack(">I", 32) + b"ftypisom" + rng.randbytes(24)
        video_body = rng.randbytes(3_000_000)  # 3MB of "video" payload
        mp4_blob = mp4_header + video_body

        # count how many coincidental "BM" pairs we actually planted, so
        # the assertion isn't just hoping the RNG cooperated
        coincidental_bm = mp4_blob.count(b"BM")
        assert coincidental_bm > 20, "test data didn't land enough coincidental BM matches to be meaningful"

        # one real, structurally valid BMP elsewhere in the file
        bmp_pixels = b"\x00" * 40
        bmp = b"BM" + struct.pack("<I", 14 + 40 + len(bmp_pixels))
        bmp += b"\x00\x00\x00\x00" + struct.pack("<I", 14 + 40)
        bmp += struct.pack("<IiiHHIIiiII", 40, 4, 4, 1, 24, 0, len(bmp_pixels), 2835, 2835, 0, 0)
        bmp += bmp_pixels

        out = mp4_blob + bmp + rng.randbytes(1000)

        with open(img_path, "wb") as f:
            f.write(out)

        candidates = scan_headers(img_path)
        by_name = {}
        for c in candidates:
            by_name.setdefault(c.signature.name, []).append(c)

        check(
            "BMP dogrulama: rastgele veri icindeki sahte 'BM' eslesmeleri elendi",
            len(by_name.get("BMP", [])) == 1,
        )
        check(
            "BMP dogrulama: gercek/gecerli BMP hala bulunuyor",
            len(by_name.get("BMP", [])) == 1 and by_name["BMP"][0].offset == len(mp4_blob),
        )

        recovered = carve_candidates(img_path, candidates, os.path.join(tmp, "out"))
        mp4_files = [r for r in recovered if r.format == "MP4"]
        check("BMP dogrulama: MP4 tek parca halinde kurtarildi (dogrulanamayan BM'lerce dogranmadi)", len(mp4_files) == 1)
        if mp4_files:
            check(
                "BMP dogrulama: kurtarilan MP4 boyutu gercek boyutla eslesiyor (kirpilmemis)",
                mp4_files[0].size == len(mp4_blob),
            )


def test_mp4_box_walk_survives_coincidental_matches_inside_video():
    # This is the bug the user actually hit on real hardware: the BMP
    # validator alone wasn't enough, because MP4 has no footer, so
    # carve_candidates_fh fell back to "stop at the next candidate" --
    # and with 200+MB of compressed video data, it only takes ONE
    # coincidental (but validator-passing) JPEG/ID3/etc. header match
    # somewhere inside that data to truncate the real MP4 early. Real
    # videos came back much smaller than their true size.
    #
    # Fix: MP4 now reads its own ISO-BMFF box sizes (ftyp/mdat/...)
    # instead of trusting where some other signature's header happens to
    # start next. This test builds a well-formed box chain, plants a
    # coincidental JPEG header that legitimately passes _validate_jpeg
    # right in the middle of the "video" payload, and checks the MP4 is
    # still recovered at its full, true length.
    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "movie.img")
        rng = random.Random(7)

        video_payload = bytearray(rng.randbytes(3_000_000))
        # Plant a coincidental "JPEG start of image plus valid marker
        # byte" sequence mid-payload: a marker byte in 0xC0-0xFE is what
        # _validate_jpeg accepts, reached here by chance rather than by
        # any real neighbouring file.
        fake_jpeg_at = 1_500_000
        video_payload[fake_jpeg_at : fake_jpeg_at + 4] = b"\xFF\xD8\xFF\xE0"

        mdat = struct.pack(">I", 8 + len(video_payload)) + b"mdat" + bytes(video_payload)
        ftyp_payload = b"isom" + rng.randbytes(16)
        ftyp = struct.pack(">I", 8 + len(ftyp_payload)) + b"ftyp" + ftyp_payload
        mp4_blob = ftyp + mdat

        out = rng.randbytes(2000) + mp4_blob + rng.randbytes(2000)

        with open(img_path, "wb") as f:
            f.write(out)

        candidates = scan_headers(img_path)
        by_name = {}
        for c in candidates:
            by_name.setdefault(c.signature.name, []).append(c)

        check(
            "MP4 box-walk: sahte JPEG eslesmesi hala aday olarak bulundu (beklenen)",
            len(by_name.get("JPEG", [])) >= 1,
        )

        recovered = carve_candidates(img_path, candidates, os.path.join(tmp, "out"))
        mp4_files = [r for r in recovered if r.format == "MP4"]
        check("MP4 box-walk: MP4 tam olarak bulundu", len(mp4_files) == 1)
        if mp4_files:
            check(
                "MP4 box-walk: kurtarilan MP4 boyutu, videonun icindeki sahte JPEG'e ragmen gercek boyutla eslesiyor",
                mp4_files[0].size == len(mp4_blob),
            )
            check(
                "MP4 box-walk: MP4 dogru offsetten baslatildi",
                mp4_files[0].offset == 2000,
            )


def _build_minimal_pe(payload: bytes) -> bytes:
    """Hand-builds the smallest well-formed PE32+ (x64) .exe the section-
    table walker (_pe_declared_size) needs to succeed: a 64-byte DOS
    header, a PE header with one section (".text"), and that section's
    raw data being exactly `payload`. Every header field the walker
    reads is filled in correctly; everything else is left zeroed since
    the walker doesn't look at it.
    """
    e_lfanew = 64
    dos_header = b"MZ" + b"\x00" * 58 + struct.pack("<I", e_lfanew)
    assert len(dos_header) == 64

    machine = 0x8664  # x64
    num_sections = 1
    size_opt = 240  # PE32+, 16 data directories: 24 + 88 + 16*8
    file_header = struct.pack("<HHIIIHH", machine, num_sections, 0, 0, 0, size_opt, 0x0022)
    assert len(file_header) == 20

    opt_start = e_lfanew + 4 + 20  # = 88
    optional_header = bytearray(size_opt)
    optional_header[0:2] = struct.pack("<H", 0x20B)  # PE32+ magic
    # leave the certificate directory (index 4) zeroed: unsigned binary

    sec_start = opt_start + size_opt  # = 328
    ptr_raw = sec_start + 40  # right after the one section header = 368
    section = (
        b".text\x00\x00\x00"
        + struct.pack("<I", len(payload))  # VirtualSize
        + struct.pack("<I", 0x1000)  # VirtualAddress
        + struct.pack("<I", len(payload))  # SizeOfRawData
        + struct.pack("<I", ptr_raw)  # PointerToRawData
        + struct.pack("<I", 0)  # PointerToRelocations
        + struct.pack("<I", 0)  # PointerToLinenumbers
        + struct.pack("<H", 0)  # NumberOfRelocations
        + struct.pack("<H", 0)  # NumberOfLinenumbers
        + struct.pack("<I", 0x60000020)  # Characteristics
    )
    assert len(section) == 40

    blob = dos_header + b"PE\x00\x00" + file_header + bytes(optional_header) + section
    assert len(blob) == ptr_raw
    return blob + payload


def test_exe_section_table_survives_coincidental_matches_inside_binary():
    # Same shape as the MP4 case. "MZ" is a bare 2-byte header, weaker
    # even than BMP's, and an .exe's code and data sections are pages of
    # dense binary like a video payload, leaving room for another
    # signature's header to appear by chance and still pass validation.
    # EXE has no footer either, so without reading its own section table
    # one such coincidence truncates a multi-MB binary early.
    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "app.img")
        rng = random.Random(13)

        payload = bytearray(rng.randbytes(2_000_000))
        fake_jpeg_at = 900_000
        payload[fake_jpeg_at : fake_jpeg_at + 4] = b"\xFF\xD8\xFF\xE1"

        exe_blob = _build_minimal_pe(bytes(payload))
        out = rng.randbytes(1500) + exe_blob + rng.randbytes(1500)

        with open(img_path, "wb") as f:
            f.write(out)

        candidates = scan_headers(img_path)
        by_name = {}
        for c in candidates:
            by_name.setdefault(c.signature.name, []).append(c)

        check(
            "EXE bolum-tablosu: sahte JPEG eslesmesi hala aday olarak bulundu (beklenen)",
            len(by_name.get("JPEG", [])) >= 1,
        )
        check("EXE bolum-tablosu: tam olarak bir EXE adayi bulundu", len(by_name.get("EXE", [])) == 1)

        recovered = carve_candidates(img_path, candidates, os.path.join(tmp, "out"))
        exe_files = [r for r in recovered if r.format == "EXE"]
        check("EXE bolum-tablosu: EXE tam olarak bulundu", len(exe_files) == 1)
        if exe_files:
            check(
                "EXE bolum-tablosu: kurtarilan EXE boyutu, icindeki sahte JPEG'e ragmen gercek boyutla eslesiyor",
                exe_files[0].size == len(exe_blob),
            )
            check(
                "EXE bolum-tablosu: EXE dogru offsetten baslatildi",
                exe_files[0].offset == 1500,
            )


def test_riff_wav_avi_disambiguation_and_exact_size():
    # AVI and WAV share the same 4-byte "RIFF" header. Searching for both
    # separately produced two candidates, and two output files with one
    # always wrong, at the same offset. This checks the
    # merged RIFF signature instead produces exactly one candidate per
    # real file, and that carve.py's peek at the form type (bytes 8-12)
    # + RIFF's own declared chunk size correctly names and exactly
    # sizes each one.
    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "media.img")
        rng = random.Random(31)

        wav_body = rng.randbytes(3000)
        wav_blob = b"RIFF" + struct.pack("<I", 4 + len(wav_body)) + b"WAVE" + wav_body

        avi_body = rng.randbytes(4000)
        avi_blob = b"RIFF" + struct.pack("<I", 4 + len(avi_body)) + b"AVI " + avi_body

        out = rng.randbytes(1000) + wav_blob + rng.randbytes(1000) + avi_blob + rng.randbytes(1000)
        with open(img_path, "wb") as f:
            f.write(out)

        candidates = scan_headers(img_path)
        check(
            "RIFF ayrimi: iki gercek dosya icin tam olarak iki aday var (ciftlenme yok)",
            len(candidates) == 2,
        )

        recovered = carve_candidates(img_path, candidates, os.path.join(tmp, "out"))
        by_format = {r.format: r for r in recovered}
        check("RIFF ayrimi: WAV dogru tanindi", "WAV" in by_format)
        check("RIFF ayrimi: AVI dogru tanindi", "AVI" in by_format)
        if "WAV" in by_format:
            check("RIFF ayrimi: WAV boyutu tam", by_format["WAV"].size == len(wav_blob))
            check("RIFF ayrimi: WAV uzantisi dogru", by_format["WAV"].path.endswith(".wav"))
        if "AVI" in by_format:
            check("RIFF ayrimi: AVI boyutu tam", by_format["AVI"].size == len(avi_blob))
            check("RIFF ayrimi: AVI uzantisi dogru", by_format["AVI"].path.endswith(".avi"))


def test_zip_office_document_detection():
    # A .docx/.xlsx/.pptx is a ZIP archive with a particular internal
    # folder layout. Without peeking at that layout every recovered
    # Office document would be labelled .zip. Builds one minimal
    # ZIP whose first entry is "word/document.xml" (the OOXML tell for
    # Word) and one plain ZIP with no such entry, and checks only the
    # first gets relabelled.
    def _build_zip(fname: bytes, content: bytes) -> bytes:
        local_header = (
            b"PK\x03\x04"
            + struct.pack("<H", 20)
            + struct.pack("<H", 0)
            + struct.pack("<H", 0)
            + struct.pack("<H", 0)
            + struct.pack("<H", 0)
            + struct.pack("<I", 0)
            + struct.pack("<I", len(content))
            + struct.pack("<I", len(content))
            + struct.pack("<H", len(fname))
            + struct.pack("<H", 0)
            + fname
            + content
        )
        eocd = b"PK\x05\x06" + b"\x00" * 18
        return local_header + eocd

    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "archives.img")
        rng = random.Random(41)

        docx_zip = _build_zip(b"word/document.xml", b"<xml>fake docx</xml>")
        plain_zip = _build_zip(b"random/file.bin", rng.randbytes(200))

        out = rng.randbytes(500) + docx_zip + rng.randbytes(500) + plain_zip + rng.randbytes(500)
        with open(img_path, "wb") as f:
            f.write(out)

        candidates = scan_headers(img_path)
        recovered = carve_candidates(img_path, candidates, os.path.join(tmp, "out"))
        by_offset = {r.offset: r for r in recovered}

        docx_offset = 500
        plain_offset = 500 + len(docx_zip) + 500
        check("ZIP/DOCX: word/document.xml iceren zip DOCX olarak taninidi", by_offset.get(docx_offset) and by_offset[docx_offset].format == "DOCX")
        if docx_offset in by_offset:
            check("ZIP/DOCX: dogru uzanti (.docx)", by_offset[docx_offset].path.endswith(".docx"))
        check("ZIP/DOCX: isaret icermeyen zip duz ZIP kaldi", by_offset.get(plain_offset) and by_offset[plain_offset].format == "ZIP")


def test_zip_dedupe_does_not_read_far_past_each_archive():
    # _dedupe_nested_zip_candidates has to find each ZIP candidate's own
    # end-of-central-directory record to learn its span, so it can drop the
    # nested PK\x03\x04 entries inside it. It used to do that with one
    # blind 64MB read per candidate. A real .docx is usually well under a
    # megabyte, so a card holding a few hundred Office documents meant
    # tens of gigabytes of redundant reads, slow enough on USB or SD
    # media to look like a hang. It now reads forward in chunks and stops
    # at the first EOCD.
    #
    # Asserts both halves: total bytes read stays within a small multiple
    # of the image rather than hundreds of times it, and the dedupe still
    # yields exactly one candidate per archive.
    def _build_zip(fname: bytes, content: bytes) -> bytes:
        local_header = (
            b"PK\x03\x04"
            + struct.pack("<H", 20)
            + struct.pack("<H", 0)
            + struct.pack("<H", 0)
            + struct.pack("<H", 0)
            + struct.pack("<H", 0)
            + struct.pack("<I", 0)
            + struct.pack("<I", len(content))
            + struct.pack("<I", len(content))
            + struct.pack("<H", len(fname))
            + struct.pack("<H", 0)
            + fname
            + content
        )
        return local_header + b"PK\x05\x06" + b"\x00" * 18

    class _CountingReader:
        """Wraps a file handle and tallies how much gets read through it."""

        def __init__(self, fh):
            self._fh = fh
            self.bytes_read = 0

        def seek(self, *a):
            return self._fh.seek(*a)

        def tell(self):
            return self._fh.tell()

        def read(self, n=-1):
            data = self._fh.read(n)
            self.bytes_read += len(data)
            return data

    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "many_zips.img")
        rng = random.Random(97)

        archive = _build_zip(b"word/document.xml", b"<xml>doc</xml>" * 8)
        n_archives = 40
        stride = 256 * 1024
        buf = bytearray(rng.randbytes(n_archives * stride))
        offsets = []
        for i in range(n_archives):
            off = i * stride + 64
            buf[off:off + len(archive)] = archive
            offsets.append(off)
        with open(img_path, "wb") as f:
            f.write(bytes(buf))

        img_size = len(buf)
        with open_source(img_path) as raw:
            counting = _CountingReader(raw)
            candidates = scan_headers_fh(counting, img_size)
            total_read = counting.bytes_read

        zip_offsets = sorted(c.offset for c in candidates if c.signature.name == "ZIP")
        check(
            "ZIP dedupe: her arsiv icin tek aday (ic girdiler ayiklandi)",
            zip_offsets == offsets,
        )
        # The pre-fix code read 64MB per archive: 40 * 64MB = 2.6GB for a
        # 10MB image, ~256x. A chunked search stays near a single pass.
        check(
            "ZIP dedupe: okunan bayt imaj boyutunun 4 katini gecmiyor "
            f"({total_read / img_size:.1f}x)",
            total_read < img_size * 4,
        )


def test_heic_vs_real_mp4_detection():
    # HEIC (iPhone photos) uses the same ISO-BMFF box structure as MP4;
    # only the 'ftyp' box's major brand differs. Unchecked, every
    # recovered iPhone photo would be labelled .mp4.
    def _build_isobmff(major_brand: bytes, payload: bytes) -> bytes:
        ftyp_rest = major_brand + struct.pack(">I", 0) + b"mif1heic"
        ftyp = struct.pack(">I", 8 + len(ftyp_rest)) + b"ftyp" + ftyp_rest
        mdat = struct.pack(">I", 8 + len(payload)) + b"mdat" + payload
        return ftyp + mdat

    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "photos.img")
        rng = random.Random(51)

        heic_blob = _build_isobmff(b"heic", rng.randbytes(50_000))
        mp4_blob = _build_isobmff(b"isom", rng.randbytes(50_000))

        out = rng.randbytes(800) + heic_blob + rng.randbytes(800) + mp4_blob + rng.randbytes(800)
        with open(img_path, "wb") as f:
            f.write(out)

        candidates = scan_headers(img_path)
        recovered = carve_candidates(img_path, candidates, os.path.join(tmp, "out"))
        by_offset = {r.offset: r for r in recovered}

        heic_offset = 800
        mp4_offset = 800 + len(heic_blob) + 800
        check("HEIC tespiti: heic markali ftyp HEIC olarak taninidi", by_offset.get(heic_offset) and by_offset[heic_offset].format == "HEIC")
        if heic_offset in by_offset:
            check("HEIC tespiti: dogru uzanti (.heic)", by_offset[heic_offset].path.endswith(".heic"))
            check("HEIC tespiti: boyut tam", by_offset[heic_offset].size == len(heic_blob))
        check("HEIC tespiti: isom markali ftyp hala MP4", by_offset.get(mp4_offset) and by_offset[mp4_offset].format == "MP4")


def test_sqlite_and_7z_exact_declared_size():
    # SQLite's header states page size * page count = exact file size;
    # 7z's header states the exact end-header offset + size. Neither
    # needs the next-candidate heuristic at all. Checks both compute the
    # true size directly from their own header fields.
    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "containers.img")
        rng = random.Random(61)

        page_size = 4096
        page_count = 10
        sqlite_total = page_size * page_count
        sqlite_header = bytearray(100)
        sqlite_header[0:16] = b"SQLite format 3\x00"
        sqlite_header[16:18] = struct.pack(">H", page_size)
        sqlite_header[28:32] = struct.pack(">I", page_count)
        sqlite_blob = bytes(sqlite_header) + rng.randbytes(sqlite_total - 100)
        assert len(sqlite_blob) == sqlite_total

        next_header_offset = 500
        next_header_size = 50
        sevenz_sig = (
            b"7z\xBC\xAF\x27\x1C"
            + bytes([0, 4])
            + struct.pack("<I", 0)
            + struct.pack("<Q", next_header_offset)
            + struct.pack("<Q", next_header_size)
            + struct.pack("<I", 0)
        )
        assert len(sevenz_sig) == 32
        sevenz_total = 32 + next_header_offset + next_header_size
        sevenz_blob = sevenz_sig + rng.randbytes(sevenz_total - 32)
        assert len(sevenz_blob) == sevenz_total

        out = rng.randbytes(300) + sqlite_blob + rng.randbytes(300) + sevenz_blob + rng.randbytes(300)
        with open(img_path, "wb") as f:
            f.write(out)

        candidates = scan_headers(img_path)
        recovered = carve_candidates(img_path, candidates, os.path.join(tmp, "out"))
        by_format = {r.format: r for r in recovered}

        check("SQLite: bulundu ve boyutu page_size*page_count ile tam eslesiyor", "SQLite" in by_format and by_format["SQLite"].size == sqlite_total)
        check("7z: bulundu ve boyutu NextHeaderOffset+Size ile tam eslesiyor", "7ZIP" in by_format and by_format["7ZIP"].size == sevenz_total)


def test_orphan_dir_entry_scan_finds_names_missed_by_live_tree():
    # A quick format rewrites the boot sector, the FAT tables and the
    # root directory's first cluster, but an old subdirectory's own
    # cluster, elsewhere on disk with its entries intact, is untouched.
    # Anything that only walks the now-empty live root cannot reach it,
    # so its original filenames are lost even though the bytes remain.
    # Builds one such orphaned but intact directory entry at an offset
    # with no path from any root, and checks the scan finds it while
    # running inside carve's normal sequential pass.
    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "disk.img")
        rng = random.Random(21)

        boot = fat.BootSector(
            bytes_per_sector=512,
            sectors_per_cluster=1,
            reserved_sectors=1,
            num_fats=1,
            root_entries=0,
            total_sectors=100_000,
            fat_size=10,
            fat_type="FAT32",
            root_cluster=2,
            fat_start=512,
            cluster_heap_start=8192,
        )

        file_cluster = 5
        file_offset = boot.cluster_to_offset(file_cluster)
        file_payload = rng.randbytes(700)  # spans two clusters on purpose

        entry = bytearray(32)
        entry[0:8] = b"OLDPIC  "
        entry[8:11] = b"JPG"
        entry[11] = 0x20  # archive, not deleted, not a directory
        entry[12] = 0x00  # NTRes
        entry[13] = 100  # CrtTimeTenth
        valid_date = (25 << 9) | (6 << 5) | 15  # a plausible FAT date
        entry[16:18] = struct.pack("<H", valid_date)  # CrtDate
        entry[18:20] = struct.pack("<H", 0)  # LastAccessDate (unset, allowed)
        entry[20:22] = struct.pack("<H", (file_cluster >> 16) & 0xFFFF)  # FstClusHI
        entry[24:26] = struct.pack("<H", valid_date)  # WrtDate
        entry[26:28] = struct.pack("<H", file_cluster & 0xFFFF)  # FstClusLO
        entry[28:32] = struct.pack("<I", len(file_payload))  # FileSize

        orphan_dir_offset = 40_000  # disconnected from any directory chain
        out = bytearray(rng.randbytes(orphan_dir_offset))
        out += bytes(entry)
        out += rng.randbytes(480)
        if len(out) < file_offset:
            out += rng.randbytes(file_offset - len(out))
        out[file_offset : file_offset + len(file_payload)] = file_payload
        out += rng.randbytes(2000)

        with open(img_path, "wb") as f:
            f.write(bytes(out))

        total_size = len(out)
        orphan_sink = []
        with open(img_path, "rb") as fh:
            # an unmatchable format name so this run only exercises the
            # orphan scan, not the signature scan too
            scan_headers_fh(fh, total_size, formats=["__none__"], boot_sector=boot, orphan_sink=orphan_sink)

        check("Oksuz dizin girdisi: en az bir aday bulundu", len(orphan_sink) >= 1)
        match = next((e for e in orphan_sink if e.name.upper() == "OLDPIC.JPG"), None)
        check("Oksuz dizin girdisi: OLDPIC.JPG bulundu", match is not None)
        if match:
            check("Oksuz dizin girdisi: boyut dogru", match.size == len(file_payload))
            check("Oksuz dizin girdisi: baslangic kumesi dogru", match.start_cluster == file_cluster)
            with open(img_path, "rb") as fh:
                recovered_path = fat.recover_entry(fh, boot, match, os.path.join(tmp, "out"))
            check("Oksuz dizin girdisi: dosya kurtarildi", recovered_path is not None)
            if recovered_path:
                with open(recovered_path, "rb") as rf:
                    check(
                        "Oksuz dizin girdisi: icerik birebir eslesiyor",
                        rf.read() == file_payload,
                    )


class _UnalignedHostileFile:
    """Stand-in for a Windows raw device handle: refuses any seek/read
    that isn't aligned to a sector boundary, exactly like real Windows
    does for \\\\.\\PhysicalDriveN / \\\\.\\X: handles. Backed by an
    in-memory buffer so this test runs anywhere, not just on Windows.
    """

    SECTOR = 512

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def seek(self, pos, whence=0):
        if whence == 2:
            pos = len(self._data) + pos
        if pos % self.SECTOR != 0:
            raise OSError(22, "seek offset not sector-aligned")
        self._pos = pos
        return self._pos

    def tell(self):
        return self._pos

    def read(self, size=-1):
        if size < 0:
            size = len(self._data) - self._pos
        if size % self.SECTOR != 0:
            raise OSError(22, "read size not sector-aligned")
        chunk = self._data[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk


def test_aligned_file():
    # deterministic-but-varied content so slicing bugs show up as mismatches;
    # length must be a sector multiple, same as any real block device
    data = bytes((i * 37 + 11) % 256 for i in range(20 * 512))
    hostile = _UnalignedHostileFile(data)
    af = AlignedFile(hostile)

    af.seek(0)
    check("AlignedFile: baştan okuma doğru", af.read(10) == data[0:10])

    af.seek(777)
    check("AlignedFile: hizasız offsetten okuma doğru", af.read(23) == data[777:800])

    af.seek(-5, 2)
    check("AlignedFile: sona göre (SEEK_END) okuma doğru", af.read(5) == data[-5:])

    af.seek(500)
    chunk1 = af.read(50)
    chunk2 = af.read(50)
    check(
        "AlignedFile: ardışık okumalar sektör sınırını doğru geçiyor",
        chunk1 == data[500:550] and chunk2 == data[550:600],
    )


class _MaxTransferHostileFile:
    """Simulates a raw device driver that rejects any single read() above
    a maximum transfer size, as some USB mass storage stacks do, by
    raising PermissionError. This is the symptom AlignedFile's
    retry-and-shrink logic exists for. Every read must still be
    sector-aligned, like a real device.
    """

    SECTOR = 512

    def __init__(self, data: bytes, max_transfer: int):
        self._data = data
        self._pos = 0
        self._max_transfer = max_transfer
        self.biggest_ok_read = 0  # what the test asserts against afterwards

    def seek(self, pos, whence=0):
        if whence == 2:
            pos = len(self._data) + pos
        if pos % self.SECTOR != 0:
            raise OSError(22, "seek offset not sector-aligned")
        self._pos = pos
        return self._pos

    def tell(self):
        return self._pos

    def read(self, size=-1):
        if size < 0:
            size = len(self._data) - self._pos
        if size % self.SECTOR != 0:
            raise OSError(22, "read size not sector-aligned")
        if size > self._max_transfer:
            raise PermissionError(13, "Permission denied")
        self.biggest_ok_read = max(self.biggest_ok_read, size)
        chunk = self._data[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk


def test_aligned_file_large_read_retry():
    # A single read this big would be rejected outright by the hostile
    # handle below; AlignedFile must transparently split it into smaller
    # reads, and remember the working size, rather than raising the
    # PermissionError up to the caller. This is what a carve scan's
    # multi-MB block reads need on a device with a small max transfer
    # size.
    data = bytes((i * 61 + 3) % 256 for i in range(4096 * 512))  # 2MB
    max_transfer = 64 * 512  # 32KB cap, like a stingy driver
    hostile = _MaxTransferHostileFile(data, max_transfer)
    af = AlignedFile(hostile)

    af.seek(0)
    big = af.read(len(data))
    check("AlignedFile: büyük okuma sürücü sınırına rağmen tam ve doğru", big == data)
    check(
        "AlignedFile: okumalar sürücünün izin verdiği sınırı aşmadı",
        hostile.biggest_ok_read <= max_transfer,
    )

    # subsequent reads should reuse the discovered safe chunk size rather
    # than re-failing on an oversized attempt every time
    af.seek(0)
    again = af.read(100_000)
    check(
        "AlignedFile: öğrenilen güvenli boyut sonraki okumalarda da korunuyor",
        again == data[:100_000],
    )


class _StrictEndHostileFile:
    """Simulates a raw device whose driver raises PermissionError for any
    read touching at or past its true end, rather than returning a short
    read. Observed on a USB drive where reading at the reported device
    size, or a block overshooting it, both raised PermissionError(13)
    instead of returning fewer bytes.

    Sized so the real length is not a multiple of AlignedFile.ALIGN
    (4096) but is a multiple of 512, as on that device (30784094208
    bytes). That combination is what makes a naive "floor to ALIGN" fix
    wrong.
    """

    SECTOR = 512

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def seek(self, pos, whence=0):
        if whence == 2:
            pos = len(self._data) + pos
        if pos % self.SECTOR != 0:
            raise OSError(22, "seek offset not sector-aligned")
        self._pos = pos
        return self._pos

    def tell(self):
        return self._pos

    def read(self, size=-1):
        if size < 0:
            size = len(self._data) - self._pos
        if size % self.SECTOR != 0:
            raise OSError(22, "read size not sector-aligned")
        if self._pos >= len(self._data) or self._pos + size > len(self._data):
            raise PermissionError(13, "Permission denied")
        chunk = self._data[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk


def test_aligned_file_strict_end_of_device():
    # length is a 512 multiple but deliberately NOT a 4096 multiple, and
    # the hostile handle throws (rather than short-reads) at/past it
    data = bytes((i * 17 + 5) % 256 for i in range(20 * 512))  # 10240 bytes
    assert len(data) % 4096 != 0
    hostile = _StrictEndHostileFile(data)
    af = AlignedFile(hostile)
    af.set_known_size(len(data))

    af.seek(0)
    check(
        "AlignedFile: bilinen boyutla tüm veri sorunsuz okunuyor",
        af.read(len(data)) == data,
    )

    # a read landing in the last (sub-ALIGN) partial block must still
    # come back correctly, not silently truncated to nothing
    af.seek(len(data) - 100)
    check(
        "AlignedFile: son kısmi blok (ALIGN'a tam bölünmeyen) doğru okunuyor",
        af.read(100) == data[-100:],
    )

    # reading past the end must come back empty, never raise
    af.seek(len(data))
    check("AlignedFile: gerçek sonun ötesini okumak hata vermeden bos donuyor", af.read(4096) == b"")

    # a request straddling the true end must be silently truncated to
    # what's actually there, not raise the hostile handle's PermissionError
    af.seek(len(data) - 50)
    check(
        "AlignedFile: sinir asan istek hataya dusmeden kirpiliyor",
        af.read(500) == data[-50:],
    )


def _tool_available(name):
    return shutil.which(name) is not None


def test_fat_undelete():
    if not (_tool_available("mkfs.vfat") and _tool_available("mcopy") and _tool_available("mdel")):
        skip("FAT32 undelete", "mkfs.vfat/mtools bulunamadı")
        return

    with tempfile.TemporaryDirectory() as tmp:
        img = os.path.join(tmp, "fat.img")
        with open(img, "wb") as f:
            f.write(b"\x00" * (32 * 1024 * 1024))
        subprocess.run(["mkfs.vfat", "-F", "32", img], check=True, capture_output=True)

        content = (b"hello world, this is a test file for undelete verification. " * 100)
        src = os.path.join(tmp, "secret.txt")
        with open(src, "wb") as f:
            f.write(content)

        subprocess.run(["mcopy", "-i", img, src, "::secret.txt"], check=True, capture_output=True)
        subprocess.run(["mdel", "-i", img, "::secret.txt"], check=True, capture_output=True)

        with open_source(img) as fh:
            boot = fat.parse_boot_sector(fh)
            check("FAT32 undelete: boot sector ayrıştırıldı", boot is not None)
            if not boot:
                return
            entries = fat.find_deleted_entries(fh, boot)
            check("FAT32 undelete: silinmiş kayıt bulundu", len(entries) == 1)
            if not entries:
                return
            out_path = fat.recover_entry(fh, boot, entries[0], os.path.join(tmp, "out"))
            check("FAT32 undelete: dosya kurtarıldı", out_path is not None)
            if out_path:
                recovered_content = open(out_path, "rb").read()
                check("FAT32 undelete: içerik birebir eşleşiyor", recovered_content == content)


def test_mbr_partition_detection():
    """The user points the tool at a WHOLE disk (\\\\.\\PhysicalDriveN on
    Windows, /dev/sdb on Linux) rather than a single partition. Byte 0 of
    a whole disk is the MBR partition table, not a filesystem boot
    sector, so the tool has to find the embedded partition and read the
    FAT boot sector from there.
    """
    if not (_tool_available("mkfs.vfat") and _tool_available("mcopy") and _tool_available("mdel")):
        skip("MBR bölüm tespiti", "mkfs.vfat/mtools bulunamadı")
        return

    from data_recover.detect import find_filesystem

    with tempfile.TemporaryDirectory() as tmp:
        vol_img = os.path.join(tmp, "vol.img")
        with open(vol_img, "wb") as f:
            f.write(b"\x00" * (16 * 1024 * 1024))
        subprocess.run(["mkfs.vfat", "-F", "32", vol_img], check=True, capture_output=True)

        content = b"mbr partition detection test content. " * 200
        src = os.path.join(tmp, "hidden.txt")
        with open(src, "wb") as f:
            f.write(content)
        subprocess.run(["mcopy", "-i", vol_img, src, "::hidden.txt"], check=True, capture_output=True)
        subprocess.run(["mdel", "-i", vol_img, "::hidden.txt"], check=True, capture_output=True)

        vol_bytes = open(vol_img, "rb").read()
        partition_offset = 1024 * 1024  # 1MiB alignment, like real formatting tools use

        mbr = bytearray(512)
        entry_off = 0x1BE
        mbr[entry_off + 0] = 0x80  # bootable flag (irrelevant to us)
        mbr[entry_off + 4] = 0x0C  # partition type: FAT32 LBA
        lba_start = partition_offset // 512
        num_sectors = len(vol_bytes) // 512
        mbr[entry_off + 8 : entry_off + 12] = lba_start.to_bytes(4, "little")
        mbr[entry_off + 12 : entry_off + 16] = num_sectors.to_bytes(4, "little")
        mbr[510:512] = b"\x55\xAA"

        whole_disk = os.path.join(tmp, "whole_disk.img")
        with open(whole_disk, "wb") as f:
            f.write(bytes(mbr))
            f.write(b"\x00" * (partition_offset - 512))
            f.write(vol_bytes)

        with open_source(whole_disk) as fh:
            view, kind, boot, part_offset = find_filesystem(fh)
            check("MBR bölüm tespiti: bölüm doğru offsette bulundu", part_offset == partition_offset)
            check("MBR bölüm tespiti: FAT olarak tanındı", kind == "fat")
            if kind != "fat":
                return
            entries = fat.find_deleted_entries(view, boot)
            check("MBR bölüm tespiti: silinmiş kayıt bulundu", len(entries) == 1)
            if not entries:
                return
            out_path = fat.recover_entry(view, boot, entries[0], os.path.join(tmp, "out"))
            check("MBR bölüm tespiti: dosya kurtarıldı", out_path is not None)
            if out_path:
                recovered_content = open(out_path, "rb").read()
                check("MBR bölüm tespiti: içerik birebir eşleşiyor", recovered_content == content)


def test_ntfs_undelete():
    if not (_tool_available("mkfs.ntfs") and os.geteuid() == 0):
        skip("NTFS undelete", "mkfs.ntfs yok veya root değil (mount gerekiyor)")
        return

    with tempfile.TemporaryDirectory() as tmp:
        img = os.path.join(tmp, "ntfs.img")
        with open(img, "wb") as f:
            f.write(b"\x00" * (64 * 1024 * 1024))
        subprocess.run(["mkfs.ntfs", "-F", "-Q", img], check=True, capture_output=True)

        mount_point = os.path.join(tmp, "mnt")
        os.makedirs(mount_point)
        content = (b"ntfs undelete test content. " * 200)
        try:
            subprocess.run(["mount", "-o", "loop", img, mount_point], check=True, capture_output=True)
            with open(os.path.join(mount_point, "secret.txt"), "wb") as f:
                f.write(content)
            subprocess.run(["sync"], check=True)
            os.remove(os.path.join(mount_point, "secret.txt"))
        finally:
            subprocess.run(["umount", mount_point], capture_output=True)

        with open_source(img) as fh:
            boot = ntfs.parse_boot_sector(fh)
            check("NTFS undelete: boot sector ayrıştırıldı", boot is not None)
            if not boot:
                return
            entries = ntfs.find_deleted_entries(fh, boot)
            found = [e for e in entries if "secret" in e.name.lower()]
            check("NTFS undelete: silinmiş kayıt bulundu", len(found) == 1)
            if not found:
                return
            out_path = ntfs.recover_entry(fh, boot, found[0], os.path.join(tmp, "out"))
            check("NTFS undelete: dosya kurtarıldı", out_path is not None)
            if out_path:
                recovered_content = open(out_path, "rb").read()
                check("NTFS undelete: içerik birebir eşleşiyor", recovered_content == content)


if __name__ == "__main__":
    test_carving()
    test_aligned_file()
    test_bmp_false_positives_dont_shred_real_files()
    test_mp4_box_walk_survives_coincidental_matches_inside_video()
    test_exe_section_table_survives_coincidental_matches_inside_binary()
    test_riff_wav_avi_disambiguation_and_exact_size()
    test_zip_office_document_detection()
    test_zip_dedupe_does_not_read_far_past_each_archive()
    test_heic_vs_real_mp4_detection()
    test_sqlite_and_7z_exact_declared_size()
    test_orphan_dir_entry_scan_finds_names_missed_by_live_tree()
    test_aligned_file_large_read_retry()
    test_aligned_file_strict_end_of_device()
    test_fat_undelete()
    test_mbr_partition_detection()
    test_ntfs_undelete()

    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} test geçti.")
    if failed:
        print("Başarısız testler:", ", ".join(failed))
        sys.exit(1)
