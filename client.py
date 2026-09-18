#!/usr/bin/env python3
"""LAN Chat client (encrypted, anonymous, pretty terminal UI).

Connects to a LAN Chat server, either directly with --host or by
auto-discovery (UDP broadcast). All messages are end-to-end encrypted
with a shared passphrase; the server never sees what you write.

Commands (type at the prompt):
    /dm <name> <msg>      private message
    /r <msg>              reply to the last sender
    /send <path>          send a file (photos, documents...)
    /users                show who is online
    /nick <name>          change display name
    /passwd <password>    change account password
    /rename <login>       change account login
    /register <l> <p>     register a new account
    /clear /help /exit
"""

import argparse
import getpass
import json
import os
import shlex
import shutil
import socket
import sys
import threading
import time
import uuid

from i18n import Translator, LANGUAGES
from crypto import (new_fernet, encrypt, decrypt, encrypt_bin, decrypt_bin,
                    EncryptionError, derive_auth_verifier, auth_hmac)

DISCOVERY_PORT_OFFSET = 1000
MAGIC = "LANCHAT_DISCOVERY"
DISCOVERY_TIMEOUT = 2.0
FILE_CHUNK = 20000
MAX_FILE = 20 * 1024 * 1024
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")

COLORS = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "cyan": "\033[96m", "yellow": "\033[93m", "red": "\033[91m",
    "green": "\033[92m", "magenta": "\033[95m", "blue": "\033[94m",
}
NAME_PALETTE = [33, 34, 35, 36, 37, 91, 92, 96, 94, 95]
FGC = "\033[38;5;{c}m"
BOX_TL, BOX_TR, BOX_BL, BOX_BR, BOX_H, BOX_V, HEART = (
    "\u250c", "\u2510", "\u2514", "\u2518", "\u2500", "\u2502", "\u2665",
)


def truncate(text, width):
    if len(text) <= width:
        return text
    return text[: width - 1] + "\u2026"


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def safe_name(path):
    return os.path.basename(path) or "file"


