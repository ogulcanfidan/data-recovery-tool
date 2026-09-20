"""Minimal i18n layer for the GUI.

Turkish is the source language everything else was written against. The
7 additional languages are roughly the most widely used worldwide:
English, Spanish, French, German, Russian, Arabic and Chinese
(Simplified). None have been checked by a native speaker, so treat them
as a first draft rather than a professional localization.

The selected language is persisted to a small JSON file beside the user's
profile, deliberately not inside the install folder so it survives a
rebuild, and re-read on the next launch. Only the GUI is translated; the
CLI stays Turkish-only.
"""

import json
import os
from typing import Dict

LANGUAGES: Dict[str, str] = {
    "tr": "Türkçe",
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "ru": "Русский",
    "ar": "العربية",
    "zh": "中文",
}

RTL_LANGUAGES = {"ar"}

_DEFAULT_LANG = "tr"

# key -> {lang: text}. Only "tr" is required per key; anything else
# missing falls back to Turkish, then to the raw key itself.
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # ---- About dialog ----
    "about_title": {
        "tr": "Hakkında", "en": "About", "es": "Acerca de", "fr": "À propos",
        "de": "Über", "ru": "О программе", "ar": "حول", "zh": "关于",
    },
    "about_app_name": {
        "tr": "Data Recovery", "en": "Data Recovery", "es": "Data Recovery", "fr": "Data Recovery",
        "de": "Data Recovery", "ru": "Data Recovery", "ar": "Data Recovery", "zh": "Data Recovery",
    },
    "about_subtitle": {
        "tr": "Silinmiş / format atılmış dosya kurtarma · sürüm {version}",
        "en": "Deleted / formatted file recovery · version {version}",
        "es": "Recuperación de archivos borrados / formateados · versión {version}",
        "fr": "Récupération de fichiers supprimés / formatés · version {version}",
        "de": "Wiederherstellung gelöschter / formatierter Dateien · Version {version}",
        "ru": "Восстановление удалённых / отформатированных файлов · версия {version}",
        "ar": "استعادة الملفات المحذوفة / المُهيّأة · الإصدار {version}",
        "zh": "已删除/已格式化文件恢复 · 版本 {version}",
    },
    "about_by": {
        "tr": "{brand} tarafından geliştirilmiştir.",
        "en": "Developed by {brand}.",
        "es": "Desarrollado por {brand}.",
        "fr": "Développé par {brand}.",
        "de": "Entwickelt von {brand}.",
        "ru": "Разработано {brand}.",
        "ar": "طُوّر بواسطة {brand}.",
        "zh": "由 {brand} 开发。",
    },
    "about_desc": {
        "tr": "Disk, USB bellek, hafıza kartı ve (bağlanmış) telefon\ndepolamasından silinmiş ya da format atılmış dosyaları\nkurtarmaya çalışır.",
        "en": "Tries to recover deleted or formatted files from disks,\nUSB drives, memory cards, and (mounted) phone storage.",
        "es": "Intenta recuperar archivos borrados o formateados de discos,\nmemorias USB, tarjetas de memoria y almacenamiento de\nteléfonos (montado).",
        "fr": "Tente de récupérer des fichiers supprimés ou formatés\nsur des disques, clés USB, cartes mémoire et le stockage\nde téléphones (monté).",
        "de": "Versucht, gelöschte oder formatierte Dateien von Festplatten,\nUSB-Sticks, Speicherkarten und (eingebundenem) Telefon-\nspeicher wiederherzustellen.",
        "ru": "Пытается восстановить удалённые или отформатированные\nфайлы с дисков, USB-накопителей, карт памяти и\n(подключённой) памяти телефона.",
        "ar": "يحاول استعادة الملفات المحذوفة أو المُهيّأة من الأقراص\nومحركات USB وبطاقات الذاكرة وتخزين الهاتف (المتصل).",
        "zh": "尝试从磁盘、U 盘、存储卡以及（已挂载的）\n手机存储中恢复已删除或已格式化的文件。",
    },
    "about_tech": {
        "tr": "Python · Tkinter", "en": "Python · Tkinter", "es": "Python · Tkinter",
        "fr": "Python · Tkinter", "de": "Python · Tkinter", "ru": "Python · Tkinter",
        "ar": "Python · Tkinter", "zh": "Python · Tkinter",
    },
    "about_ok": {
        "tr": "Tamam", "en": "OK", "es": "Aceptar", "fr": "OK",
        "de": "OK", "ru": "ОК", "ar": "موافق", "zh": "确定",
    },

    # ---- main window chrome ----
    "brand_about_btn": {
        "tr": "Hakkında", "en": "About", "es": "Acerca de", "fr": "À propos",
        "de": "Über", "ru": "О программе", "ar": "حول", "zh": "关于",
    },
    "language_label": {
        "tr": "Dil:", "en": "Language:", "es": "Idioma:", "fr": "Langue:",
        "de": "Sprache:", "ru": "Язык:", "ar": "اللغة:", "zh": "语言:",
    },
    "source_label": {
        "tr": "Kaynak (disk/aygıt yolu ya da imaj dosyası):",
        "en": "Source (disk/device path or image file):",
        "es": "Origen (ruta del disco/dispositivo o archivo de imagen):",
        "fr": "Source (chemin du disque/périphérique ou fichier image):",
        "de": "Quelle (Laufwerk-/Gerätepfad oder Image-Datei):",
        "ru": "Источник (путь к диску/устройству или файл образа):",
        "ar": "المصدر (مسار القرص/الجهاز أو ملف صورة):",
        "zh": "源（磁盘/设备路径或镜像文件）：",
    },
    "browse_image_btn": {
        "tr": "İmaj Dosyası Seç...", "en": "Choose Image File...", "es": "Elegir archivo de imagen...",
        "fr": "Choisir un fichier image...", "de": "Image-Datei wählen...", "ru": "Выбрать файл образа...",
        "ar": "اختر ملف صورة...", "zh": "选择镜像文件...",
    },
    "list_devices_btn": {
        "tr": "Aygıtları Listele", "en": "List Devices", "es": "Listar dispositivos",
        "fr": "Lister les périphériques", "de": "Geräte auflisten", "ru": "Список устройств",
        "ar": "سرد الأجهزة", "zh": "列出设备",
    },
    "list_volumes_btn": {
        "tr": "Bağlı Bölümleri Listele", "en": "List Mounted Volumes", "es": "Listar volúmenes montados",
        "fr": "Lister les volumes montés", "de": "Eingebundene Laufwerke auflisten", "ru": "Список подключённых томов",
        "ar": "سرد وحدات التخزين المتصلة", "zh": "列出已挂载卷",
    },
    "output_label": {
        "tr": "Kurtarılan dosyaların kaydedileceği klasör:",
        "en": "Folder where recovered files will be saved:",
        "es": "Carpeta donde se guardarán los archivos recuperados:",
        "fr": "Dossier où les fichiers récupérés seront enregistrés:",
        "de": "Ordner für wiederhergestellte Dateien:",
        "ru": "Папка для сохранения восстановленных файлов:",
        "ar": "المجلد الذي سيتم حفظ الملفات المستعادة فيه:",
        "zh": "恢复文件的保存文件夹：",
    },
    "browse_output_btn": {
        "tr": "Klasör Seç...", "en": "Choose Folder...", "es": "Elegir carpeta...",
        "fr": "Choisir un dossier...", "de": "Ordner wählen...", "ru": "Выбрать папку...",
        "ar": "اختر مجلدًا...", "zh": "选择文件夹...",
    },
    "formats_frame_title": {
        "tr": "İmza taramasında (carve) aranacak formatlar",
        "en": "Formats to search for (signature scan)",
        "es": "Formatos a buscar (escaneo por firma)",
        "fr": "Formats à rechercher (analyse par signature)",
        "de": "Zu suchende Formate (Signatursuche)",
        "ru": "Форматы для поиска (сканирование по сигнатурам)",
        "ar": "الصيغ المراد البحث عنها (فحص التوقيع)",
        "zh": "要搜索的格式（特征扫描）",
    },
    "select_all_btn": {
        "tr": "Hepsini Seç", "en": "Select All", "es": "Seleccionar todo", "fr": "Tout sélectionner",
        "de": "Alle auswählen", "ru": "Выбрать все", "ar": "تحديد الكل", "zh": "全选",
    },
    "select_none_btn": {
        "tr": "Hiçbirini Seçme", "en": "Select None", "es": "No seleccionar ninguno", "fr": "Tout désélectionner",
        "de": "Keine auswählen", "ru": "Снять выбор", "ar": "إلغاء تحديد الكل", "zh": "全不选",
    },
    "scan_btn": {
        "tr": "Taramayı Başlat (önerilen: hem undelete hem carve)",
        "en": "Start Scan (recommended: both undelete and carve)",
        "es": "Iniciar escaneo (recomendado: undelete y carve)",
        "fr": "Démarrer l'analyse (recommandé : undelete et carve)",
        "de": "Scan starten (empfohlen: undelete und carve)",
        "ru": "Начать сканирование (рекомендуется: undelete и carve)",
        "ar": "بدء الفحص (يُستحسن: undelete و carve معًا)",
        "zh": "开始扫描（推荐：undelete + carve 同时进行）",
    },
    "undelete_btn": {
        "tr": "Sadece Dosya Sistemi Taraması", "en": "File System Scan Only", "es": "Solo escaneo del sistema de archivos",
        "fr": "Analyse du système de fichiers uniquement", "de": "Nur Dateisystem-Scan", "ru": "Только сканирование файловой системы",
        "ar": "فحص نظام الملفات فقط", "zh": "仅文件系统扫描",
    },
    "carve_btn": {
        "tr": "Sadece İmza Taraması", "en": "Signature Scan Only", "es": "Solo escaneo por firma",
        "fr": "Analyse par signature uniquement", "de": "Nur Signatursuche", "ru": "Только сканирование по сигнатурам",
        "ar": "فحص التوقيع فقط", "zh": "仅特征扫描",
    },
    "cancel_btn": {
        "tr": "İptal", "en": "Cancel", "es": "Cancelar", "fr": "Annuler",
        "de": "Abbrechen", "ru": "Отмена", "ar": "إلغاء", "zh": "取消",
    },
    "ready_status": {
        "tr": "Hazır.", "en": "Ready.", "es": "Listo.", "fr": "Prêt.",
        "de": "Bereit.", "ru": "Готово.", "ar": "جاهز.", "zh": "就绪。",
    },
    "log_frame_title": {
        "tr": "Günlük", "en": "Log", "es": "Registro", "fr": "Journal",
        "de": "Protokoll", "ru": "Журнал", "ar": "السجل", "zh": "日志",
    },

    # ---- dialogs / message boxes ----
    "dlg_pick_image_title": {
        "tr": "Disk imajı seç", "en": "Choose disk image", "es": "Elegir imagen de disco",
        "fr": "Choisir une image disque", "de": "Datenträgerabbild wählen", "ru": "Выбрать образ диска",
        "ar": "اختر صورة القرص", "zh": "选择磁盘镜像",
    },
    "dlg_pick_output_title": {
        "tr": "Çıktı klasörünü seç", "en": "Choose output folder", "es": "Elegir carpeta de salida",
        "fr": "Choisir le dossier de sortie", "de": "Ausgabeordner wählen", "ru": "Выбрать папку вывода",
        "ar": "اختر مجلد الإخراج", "zh": "选择输出文件夹",
    },
    "devices_title": {
        "tr": "Aygıtlar", "en": "Devices", "es": "Dispositivos", "fr": "Périphériques",
        "de": "Geräte", "ru": "Устройства", "ar": "الأجهزة", "zh": "设备",
    },
    "devices_none_msg": {
        "tr": "Hiçbir disk/aygıt bulunamadı. Ham disk erişimi genelde yönetici/root yetkisi ister; bu programı yönetici olarak çalıştırmayı dene.",
        "en": "No disks/devices found. Raw disk access usually needs administrator/root rights — try running this program as administrator.",
        "es": "No se encontraron discos/dispositivos. El acceso a disco en bruto suele requerir permisos de administrador/root; intenta ejecutar el programa como administrador.",
        "fr": "Aucun disque/périphérique trouvé. L'accès brut au disque nécessite généralement des droits administrateur/root ; essayez d'exécuter le programme en tant qu'administrateur.",
        "de": "Keine Laufwerke/Geräte gefunden. Roh-Datenträgerzugriff erfordert meist Administrator-/Root-Rechte — versuche, das Programm als Administrator auszuführen.",
        "ru": "Диски/устройства не найдены. Прямой доступ к диску обычно требует прав администратора/root — попробуйте запустить программу от имени администратора.",
        "ar": "لم يتم العثور على أقراص/أجهزة. الوصول الخام للقرص يتطلب عادةً صلاحيات المسؤول/الجذر — جرّب تشغيل البرنامج كمسؤول.",
        "zh": "未找到磁盘/设备。原始磁盘访问通常需要管理员/root 权限 — 请尝试以管理员身份运行本程序。",
    },
    "devices_found_title": {
        "tr": "Bulunan Aygıtlar", "en": "Devices Found", "es": "Dispositivos encontrados",
        "fr": "Périphériques trouvés", "de": "Gefundene Geräte", "ru": "Найденные устройства",
        "ar": "الأجهزة الموجودة", "zh": "找到的设备",
    },
    "use_as_source_btn": {
        "tr": "Bunu Kaynak Olarak Kullan", "en": "Use This As Source", "es": "Usar como origen",
        "fr": "Utiliser comme source", "de": "Als Quelle verwenden", "ru": "Использовать как источник",
        "ar": "استخدم هذا كمصدر", "zh": "用作源",
    },
    "volumes_title": {
        "tr": "Bölümler", "en": "Volumes", "es": "Volúmenes", "fr": "Volumes",
        "de": "Laufwerke", "ru": "Тома", "ar": "وحدات التخزين", "zh": "卷",
    },
    "volumes_none_msg": {
        "tr": "Bağlı bir bölüm/klasör bulunamadı.", "en": "No mounted volume/folder found.",
        "es": "No se encontró ningún volumen/carpeta montado.", "fr": "Aucun volume/dossier monté trouvé.",
        "de": "Kein eingebundenes Laufwerk/Ordner gefunden.", "ru": "Подключённые тома/папки не найдены.",
        "ar": "لم يتم العثور على وحدة تخزين/مجلد متصل.", "zh": "未找到已挂载的卷/文件夹。",
    },
    "volumes_found_title": {
        "tr": "Bağlı Bölümler / Klasörler", "en": "Mounted Volumes / Folders", "es": "Volúmenes/carpetas montados",
        "fr": "Volumes / dossiers montés", "de": "Eingebundene Laufwerke / Ordner", "ru": "Подключённые тома / папки",
        "ar": "وحدات التخزين/المجلدات المتصلة", "zh": "已挂载卷/文件夹",
    },
    "missing_info_title": {
        "tr": "Eksik bilgi", "en": "Missing information", "es": "Falta información",
        "fr": "Information manquante", "de": "Fehlende Angaben", "ru": "Недостаточно данных",
        "ar": "معلومات ناقصة", "zh": "信息缺失",
    },
    "missing_source_msg": {
        "tr": "Önce bir kaynak (disk/aygıt/imaj dosyası) seç.", "en": "First choose a source (disk/device/image file).",
        "es": "Primero elige un origen (disco/dispositivo/archivo de imagen).", "fr": "Choisissez d'abord une source (disque/périphérique/fichier image).",
        "de": "Wähle zuerst eine Quelle (Laufwerk/Gerät/Image-Datei).", "ru": "Сначала выберите источник (диск/устройство/файл образа).",
        "ar": "اختر أولاً مصدرًا (قرص/جهاز/ملف صورة).", "zh": "请先选择源（磁盘/设备/镜像文件）。",
    },
    "missing_output_msg": {
        "tr": "Kurtarılan dosyaların kaydedileceği bir klasör seç.", "en": "Choose a folder to save recovered files to.",
        "es": "Elige una carpeta donde guardar los archivos recuperados.", "fr": "Choisissez un dossier pour enregistrer les fichiers récupérés.",
        "de": "Wähle einen Ordner für die wiederhergestellten Dateien.", "ru": "Выберите папку для сохранения восстановленных файлов.",
        "ar": "اختر مجلدًا لحفظ الملفات المستعادة فيه.", "zh": "请选择用于保存恢复文件的文件夹。",
    },
    "source_not_found_title": {
        "tr": "Kaynak bulunamadı", "en": "Source not found", "es": "Origen no encontrado",
        "fr": "Source introuvable", "de": "Quelle nicht gefunden", "ru": "Источник не найден",
        "ar": "المصدر غير موجود", "zh": "未找到源",
    },
    "source_not_found_msg": {
        "tr": "'{source}' bulunamadı ya da erişilemiyor.", "en": "'{source}' was not found or is not accessible.",
        "es": "No se encontró '{source}' o no es accesible.", "fr": "« {source} » est introuvable ou inaccessible.",
        "de": "'{source}' wurde nicht gefunden oder ist nicht zugänglich.", "ru": "«{source}» не найден или недоступен.",
        "ar": "'{source}' غير موجود أو لا يمكن الوصول إليه.", "zh": "未找到或无法访问 “{source}”。",
    },
    "warning_title": {
        "tr": "Uyarı", "en": "Warning", "es": "Advertencia", "fr": "Avertissement",
        "de": "Warnung", "ru": "Предупреждение", "ar": "تحذير", "zh": "警告",
    },
    "output_inside_source_msg": {
        "tr": "Çıktı klasörü kaynağın içinde olamaz — kurtarmaya çalıştığın veriyi kendi üstüne yazabilirsin. Farklı bir çıktı klasörü seç.",
        "en": "The output folder can't be inside the source — you could overwrite the very data you're trying to recover. Choose a different output folder.",
        "es": "La carpeta de salida no puede estar dentro del origen — podrías sobrescribir los datos que intentas recuperar. Elige otra carpeta de salida.",
        "fr": "Le dossier de sortie ne peut pas se trouver dans la source — vous risqueriez d'écraser les données que vous essayez de récupérer. Choisissez un autre dossier de sortie.",
        "de": "Der Ausgabeordner darf nicht innerhalb der Quelle liegen — du könntest die Daten überschreiben, die du wiederherstellen willst. Wähle einen anderen Ausgabeordner.",
        "ru": "Папка вывода не может находиться внутри источника — вы можете перезаписать восстанавливаемые данные. Выберите другую папку вывода.",
        "ar": "لا يمكن أن يكون مجلد الإخراج داخل المصدر — قد تكتب فوق البيانات التي تحاول استعادتها. اختر مجلد إخراج مختلفًا.",
        "zh": "输出文件夹不能位于源内部 — 否则可能覆盖你正在恢复的数据。请选择其他输出文件夹。",
    },
    "cancel_requested_log": {
        "tr": "İptal isteği gönderildi, mevcut adım bitince duracak...",
        "en": "Cancel requested, will stop once the current step finishes...",
        "es": "Cancelación solicitada, se detendrá al terminar el paso actual...",
        "fr": "Annulation demandée, l'arrêt se fera à la fin de l'étape en cours...",
        "de": "Abbruch angefordert, wird nach dem aktuellen Schritt stoppen...",
        "ru": "Запрошена отмена, остановится после завершения текущего шага...",
        "ar": "تم طلب الإلغاء، سيتوقف بعد انتهاء الخطوة الحالية...",
        "zh": "已请求取消，将在当前步骤完成后停止……",
    },
    "busy_title": {
        "tr": "Meşgul", "en": "Busy", "es": "Ocupado", "fr": "Occupé",
        "de": "Beschäftigt", "ru": "Занято", "ar": "مشغول", "zh": "正忙",
    },
    "busy_msg": {
        "tr": "Zaten bir tarama çalışıyor.", "en": "A scan is already running.",
        "es": "Ya hay un escaneo en curso.", "fr": "Une analyse est déjà en cours.",
        "de": "Es läuft bereits ein Scan.", "ru": "Сканирование уже выполняется.",
        "ar": "هناك فحص قيد التشغيل بالفعل.", "zh": "已有扫描正在进行。",
    },
    "permission_error_log": {
        "tr": "HATA: Yetki hatası. Bu programı yönetici/root olarak çalıştırmayı dene.",
        "en": "ERROR: Permission error. Try running this program as administrator/root.",
        "es": "ERROR: Error de permisos. Intenta ejecutar este programa como administrador/root.",
        "fr": "ERREUR : erreur de permission. Essayez d'exécuter ce programme en tant qu'administrateur/root.",
        "de": "FEHLER: Berechtigungsfehler. Versuche, dieses Programm als Administrator/root auszuführen.",
        "ru": "ОШИБКА: ошибка доступа. Попробуйте запустить программу от имени администратора/root.",
        "ar": "خطأ: خطأ في الصلاحيات. جرّب تشغيل هذا البرنامج كمسؤول/جذر.",
        "zh": "错误：权限错误。请尝试以管理员/root 身份运行本程序。",
    },
    "generic_error_log": {
        "tr": "HATA: {error}", "en": "ERROR: {error}", "es": "ERROR: {error}", "fr": "ERREUR : {error}",
        "de": "FEHLER: {error}", "ru": "ОШИБКА: {error}", "ar": "خطأ: {error}", "zh": "错误：{error}",
    },
    "done_status": {
        "tr": "Bitti.", "en": "Done.", "es": "Listo.", "fr": "Terminé.",
        "de": "Fertig.", "ru": "Готово.", "ar": "تم.", "zh": "完成。",
    },
    "eta_calculating": {
        "tr": " — tahmini kalan: hesaplanıyor...", "en": " — estimated remaining: calculating...",
        "es": " — tiempo restante estimado: calculando...", "fr": " — temps restant estimé : calcul en cours...",
        "de": " — geschätzte Restzeit: wird berechnet...", "ru": " — осталось (оценка): вычисляется...",
        "ar": " — الوقت المتبقي المقدر: قيد الحساب...", "zh": " — 预计剩余：计算中……",
    },
    "eta_remaining": {
        "tr": " — tahmini kalan: {eta}", "en": " — estimated remaining: {eta}",
        "es": " — tiempo restante estimado: {eta}", "fr": " — temps restant estimé : {eta}",
        "de": " — geschätzte Restzeit: {eta}", "ru": " — осталось (оценка): {eta}",
        "ar": " — الوقت المتبقي المقدر: {eta}", "zh": " — 预计剩余：{eta}",
    },
    "partition_found_log": {
        "tr": "Bölüm tablosu üzerinden bölüm bulundu (offset {offset}), oradan devam ediliyor.",
        "en": "Found a partition via the partition table (offset {offset}), continuing from there.",
        "es": "Se encontró una partición mediante la tabla de particiones (offset {offset}), continuando desde ahí.",
        "fr": "Partition trouvée via la table des partitions (offset {offset}), poursuite à partir de là.",
        "de": "Partition über die Partitionstabelle gefunden (Offset {offset}), wird von dort fortgesetzt.",
        "ru": "Раздел найден через таблицу разделов (смещение {offset}), продолжаем оттуда.",
        "ar": "تم العثور على قسم عبر جدول الأقسام (الإزاحة {offset})، والمتابعة من هناك.",
        "zh": "通过分区表找到分区（偏移量 {offset}），从该处继续。",
    },
    "ntfs_detected_log": {
        "tr": "NTFS bölümü tespit edildi, MFT taranıyor...", "en": "NTFS partition detected, scanning the MFT...",
        "es": "Partición NTFS detectada, escaneando la MFT...", "fr": "Partition NTFS détectée, analyse de la MFT...",
        "de": "NTFS-Partition erkannt, MFT wird gescannt...", "ru": "Обнаружен раздел NTFS, сканирование MFT...",
        "ar": "تم اكتشاف قسم NTFS، يتم فحص MFT...", "zh": "检测到 NTFS 分区，正在扫描 MFT……",
    },
    "deleted_found_log": {
        "tr": "{count} silinmiş dosya kaydı bulundu.", "en": "{count} deleted file record(s) found.",
        "es": "Se encontraron {count} registros de archivos borrados.", "fr": "{count} enregistrement(s) de fichier supprimé trouvé(s).",
        "de": "{count} gelöschte Dateieinträge gefunden.", "ru": "Найдено записей об удалённых файлах: {count}.",
        "ar": "تم العثور على {count} سجل ملف محذوف.", "zh": "找到 {count} 条已删除文件记录。",
    },
    "cancelled_log": {
        "tr": "İptal edildi.", "en": "Cancelled.", "es": "Cancelado.", "fr": "Annulé.",
        "de": "Abgebrochen.", "ru": "Отменено.", "ar": "أُلغي.", "zh": "已取消。",
    },
    "recovered_log": {
        "tr": "  kurtarıldı: {name} ({size})", "en": "  recovered: {name} ({size})",
        "es": "  recuperado: {name} ({size})", "fr": "  récupéré : {name} ({size})",
        "de": "  wiederhergestellt: {name} ({size})", "ru": "  восстановлено: {name} ({size})",
        "ar": "  تمت الاستعادة: {name} ({size})", "zh": "  已恢复：{name}（{size}）",
    },
    "total_recovered_log": {
        "tr": "Toplam kurtarılan: {recovered}/{total}", "en": "Total recovered: {recovered}/{total}",
        "es": "Total recuperado: {recovered}/{total}", "fr": "Total récupéré : {recovered}/{total}",
        "de": "Insgesamt wiederhergestellt: {recovered}/{total}", "ru": "Всего восстановлено: {recovered}/{total}",
        "ar": "الإجمالي المستعاد: {recovered}/{total}", "zh": "共恢复：{recovered}/{total}",
    },
    "fat_detected_log": {
        "tr": "{fat_type} bölümü tespit edildi, dizin tablosu taranıyor...",
        "en": "{fat_type} partition detected, scanning the directory table...",
        "es": "Partición {fat_type} detectada, escaneando la tabla de directorios...",
        "fr": "Partition {fat_type} détectée, analyse de la table de répertoires...",
        "de": "{fat_type}-Partition erkannt, Verzeichnistabelle wird gescannt...",
        "ru": "Обнаружен раздел {fat_type}, сканирование таблицы каталогов...",
        "ar": "تم اكتشاف قسم {fat_type}، يتم فحص جدول الدليل...",
        "zh": "检测到 {fat_type} 分区，正在扫描目录表……",
    },
    "no_fs_found_log": {
        "tr": "Tanınan bir FAT/NTFS dosya sistemi bulunamadı (format atılmış ya da bozuk olabilir; bölüm tablosu da taranmış ama uyan bir bölüm çıkmadı). 'Sadece İmza Taraması' butonunu dene.",
        "en": "No recognizable FAT/NTFS file system was found (it may be formatted or corrupted; the partition table was also scanned but no matching partition turned up). Try the 'Signature Scan Only' button.",
        "es": "No se encontró un sistema de archivos FAT/NTFS reconocible (puede estar formateado o dañado; también se escaneó la tabla de particiones pero no apareció ninguna coincidencia). Prueba el botón 'Solo escaneo por firma'.",
        "fr": "Aucun système de fichiers FAT/NTFS reconnaissable trouvé (il peut être formaté ou corrompu ; la table des partitions a aussi été analysée sans résultat correspondant). Essayez le bouton « Analyse par signature uniquement ».",
        "de": "Kein erkennbares FAT/NTFS-Dateisystem gefunden (könnte formatiert oder beschädigt sein; die Partitionstabelle wurde ebenfalls durchsucht, aber keine passende Partition gefunden). Probiere den Button 'Nur Signatursuche'.",
        "ru": "Распознаваемая файловая система FAT/NTFS не найдена (возможно, отформатирована или повреждена; таблица разделов также просканирована, но подходящий раздел не найден). Попробуйте кнопку «Только сканирование по сигнатурам».",
        "ar": "لم يتم العثور على نظام ملفات FAT/NTFS معروف (قد يكون مُهيّأً أو تالفًا؛ تم أيضًا فحص جدول الأقسام دون العثور على قسم مطابق). جرّب زر 'فحص التوقيع فقط'.",
        "zh": "未找到可识别的 FAT/NTFS 文件系统（可能已被格式化或损坏；分区表也已扫描但未找到匹配分区）。请尝试“仅特征扫描”按钮。",
    },
    "fat_trace_log": {
        "tr": "(FAT izi bulundu, öksüz dizin girdisi taraması da aynı geçişte yapılacak.)",
        "en": "(FAT trace found, orphan directory-entry scanning will run in the same pass.)",
        "es": "(Se encontró un rastro FAT, el escaneo de entradas de directorio huérfanas se hará en la misma pasada.)",
        "fr": "(Trace FAT trouvée, l'analyse des entrées de répertoire orphelines se fera dans le même passage.)",
        "de": "(FAT-Spur gefunden, verwaiste Verzeichniseinträge werden im selben Durchgang gesucht.)",
        "ru": "(Обнаружен след FAT, сканирование потерянных записей каталога выполнится за тот же проход.)",
        "ar": "(تم العثور على أثر FAT، سيتم فحص إدخالات الدليل اليتيمة في نفس التمريرة.)",
        "zh": "（发现 FAT 痕迹，孤立目录项扫描将在同一遍完成。）",
    },
    "scanning_status": {
        "tr": "Kaynak taranıyor...", "en": "Scanning source...", "es": "Escaneando origen...",
        "fr": "Analyse de la source...", "de": "Quelle wird gescannt...", "ru": "Сканирование источника...",
        "ar": "يتم فحص المصدر...", "zh": "正在扫描源……",
    },
    "candidates_found_log": {
        "tr": "{count} olası dosya bulundu.", "en": "{count} candidate file(s) found.",
        "es": "Se encontraron {count} archivos candidatos.", "fr": "{count} fichier(s) candidat(s) trouvé(s).",
        "de": "{count} mögliche Dateien gefunden.", "ru": "Найдено кандидатов: {count}.",
        "ar": "تم العثور على {count} ملف مرشح.", "zh": "找到 {count} 个候选文件。",
    },
    "orphan_found_log": {
        "tr": "{count} öksüz dizin girdisi bulundu ({new} tanesi yeni) — orijinal isimleriyle kurtarılıyor...",
        "en": "{count} orphan directory entries found ({new} of them new) — recovering with original names...",
        "es": "Se encontraron {count} entradas de directorio huérfanas ({new} nuevas) — recuperando con nombres originales...",
        "fr": "{count} entrées de répertoire orphelines trouvées ({new} nouvelles) — récupération avec les noms d'origine...",
        "de": "{count} verwaiste Verzeichniseinträge gefunden ({new} davon neu) — Wiederherstellung mit Originalnamen...",
        "ru": "Найдено потерянных записей каталога: {count} (новых: {new}) — восстановление с исходными именами...",
        "ar": "تم العثور على {count} إدخال دليل يتيم ({new} منها جديد) — يتم الاستعادة بالأسماء الأصلية...",
        "zh": "找到 {count} 个孤立目录项（其中 {new} 个是新的）-- 正在以原文件名恢复……",
    },
    "orphan_recovered_log": {
        "tr": "  kurtarıldı (orijinal isim): {name} ({size})", "en": "  recovered (original name): {name} ({size})",
        "es": "  recuperado (nombre original): {name} ({size})", "fr": "  récupéré (nom d'origine) : {name} ({size})",
        "de": "  wiederhergestellt (Originalname): {name} ({size})", "ru": "  восстановлено (исходное имя): {name} ({size})",
        "ar": "  تمت الاستعادة (بالاسم الأصلي): {name} ({size})", "zh": "  已恢复（原文件名）：{name}（{size}）",
    },
    "orphan_total_log": {
        "tr": "Orijinal isimle kurtarılan: {recovered}/{total}", "en": "Recovered with original name: {recovered}/{total}",
        "es": "Recuperados con nombre original: {recovered}/{total}", "fr": "Récupérés avec le nom d'origine : {recovered}/{total}",
        "de": "Mit Originalname wiederhergestellt: {recovered}/{total}", "ru": "Восстановлено с исходным именем: {recovered}/{total}",
        "ar": "تمت الاستعادة بالاسم الأصلي: {recovered}/{total}", "zh": "以原文件名恢复：{recovered}/{total}",
    },
    "extracting_status": {
        "tr": "Dosyalar çıkarılıyor...", "en": "Extracting files...", "es": "Extrayendo archivos...",
        "fr": "Extraction des fichiers...", "de": "Dateien werden extrahiert...", "ru": "Извлечение файлов...",
        "ar": "يتم استخراج الملفات...", "zh": "正在提取文件……",
    },
    "total_files_log": {
        "tr": "Toplam kurtarılan dosya: {count}", "en": "Total recovered files: {count}",
        "es": "Total de archivos recuperados: {count}", "fr": "Total de fichiers récupérés : {count}",
        "de": "Insgesamt wiederhergestellte Dateien: {count}", "ru": "Всего восстановлено файлов: {count}",
        "ar": "إجمالي الملفات المستعادة: {count}", "zh": "共恢复文件：{count}",
    },
    "format_count_log": {
        "tr": "  {fmt}: {count} dosya, toplam {size}", "en": "  {fmt}: {count} file(s), {size} total",
        "es": "  {fmt}: {count} archivos, {size} en total", "fr": "  {fmt} : {count} fichier(s), {size} au total",
        "de": "  {fmt}: {count} Datei(en), {size} insgesamt", "ru": "  {fmt}: {count} файлов, всего {size}",
        "ar": "  {fmt}: {count} ملف، الإجمالي {size}", "zh": "  {fmt}：{count} 个文件，共 {size}",
    },
    "truncated_note_log": {
        "tr": "Not: {count} dosya net bitiş imzası bulunamadığı için boyut sınırıyla kesildi.",
        "en": "Note: {count} file(s) had no clear end signature, so they were cut off at the size limit.",
        "es": "Nota: {count} archivo(s) no tenían una firma de fin clara, así que se cortaron al llegar al límite de tamaño.",
        "fr": "Remarque : {count} fichier(s) n'avaient pas de signature de fin claire, ils ont donc été coupés à la limite de taille.",
        "de": "Hinweis: Bei {count} Datei(en) wurde keine eindeutige Endsignatur gefunden, sie wurden daher bei der Größenobergrenze abgeschnitten.",
        "ru": "Примечание: у {count} файлов не найдена чёткая сигнатура конца, поэтому они были обрезаны по предельному размеру.",
        "ar": "ملاحظة: {count} ملف لم يُعثر له على توقيع نهاية واضح، لذا تم قطعه عند حد الحجم.",
        "zh": "注意：{count} 个文件没有明确的结束特征，因此按大小上限被截断。",
    },
    "fs_scan_header_log": {
        "tr": "=== Dosya sistemi taraması: {source} ===", "en": "=== File system scan: {source} ===",
        "es": "=== Escaneo del sistema de archivos: {source} ===", "fr": "=== Analyse du système de fichiers : {source} ===",
        "de": "=== Dateisystem-Scan: {source} ===", "ru": "=== Сканирование файловой системы: {source} ===",
        "ar": "=== فحص نظام الملفات: {source} ===", "zh": "=== 文件系统扫描：{source} ===",
    },
    "sig_scan_header_log": {
        "tr": "=== İmza taraması: {source} ===", "en": "=== Signature scan: {source} ===",
        "es": "=== Escaneo por firma: {source} ===", "fr": "=== Analyse par signature : {source} ===",
        "de": "=== Signatursuche: {source} ===", "ru": "=== Сканирование по сигнатурам: {source} ===",
        "ar": "=== فحص التوقيع: {source} ===", "zh": "=== 特征扫描：{source} ===",
    },
    "restart_needed_msg": {
        "tr": "Dil değişikliği uygulandı.", "en": "Language changed.", "es": "Idioma cambiado.",
        "fr": "Langue modifiée.", "de": "Sprache geändert.", "ru": "Язык изменён.",
        "ar": "تم تغيير اللغة.", "zh": "语言已更改。",
    },
}


def _config_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "data-recovery", "config.json")


def load_language() -> str:
    try:
        with open(_config_path(), "r", encoding="utf-8") as f:
            lang = json.load(f).get("language")
            if lang in LANGUAGES:
                return lang
    except Exception:
        pass
    return _DEFAULT_LANG


def save_language(lang: str) -> None:
    path = _config_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"language": lang}, f)
    except Exception:
        pass  # best-effort only; this must never crash the app


_current_lang = load_language()


def get_language() -> str:
    return _current_lang


def set_language(lang: str) -> None:
    global _current_lang
    if lang not in LANGUAGES:
        lang = _DEFAULT_LANG
    _current_lang = lang
    save_language(lang)


def t(key: str, **kwargs) -> str:
    """Translate `key` into the current language, formatting with kwargs.

    Falls back to Turkish, then to the bare key, when a translation or the
    key itself is missing, so a missing string cannot crash the UI.
    """
    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key
    text = entry.get(_current_lang) or entry.get(_DEFAULT_LANG) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
