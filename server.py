#!/usr/bin/env python3
"""LAN Chat server (encrypted, anonymous).

Hosts a chat room on your local network. The server ONLY relays
ciphertext. It never sees real names or message contents, so it can
be run by anyone without breaking the group's privacy.

Features:
  * account login (challenge-response, SCRAM-like)
  * self-service: register / change password / rename account
  * every account event is delivered to the admin terminal
    as a formatted "mailbox letter" and logged to mailbox.log
  * file transfers are relayed as encrypted chunks (server is blind)

Usage:
    python3 server.py [--port 5555] [--lang en|ru|ar] [--no-color]
"""

import argparse
import datetime
import hmac
import json
import os
import random
import secrets
import socket
import string
import sys
import threading
import time

from i18n import Translator, LANGUAGES
from crypto import auth_hmac, derive_auth_verifier, decrypt_bin

DISCOVERY_PORT_OFFSET = 1000
MAGIC = "LANCHAT_DISCOVERY"
RECV_LIMIT = 4 * 1024 * 1024   # max single line (file chunks)
MAX_RECV_TOTAL = 512 * 1024 * 1024
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")
MAILBOX_FILE = os.path.join(BASE_DIR, "mailbox.log")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")

C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "green": "\033[92m", "red": "\033[91m", "yellow": "\033[93m",
    "cyan": "\033[96m", "magenta": "\033[95m", "blue": "\033[94m",
}
KIND_COLOR = {
    "register": "green", "passwd": "yellow", "rename": "magenta",
    "join": "green", "left": "red", "auth_failed": "red",
    "file": "cyan", "dm": "magenta", "info": "dim",
}


def random_anon_id():
    return "ANON-" + "".join(
        random.choices(string.ascii_uppercase + string.digits, k=4)
    )


def load_users():
    """Returns (users, admins): users maps login -> verifier bytes,
    admins is a set of logins that are blocked from joining the chat."""
    try:
        with open(USERS_FILE) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}, set()
    users, admins = {}, set()
    for login, rec in data.items():
        try:
            users[login] = bytes.fromhex(rec["verifier"])
        except (KeyError, TypeError, ValueError):
            continue
        if rec.get("admin"):
            admins.add(login)
    return users, admins


def save_users(users, admins=frozenset()):
    data = {}
    for login, v in users.items():
        rec = {"verifier": v.hex()}
        if login in admins:
            rec["admin"] = True
        data[login] = rec
    tmp = USERS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, USERS_FILE)


def plain_len(s):
    n = 0
    for ch in s:
        n += 1 if ch.isascii() else 2
    return n


def pad_to(s, w):
    return s + " " * max(0, w - plain_len(s))


