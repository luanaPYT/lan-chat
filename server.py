#!/usr/bin/env python3
"""LAN Chat server (encrypted, anonymous).

Hosts a chat room on your local network. The server ONLY relays
ciphertext. It never sees real names or message contents, so it can
be run by anyone without breaking the group's privacy.

Usage:
    python3 server.py [--port 5555] [--lang en|ru|ar]
"""

import argparse
import hmac
import json
import os
import random
import secrets
import socket
import string
import threading
import time

from i18n import Translator, LANGUAGES
from crypto import auth_hmac, derive_auth_verifier

DISCOVERY_PORT_OFFSET = 1000
MAGIC = "LANCHAT_DISCOVERY"
RECV_LIMIT = 65536
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")


def random_anon_id():
    return "ANON-" + "".join(
        random.choices(string.ascii_uppercase + string.digits, k=4)
    )


def load_users():
    try:
        with open(USERS_FILE) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    out = {}
    for login, rec in data.items():
        try:
            out[login] = bytes.fromhex(rec["verifier"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


class ChatServer:
    def __init__(self, host="0.0.0.0", port=5555, lang="en"):
        self.host = host
        self.port = port
        self.tr = Translator(lang)
        self.clients = {}      # socket -> anonymous id
        self.lock = threading.Lock()
        self.users = load_users()
        self._users_mtime = os.path.getmtime(USERS_FILE) \
            if os.path.exists(USERS_FILE) else 0

    def reload_users(self):
        """Live-reload users.json when it changes (add a user without restart)."""
        try:
            mtime = os.path.getmtime(USERS_FILE)
        except OSError:
            return
        if mtime != self._users_mtime:
            self.users = load_users()
            self._users_mtime = mtime
            self.log(f"users.json reloaded: {len(self.users)} accounts")

    def authenticate(self, sock):
        """Challenge-response login. Returns True on success."""
        challenge = secrets.token_hex(16)
        try:
            sock.sendall(f"H {challenge}\n".encode())
            data = sock.recv(4096)
            if not data:
                return False
            line = data.decode("utf-8", "replace").strip()
            parts = line.split(" ")
            if len(parts) != 3 or parts[0] != "A":
                return False
            _, login, client_hmac = parts
            verifier = self.users.get(login)
            if not verifier:
                return False
            expected = auth_hmac(verifier, challenge)
            sent = bytes.fromhex(client_hmac) if len(client_hmac) == 64 else b""
            if not hmac.compare_digest(expected, sent):
                return False
            sock.sendall(b"I " + random_anon_id().encode() + b"\n")
            return True
        except OSError:
            return False

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
            self.log(self.tr.t("server_client_left", name=anon))
        try:
            sock.close()
        except OSError:
            pass

    def handle_client(self, sock, addr):
        if not self.authenticate(sock):
            self._send(sock, "E")
            self.log(self.tr.t("auth_failed", addr=str(addr[0])))
            sock.close()
            return
        anon = random_anon_id()
        with self.lock:
            self.clients[sock] = anon
        self.log(self.tr.t("server_client_joined", name=anon))
        self.log(self.tr.t("clients_connected",
                           count=len(self.clients)))
        self._send(sock, f"I {anon}")

        while True:
            try:
                data = sock.recv(RECV_LIMIT)
            except OSError:
                break
            if not data:
                break
            for line in data.decode("utf-8", "replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                if line == "L":
                    with self.lock:
                        ids = [a for s, a in self.clients.items()]
                    self._send(sock, "U " + " ".join(ids))
                elif line.startswith("M "):
                    token = line[2:].strip()
                    if token:
                        self.broadcast(f"D {anon} {token}", exclude=sock)
                elif line == "Q":
                    break

        self.disconnect(sock)

    def _watch_users(self):
        while True:
            time.sleep(3)
            self.reload_users()

    def log(self, msg):
        print(msg, flush=True)

    def discovery_loop(self):
        """Answer UDP discovery broadcasts so clients can auto-connect."""
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
        banner = self.tr.t("server_started", host="0.0.0.0", port=self.port)
        print(banner, flush=True)
        print(self.tr.t("server_waiting"), flush=True)
        print(self.tr.t("accounts_loaded", count=len(self.users)), flush=True)
        print("=" * len(banner) if len(banner) < 60 else "=" * 60, flush=True)

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
    args = parser.parse_args()

    try:
        ChatServer(args.host, args.port, args.lang).run()
    except KeyboardInterrupt:
        print()
    except OSError as e:
        print(f"Error: {e}", flush=True)


if __name__ == "__main__":
    main()