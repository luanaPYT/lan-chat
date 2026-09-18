#!/usr/bin/env python3
"""LAN Chat client (encrypted, anonymous, pretty terminal UI).

Connects to a LAN Chat server, either directly with --host or by
auto-discovery (UDP broadcast). All messages are end-to-end encrypted
with a shared passphrase; the server never sees what you write.

Usage:
    python3 client.py [--host 192.168.1.10] [--port 5555]
                      [--name Alice] [--lang en|ru|ar]
                      [--no-color] [--pass <passphrase>]

Commands (type at the prompt):
    /exit , /quit     leave the chat
    /users            show who is online (anonymous ids)
    /clear            clear the screen
    /help             show this help
"""

import argparse
import getpass
import json
import os
import shutil
import socket
import struct
import sys
import threading
import time

from i18n import Translator, LANGUAGES
from crypto import (new_fernet, encrypt, decrypt, EncryptionError,
                    derive_auth_verifier, auth_hmac)

DISCOVERY_PORT_OFFSET = 1000
MAGIC = "LANCHAT_DISCOVERY"
DISCOVERY_TIMEOUT = 2.0

# --- ANSI helpers -----------------------------------------------------------

COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "cyan": "\033[96m",
    "yellow": "\033[93m",
    "red": "\033[91m",
    "green": "\033[92m",
    "magenta": "\033[95m",
}

NAME_PALETTE = [33, 34, 35, 36, 37, 91, 92, 96, 94, 95]  # 256-color
BGC = "\033[48;5;{c}m"   # true color bg
FGC = "\033[38;5;{c}m"

BOX_TL, BOX_TR, BOX_BL, BOX_BR, BOX_H, BOX_V, HEART = (
    "\u250c", "\u2510", "\u2514", "\u2518", "\u2500", "\u2502", "\u2665",
)


def truncate(text, width):
    if len(text) <= width:
        return text
    return text[: width - 1] + "\u2026"


class ChatUI:
    """Minimal raw-mode terminal UI: message area + input prompt line."""

    def __init__(self, lang, color=True):
        self.tr = Translator(lang)
        self.color = color and sys.stdout.isatty()
        self.prompt = "\u276f "  # ❯
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

    # public API ------------------------------------------------------------

    def draw_header(self, host, port, lang_name):
        w = min(self.width, 58)
        sep = BOX_H * (w - 2)
        pad = w - 2 - 8  # len("LAN CHAT")
        left = max(0, pad // 2)
        right = max(0, pad - left)
        head = (
            f"{self.c('cyan')}{BOX_TL}{sep}{BOX_TR}{self.c('reset')}\n"
            f"{self.c('cyan')}{BOX_V}{self.c('reset')}"
            f"{' ' * left}{self.c('bold')}{self.c('cyan')}LAN CHAT"
            f" {HEART} {self.c('reset')}{' ' * right}"
            f"{self.c('cyan')}{BOX_V}{self.c('reset')}\n"
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

    def system(self, msg):
        self._write(f"{self.c('yellow')}\u2699 {msg}{self.c('reset')}")

    def err(self, msg):
        self._write(f"{self.c('red')}\u2718 {msg}{self.c('reset')}")

    def message(self, name, text, name_color, highlight=False, mine=False):
        n = truncate(name, 22)
        if self.color:
            caret = "\u27a4" if mine else "\u25c6"
            nl = f"{FGC.format(c=name_color)}{self.c('bold')} {caret} {n}"
            msg = truncate(text, max(10, self.width - len(n) - 4))
            line = nl + self.c("reset") + " " + msg
        else:
            tag = "you" if mine else n
            line = f"\u25c6 {tag}: {text}"
        self._write(line + self.c("reset"))

    def joined(self, name):
        msg = self.tr.t("joined_msg", name=name)
        self._write(f"{self.c('green')}\u25b8 {msg}{self.c('reset')}")

    def left(self, name):
        msg = self.tr.t("left_msg", name=name)
        self._write(f"{self.c('red')}\u25c2 {msg}{self.c('reset')}")

    # raw line input --------------------------------------------------------

    def read_line(self):
        """Read one UTF-8 line from the terminal in raw mode."""
        self.buffer = ""
        self._render_prompt()

        if sys.platform == "win32":
            # basic fallback for Windows (no raw mode)
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
                if ch == b"\x03":  # Ctrl+C
                    for _ in range(4):
                        sys.stdout.write("\a")
                    sys.stdout.flush()
                    continue
                pending += ch
                if ch in (b"\r", b"\n"):
                    return self.buffer
                if ch == b"\x7f":  # backspace
                    if pending == b"\x7f":
                        from_cell = self.buffer[-1:] if self.buffer else ""
                        if from_cell:
                            self.buffer = self.buffer[:-1]
                        pending = b""
                        self._reprint_prompt()
                    else:
                        sys.stdout.write("\a")
                        sys.stdout.flush()
                        pending = b""
                    continue
                # decode fully-arrived utf-8 chars
                while pending:
                    try:
                        text = pending.decode("utf-8")
                        pending = b""
                        self.buffer += text
                        break
                    except UnicodeDecodeError as e:
                        if e.reason == "unexpected end of data":
                            break  # wait for more bytes
                        # invalid byte -> emit replacement and continue
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
                            self.tr.t("language_name"))
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

    def request_users(self):
        try:
            self.sock.sendall(b"L\n")
        except OSError:
            pass

    # message handlers ------------------------------------------------------

    def handle_line(self, line):
        if line.startswith("D "):
            parts = line.split(" ", 2)
            if len(parts) < 3:
                return
            sender, token = parts[1], parts[2]
            try:
                payload = json.loads(decrypt(self.fernet, token))
            except EncryptionError as e:
                self.ui.err(str(e))
                return
            mtype = payload.get("t", "chat")
            name = payload.get("n", "???")
            text = payload.get("m", "")
            if mtype == "chat":
                c = NAME_PALETTE[hash(sender or name) % len(NAME_PALETTE)]
                self.ui.message(name, text, c, highlight=(name == self.name))
            elif mtype == "join":
                self.ui.joined(name)
            elif mtype == "leave":
                self.ui.left(name)
        elif line.startswith("X "):
            self.ui.system(self.tr.t("anon_left_msg"))
        elif line.startswith("U "):
            self.online = line[2:].split()
            self.ui.system(self.tr.t("online") + " " + ", ".join(self.online))

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

    # main loop -------------------------------------------------------------

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
                                self.tr.t("language_name"))
            return
        if line == "/help":
            self.ui.info(self.tr.t("help"))
            return
        if line.startswith("/"):
            self.ui.err(self.tr.t("unknown_cmd", cmd=line))
            return
        c = NAME_PALETTE[hash(self.name) % len(NAME_PALETTE)]
        self.ui.message(self.name, line, c, highlight=True, mine=True)
        try:
            self.send_json({"t": "chat", "n": self.name, "m": line})
        except OSError:
            self.ui.err(self.tr.t("disconnected"))
            self.running = False

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

    name = args.name
    if not name:
        name = input(tr.t("enter_name") + " ")
        name = name.strip() or "Ghost_" + os.urandom(2).hex().upper()

    login = args.login or input(tr.t("enter_login") + " ").strip()
    account_pass = args.account_pass or getpass.getpass(
        tr.t("enter_account_pass") + " ")
    group_key = args.groupkey or getpass.getpass(
        tr.t("enter_groupkey") + " ")

    client = ChatClient(args.host, args.port, name, login, account_pass,
                        group_key, args.lang, not args.no_color)
    try:
        client.run(args.host, args.port)
    except KeyboardInterrupt:
        client.leave()
    except OSError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()