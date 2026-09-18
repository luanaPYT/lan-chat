<div align="center">

# LAN Chat 🔐

**Encrypted & anonymous chat for your local network — right in the terminal.**

</div>

> **English · [Русский](#🇷🇺-русский) · [العربية](#🇸🇦-العربية)**

Anyone on the same LAN downloads this project and connects to a local
server to chat together. The server **cannot read anything you write**:
all messages are end-to-end encrypted, and real usernames are encrypted
too. Only you and your friends know the group passphrase.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔒 **End-to-end encryption** | AES (Fernet) with a key derived from a shared passphrase via PBKDF2-SHA256. The server only ever relays ciphertext. |
| 🕵️ **Anonymity** | The server never sees real names or message content. Users appear as random `ANON-XXXX` ids to the server. |
| 📡 **Auto-discovery** | No IP needed — clients find the server over UDP broadcast on the LAN. |
| 🌍 **3 languages** | English, Русский, العربية (choose with `--lang`). |
| 🎨 **Pretty terminal UI** | Colored names, box header, RTL-friendly, raw-mode input, `~/users`/`/clear` commands. |
| 📦 **Zero server setup** | Python stdlib + one dependency (`cryptography`). No database, no web server. |

---

## 📥 Install

```bash
# 1. install the only dependency
pip install -r requirements.txt
# or:  pip install cryptography
```

Requires **Python 3.8+**. Tested on Linux. Windows works with `--no-color`
(fallback input mode).

---

## 🚀 Quick start

### 1. Host the chat (one person on the LAN)

```bash
python3 server.py
#   Server started on 0.0.0.0:5555
```
Custom port / language:
```bash
python3 server.py --port 7777 --lang ru
```

### 2. Join the chat (everyone else on the same LAN)

```bash
python3 client.py                # auto-discovers the server
# or specify the server directly:
python3 client.py --host 192.168.1.10
```
Set your display name, then enter the **group passphrase** — it must be the
**same for everyone**. That passphrase is the key; without it nobody can read
the chat, including the server host.

Options:
```bash
python3 client.py --name Alice --lang ar --port 7777
python3 client.py --host 192.168.1.10 --no-color
```

### Commands (while chatting)

```
/exit   /quit   leave the chat
/users           show who is online (anonymous ids)
/clear           clear the screen
/help            show help
```

---

## 🔐 How it works

```
                 ┌────────────── NO ONE can read this ─────────────┐
  Bob  ──encrypt──▶  [ciphertext]  ──relay──▶  [ciphertext]  ──decrypt──▶  Alice
  Alice┘          📡 LAN Chat server (blind relay)                └── 💬 Server host
                        sees only: ANON-XXXX · AES ciphertext
```
- **Key**: PBKDF2-HMAC-SHA256, 200 000 iterations, from the shared passphrase.
- **Cipher**: AES-128-CBC via `cryptography`'s Fernet.
- **Server**: relays tokens, announces joins/leaves with anonymous ids,
  answers discovery broadcasts. It is a *blind relay*.
- **Per-session anonymity**: every connection gets a fresh random `ANON-*` id,
  so the server cannot even link two messages to the same person.

> ⚠️ **Security notes**: this is a trusted-friends LAN tool, not a review-hardened
> chat platform. The passphrase should be shared out-of-band. Keep duplicates low,
> passphrase strong.

---

## 🗂 Files

```
lan-chat/
├── server.py        # blind-relay TCP chat server (+ UDP discovery)
├── client.py        # pretty raw-mode terminal client
├── crypto.py        # PBKDF2 key derivation + AES (Fernet) encrypt/decrypt
├── i18n.py          # en / ru / ar translations
└── requirements.txt # cryptography
```

---

## 🧪 Testing

```bash
python3 server.py --port 5923 &
python3 client.py --host 127.0.0.1 --port 5923 --name Alice &
python3 client.py --host 127.0.0.1 --port 5923 --name Bob   &
```

---

## 📄 License

MIT. Free to use, fork and share.

---

# 🇷🇺 Русский

**LAN Chat** — зашифрованный и анонимный чат для локальной сети прямо в терминале.

Любой, кто скачает этот проект и подключится к локальному серверу, сможет общаться
с другими. **Сервер не видит ни одно слово:** все сообщения зашифрованы сквозным
шифрованием, а настоящие имена скрыты. Только вы и ваши друзья знаете общий пароль.

### Возможности
- 🔒 **Сквозное шифрование** — AES (Fernet), ключ из общего пароля через PBKDF2-SHA256. Сервер передаёт только шифротекст.
- 🕵️ **Анонимность** — сервер видит лишь случайные `ANON-XXXX` и шифрограммы, но не имена и не текст.
- 📡 **Автопоиск сервера** — указывать IP не нужно, клиенты находят сервер по UDP-рассылаемому сигналу.
- 🌍 **3 языка** — English, Русский, العربية (`--lang`).
- 🎨 **Красивый интерфейс в терминале** — цветные имена, рамка-шапка, raw-ввод, команды `/users`, `/clear`.

### Установка и запуск

```bash
pip install -r requirements.txt
```

**Хост (один человек в сети):**
```bash
python3 server.py                 # по умолчанию порт 5555
python3 server.py --port 7777 --lang ru
```

**Клиенты (все остальные):**
```bash
python3 client.py                 # автоопределение сервера
python3 client.py --host 192.168.1.10 --name Дима --lang ru
```
Введите своё имя и **общий пароль группы** — он одинаковый у всех. Без него
никто не сможет прочитать чат, даже владелец сервера.

### Команды
```
/exit  /quit  выйти из чата
/users         показать, кто онлайн (анонимные id)
/clear         очистить экран
/help          справка
```

---

# 🇸🇦 العربية

**دردشة الشبكة المحلية** — دردشة مشفرة ومجهولة لشبكتك المحلية مباشرة من الطرفية.

أي شخص يحمّل هذا المشروع يتصل بالخادم المحلي ويتحدث مع الآخرين. **الخادم لا يقرأ أي شيء:**
كل الرسائل مشفرة من طرف إلى طرف، والأسماء الحقيقية مخفية. أنت وأصدقاؤك فقط تعرفون
كلمة مرور المجموعة.

### المميزات
- 🔒 **تشفير من طرف إلى طرف** — AES (Fernet) بمفتاح مشتق من كلمة مرور مشتركة عبر PBKDF2-SHA256. الخادم يمرّر النص المشفر فقط.
- 🕵️ **إخفاء الهوية** — الخادم يرى فقط معرّفات عشوائية `ANON-XXXX` ولا يرى الأسماء أو الرسائل.
- 📡 **اكتشاف تلقائي** — لا حاجة لعنوان IP، يجد العملاء الخادم عبر بث UDP.
- 🌍 **3 لغات** — English, Русский, العربية (`--lang`).
- 🎨 **واجهة طرفية جميلة** — أسماء ملونة، إطار علوي، إدخال بأسلوب خام، أوامر `/users` و`/clear`.

### التثبيت والتشغيل

```bash
pip install -r requirements.txt
```

**المضيف (شخص واحد في الشبكة):**
```bash
python3 server.py                  # المنفذ الافتراضي 5555
python3 server.py --port 7777 --lang ar
```

**العملاء (كل الباقين):**
```bash
python3 client.py                  # اكتشاف تلقائي للخادم
python3 client.py --host 192.168.1.10 --name أحمد --lang ar
```
أدخل اسمك ثم **كلمة مرور المجموعة** — يجب أن تكون متطابقة عند الجميع. بدونها لا
يستطيع أحد قراءة الدردشة، حتى مشغّل الخادم.

### الأوامر
```
/exit  /quit  غادر الدردشة
/users         أظهر المتصلين الآن (معرّفات مجهولة)
/clear         امسح الشاشة
/help          المساعدة
```

---

Released under the [MIT License](LICENSE). Made with ♥ for local networks.