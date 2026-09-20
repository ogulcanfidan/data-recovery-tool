"""Command-line interface.

Usage examples:
    data-recover list-devices
    data-recover list-volumes
    data-recover undelete /dev/sdb1 -o ./recovered
    data-recover carve /dev/sdb -o ./recovered --formats jpg,png,pdf
    data-recover scan /dev/sdb -o ./recovered
"""

import argparse
import dataclasses
import sys
import time
import traceback

from . import __version__
from .carve import SELF_DESCRIBING_FORMATS, carve_candidates_fh, scan_headers_fh
from .detect import find_filesystem
from .filesystems import fat, ntfs
from .signatures import FORMAT_ALIASES, SIGNATURES
from .utils import estimate_remaining, get_source_size, human_size, is_windows, list_block_devices, iter_mounted_volumes, open_source


def _progress_printer(label: str):
    start = time.time()
    last_print = [0.0]

    def cb(done: int, total: int):
        now = time.time()
        if now - last_print[0] < 0.2 and done < total:
            return
        last_print[0] = now
        pct = (done / total * 100) if total else 0
        elapsed = now - start
        eta = estimate_remaining(done, total, elapsed)
        eta_part = f"  tahmini kalan: {eta}" if eta else "  tahmini kalan: hesaplanıyor..."
        sys.stderr.write(f"\r{label}: {pct:5.1f}%  ({human_size(done)}/{human_size(total)})  {elapsed:.0f}s{eta_part}   ")
        sys.stderr.flush()
        if done >= total:
            sys.stderr.write("\n")

    return cb


def cmd_list_devices(args):
    devices = list_block_devices()
    if not devices:
        print("Hiçbir disk/aygıt bulunamadı (yönetici/root yetkisi gerekebilir).")
        if is_windows():
            print("İpucu: Yönetici olarak çalıştırıp \\\\.\\PhysicalDrive0 gibi bir yol dene.")
        return
    print("Bulunan diskler/aygıtlar:")
    for path, desc in devices:
        print(f"  {path}\t{desc}")
    print(
        "\nNot: Ham diske erişmek genelde yönetici/root yetkisi ister "
        "(Linux/Mac: sudo, Windows: yönetici olarak çalıştır)."
    )


def cmd_list_volumes(args):
    volumes = iter_mounted_volumes()
    if not volumes:
        print("Bağlı bir bölüm/klasör bulunamadı.")
        return
    print("Bağlı bölümler / klasörler (telefon dosya aktarım modu dahil):")
    for path, desc in volumes:
        print(f"  {path}\t{desc}")




def cmd_list_formats(args):
    print("Desteklenen dosya formatları (carving için):")
    aliases_by_name = {}
    for alias, real_name in FORMAT_ALIASES.items():
        aliases_by_name.setdefault(real_name, []).append(alias)
    for sig in SIGNATURES:
        if sig.footers:
            size_note = "footer var"
        elif sig.name in SELF_DESCRIBING_FORMATS:
            size_note = "kendi yapısından gerçek boyutunu okur"
        else:
            size_note = "footer yok (boyut sınırıyla kesilir)"
        alias_note = ""
        aliases = aliases_by_name.get(sig.name)
        if aliases:
            alias_note = f"  (--formats için ayrıca: {', '.join(sorted(aliases))})"
        print(f"  {sig.name:10s} .{sig.ext:6s} {size_note}{alias_note}")


def _absolute_fat_boot(fh):
    """Tries to find a FAT filesystem anywhere on `fh` (partitioned or
    not) purely to get a BootSector usable for orphan directory-entry
    scanning during carve. Cheap: only the boot sector and partition
    table, not a full scan. Returns None if none is found or it isn't
    FAT (NTFS orphan scanning isn't implemented). The returned
    BootSector's offsets are shifted to be absolute on `fh` itself, since
    carve always scans the whole raw source from offset 0, not just the
    partition find_filesystem() may have windowed into.
    """
    try:
        _view, kind, boot, part_offset = find_filesystem(fh)
    except Exception:
        return None
    if kind != "fat" or boot is None:
        return None
    if not part_offset:
        return boot
    return dataclasses.replace(
        boot,
        fat_start=boot.fat_start + part_offset,
        cluster_heap_start=boot.cluster_heap_start + part_offset,
    )