class ChatUI:
    def __init__(self, lang, color=True):
        self.tr = Translator(lang)
        self.color = color and sys.stdout.isatty()
        self.prompt = "\u276f "
        self.buffer = ""
        self.lock = threading.Lock()
        self.width = shutil.get_terminal_size((80, 24)).columns

    def c(self, name):
        return COLORS[name] if self.color else ""

    def clear_line(self):
        sys.stdout.write("\r\033[2K")
        sys.stdout.flush()

    def _write(self, s):
        with self.lock:
            self.clear_line()
            sys.stdout.write(s + "\n")
            sys.stdout.flush()
            self._render_prompt()

    def _render_prompt(self):
        line = truncate(self.prompt + self.buffer, self.width)
        sys.stdout.write(line + self.c("reset"))
        sys.stdout.flush()

    def draw_header(self, host, port, login, lang_name):
        w = min(self.width, 54)
        sep = BOX_H * (w - 2)
        head = (
            f"{self.c('cyan')}{BOX_TL}{sep}{BOX_TR}{self.c('reset')}\n"
            f"{self.c('cyan')}{BOX_V}{self.c('reset')}"
            f"  {self.c('bold')}{self.c('cyan')}LAN CHAT {HEART}"
            f"{self.c('reset')}\n"
            f"{self.c('cyan')}{BOX_V}{self.c('reset')}  "
            f"{self.c('dim')}{host}:{port}  ·  {login}{self.c('reset')}\n"
            f"{self.c('cyan')}{BOX_TL}{sep}{BOX_TR}{self.c('reset')}\n"
        )
        with self.lock:
            sys.stdout.write(head)
            sys.stdout.flush()
        self.info(self.tr.t("welcome"))
        self.info(self.tr.t("connected", host=host, port=port))
        self.info(self.tr.t("type_exit"))

    def info(self, msg):
        self._write(f"{self.c('dim')}{msg}{self.c('reset')}")

    def system(self, msg, color="yellow"):
        self._write(f"{self.c(color)}\u2699 {msg}{self.c('reset')}")

    def err(self, msg):
        self._write(f"{self.c('red')}\u2718 {msg}{self.c('reset')}")

    def message(self, name, text, name_color, mine=False, private=False):
        n = truncate(name, 22)
        if self.color:
            caret = "\u27a4" if mine else "\u25c6"
            tag = "🔒" if private else ""
            nl = f"{FGC.format(c=name_color)}{self.c('bold')}{tag} {caret} {n}"
            msg = truncate(text, max(10, self.width - len(n) - 4))
            line = nl + self.c("reset") + " " + msg
        else:
            tag = "you" if mine else (f"priv {n}" if private else n)
            line = f"\u25c6 {tag}: {text}"
        self._write(line + self.c("reset"))

    def private(self, name, text, name_color, reply=False, mine=False):
        label = self.tr.t(
            "dm_sent" if mine else ("reply_received" if reply else "dm_received"),
            name=name)
        if self.color:
            line = (f"{self.c('magenta')}\u27a1 {self.c('bold')}"
                    f"🔒 {self.c('reset')}"
                    f"{self.c('magenta')}{truncate(label, 30)}"
                    f"{self.c('reset')}\n"
                    f"  {FGC.format(c=name_color)}{self.c('bold')}{name}"
                    f"{self.c('reset')}: {truncate(text, max(10, self.width - 6))}")
        else:
            line = f"🔒 {label}: {text}"
        self._write(line)

    def file_card(self, sender, fn, size, path):
        if self.color:
            label = f"{self.c('bold')}{self.c('cyan')}\U0001f4e6 {sender}"
            f"{self.c('reset')} · {fn} ({human_size(size)})"
            if path:
                label += (f"\n  {self.c('green')}saved{self.c('reset')} → "
                          f"{self.c('dim')}{path}{self.c('reset')}")
            self._write(label)
        else:
            line = f"\U0001f4e6 {sender} file {fn} ({human_size(size)})"
            if path:
                line += f" saved → {path}"
            self._write(line)

    def joined(self, name):
        msg = self.tr.t("joined_msg", name=name)
        self._write(f"{self.c('green')}\u25b8 {msg}{self.c('reset')}")

    def left(self, name):
        msg = self.tr.t("left_msg", name=name)
        self._write(f"{self.c('red')}\u25c2 {msg}{self.c('reset')}")

    def read_line(self):
        self.buffer = ""
        self._render_prompt()

        if sys.platform == "win32":
            try:
                line = sys.stdin.readline()
                return line.rstrip("\n")
            except (EOFError, KeyboardInterrupt):
                return None

        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        pending = b""
        try:
            tty.setraw(fd)
            while True:
                ch = os.read(fd, 1)
                if not ch:
                    return None
                if ch == b"\x03":
                    for _ in range(4):
                        sys.stdout.write("\a")
                    sys.stdout.flush()
                    continue
                pending += ch
                if ch in (b"\r", b"\n"):
                    return self.buffer
                if ch == b"\x7f":
                    if pending == b"\x7f":
                        if self.buffer:
                            self.buffer = self.buffer[:-1]
                        pending = b""
                        self._reprint_prompt()
                    else:
                        sys.stdout.write("\a")
                        sys.stdout.flush()
                        pending = b""
                    continue
                while pending:
                    try:
                        text = pending.decode("utf-8")
                        pending = b""
                        self.buffer += text
                        break
                    except UnicodeDecodeError as e:
                        if e.reason == "unexpected end of data":
                            break
                        self.buffer += "\ufffd"
                        pending = pending[1:]
                self._reprint_prompt()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def _reprint_prompt(self):
        with self.lock:
            self.clear_line()
            self._render_prompt()


