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
import colorsys
import getpass
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import sys
import threading
import time
import uuid

from i18n import Translator, LANGUAGES
from crypto import (new_fernet, encrypt, decrypt, encrypt_bin, decrypt_bin,
                    EncryptionError, derive_auth_verifier, derive_pin_verifier,
                    auth_hmac)

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


def stable_seed(text):
    """Deterministic hash across processes (hash() is randomized)."""
    return int.from_bytes(hashlib.md5(text.encode("utf-8")).digest()[:4],
                          "big")


def hsv_rgb(hue, sat=0.85, val=0.92):
    h1 = (hue % 360) / 360.0
    return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h1, sat, val))


def gradient_text(text, seed, spread=42):
    """Render text as a smooth hue gradient (truecolor)."""
    h0 = stable_seed(seed) % 360
    h1 = (h0 + spread) % 360
    n = max(1, len(text))
    out = []
    for i, ch in enumerate(text):
        t = i / (n - 1) if n > 1 else 0
        hue = h0 + (h1 - h0) * t
        r, g, b = hsv_rgb(hue)
        out.append(f"\033[38;2;{r};{g};{b}m{ch}")
    return "".join(out) + "\033[0m"


def truecolor():
    return os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")


def name_colored(name, seed):
    """Gradient name when supported, else the fixed palette color."""
    if truecolor():
        return gradient_text(name, seed)
    c = NAME_PALETTE[stable_seed(seed) % len(NAME_PALETTE)]
    return f"{FGC.format(c=c)}{name}\033[0m"


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def safe_name(path):
    return os.path.basename(path) or "file"


URL_RE = re.compile(r"https?://[^\s<>\"']+")

