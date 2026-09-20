# Data Recovery

Silinmiş ya da format atılmış dosyaları geri getirmeye çalışan bir araç.
Disk, USB bellek, hafıza kartı ve disk imajlarıyla çalışır; terminalden ya da
basit bir pencere arayüzünden kullanılır.

Sadece Python standart kütüphanesini kullanır, ek paket gerekmez.
Windows, macOS ve Linux'ta çalışır.

## Kurulum

```bash
git clone https://github.com/ogulcanfidan/data-recovery-tool.git
cd data-recovery-tool
pip install -e .
```

Kurmadan: `python3 -m data_recovery.cli --help`

## Kullanım

Önce hedefi bul:

```bash
data-recovery list-devices     # ham diskler (yönetici/root ister)
data-recovery list-volumes     # bağlı bölümler ve klasörler
```

Sonra tara:

```bash
sudo data-recovery scan /dev/sdb1 -o ./kurtarilanlar          # Linux/Mac
data-recovery scan \\.\PhysicalDrive1 -o C:\kurtarilanlar     # Windows
```

`scan` iki yöntemi birden dener. Tek tek de kullanılabilir:

- **`undelete`** — dosya sistemi hâlâ okunabiliyorsa (FAT32/FAT16/NTFS).
  Hızlıdır ve **dosya adlarını geri verir**.
- **`carve`** — dosya sistemi tamamen gittiyse (format, bozuk bölüm tablosu).
  Ham baytlarda dosya imzası arar; adlar gelmez, içerik genelde gelir.
  `--formats jpg,png,mp4` ile daraltılabilir.

Disk imajları (`.img`, `.dd`) da kaynak olarak verilebilir.

Pencere arayüzü: `data-recovery-gui` (8 dil destekler). Linux'ta Tkinter
ayrıca kurulmalı olabilir: `sudo apt install python3-tk`

## Desteklenen formatlar

JPEG, PNG, GIF, BMP, TIFF, PDF, ZIP (DOCX/XLSX/PPTX), RAR, 7Z, WAV/AVI, MP3,
MKV, MP4/MOV (HEIC/HEIF/AVIF), SQLite, DOC, HTML, EXE/DLL.

Tam liste: `data-recovery list-formats`

## Bilinmesi gerekenler

- **Kurtarılanları başka bir diske kaydet.** `-o` klasörü kaynak diskte
  olmamalı, yoksa kurtarmaya çalıştığın verinin üstüne yazabilirsin.
- **Üzerine yazılmış veri geri gelmez.** Araç, "silindi" işareti konmuş ama
  henüz üzerine yazılmamış veriyi kurtarır.
- **Hızlı davran.** Silme sonrası diske yeni bir şey yazmamak kurtarma
  şansını ciddi artırır.
- **Telefonlar:** MTP modunda silinmiş veriye erişilemez; SD kartı okuyucuya
  takmak en garantili yol.

## Test

```bash
python3 tests/run_tests.py
```

## Ayrıntılar

- [Taşınabilir .exe üretme](docs/tasinabilir-exe.md)
- [Telefonlardan kurtarma](docs/telefonlar.md)
