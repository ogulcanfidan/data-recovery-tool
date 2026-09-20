# Taşınabilir .exe üretme

Aracı bir USB belleğe atıp, Python kurulu olmayan herhangi bir Windows
bilgisayarda çift tıklayıp çalıştırmak için tek dosyalık `.exe`
üretebilirsin. Bunu bir kere kendi bilgisayarında inşa etmen yeterli;
sonra exe'yi istediğin yere kopyalayabilirsin, hedef bilgisayarda
Python'a gerek kalmaz.

## 1) PyInstaller'ı kur

Sadece inşa ederken gerekiyor, çalıştırırken değil.

```powershell
pip install pyinstaller
```

## 2) Proje klasörünün içindeyken iki exe'yi inşa et

```powershell
pyinstaller --onefile --uac-admin --name data-recovery build_cli.py
pyinstaller --onefile --uac-admin --windowed --name data-recovery-gui --icon "data_recovery/assets/app_icon.ico" --add-data "data_recovery/assets;data_recovery/assets" build_gui.py
```

Bayrakların ne yaptığı:

- `--add-data`, pencerenin içinde kullanılan FMJ Software logosunu
  (Hakkında penceresi ve üst başlık) exe'nin içine gömüyor.
- `--icon` bundan ayrı bir şey: exe dosyasının kendi simgesini belirliyor
  (görev çubuğunda, masaüstünde, Gezgin'de görünen). Bunun için marka
  logosu değil, uygulamaya özel `app_icon.ico` kullanılıyor.
- `--uac-admin`, exe'ye çift tıklandığında Windows'un "Yönetici izni ver
  mi?" (UAC) penceresini otomatik göstermesini sağlıyor. Ham disk
  taraması yönetici yetkisi istediği için bu, her seferinde elle
  "yönetici olarak çalıştır" demekten kurtarır.

CLI'da görsel kullanılmadığı için ona ikisi de gerekmiyor.

## 3) Ortaya çıkan dosyalar

```
dist\data-recovery.exe
dist\data-recovery-gui.exe
```

Bu ikisini USB belleğine kopyala. Artık hangi Windows bilgisayara taksan,
Python kurulu olmasa bile GUI için çift tıklayarak, CLI için terminalden
`data-recovery.exe scan ... -o ...` diyerek çalıştırabilirsin.

## Notlar

- İlk açılış birkaç saniye sürebilir. `--onefile` her çalıştırmada
  kendini geçici bir klasöre açıyor; normal, arıza değil.
- Windows Defender/SmartScreen imzasız bir exe gördüğünde "tanınmayan
  uygulama" uyarısı verebilir. "Daha fazla bilgi" → "Yine de çalıştır"
  ile geçebilirsin.
- İkonu değiştirdikten sonra Windows'un ikon önbelleği eski görüntüyü
  tutabilir. Yeni bir isimle kopyalayıp öyle bakmak, ya da
  `ie4uinit.exe -ClearIconCache` çalıştırıp Gezgin'i yeniden başlatmak
  genelde yeterli oluyor.
- Bu adımlar Windows'a özel. Mac/Linux'ta aynı mantıkla
  (`pyinstaller --onefile build_cli.py`) kendi platformunun dosyasını o
  platformda inşa edebilirsin. PyInstaller çapraz derleme yapmaz;
  ürettiği dosya sadece inşa edildiği işletim sisteminde çalışır.