class ChatClient:
    def __init__(self, host, port, name, login, account_pass,
                 group_key, lang, color):
        self.tr = Translator(lang)
        self.ui = ChatUI(lang, color)
        self.fernet = new_fernet(group_key)
        self.auth_key = derive_auth_verifier(login, account_pass)
        self.name = name
        self.login = login
        self.sock = None
        self.anon_id = None
        self.online = []
        self.running = True
        self.last_sender = None
        self.known_names = {}       # anon -> display name
        self.file_incoming = {}     # file_id -> state

    # networking ------------------------------------------------------------

    def connect(self, host, port):
        if host:
            self._tcp_connect(host, port)
        else:
            found = self._discover(port)
            if not found:
                self.ui.err(self.tr.t("server_not_found"))
                return False
            self.ui._write("")
            self._tcp_connect(*found)
        self.sock.settimeout(None)
        if not self._authenticate():
            self.ui.err(self.tr.t("wrong_credentials"))
            try:
                self.sock.close()
            except OSError:
                pass
            return False
        self.ui.draw_header(host or self._shown_host, port,
                            self.login, self.tr.t("language_name"))
        return True

    def _recv_line(self, timeout=8):
        self.sock.settimeout(timeout)
        buf = b""
        try:
            while b"\n" not in buf:
                chunk = self.sock.recv(4096)
                if not chunk:
                    return None
                buf += chunk
            line, _ = buf.split(b"\n", 1)
            return line.decode("utf-8", "replace").strip()
        except OSError:
            return None
        finally:
            self.sock.settimeout(None)

    def _authenticate(self):
        challenge = self._recv_line()
        if not challenge or not challenge.startswith("H "):
            return False
        nonce = challenge[2:].strip()
        hmac_hex = auth_hmac(self.auth_key, nonce).hex()
        try:
            self.sock.sendall(f"A {self.login} {hmac_hex}\n".encode())
        except OSError:
            return False
        resp = self._recv_line()
        if not resp or not resp.startswith("I "):
            return False
        self.anon_id = resp[2:].strip()
        return True

    def _tcp_connect(self, host, port):
        self._shown_host = host
        self.sock = socket.create_connection((host, port), timeout=5)
        self.sock.settimeout(None)

    def _discover(self, port):
        dport = port + DISCOVERY_PORT_OFFSET
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(DISCOVERY_TIMEOUT)
        s.bind(("", 0))
        s.sendto(MAGIC.encode(), ("255.255.255.255", dport))
        results = []
        try:
            while True:
                data, addr = s.recvfrom(1024)
                if data.decode().strip() == str(port):
                    results.append((addr[0], port))
                    break
        except socket.timeout:
            pass
        finally:
            s.close()
        return results[0] if results else None

    def send_json(self, obj):
        token = encrypt(self.fernet, json.dumps(obj, ensure_ascii=False))
        self.sock.sendall(f"M {token}\n".encode("utf-8"))

    def send_line(self, line):
        self.sock.sendall((line + "\n").encode("utf-8"))

    def request_users(self):
        try:
            self.send_line("L")
        except OSError:
            pass

    # file transfer ---------------------------------------------------------

    def send_file(self, path):
        path = os.path.expanduser(path)
        if not os.path.isfile(path):
            self.ui.err(self.tr.t("file_missing", path=path))
            return
        size = os.path.getsize(path)
        if size > MAX_FILE:
            self.ui.err(self.tr.t("file_too_big", size=human_size(size)))
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            self.ui.err(self.tr.t("file_error", error=e))
            return
        chunks = [data[i:i + FILE_CHUNK] for i in range(0, len(data), FILE_CHUNK)]
        fid = uuid.uuid4().hex[:12]
        self.send_json({"t": "file", "n": self.name, "fn": safe_name(path),
                        "size": len(data), "chunks": len(chunks), "id": fid})
        for i, c in enumerate(chunks):
            token = encrypt_bin(self.fernet, c)
            self.send_json({"t": "fchunk", "id": fid, "i": i, "d": token})
        self.ui.file_card(self.name, safe_name(path), len(data), "")
        self.ui.info(self.tr.t("file_sent", name=safe_name(path),
                               size=human_size(len(data))))

    def _receive_file(self, payload):
        fid = payload["id"]
        if payload.get("i") is None:  # header
            state = {"fn": payload.get("fn", "file"), "chunks": payload["chunks"],
                     "size": payload["size"], "parts": {}}
            self.file_incoming[fid] = state
            return
        state = self.file_incoming.get(fid)
        if not state:
            return
        try:
            bytes_ = decrypt_bin(self.fernet, payload["d"])
        except EncryptionError as e:
            self.ui.err(self.tr.t("file_error", error=e))
            return
        state["parts"][payload["i"]] = bytes_
        if len(state["parts"]) >= state["chunks"]:
            self._finish_file(fid, state)

    def _finish_file(self, fid, state):
        self.file_incoming.pop(fid, None)
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        fn = safe_name(state["fn"])
        path = os.path.join(DOWNLOADS_DIR, fn)
        if os.path.exists(path):
            stem, ext = os.path.splitext(fn)
            path = os.path.join(DOWNLOADS_DIR,
                                f"{stem}-{fid[:6]}{ext}")
        try:
            with open(path, "wb") as f:
                for i in range(state["chunks"]):
                    f.write(state["parts"][i])
        except (OSError, KeyError) as e:
            self.ui.err(self.tr.t("file_error", error=e))
            return
        who = self.known_names.get(getattr(self, "_last_anon", ""), "?")
        self.ui.file_card(who, state["fn"], state["size"], path)

    # message handling ------------------------------------------------------

    def handle_payload(self, sender, payload):
        mtype = payload.get("t", "chat")
        name = payload.get("n", "???")
        if sender:
            self.known_names[sender] = name
        if mtype == "chat":
            if payload.get("to"):
                if payload["to"] in (self.name,) and name != self.name:
                    self.last_sender = name
                    c = NAME_PALETTE[hash(sender or name) % len(NAME_PALETTE)]
                    self.ui.private(name, payload.get("m", ""), c)
                return
            self.last_sender = name
            c = NAME_PALETTE[hash(sender or name) % len(NAME_PALETTE)]
            self.ui.message(name, payload.get("m", ""), c)
        elif mtype == "join":
            self.ui.joined(name)
        elif mtype == "leave":
            self.ui.left(name)
        elif mtype == "nick":
            old, new = payload.get("n"), payload.get("to")
            if sender:
                self.known_names[sender] = new
            if old == self.name:
                self.name = new
            self.ui.system(self.tr.t("nick_set_by", old=old, new=new))
        elif mtype == "file":
            self._receive_file(payload)
        elif mtype == "fchunk":
            self._receive_file(payload)
        elif mtype == "dm":
            to = payload.get("to")
            if to is None or to in (self.name,) and name != self.name:
                self.last_sender = name
                c = NAME_PALETTE[hash(sender or name) % len(NAME_PALETTE)]
                self.ui.private(name, payload.get("m", ""), c, reply=True)

    def handle_line(self, line):
        if line.startswith("D "):
            parts = line.split(" ", 2)
            if len(parts) < 3:
                return
            sender, token = parts[1], parts[2]
            self._last_anon = sender
            try:
                payload = json.loads(decrypt(self.fernet, token))
            except EncryptionError as e:
                self.ui.err(str(e))
                return
            self.handle_payload(sender, payload)
        elif line.startswith("X "):
            anon = line[2:].strip()
            self.ui.system(self.tr.t("anon_left_msg"), "red")
        elif line.startswith("U "):
            self.online = line[2:].split()
            self.ui.system(self.tr.t("online") + " " + ", ".join(self.online))
        elif line.startswith("OKR"):
            login = line.split(" ", 1)[1] if " " in line else "?"
            self.ui.system(self.tr.t("register_ok", login=login), "green")
        elif line.startswith("ERRR"):
            reason = line.split(" ", 1)[1] if " " in line else "?"
            self.ui.err(self.tr.t("register_fail", reason=reason))
        elif line.startswith("OKPW"):
            self.ui.system(self.tr.t("passwd_changed"), "green")
        elif line.startswith("OKRN"):
            new_login = line.split(" ", 1)[1] if " " in line else "?"
            self.login = new_login
            self.ui.system(self.tr.t("rename_ok", login=new_login), "green")
        elif line.startswith("ERR"):
            self.ui.err(self.tr.t("rename_fail", reason="ERR"))

    def receiver(self):
        buf = b""
        try:
            while self.running:
                data = self.sock.recv(65536)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self.handle_line(line.decode("utf-8", "replace").strip())
        except OSError:
            pass
        if self.running:
            self.ui.err(self.tr.t("disconnected"))
            self.running = False

    # commands --------------------------------------------------------------

    def handle_command(self, text):
        line = text.strip()
        if not line:
            return
        if line in ("/exit", "/quit"):
            self.running = False
            return
        if line == "/users":
            self.request_users()
            return
        if line == "/clear":
            os.system("clear" if os.name == "posix" else "cls")
            self.ui.draw_header(self._shown_host, self.sock.getpeername()[1],
                                self.login, self.tr.t("language_name"))
            return
        if line == "/help":
            self.ui.info(self.tr.t("help"))
            return

        parts = shlex.split(line)
        cmd = parts[0] if parts else ""

        if cmd == "/nick":
            if len(parts) < 2:
                self.ui.err(self.tr.t("nick_empty"))
                return
            old, new = self.name, parts[1]
            self.send_json({"t": "nick", "n": old, "to": new})
            self.name = new
            self.ui.system(self.tr.t("nick_changed", name=new), "green")
            return

        if cmd in ("/dm", "/msg"):
            if len(parts) < 3:
                self.ui.err(self.tr.t("dm_user_unknown", name="?"))
                return
            target, msg = parts[1], " ".join(parts[2:])
            if target == self.name:
                self.ui.err(self.tr.t("dm_to_yourself"))
                return
            names = set(self.known_names.values())
            if target not in names:
                self.ui.err(self.tr.t("dm_user_unknown", name=target))
                return
            self.send_json({"t": "chat", "n": self.name, "m": msg,
                            "to": target})
            c = NAME_PALETTE[hash(target) % len(NAME_PALETTE)]
            self.ui.private(target, msg, c, mine=True)
            return

        if cmd == "/r":
            if not self.last_sender or self.last_sender == self.name:
                self.ui.err(self.tr.t("dm_user_unknown", name="?"))
                return
            msg = " ".join(parts[1:]) if len(parts) > 1 else ""
            if not msg:
                self.ui.err(self.tr.t("dm_user_unknown", name="?"))
                return
            self.send_json({"t": "chat", "n": self.name, "m": msg,
                            "to": self.last_sender})
            c = NAME_PALETTE[hash(self.last_sender) % len(NAME_PALETTE)]
            self.ui.private(self.last_sender, msg, c)
            return

        if cmd == "/send":
            if len(parts) < 2:
                self.ui.err("usage: /send <path>")
                return
            self.send_file(parts[1])
            return

        if cmd == "/passwd":
            if len(parts) < 2:
                self.ui.err(self.tr.t("passwd_usage"))
                return
            self.send_line(f"PW {parts[1]}")
            return

        if cmd == "/rename":
            if len(parts) < 2:
                self.ui.err(self.tr.t("rename_usage"))
                return
            self.send_line(f"RN {parts[1]}")
            return

        if cmd == "/register":
            if len(parts) < 3:
                self.ui.err(self.tr.t("register_usage"))
                return
            self.send_line(f"R {parts[1]} {parts[2]}")
            return

        if line.startswith("/"):
            self.ui.err(self.tr.t("unknown_cmd", cmd=line))
            return

        c = NAME_PALETTE[hash(self.name) % len(NAME_PALETTE)]
        self.ui.message(self.name, line, c, mine=True)
        try:
            self.send_json({"t": "chat", "n": self.name, "m": line})
        except OSError:
            self.ui.err(self.tr.t("disconnected"))
            self.running = False

    # lifecycle -------------------------------------------------------------

    def run(self, host, port):
        if not self.connect(host, port):
            return
        self.send_json({"t": "join", "n": self.name, "m": ""})
        threading.Thread(target=self.receiver, daemon=True).start()
        try:
            while self.running:
                line = self.ui.read_line()
                if line is None:
                    break
                self.handle_command(line)
        finally:
            self.leave()

    def leave(self):
        if not self.running:
            try:
                self.send_json({"t": "leave", "n": self.name, "m": ""})
            except OSError:
                pass
        self.running = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
        print()


def main():
    parser = argparse.ArgumentParser(
        description="LAN Chat client - encrypted & anonymous chat."
    )
    parser.add_argument("--host", default=None,
                        help="server IP (omit to auto-discover on LAN)")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--name", default=None,
                        help="your display name (default: random)")
    parser.add_argument("--lang", default="en", choices=LANGUAGES)
    parser.add_argument("--login", default=None,
                        help="account login from users.json")
    parser.add_argument("--pass", dest="account_pass", default=None,
                        help="account password (alternative to prompt)")
    parser.add_argument("--groupkey", default=None,
                        help="shared group passphrase for E2E encryption")
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args()

    tr = Translator(args.lang)

    login = args.login or input(tr.t("enter_login") + " ").strip()
    account_pass = args.account_pass or getpass.getpass(
        tr.t("enter_account_pass") + " ")
    group_key = args.groupkey or getpass.getpass(
        tr.t("enter_groupkey") + " ")

    if not args.name:
        args.name = login

    client = ChatClient(args.host, args.port, args.name, login, account_pass,
                        group_key, args.lang, not args.no_color)
    try:
        client.run(args.host, args.port)
    except KeyboardInterrupt:
        client.leave()
    except OSError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()