# Data Recovery

Terminalden çalışan, dış bağımlılığı olmayan (sadece Python), diskten /
USB'den / hafıza kartından / (mount edilmiş) telefon depolamasından
silinmiş ya da format atılmış dosyaları kurtarmaya çalışan bir araç.

Windows, macOS ve Linux'ta çalışır. Sadece Python standart kütüphanesini
kullanır, kurulum için internetten paket indirmeye gerek yoktur.

## Kurulum

```bash
git clone https://github.com/ogulcanfidan/data-recovery-tool.git
cd data-recovery-tool
pip install -e .
```

Kurulum sonrası `data-recovery` komutu terminalde kullanılabilir hale
gelir. Kurmadan da doğrudan çalıştırabilirsin:

```bash
python3 -m data_recovery.cli --help
```

## Grafik arayüz (GUI)

Terminale girmeden, pencereden tıklayarak kullanmak istersen basit bir
grafik arayüz de var — çekirdek motor terminal aracıyla birebir aynı,
sadece üstüne bir pencere eklendi:

```bash
python3 -m data_recovery.gui
# ya da kurulumdan sonra:
data-recovery-gui
```

Kaynağı (disk/aygıt yolu ya da imaj dosyası) ve çıktı klasörünü seç,
istersen hangi dosya formatlarının aranacağını işaretle, sonra
"Taramayı Başlat" (önerilen — hem dosya sistemi hem imza taraması
birden), ya da sadece birini yapan butonlardan birine bas. Tarama arka
planda çalışır, ilerleme çubuğu ve günlük penceresi canlı güncellenir,
istersen "İptal" ile durdurabilirsin.

Sağ üstteki "Dil" menüsünden arayüz dilini değiştirebilirsin (Türkçe,
İngilizce, İspanyolca, Fransızca, Almanca, Rusça, Arapça, Çince) —
seçim anında uygulanır, programı yeniden başlatmaya gerek yok, ve bir
sonraki açılışta hatırlanır. Çeviriler profesyonel bir çevirmen
kontrolünden geçmedi; anlaşılır ama kusursuz olmayabilir. CLI
(terminal aracı) şimdilik yalnızca Türkçe.

Tkinter (bu arayüzün dayandığı kütüphane) Windows ve Mac'te Python'la
birlikte zaten gelir. Linux'ta bazı dağıtımlarda ayrıca kurman
gerekebilir:

```bash
sudo apt install python3-tk        # Debian/Ubuntu
sudo dnf install python3-tkinter   # Fedora
```

## Taşınabilir sürüm (tek .exe, USB'de taşımak için)

Aracı bir USB belleğe atıp, Python kurulu olmayan **herhangi bir**
Windows bilgisayarda çift tıklayıp çalıştırmak istiyorsan, tek dosyalık
bir `.exe` üretebilirsin. Bunu bir kere, kendi bilgisayarında (Python
zaten kurulu olduğu için) inşa etmen yeterli — sonra o `.exe` dosyasını
istediğin yere kopyalayabilirsin, hedef bilgisayarda Python/pip'e hiç
gerek kalmaz.

**1) PyInstaller'ı kur (sadece inşa ederken gerekiyor, çalıştırırken değil):**
```powershell
pip install pyinstaller
```

**2) Proje klasörünün içindeyken iki exe'yi inşa et:**
```powershell
pyinstaller --onefile --uac-admin --name data-recovery build_cli.py
pyinstaller --onefile --uac-admin --windowed --name data-recovery-gui --icon "data_recovery/assets/app_icon.ico" --add-data "data_recovery/assets;data_recovery/assets" build_gui.py
```
GUI'nin `--add-data` bayrağı pencerenin içindeki FMJ Software logosunu (marka görseli, Hakkında penceresinde ve üst başlıkta kullanılıyor) exe'nin içine gömüyor. `--icon` bayrağı ise ayrı bir şey: exe dosyasının kendi simgesini (görev çubuğunda/masaüstünde/Gezgin'de görünen) belirliyor; bunun için marka logosu değil, uygulamaya özel `app_icon.ico` kullanılıyor. CLI'da görsel kullanılmadığı için ikisine de gerek yok.

İkon değişikliği sonrası Windows'un ikon önbelleği eski görüntüyü tutabilir; yeni bir isimle kopyalayıp öyle bakmak (ya da `ie4uinit.exe -ClearIconCache` çalıştırıp Gezgin'i yeniden başlatmak) genelde yeterli oluyor.
`--uac-admin`, exe'yi çift tıkladığında Windows'un otomatik olarak
"Yönetici izni ver mi?" (UAC) penceresi göndermesini sağlıyor — ham
disk taraması yönetici yetkisi istediği için bu, her seferinde elle
"yönetici olarak çalıştır" demekten kurtarır.

