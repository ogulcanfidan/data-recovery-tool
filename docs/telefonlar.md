# Telefonlardan kurtarma

Bir Android telefon "dosya aktarımı" (MTP) modunda bağlandığında,
işletim sistemi onu ham bir disk gibi değil, sınırlı bir dosya listesi
olarak gösterir. Bu modda telefonun **silinmiş** verilerine bu araç
erişemez; MTP protokolü buna izin vermiyor.

Gerçek ham erişim için üç durum var.

## SD kart varsa

En garantili yol. Kartı telefondan çıkarıp bir kart okuyucuyla
bilgisayara tak; o zaman normal bir USB disk gibi taranır.

```bash
sudo data-recovery scan /dev/sdb1 -o ./kurtarilanlar
```

## Root'lu Android

`adb` ile depolama bölümünün ham bir kopyasını (imaj) alıp o imaj
üzerinde çalışabilirsin.

```bash
adb shell "su -c 'dd if=/dev/block/bootdevice/by-name/userdata of=/sdcard/userdata.img'"
adb pull /sdcard/userdata.img
data-recovery scan userdata.img -o ./kurtarilanlar
```

İmajın sığabilmesi için `/sdcard` üzerinde yeterli boş alan olması
gerekir. Alan yetmiyorsa imajı doğrudan bilgisayara aktarmak da mümkün
ama yöntem cihaza göre değişir.

## Root'suz Android veya iPhone

Pratikte mümkün değil. İşletim sistemi ham disk erişimini kapatıyor;
iPhone'da Apple bunu hiç vermiyor. Bu durumda tek gerçekçi yol
telefonun kendi yedeğinden (Google Drive, iCloud, iTunes) geri
yüklemektir.

## Not

Telefon uygulamalarının verileri genelde SQLite veritabanlarında tutulur.
`carve` SQLite'ı destekliyor, yani mesaj/kayıt veritabanları bir imajdan
çıkarılabilir.
