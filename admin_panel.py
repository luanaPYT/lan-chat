#!/usr/bin/env python3
"""LAN Chat admin panel for the admin account (luana).

Connect with the admin login + password, and a second-factor PIN.
The panel shows a live feed of everything the server logs (new
accounts, password changes, login failures, joins/leaves, kicks,
warnings) and lets the admin kick users, broadcast a red warning to
everyone, and inspect the account database.

The PIN and password are never stored in plaintext anywhere: both are
checked as salted PBKDF2 verifiers, and every admin command is HMAC-
signed with a per-session key issued at handshake.

Usage:
    python3 admin_panel.py --host 127.0.0.1 --login luana --pass luana
                           [--pin 535612345] [--groupkey <group key>]
    (if --pin is omitted you are prompted for it)

Panel commands:
    /anons           online anonymous ids
    /accounts        account database (login / role / pin)
    /kick <anon>     disconnect that client
    /msg <text>      red warning to everyone
    /help            this help
    /exit            leave panel
"""

import argparse
import getpass
import json
import os
import sys
import threading

from client import (ChatClient, ChatUI, Translator, gradient_text,
                    truecolor, auth_hmac)
from i18n import LANGUAGES

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")


class AdminPanel(ChatClient):
    FEED_COLOR = {
        "register": "green", "passwd": "yellow", "rename": "magenta",
        "auth_failed": "red", "join": "green", "left": "red",
        "kick": "red", "msg": "cyan",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.online = []
        self._groupkey_ok = False  # set by main() when a group key was given

    # --- incoming lines ----------------------------------------------------

    def handle_line(self, line):
        if line.startswith("F "):
            self._on_feed(line[2:].strip())
            return
        if line.startswith("D ") and not self._groupkey_ok:
            return
        if line.startswith("U "):
            self.online = line[2:].split()
            self._show_online()
            return
        super().handle_line(line)

    def _on_feed(self, feed):
        parts = feed.split("|")
        if len(parts) < 3:
            return
        kind, ts = parts[0], parts[1]
        fields = [kv.split("=", 1)[-1] if "=" in kv else kv for kv in parts[2:]]
        color = self.FEED_COLOR.get(kind, "dim")
        title = kind.upper().replace("_", " ")
        line = f"\U0001f4cb {title}  [{ts}]  " + " \u00b7 ".join(fields)
        self.ui.system(line, color)

    def _show_online(self):
        items = "  ".join(self.online)
        self.ui.system(f"\U0001f465 Online ({len(self.online)}): {items}", "cyan")

    # --- local admin tools ------------------------------------------------

    def cmd_accounts(self):
        try:
            with open(USERS_FILE) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            self.ui.err(f"users.json: {e}")
            return
        rows = [f"{'LOGIN':<16} {'ROLE':<7} {'PIN':<4}",
                "-" * 34]
        for login, rec in sorted(data.items()):
            role = "ADMIN" if rec.get("admin") else "user"
            pin = "yes" if rec.get("pin") else "-"
            rows.append(f"{login:<16} {role:<7} {pin:<4}")
        self.ui.info(f"{'ACCOUNTS':^34}\n" + "\n".join(rows))
        self.ui.system(f"total: {len(data)} accounts", "dim")

    def send_admin(self, cmd, sig, rest=""):
        self.send_line(f"ADM {cmd} {sig} {rest}".rstrip())

    def cmd_kick(self, anon):
        if not self.admin_key:
            self.ui.err("kick requires an admin session")
            return
        sig = auth_hmac(self.admin_key.encode(), "kick:" + anon).hex()
        self.send_line(f"ADM KICK {anon} {sig}")
        self.ui.system(f"kick sent: {anon}", "red")

    def cmd_broadcast(self, text):
        if not self.admin_key:
            self.ui.err("broadcast requires an admin session")
            return
        sig = auth_hmac(self.admin_key.encode(), "msg:" + text).hex()
        self.send_admin("MSG", sig, text)
        self.ui.system(f"warning sent", "cyan")

    # --- command loop ------------------------------------------------------

    def run_panel(self):
        banner = gradient_text("ADMIN PANEL", seed="admin",
                               spread=200) if truecolor() else "ADMIN PANEL"
        self.ui._write(f"{banner}  \u26a1  {self.login}")
        self.ui.info("type /help for commands.")
        threading.Thread(target=self.receiver, daemon=True).start()
        self.send_line("L")
        try:
            while self.running:
                line = self.ui.read_line()
                if line is None:
                    break
                self._handle_cmd(line)
        finally:
            self.running = False
            self.send_line("Q")
            try:
                self.sock.close()
            except OSError:
                pass

    def _handle_cmd(self, text):
        line = text.strip()
        if not line:
            return
        if line in ("/exit", "/quit"):
            self.running = False
            return
        if line in ("/anons", "/online", "/who"):
            self.send_line("L")
            return
        if line == "/accounts":
            self.cmd_accounts()
            return
        if line == "/refresh":
            self.send_line("L")
            self.cmd_accounts()
            return
        parts = line.split(maxsplit=1)
        cmd = parts[0]
        if cmd == "/kick":
            if len(parts) < 2:
                self.ui.err("usage: /kick <anon>")
            else:
                self.cmd_kick(parts[1].strip())
            return
        if cmd == "/msg":
            if len(parts) < 2 or not parts[1].strip():
                self.ui.err("usage: /msg <text>")
            else:
                self.cmd_broadcast(parts[1].strip())
            return
        if line == "/help":
            self.ui.info(
                "/anons          online ids\n"
                "/accounts       users.json (login / role / pin)\n"
                "/kick <anon>    disconnect a client\n"
                "/msg <text>     red warning to everyone\n"
                "/refresh        re-check accounts\n"
                "/exit           leave panel")
            return
        self.ui.err(f"\u2718 unknown: {cmd}")


def main():
    ap = argparse.ArgumentParser(description="LAN Chat admin panel")
    ap.add_argument("--host", default=None, help="server host (auto-discover if omitted)")
    ap.add_argument("--port", type=int, default=5555)
    ap.add_argument("--login", default="luana")
    ap.add_argument("--pass", dest="password", default=None)
    ap.add_argument("--pin", default=None)
    ap.add_argument("--groupkey", default="", help="group passphrase to decrypt chat")
    ap.add_argument("--lang", choices=sorted(LANGUAGES), default="ru")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()

    color = not args.no_color
    tr = Translator(args.lang)
    password = args.password or getpass.getpass("password: ")
    pin = args.pin or getpass.getpass("PIN: ")

    panel = AdminPanel(args.host, args.port, "ADMIN", args.login, password,
                       args.groupkey, args.lang, color, pin=pin)
    panel._groupkey_ok = bool(args.groupkey)
    if not panel.connect(args.host, args.port):
        return 1
    panel.run_panel()
    return 0


if __name__ == "__main__":
    sys.exit(main())