**3) Ortaya çıkan dosyalar:**
```
dist\data-recovery.exe
dist\data-recovery-gui.exe
```
Bu ikisini USB belleğine kopyala. Artık hangi Windows bilgisayara
taksan, Python kurulu olmasa bile çift tıklayarak (GUI için) ya da
terminalden `data-recovery.exe scan ... -o ...` diyerek (CLI için)
direkt çalıştırabilirsin.

**Notlar:**
- İlk açılış birkaç saniye sürebilir (`--onefile` her çalıştırmada
  kendini geçici bir klasöre açıyor) — normal, arıza değil.
- Windows Defender/SmartScreen, imzasız (kendi ürettiğin) bir exe
  gördüğünde "tanınmayan uygulama" uyarısı verebilir. "Daha fazla
  bilgi" → "Yine de çalıştır" diyerek geçebilirsin, kendi ürettiğin
  zararsız bir dosya olduğu için sorun değil.
- Sadece Windows için geçerli bu adımlar. Mac/Linux'ta aynı mantıkla
  (`pyinstaller --onefile build_cli.py` vb.) kendi platformunun exe'sini
  o platformda inşa edebilirsin — PyInstaller'la üretilen dosya sadece
  inşa edildiği işletim sisteminde çalışır, çapraz derleme yapmaz.

## Nasıl çalışır

İki farklı kurtarma yöntemi kullanır, ve `scan` komutu ikisini birden
otomatik dener:

1. **`undelete` — dosya sistemi seviyesinde kurtarma.** Disk hâlâ
   okunabilir bir FAT32/FAT16 ya da NTFS bölümüyse, silinen dosyaların
   ismi/boyutu/konumu genelde dosya sistemi tablosunda (FAT dizin girişi
   ya da NTFS'te MFT kaydı) hâlâ durur, sadece "silindi" işareti
   konmuştur. Bu yöntem hızlıdır ve dosya adını da geri verir.
   - NTFS'te dosyanın gerçek küme (cluster) haritası MFT kaydında
     saklı kaldığı için **parçalanmış dosyalar bile** kurtarılabilir.
   - FAT'ta silme sırasında zincir bilgisi silindiği için, dosyanın
     **bitişik (parçalanmamış) kümelerde** olduğu varsayılır. Bu, tek
     seferde yazılmış fotoğraf/video gibi dosyalarda genelde doğru
     çıkar; parçalanmış büyük dosyalarda bozulma olabilir.

2. **`carve` — imza tabanlı kurtarma.** Dosya sistemi tamamen gitmişse
   (format atılmış, bölüm tablosu bozulmuş, disk sadece ham veri olarak
   elde ediliyorsa) bu yöntem dosya sistemine hiç bakmadan, diskin ham
   baytlarını baştan sona tarayıp her dosya tipinin bilinen başlangıç
   (ve varsa bitiş) imzasını arar — JPEG'in `FFD8FF...FFD9`'u, PDF'in
   `%PDF-...%%EOF`'u gibi. Bulduğu her eşleşmeyi ayrı bir dosya olarak
   çıkarır. Dosya adı bilgisi olmaz (isimler dosya sistemiyle birlikte
   gider), ama içerik genelde geri gelir.

Desteklenen formatlar: JPEG, PNG, GIF, BMP, TIFF, PDF, ZIP (DOCX/XLSX/
PPTX içeriğini otomatik tanıyıp doğru uzantıyla kaydeder, gerçek ZIP/
APK/JAR ise .zip kalır), RAR, 7Z, RIFF (WAV/AVI, RIFF'in kendi form
alanına bakarak otomatik ayırt edilir), MP3, MKV, MP4/MOV (HEIC/HEIF/
AVIF iPhone fotoğrafları da aynı kutu yapısını kullandığı için ayrı
tanınır), SQLite (telefon uygulama veritabanları için faydalı), eski
OLE tabanlı DOC, HTML, EXE/DLL. BMP, MP4, EXE, RIFF, SQLite ve 7Z gibi
"footer'ı olmayan" formatlar artık komşu bir dosyanın tesadüfi
eşleşmesine değil, kendi iç yapılarından okunan gerçek boyuta göre
kesiliyor. Tam liste:

```bash
data-recovery list-formats
```

## Kullanım

**Önce hedefi bul:**

```bash
data-recovery list-devices     # ham diskleri listeler (yönetici/root ister)
data-recovery list-volumes     # bağlı bölümleri/klasörleri listeler
```

**En kapsamlı tarama (önerilen — hem undelete hem carve):**

```bash
# Linux/Mac (root gerekir)
sudo data-recovery scan /dev/sdb1 -o ./kurtarilanlar

# Windows (yönetici terminalde)
data-recovery scan \\.\PhysicalDrive1 -o C:\kurtarilanlar
```

**Sadece dosya sistemi seviyesinde (hızlı, isimler korunur):**

```bash
sudo data-recovery undelete /dev/sdb1 -o ./kurtarilanlar
```

**Sadece imza tabanlı (format atılmış diskler için):**

```bash
sudo data-recovery carve /dev/sdb -o ./kurtarilanlar --formats jpg,png,mp4
```

`--formats` verilmezse tüm desteklenen formatlar aranır.

Bir disk imajı (`.img`, `.dd`, `dd` ile alınmış ham kopya) üzerinde de
aynen çalışır — `source` olarak imaj dosyasının yolunu ver.

## Önemli sınırlamalar (gerçekçi olalım)

- **Gerçekten üzerine yazılarak silinmiş (secure wipe / "dip
  temizleme") veri geri getirilemez.** Bu bir yazılım kısıtlaması değil,
  fizik: veri fiziksel olarak başka verilerle üzerine yazılmışsa hiçbir
  araç onu okuyamaz. Bu araç sadece "silindi" işareti konmuş ama henüz
  üzerine yazılmamış veriyi kurtarır — çoğu "yanlışlıkla sildim" veya
  "format attım" durumu tam olarak budur.
- **Ne kadar hızlı davranırsan o kadar iyi.** Silme/format sonrası
  diske yeni bir şey yazmadan (yeni dosya kaydetmeden, hatta işletim
  sistemini o diskte fazla kullanmadan) taramak kurtarma şansını ciddi
  artırır.
- **Telefonlar:** Android bir telefon "dosya aktarımı" (MTP) modunda
  bağlandığında işletim sistemi onu ham bir disk gibi değil, sınırlı bir
  dosya listesi olarak gösterir — bu modda telefonun **silinmiş**
  verilerine bu araç erişemez (MTP protokolü buna izin vermez). Gerçek
  ham erişim için:
  - **SD kart varsa** en garantili yol: kartı çıkarıp bir kart okuyucuyla
    bilgisayara takmak. O zaman normal bir USB disk gibi taranır.
  - **Root'lu Android'de**, `adb` ile depolama bölümünün ham bir
    kopyasını (imaj) alıp o imaj üzerinde çalışmak mümkün:
    ```bash
    adb shell "su -c 'dd if=/dev/block/bootdevice/by-name/userdata of=/sdcard/userdata.img'"
    adb pull /sdcard/userdata.img
    data-recovery scan userdata.img -o ./kurtarilanlar
    ```
  - **Root'suz Android veya iPhone'da** işletim sistemi ham disk
    erişimini kapattığı için (özellikle iPhone'da Apple hiç izin
    vermez), bu araçla silinmiş veri kurtarma pratikte mümkün değil.
    Bu durumda tek gerçekçi yol telefonun kendi yedeğinden (Google
    Drive/iCloud/iTunes yedeği) geri yüklemektir.
- **FAT'ta parçalanmış büyük dosyalar** (özellikle önce küçük
  parçalar halinde yazılıp diskte boşluk azken büyütülmüş dosyalar)
  bitişiklik varsayımı yüzünden bozuk çıkabilir.
- Kurtarılan dosyaları **kaynak diskten farklı bir diske** kaydet
  (`-o` ile verdiğin klasör kaynak diskte olmasın) — aksi halde
  kurtarmaya çalıştığın veriyi kendi üstüne yazabilirsin.

## Test

`tests/` klasöründe, sahte bir disk imajı üzerinde dosya
silip kurtarma akışını doğrulayan bir betik var:

```bash
python3 tests/run_tests.py
```
