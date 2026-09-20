# Data Recovery

Silinmiş ya da format atılmış dosyaları geri getirmeye çalışan bir araç.
Disk, USB bellek, hafıza kartı ve disk imajlarıyla çalışır; terminalden
ya da basit bir pencere arayüzünden kullanılır.

Sadece Python standart kütüphanesini kullanır, ek paket gerekmez.
Windows, macOS ve Linux'ta çalışır.

## Kurulum

```bash
git clone https://github.com/ogulcanfidan/data-recovery-tool.git
cd data-recovery-tool
pip install -e .
```

Kurmadan da çalıştırabilirsin: `python3 -m data_recovery.cli --help`

## Kullanım

Önce hedefi bul:

```bash
data-recovery list-devices     # ham diskler (yönetici/root ister)
data-recovery list-volumes     # bağlı bölümler ve klasörler
```

Sonra tara. `scan` en kapsamlı seçenek, iki yöntemi birden dener:

```bash
# Linux/Mac (root gerekir)
sudo data-recovery scan /dev/sdb1 -o ./kurtarilanlar

# Windows (yönetici terminalde)
data-recovery scan \\.\PhysicalDrive1 -o C:\kurtarilanlar
```

Tek bir yöntemi istersen `undelete` (hızlı, dosya adlarını korur) veya
`carve` (format atılmış diskler için) komutlarını kullan. `carve`'e
`--formats jpg,png,mp4` vererek aramayı daraltabilirsin.

Disk imajları (`.img`, `.dd`) da kaynak olarak verilebilir.

### Pencere arayüzü

```bash
data-recovery-gui
```

Kaynağı ve çıktı klasörünü seç, tarama tipini seç, başlat. Arayüz 8 dili
destekler (sağ üstteki "Dil" menüsü). Linux'ta Tkinter ayrıca kurulmalı
olabilir: `sudo apt install python3-tk`

## Nasıl çalışır

İki yöntem var, `scan` ikisini birden dener:

**`undelete`** — dosya sistemi seviyesinde. Disk hâlâ okunabilir bir
FAT32/FAT16 ya da NTFS bölümüyse, silinen dosyanın adı ve konumu
genelde dosya sistemi tablosunda durur; sadece "silindi" işareti
konmuştur. Hızlıdır ve **dosya adlarını geri verir**. NTFS'te küme
haritası korunduğu için parçalanmış dosyalar da kurtarılabilir; FAT'ta
dosyanın bitişik olduğu varsayılır.

**`carve`** — imza tabanlı. Dosya sistemi tamamen gitmişse (format,
bozuk bölüm tablosu) ham baytları tarayıp bilinen dosya imzalarını arar
(JPEG'in `FFD8FF...FFD9`'u gibi). Dosya adları gelmez, ama içerik
genelde gelir.

## Desteklenen formatlar

JPEG, PNG, GIF, BMP, TIFF, PDF, ZIP (DOCX/XLSX/PPTX otomatik tanınır),
RAR, 7Z, WAV/AVI, MP3, MKV, MP4/MOV (HEIC/HEIF/AVIF dahil), SQLite,
DOC, HTML, EXE/DLL.

Tam liste: `data-recovery list-formats`

## Bilinmesi gerekenler

- **Kurtarılanları başka bir diske kaydet.** `-o` ile verdiğin klasör
  kaynak diskte olmamalı, yoksa kurtarmaya çalıştığın verinin üstüne
  yazabilirsin.
- **Üzerine yazılmış veri geri gelmez.** Bu araç "silindi" işareti
  konmuş ama henüz üzerine yazılmamış veriyi kurtarır. Çoğu
  "yanlışlıkla sildim" / "format attım" durumu budur.
- **Hızlı davran.** Silme sonrası diske yeni bir şey yazmamak kurtarma
  şansını ciddi artırır.
- **Telefonlar:** MTP ("dosya aktarımı") modunda silinmiş veriye
  erişilemez. SD kartı okuyucuya takmak en garantili yol; ayrıntılar
  için [docs/telefonlar.md](docs/telefonlar.md).

## Test

```bash
python3 tests/run_tests.py
```

## Ayrıntılar

- [Taşınabilir .exe üretme](docs/tasinabilir-exe.md) — Python kurulu
  olmayan Windows bilgisayarlarda çalıştırmak için
- [Telefonlardan kurtarma](docs/telefonlar.md) — Android, iPhone, SD kart
