#!/usr/bin/env python3
"""Translations for LAN Chat. Supported languages: en, ru, ar."""

TRANSLATIONS = {
    "en": {
        "language_name": "English",
        "server_started": "Server started on {host}:{port} (Ctrl+C to stop)",
        "server_waiting": "Waiting for connections...",
        "server_client_joined": "[+] {name} joined",
        "server_client_left": "[-] {name} left",
        "clients_connected": "Connected clients: {count}",
        "welcome": "Welcome to LAN Chat!",
        "enter_name": "Enter your display name: ",
        "connected": "Connected to {host}:{port}",
        "connect_error": "Could not connect: {error}",
        "connected_to_server": "Connected! Type your message and press Enter.",
        "type_exit": "Type /help for commands.",
        "no_cmd_hint": "no such command",
        "you_left": "You left the chat.",
        "online": "Users online:",
        "unknown_cmd": "Unknown command: {cmd}",
        "server_not_found": "No server found on the network.",
        "searching": "Searching for server on LAN...",
        "disconnected": "Server closed the connection.",
        "enter_pass": "Group passphrase (must match everyone): ",
        "enter_login": "Login: ",
        "enter_account_pass": "Account password: ",
        "enter_groupkey": "Group passphrase (must match everyone): ",
        "entry_ask": "1) Login   2) Register    Choose: ",
        "enter_new_login": "New login (A-Z, a-z, 0-9): ",
        "enter_new_pass": "New password (A-Z, a-z, 0-9): ",
        "enter_new_pass_repeat": "Repeat password: ",
        "pass_nomatch": "Passwords do not match.",
        "register_chars": "Only English letters and digits 0-9 are allowed.",
        "register_exists": "This login is already taken.",
        "wrong_credentials": "Wrong login or password.",
        "pin_prompt": "Secret PIN",
        "admin_blocked": "This is an admin account — chat access is blocked for it.",
        "auth_failed": "[!] denied login from {addr}",
        "accounts_loaded": "{count} accounts loaded",
        "file_sent": "sending file: {name} ({size})",
        "file_received": "received file {name} ({size}) → {path}",
        "file_too_big": "file too big ({size}) — max 20 MB",
        "file_missing": "file not found: {path}",
        "file_error": "file transfer error: {error}",
        "file_reassembled": "all chunks received for {name}",
        "dm_received": "private from {name}",
        "dm_to_yourself": "cannot DM yourself",
        "dm_user_unknown": "unknown user: {name}",
        "dm_sent": "private → {name}",
        "reply_received": "private from {name} (reply)",
        "nick_changed": "you are now {name}",
        "nick_set_by": "{old} is now {new}",
        "nick_empty": "name cannot be empty",
        "passwd_changed": "password changed successfully",
        "passwd_usage": "usage: /passwd <new-password>",
        "register_ok": "account '{login}' registered",
        "register_fail": "registration failed: {reason}",
        "register_usage": "usage: /register <login> <password>",
        "rename_ok": "login changed to {login}",
        "rename_fail": "rename failed: {reason}",
        "rename_usage": "usage: /rename <new-login>",
        "mail_new_account": "NEW ACCOUNT",
        "mail_pass_changed": "PASSWORD CHANGED",
        "mail_login_renamed": "LOGIN RENAMED",
        "mail_auth_failed": "LOGIN DENIED",
        "mail_admin_blocked": "ADMIN ACCOUNT BLOCKED (ADMIN), CHAT NOT ALLOWED",
        "joined_msg": "{name} joined",
        "left_msg": "{name} left",
        "anon_left_msg": "An anonymous user left the chat",
        "links_header": "Links:",
        "links_empty": "no links yet",
        "links_hint": "open: /open <number>",
        "open_usage": "usage: /open <number> or /open <url>",
        "opening": "opening: {url}",
        "open_path": "no browser found — open it yourself: {url}",
        "mail_admin_blocked": "ADMIN ACCOUNT BLOCKED (ADMIN), CHAT NOT ALLOWED",
        "help": (
            "/dm <name> <msg>   private message\n"
            "/r <msg>           reply to last sender\n"
            "/send <path>       send a file\n"
            "/open [num|url]   open a link from chat\n"
            "/links            show collected links\n"
            "/users             who is online\n"
            "/nick <name>       change display name\n"
            "/passwd <pass>     change account password\n"
            "/rename <login>    change account login\n"
            "/register <l> <p>  register new account\n"
            "/clear             clear screen\n"
            "/exit              leave chat"
        ),
    },
    "ru": {
        "language_name": "Русский",
        "server_started": "Сервер запущен на {host}:{port} (Ctrl+C для остановки)",
        "server_waiting": "Ожидание подключений...",
        "server_client_joined": "[+] {name} присоединился",
        "server_client_left": "[-] {name} покинул чат",
        "clients_connected": "Подключено клиентов: {count}",
        "welcome": "Добро пожаловать в LAN Chat!",
        "enter_name": "Введите отображаемое имя: ",
        "connected": "Подключено к {host}:{port}",
        "connect_error": "Не удалось подключиться: {error}",
        "connected_to_server": "Вы подключены! Введите сообщение и нажмите Enter.",
        "type_exit": "Введите /help для списка команд.",
        "no_cmd_hint": "нет такой команды",
        "you_left": "Вы покинули чат.",
        "online": "Пользователи онлайн:",
        "unknown_cmd": "Неизвестная команда: {cmd}",
        "server_not_found": "Сервер не найден в сети.",
        "searching": "Поиск сервера в локальной сети...",
        "disconnected": "Сервер закрыл соединение.",
        "enter_pass": "Общий пароль чата (одинаковый у всех): ",
        "enter_login": "Логин: ",
        "enter_account_pass": "Пароль аккаунта: ",
        "enter_groupkey": "Общий пароль чата (одинаковый у всех): ",
        "entry_ask": "1) Вход   2) Регистрация    Выбор: ",
        "enter_new_login": "Новый логин (A-Z, a-z, 0-9): ",
        "enter_new_pass": "Новый пароль (A-Z, a-z, 0-9): ",
        "enter_new_pass_repeat": "Повторите пароль: ",
        "pass_nomatch": "Пароли не совпадают.",
        "register_chars": "Только латинские буквы и цифры 0-9.",
        "register_exists": "Такой логин уже занят.",
        "wrong_credentials": "Неверный логин или пароль.",
        "pin_prompt": "Секретный PIN",
        "admin_blocked": "Это админ-аккаунт — вход в чат для него запрещён.",
        "auth_failed": "[!] отказ входа от {addr}",
        "accounts_loaded": "Загружено аккаунтов: {count}",
        "file_sent": "отправка файла: {name} ({size})",
        "file_received": "получен файл {name} ({size}) → {path}",
        "file_too_big": "файл слишком большой ({size}) — макс 20 МБ",
        "file_missing": "файл не найден: {path}",
        "file_error": "ошибка передачи файла: {error}",
        "file_reassembled": "все фрагменты получены: {name}",
        "dm_received": "приватное от {name}",
        "dm_to_yourself": "нельзя писать самому себе",
        "dm_user_unknown": "пользователь не найден: {name}",
        "dm_sent": "приватное → {name}",
        "reply_received": "приватное от {name} (ответ)",
        "nick_changed": "вы теперь {name}",
        "nick_set_by": "{old} теперь {new}",
        "nick_empty": "имя не может быть пустым",
        "passwd_changed": "пароль успешно изменён",
        "passwd_usage": "использование: /passwd <новый-пароль>",
        "register_ok": "аккаунт '{login}' зарегистрирован",
        "register_fail": "регистрация не удалась: {reason}",
        "register_usage": "использование: /register <логин> <пароль>",
        "rename_ok": "логин изменён на {login}",
        "rename_fail": "смена логина не удалась: {reason}",
        "rename_usage": "использование: /rename <новый-логин>",
        "mail_new_account": "НОВАЯ РЕГИСТРАЦИЯ",
        "mail_pass_changed": "ПАРОЛЬ ИЗМЕНЁН",
        "mail_login_renamed": "ЛОГИН ИЗМЕНЁН",
        "mail_auth_failed": "ВХОД ОТКЛОНЁН",
        "mail_admin_blocked": "АККАУНТ АДМИНА ЗАБЛОКИРОВАН, ВХОД В ЧАТ ЗАПРЕЩЁН",
        "joined_msg": "{name} присоединился",
        "left_msg": "{name} покинул чат",
        "anon_left_msg": "Анонимный пользователь покинул чат",
        "links_header": "Ссылки:",
        "links_empty": "ссылок пока нет",
        "links_hint": "открыть: /open <номер>",
        "open_usage": "использование: /open <номер> или /open <URL>",
        "opening": "открываю: {url}",
        "open_path": "нет браузера — открой сам: {url}",
        "help": (
            "/dm <имя> <текст>  приватное сообщение\n"
            "/r <текст>         ответ последнему\n"
            "/send <путь>       отправить файл\n"
            "/open [номер|URL] открыть ссылку из чата\n"
            "/links            показать собранные ссылки\n"
            "/users             кто онлайн\n"
            "/nick <имя>        сменить отображаемое имя\n"
            "/passwd <пароль>   сменить пароль\n"
            "/rename <логин>    сменить логин\n"
            "/register <л> <п>  зарегистрировать аккаунт\n"
            "/clear             очистить экран\n"
            "/exit              выйти из чата"
        ),
    },
    "ar": {
        "language_name": "العربية",
        "server_started": "تم تشغيل الخادم على {host}:{port} (Ctrl+C للإيقاف)",
        "server_waiting": "في انتظار الاتصالات...",
        "server_client_joined": "[+] انضم {name}",
        "server_client_left": "[-] غادر {name}",
        "clients_connected": "العملاء المتصلون: {count}",
        "welcome": "مرحبًا بك في دردشة الشبكة المحلية!",
        "enter_name": "أدخل اسمك: ",
        "connected": "متصل بـ {host}:{port}",
        "connect_error": "تعذر الاتصال: {error}",
        "connected_to_server": "متصل! اكتب رسالتك واضغط Enter.",
        "type_exit": "اكتب /help للأوامر.",
        "no_cmd_hint": "لا يوجد أمر بهذا الاسم",
        "you_left": "غادرت الدردشة.",
        "online": "المستخدمون المتصلون:",
        "unknown_cmd": "أمر غير معروف: {cmd}",
        "server_not_found": "لم يتم العثور على خادم على الشبكة.",
        "searching": "جارٍ البحث عن خادم على الشبكة المحلية...",
        "disconnected": "أغلق الخادم الاتصال.",
        "enter_pass": "كلمة مرور المجموعة: ",
        "enter_login": "اسم المستخدم: ",
        "enter_account_pass": "كلمة مرور الحساب: ",
        "enter_groupkey": "كلمة مرور المجموعة (يجب أن تتطابق مع الجميع): ",
        "entry_ask": "1) دخول   2) تسجيل    الاختيار: ",
        "enter_new_login": "اسم مستخدم جديد (A-Z, a-z, 0-9): ",
        "enter_new_pass": "كلمة مرور جديدة (A-Z, a-z, 0-9): ",
        "enter_new_pass_repeat": "أعد كلمة المرور: ",
        "pass_nomatch": "كلمتا المرور غير متطابقتين.",
        "register_chars": "فقط الحروف اللاتينية والأرقام 0-9.",
        "register_exists": "اسم المستخدم هذا محجوز بالفعل.",
        "wrong_credentials": "اسم مستخدم أو كلمة مرور خاطئة.",
        "pin_prompt": "رمز PIN السري",
        "admin_blocked": "هذا حساب مدير — تم منع الدخول إلى الدردشة.",
        "auth_failed": "[!] رفض الدخول من {addr}",
        "accounts_loaded": "تم تحميل الحسابات: {count}",
        "file_sent": "جارٍ إرسال الملف: {name} ({size})",
        "file_received": "تم استلام الملف {name} ({size}) → {path}",
        "file_too_big": "الملف كبير جدًا ({size}) — الحد الأقصى 20 ميغابايت",
        "file_missing": "الملف غير موجود: {path}",
        "file_error": "خطأ في نقل الملف: {error}",
        "file_reassembled": "تم استلام جميع الأجزاء: {name}",
        "dm_received": "رسالة خاصة من {name}",
        "dm_to_yourself": "لا يمكنك إرسال رسالة لنفسك",
        "dm_user_unknown": "المستخدم غير معروف: {name}",
        "dm_sent": "رسالة خاصة → {name}",
        "reply_received": "رد خاص من {name}",
        "nick_changed": "اسمك الآن {name}",
        "nick_set_by": "{old} الآن {new}",
        "nick_empty": "لا يمكن أن يكون الاسم فارغًا",
        "passwd_changed": "تم تغيير كلمة المرور بنجاح",
        "passwd_usage": "استخدام: /passwd <كلمة-مرور-جديدة>",
        "register_ok": "تم تسجيل الحساب '{login}'",
        "register_fail": "فشلت التسجيل: {reason}",
        "register_usage": "استخدام: /register <مستخدم> <كلمة-مرور>",
        "rename_ok": "تم تغيير اسم المستخدم إلى {login}",
        "rename_fail": "فشل تغيير الاسم: {reason}",
        "rename_usage": "استخدام: /rename <اسم-جديد>",
        "mail_new_account": "حساب جديد",
        "mail_pass_changed": "تم تغيير كلمة المرور",
        "mail_login_renamed": "تم تغيير اسم المستخدم",
        "mail_auth_failed": "تم رفض الدخول",
        "mail_admin_blocked": "حساب المدير محظور، لا يمكن دخول الدردشة",
        "joined_msg": "انضم {name}",
        "left_msg": "غادر {name}",
        "anon_left_msg": "غادر مستخدم مجهول الدردشة",
        "links_header": "الروابط:",
        "links_empty": "لا توجد روابط بعد",
        "links_hint": "افتح: /open <رقم>",
        "open_usage": "الاستخدام: /open <رقم> أو /open <الرابط>",
        "opening": "جارٍ فتح: {url}",
        "open_path": "لا يوجد متصفح — افتح بنفسك: {url}",
        "help": (
            "/dm <اسم> <نص>    رسالة خاصة\n"
            "/r <نص>            رد على آخر مرسل\n"
            "/send <مسار>       إرسال ملف\n"
            "/open [رقم|رابط]   فتح رابط من الدردشة\n"
            "/links            عرض الروابط المجمعة\n"
            "/users             من متصل\n"
            "/nick <اسم>        تغيير الاسم المعروض\n"
            "/passwd < كلمة>   تغيير كلمة المرور\n"
            "/rename <اسم>      تغيير اسم المستخدم\n"
            "/register <م> <ك>   تسجيل حساب جديد\n"
            "/clear             مسح الشاشة\n"
            "/exit              مغادرة الدردشة"
        ),
    },
}

LANGUAGES = ["en", "ru", "ar"]


class Translator:
    def __init__(self, lang="en"):
        self.lang = lang if lang in TRANSLATIONS else "en"

    def t(self, key, **kwargs):
        msg = TRANSLATIONS[self.lang].get(
            key, TRANSLATIONS["en"].get(key, key)
        )
        return msg.format(**kwargs)