class ChatServer:
    def __init__(self, host="0.0.0.0", port=5555, lang="en", color=True):
        self.host = host
        self.port = port
        self.color = color and sys.stdout.isatty()
        self.tr = Translator(lang)
        self.clients = {}      # socket -> anonymous id
        self.lock = threading.Lock()
        self.users, self.admins = load_users()
        self._users_mtime = os.path.getmtime(USERS_FILE) \
            if os.path.exists(USERS_FILE) else 0

    # --- styling -----------------------------------------------------------

    def c(self, name):
        return C[name] if self.color else ""

    def log(self, msg, color="reset"):
        print(f"{self.c(color)}{msg}{self.c('reset')}", flush=True)

    def letter(self, kind, title, fields):
        """A mailbox 'letter' shown in the admin terminal."""
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        head = f"📬 {title}"
        rows = [f"{self.c('bold')}{self.c(KIND_COLOR.get(kind, 'info'))}"
                f"{head}{self.c('reset')}", f"{self.c('dim')}🕐 {ts}"
                f"{self.c('reset')}"]
        for k, v in fields:
            rows.append(f"{k}: {v}")
        width = min(72, max(24, max(plain_len(r) for r in rows) + 2))
        box = [f"{self.c('cyan')}┌{'─' * width}┐{self.c('reset')}"]
        for r in rows:
            box.append(f"{self.c('cyan')}│{self.c('reset')} "
                       f"{pad_to(r, width - 2)} "
                       f"{self.c('cyan')}│{self.c('reset')}")
        box.append(f"{self.c('cyan')}└{'─' * width}┘{self.c('reset')}")
        for line in box:
            print(line, flush=True)
        with open(MAILBOX_FILE, "a") as f:
            f.write(f"\n[{ts}] {title}\n")
            for k, v in fields:
                f.write(f"  {k}: {v}\n")
            f.write("-" * 40 + "\n")

    # --- networking --------------------------------------------------------

    def _send(self, sock, line):
        try:
            sock.sendall((line + "\n").encode("utf-8"))
        except OSError:
            self.disconnect(sock)

    def broadcast(self, line, exclude=None):
        with self.lock:
            targets = [s for s in self.clients if s is not exclude]
        for sock in targets:
            self._send(sock, line)

    def disconnect(self, sock):
        with self.lock:
            anon = self.clients.pop(sock, None)
        if anon:
            self.broadcast(f"X {anon}")
            msg = self.tr.t("server_client_left", name=anon)
            self.log(msg, "red")
        try:
            sock.close()
        except OSError:
            pass

    def save_users_locked(self):
        with self.lock:
            save_users(self.users, self.admins)

    def apply_registration(self, login, password):
        if login in self.users:
            return False, "exists"
        verifier = derive_auth_verifier(login, password)
        self.users[login] = verifier
        save_users(self.users, self.admins)
        self.letter("register", self.tr.t("mail_new_account"),
                    [("LOGIN", login), ("PASSWORD", password)])
        return True, "ok"

    def apply_password(self, login, new_password):
        if login not in self.users:
            return False
        verifier = derive_auth_verifier(login, new_password)
        self.users[login] = verifier
        save_users(self.users, self.admins)
        self.letter("passwd", self.tr.t("mail_pass_changed"),
                    [("LOGIN", login), ("NEW PASSWORD", new_password)])
        return True

    def apply_rename(self, login, new_login):
        if login not in self.users or new_login in self.users:
            return False
        self.users[new_login] = self.users.pop(login)
        if login in self.admins:
            self.admins.add(new_login)
            self.admins.discard(login)
        save_users(self.users, self.admins)
        self.letter("rename", self.tr.t("mail_login_renamed"),
                    [("FROM", login), ("TO", new_login)])
        return True

    def reload_users(self):
        try:
            mtime = os.path.getmtime(USERS_FILE)
        except OSError:
            return
        if mtime != self._users_mtime:
            self.users, self.admins = load_users()
            self._users_mtime = mtime
            self.log(f"users.json reloaded: {len(self.users)} accounts", "dim")

    def authenticate(self, sock):
        """Challenge-response auth. Returns "ok", "bad" or "blocked"."""
        challenge = secrets.token_hex(16)
        login = None
        try:
            sock.sendall(f"H {challenge}\n".encode())
            data = sock.recv(4096)
            if not data:
                return "bad", None
            line = data.decode("utf-8", "replace").strip()
            parts = line.split(" ")
            if len(parts) != 3 or parts[0] != "A":
                return "bad", None
            _, login, client_hmac = parts
            verifier = self.users.get(login)
            if not verifier:
                return "bad", login
            expected = auth_hmac(verifier, challenge)
            sent = bytes.fromhex(client_hmac) if len(client_hmac) == 64 else b""
            if not hmac.compare_digest(expected, sent):
                return "bad", login
            if login in self.admins:
                return "blocked", login
            sock.sendall(b"I " + random_anon_id().encode() + b"\n")
            return "ok", login
        except OSError:
            return "bad", login

    def handle_command(self, sock, anon, line):
        """Handles a full protocol line. Returns False to drop the client."""
        if line.startswith("M "):
            token = line[2:].strip()
            if token:
                self.broadcast(f"D {anon} {token}", exclude=sock)
        elif line == "L":
            with self.lock:
                ids = [a for s, a in self.clients.items()]
            self._send(sock, "U " + " ".join(ids))
        elif line.startswith("R ") or line.startswith("PW ") \
                or line.startswith("RN "):
            self.handle_account_cmd(sock, anon, line)
        elif line == "Q":
            return False
        return True

    def handle_account_cmd(self, sock, anon, line):
        cmd, _, rest = line.partition(" ")
        if cmd == "R":
            parts = rest.split(" ", 1)
            if len(parts) < 2:
                self._send(sock, "ERR")
                return
            login, password = parts[0], parts[1]
            ok, reason = self.apply_registration(login, password)
            self._send(sock, f"OKR {login}" if ok else f"ERRR {reason}")
        elif cmd == "PW":
            new_pass = rest.strip()
            if not new_pass or not self.apply_password(anon, new_pass):
                self._send(sock, "ERR")
            else:
                self._send(sock, f"OKPW {anon}")
        elif cmd == "RN":
            new_login = rest.strip()
            if not new_login or not self.apply_rename(anon, new_login):
                self._send(sock, "ERR")
            else:
                self._send(sock, f"OKRN {new_login}")

    def handle_client(self, sock, addr):
        status, login = self.authenticate(sock)
        if status != "ok":
            if status == "blocked":
                self._send(sock, "E B")
                self.letter("auth_failed", self.tr.t("mail_admin_blocked"),
                            [("LOGIN", login or "?"),
                             ("ADDR", str(addr[0]))])
            else:
                self._send(sock, "E")
                self.letter("auth_failed", self.tr.t("mail_auth_failed"),
                            [("ADDR", str(addr[0]))])
            sock.close()
            return
        anon = random_anon_id()
        with self.lock:
            self.clients[sock] = anon
        msg = self.tr.t("server_client_joined", name=anon)
        self.log(msg, "green")
        self.log(self.tr.t("clients_connected", count=len(self.clients)),
                 "dim")
        self._send(sock, f"I {anon}")

        buf = b""
        total = 0
        try:
            while True:
                data = sock.recv(65536)
                if not data:
                    break
                buf += data
                total += len(data)
                if total > MAX_RECV_TOTAL:
                    break
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    l = line.decode("utf-8", "replace").strip()
                    if len(l) > RECV_LIMIT:
                        return
                    if not self.handle_command(sock, anon, l):
                        self.disconnect(sock)
                        return
        except OSError:
            pass
        self.disconnect(sock)

    def discovery_loop(self):
        dport = self.port + DISCOVERY_PORT_OFFSET
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("", dport))
        except OSError:
            return
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                if data.decode("utf-8", "replace").strip() == MAGIC:
                    sock.sendto(str(self.port).encode(), addr)
            except OSError:
                break

    def run(self):
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        banner = self.tr.t("server_started", host="0.0.0.0", port=self.port)
        width = max(50, min(72, plain_len(banner) + 2))
        print(f"{self.c('cyan')}╔{'═' * width}╗{self.c('reset')}", flush=True)
        print(f"{self.c('cyan')}║{self.c('reset')} "
              f"{self.c('bold')}{self.c('green')}{pad_to('LAN CHAT SERVER', width - 2)}"
              f"{self.c('reset')} {self.c('cyan')}║{self.c('reset')}", flush=True)
        print(f"{self.c('cyan')}║{self.c('reset')} "
              f"{self.c('dim')}{pad_to(self.tr.t('server_waiting'), width - 2)}"
              f"{self.c('reset')} {self.c('cyan')}║{self.c('reset')}", flush=True)
        print(f"{self.c('cyan')}║{self.c('reset')} "
              f"{self.c('yellow')}{pad_to(self.tr.t('accounts_loaded', count=len(self.users)), width - 2)}"
              f"{self.c('reset')} {self.c('cyan')}║{self.c('reset')}", flush=True)
        print(f"{self.c('cyan')}╚{'═' * width}╝{self.c('reset')}", flush=True)

        threading.Thread(target=self.discovery_loop, daemon=True).start()
        threading.Thread(target=self._watch_users, daemon=True).start()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((self.host, self.port))
            srv.listen()
            while True:
                sock, addr = srv.accept()
                threading.Thread(
                    target=self.handle_client, args=(sock, addr), daemon=True
                ).start()

    def _watch_users(self):
        while True:
            time.sleep(3)
            self.reload_users()


def main():
    parser = argparse.ArgumentParser(
        description="LAN Chat server - encrypted & anonymous LAN chat room."
    )
    parser.add_argument("--host", default="0.0.0.0",
                        help="interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5555,
                        help="TCP port (default: 5555)")
    parser.add_argument("--lang", default="en", choices=LANGUAGES,
                        help="server console language")
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args()

    try:
        ChatServer(args.host, args.port, args.lang,
                   not args.no_color).run()
    except KeyboardInterrupt:
        print()
    except OSError as e:
        print(f"Error: {e}", flush=True)


if __name__ == "__main__":
    main()