def highlight_urls(text, url_color="\033[96m"):
    """Wrap every URL in the message with the given color."""
    if url_color:
        return URL_RE.sub(lambda m: url_color + m.group(0) + "\033[0m", text)
    return text


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
            nl = (self.c("bold") + tag + " " + caret + " "
                  + name_colored(n, seed=name))
            msg = truncate(highlight_urls(text), max(10, self.width - len(n) - 4))
            line = nl + " " + msg
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
                    f"  {name_colored(name, seed=name)}: "
                    f"{truncate(highlight_urls(text), max(10, self.width - 6))}")
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

    def _discard_escape(self, fd, seq):
        """Read the rest of a CSI/SS3 escape sequence (arrow keys, etc.)
        and discard it so it never corrupts the input buffer."""
        import select as _select
        while True:
            final = 0x40 <= seq[-1] <= 0x7E
            prefix = seq in (b"\x1b[", b"\x1bO", b"\x1bP")
            if final and not prefix:
                return
            r, _, _ = _select.select([fd], [], [], 0.05)
            if not r:
                return
            try:
                b = os.read(fd, 1)
            except OSError:
                return
            if not b:
                return
            seq += b

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
                if ch == b"\x1b":
                    self._discard_escape(fd, b"\x1b")
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
                 group_key, lang, color, pin=None):
        self.tr = Translator(lang)
        self.ui = ChatUI(lang, color)
        self.fernet = new_fernet(group_key)
        self.auth_key = derive_auth_verifier(login, account_pass)
        self.pin = pin
        self.name = name
        self.login = login
        self.sock = None
        self.anon_id = None
        self.online = []
        self.running = True
        self.last_sender = None
        self.known_names = {}       # anon -> display name
        self.file_incoming = {}     # file_id -> state
        self.links = []             # collected URLs shown in chat

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
        status = self._authenticate()
        if status != "ok":
            if status == "blocked":
                self.ui.err(self.tr.t("admin_blocked"))
            else:
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
            return "bad"
        nonce = challenge[2:].strip()
        hmac_hex = auth_hmac(self.auth_key, nonce).hex()
        try:
            self.sock.sendall(f"A {self.login} {hmac_hex}\n".encode())
        except OSError:
            return "bad"
        resp = self._recv_line()
        if not resp:
            return "bad"
        if resp.startswith("P"):
            pin = self.pin or getpass.getpass(self.tr.t("pin_prompt") + " ")
            if not pin:
                return "bad"
            pin_verifier = derive_pin_verifier(self.login, pin)
            try:
                self.sock.sendall(f"K {auth_hmac(pin_verifier, nonce).hex()}\n"
                                  .encode())
            except OSError:
                return "bad"
            resp = self._recv_line()
        if not resp:
            return "bad"
        if resp.startswith("E B"):
            return "blocked"
        if not resp.startswith("I "):
            return "bad"
        self.anon_id = resp[2:].strip()
        self.is_admin = False
        self.admin_key = None
        if " K:" in resp:
            self.anon_id, _, keypart = resp[2:].partition(" K:")
            self.is_admin = True
            self.admin_key = keypart.strip()
        return "ok"

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

    def _receive_file(self, payload, sender=None):
        fid = payload["id"]
        if payload.get("i") is None:  # header
            state = {"fn": payload.get("fn", "file"), "chunks": payload["chunks"],
                     "size": payload["size"], "parts": {},
                     "anon": sender or getattr(self, "_last_anon", ""),
                     "sname": payload.get("n", sender or "???")}
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
        who = (state.get("sname") or state.get("anon")
               or self.known_names.get(state.get("anon", ""), "???"))
        self.ui.file_card(who, state["fn"], state.get("size", 0), path)

    # message handling ------------------------------------------------------

    def _collect_links(self, text):
        found = URL_RE.findall(text or "")
        for url in found:
            unique = url.rstrip(".,;:!?")
            if unique not in self.links:
                self.links.append(unique)

    def handle_payload(self, sender, payload):
        mtype = payload.get("t", "chat")
        name = payload.get("n", "???")
        if sender:
            self.known_names[sender] = name
        if mtype == "chat":
            text = payload.get("m", "")
            self._collect_links(text)
            if payload.get("to"):
                if payload["to"] in (self.name,) and name != self.name:
                    self.last_sender = name
                    c = NAME_PALETTE[hash(sender or name) % len(NAME_PALETTE)]
                    self.ui.private(name, text, c)
                return
            self.last_sender = name
            c = NAME_PALETTE[hash(sender or name) % len(NAME_PALETTE)]
            self.ui.message(name, text, c)
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
            self._receive_file(payload, sender)
        elif mtype == "fchunk":
            self._receive_file(payload, sender)
        elif mtype == "dm":
            to = payload.get("to")
            text = payload.get("m", "")
            self._collect_links(text)
            if to is None or to in (self.name,) and name != self.name:
                self.last_sender = name
                c = NAME_PALETTE[hash(sender or name) % len(NAME_PALETTE)]
                self.ui.private(name, text, c, reply=True)

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
        elif line.startswith("! "):
            self.ui.system(line[2:].strip(), "red")
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
            self._collect_links(msg)
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
            self._collect_links(msg)
            c = NAME_PALETTE[hash(self.last_sender) % len(NAME_PALETTE)]
            self.ui.private(self.last_sender, msg, c)
            return

        if cmd == "/send":
            if len(parts) < 2:
                self.ui.err("usage: /send <path>")
                return
            self.send_file(parts[1])
            return

        if cmd == "/open":
            self.open_link(parts)
            return

        if cmd == "/links":
            self.list_links()
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
        self._collect_links(line)
        self.ui.message(self.name, line, c, mine=True)
        try:
            self.send_json({"t": "chat", "n": self.name, "m": line})
        except OSError:
            self.ui.err(self.tr.t("disconnected"))
            self.running = False

    # lifecycle -------------------------------------------------------------

    def open_link(self, parts):
        """Open a link collected from chat (/open <number|url>)."""
        import shutil
        import subprocess
        if len(parts) >= 2:
            arg = " ".join(parts[1:]).strip()
            if URL_RE.fullmatch(arg):
                url = arg
            elif arg.isdigit():
                idx = int(arg) - 1
                if not (0 <= idx < len(self.links)):
                    self.ui.err(self.tr.t("links_empty"))
                    return
                url = self.links[idx]
            else:
                self.ui.err(self.tr.t("open_usage"))
                return
            opener = shutil.which("xdg-open") or shutil.which("open")
            if not opener:
                self.ui.info(self.tr.t("open_path", url=url))
                return
            subprocess.Popen([opener, url], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            self.ui.info(self.tr.t("opening", url=url))
            return
        self.list_links()

    def list_links(self):
        if not self.links:
            self.ui.err(self.tr.t("links_empty"))
            return
        rows = [f"{i + 1}) {url}" for i, url in enumerate(self.links[-20:])]
        self.ui.info(self.tr.t("links_header") + "\n" + "\n".join(rows)
                     + "\n" + self.tr.t("links_hint"))

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
    parser.add_argument("--pin", default=None,
                        help="second-factor PIN for admin accounts")
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
                        group_key, args.lang, not args.no_color, pin=args.pin)
    try:
        client.run(args.host, args.port)
    except KeyboardInterrupt:
        client.leave()
    except OSError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()