def _do_carve(fh, total_size, args, boot_sector=None, seen_dir_offsets=None):
    formats = args.formats.split(",") if args.formats else None
    if boot_sector is None:
        boot_sector = _absolute_fat_boot(fh)
        if boot_sector:
            print("(FAT dosya sistemi izi bulundu, öksüz dizin girdisi taraması da aynı geçişte yapılacak.)")

    orphan_entries = [] if boot_sector else None
    print(f"[1/2] Kaynak taranıyor: {args.source}")
    candidates = scan_headers_fh(
        fh,
        total_size,
        formats=formats,
        progress_cb=_progress_printer("Tarama"),
        boot_sector=boot_sector,
        orphan_sink=orphan_entries,
    )
    print(f"{len(candidates)} olası dosya bulundu.")

    if orphan_entries:
        seen = seen_dir_offsets or set()
        new_entries = [e for e in orphan_entries if e.dir_offset not in seen]
        print(
            f"{len(orphan_entries)} öksüz dizin girdisi bulundu "
            f"({len(new_entries)} tanesi undelete aşamasında zaten bulunmamıştı), "
            "orijinal isimleriyle kurtarılıyor..."
        )
        named_recovered = 0
        for e in new_entries:
            path = fat.recover_entry(fh, boot_sector, e, args.output)
            if path:
                named_recovered += 1
        print(f"Orijinal isimle kurtarılan: {named_recovered}/{len(new_entries)}")

    if not candidates:
        return
    print(f"[2/2] Dosyalar çıkarılıyor -> {args.output}")
    recovered = carve_candidates_fh(fh, total_size, candidates, args.output, progress_cb=_progress_printer("Kurtarma"))
    _print_carve_summary(recovered)


def cmd_carve(args):
    with open_source(args.source) as fh:
        total_size = get_source_size(args.source, fh)
        _do_carve(fh, total_size, args)


def _print_carve_summary(recovered):
    print(f"\nToplam kurtarılan dosya: {len(recovered)}")
    by_format = {}
    for r in recovered:
        by_format.setdefault(r.format, [0, 0])
        by_format[r.format][0] += 1
        by_format[r.format][1] += r.size
    for fmt, (count, total_size) in sorted(by_format.items()):
        print(f"  {fmt:10s} {count:5d} dosya, toplam {human_size(total_size)}")
    truncated = sum(1 for r in recovered if r.truncated)
    if truncated:
        print(
            f"\nNot: {truncated} dosya net bir bitiş imzası bulunamadığı için boyut sınırıyla "
            "kesildi; bunlar bozuk/eksik olabilir, açarken kontrol et."
        )


def _do_undelete(fh, args):
    """Returns (kind, absolute_fat_boot, seen_dir_offsets) so cmd_scan
    can hand FAT geometry and a de-dupe set to _do_carve's orphan-entry
    scan afterwards. absolute_fat_boot is None for anything but FAT
    (NTFS orphan scanning isn't implemented), and seen_dir_offsets is
    always in *raw-disk-absolute* coordinates (shifted by part_offset
    when the filesystem lives inside a partition), matching what the
    orphan scan (which always runs against the raw source) will see.
    """
    view, kind, boot, part_offset = find_filesystem(fh)

    if part_offset is not None:
        print(f"Bölüm tablosu üzerinden bölüm bulundu (offset {part_offset}), oradan devam ediliyor.")
    shift = part_offset or 0

    if kind == "ntfs":
        print("NTFS bölümü tespit edildi, MFT taranıyor...")
        entries = ntfs.find_deleted_entries(view, boot)
        print(f"{len(entries)} silinmiş dosya kaydı bulundu.")
        recovered = 0
        for e in entries:
            path = ntfs.recover_entry(view, boot, e, args.output)
            if path:
                recovered += 1
                if args.verbose:
                    print(f"  kurtarıldı: {path} ({human_size(e.size)})")
        print(f"\nToplam kurtarılan: {recovered}/{len(entries)}")
        return kind, None, set()

    if kind == "fat":
        print(f"{boot.fat_type} bölümü tespit edildi, dizin tablosu taranıyor...")
        entries = fat.find_deleted_entries(view, boot)
        print(f"{len(entries)} silinmiş dosya kaydı bulundu.")
        recovered = 0
        for e in entries:
            path = fat.recover_entry(view, boot, e, args.output)
            if path:
                recovered += 1
                if args.verbose:
                    print(f"  kurtarıldı: {path} ({human_size(e.size)})")
        print(f"\nToplam kurtarılan: {recovered}/{len(entries)}")
        print(
            "\nNot: FAT dosya sisteminde parçalanmamış (bitişik) dosyalar varsayımıyla "
            "kurtarıldı; parçalanmış büyük dosyalarda bozulma olabilir."
        )
        absolute_boot = boot if not shift else dataclasses.replace(
            boot,
            fat_start=boot.fat_start + shift,
            cluster_heap_start=boot.cluster_heap_start + shift,
        )
        seen = {e.dir_offset + shift for e in entries}
        return kind, absolute_boot, seen

    print(
        "Tanınan bir FAT/NTFS dosya sistemi bulunamadı (format atılmış, exFAT, ya da "
        "bozuk olabilir; bölüm tablosu da taranmış ama uyan bir bölüm çıkmadı). Bunun "
        "yerine 'carve' komutunu dene: dosya sistemi olmadan ham baytlardan dosya "
        "imzalarıyla kurtarma yapar."
    )
    return kind, None, set()


def cmd_undelete(args):
    with open_source(args.source) as fh:
        _do_undelete(fh, args)


def cmd_scan(args):
    with open_source(args.source) as fh:
        total_size = get_source_size(args.source, fh)
        print("=== Aşama 1: Dosya sistemi seviyesinde silinmiş dosya taraması ===")
        kind, absolute_boot, seen_dir_offsets = _do_undelete(fh, args)
        print("\n=== Aşama 2: İmza tabanlı (carving) tarama ===")
        if absolute_boot is not None:
            print(
                "(Aşama 1'de bulunan FAT dosya sistemi, öksüz (canlı dizin ağacından "
                "erişilemeyen ama hâlâ diskte duran) dizin girdilerini de aynı geçişte "
                "aramak için kullanılacak.)"
            )
        _do_carve(fh, total_size, args, boot_sector=absolute_boot, seen_dir_offsets=seen_dir_offsets)


def build_parser():
    p = argparse.ArgumentParser(
        prog="data-recover",
        description="Disk, USB, hafıza kartı ve (mount edilmiş) telefon depolamasından silinmiş/format atılmış dosyaları kurtarma aracı.",
    )
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("list-devices", help="Ham disk/aygıtları listele")
    sp.set_defaults(func=cmd_list_devices)

    sp = sub.add_parser("list-volumes", help="Bağlı bölümleri/klasörleri listele (telefon dahil)")
    sp.set_defaults(func=cmd_list_volumes)

    sp = sub.add_parser("list-formats", help="Desteklenen dosya formatlarını listele")
    sp.set_defaults(func=cmd_list_formats)

    sp = sub.add_parser("carve", help="İmza tabanlı kurtarma (dosya sistemi olmadan da çalışır)")
    sp.add_argument("source", help="Disk/aygıt yolu (örn. /dev/sdb) ya da bir disk imaj dosyası")
    sp.add_argument("-o", "--output", required=True, help="Kurtarılan dosyaların yazılacağı klasör")
    sp.add_argument("--formats", help="Virgülle ayrılmış format listesi (örn. jpg,png,pdf). Boş = hepsi")
    sp.set_defaults(func=cmd_carve)

    sp = sub.add_parser("undelete", help="Dosya sistemi seviyesinde (FAT/NTFS) silinmiş dosya kurtarma")
    sp.add_argument("source", help="Bölüm/aygıt yolu (örn. /dev/sdb1) ya da bir imaj dosyası")
    sp.add_argument("-o", "--output", required=True, help="Kurtarılan dosyaların yazılacağı klasör")
    sp.add_argument("-v", "--verbose", action="store_true")
    sp.set_defaults(func=cmd_undelete)

    sp = sub.add_parser("scan", help="Hem undelete hem carve birlikte (önerilen, en kapsamlı)")
    sp.add_argument("source", help="Disk/bölüm/aygıt yolu ya da bir imaj dosyası")
    sp.add_argument("-o", "--output", required=True, help="Kurtarılan dosyaların yazılacağı klasör")
    sp.add_argument("--formats", help="carve aşaması için virgülle ayrılmış format listesi")
    sp.add_argument("-v", "--verbose", action="store_true")
    sp.set_defaults(func=cmd_scan)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except PermissionError as e:
        print("\n--- tanı için tam hata izi (traceback) ---", file=sys.stderr)
        traceback.print_exc()
        print("--- traceback sonu ---\n", file=sys.stderr)
        print(
            f"\nYetki hatası (ham hata: {e!r}): ham disk erişimi için yönetici/root yetkisi "
            "gerekiyor.\nLinux/Mac: 'sudo data-recover ...' ile çalıştır.\n"
            "Windows: terminali yönetici olarak aç.\n"
            "Eğer zaten yöneticiysen ve hata devam ediyorsa, bu antivirüs/güvenlik "
            "yazılımının ham disk taramasını engellemesinden kaynaklanıyor olabilir "
            "-- yukarıdaki 'ham hata' satırını yazan kişiye ilet.",
            file=sys.stderr,
        )
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"\nKaynak bulunamadı: {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print("\n--- tanı için tam hata izi (traceback) ---", file=sys.stderr)
        traceback.print_exc()
        print("--- traceback sonu ---\n", file=sys.stderr)
        print(f"\nBeklenmeyen sistem hatası: {e!r}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nİptal edildi.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
