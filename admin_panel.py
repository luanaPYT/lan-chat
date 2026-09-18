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

_UI = {
    "en": {
        "online": "Online ({}):",
        "accounts_header": "ACCOUNTS",
        "col_login": "LOGIN", "col_role": "ROLE", "col_pin": "PIN",
        "role_admin": "ADMIN", "role_user": "user",
        "pin_yes": "yes", "pin_no": "-",
        "total_accounts": "total: {} accounts",
        "kick_sent": "kick sent: {}",
        "warning_sent": "warning sent",
        "type_help": "type /help for commands.",
        "usage_kick": "usage: /kick <anon>",
        "usage_msg": "usage: /msg <text>",
        "need_admin_kick": "kick requires an admin session",
        "need_admin_msg": "broadcast requires an admin session",
        "unknown": "unknown: {}",
        "feed_register": "NEW ACCOUNT", "feed_passwd": "PASSWORD CHANGED",
        "feed_rename": "RENAME", "feed_auth_failed": "AUTH FAILED",
        "feed_join": "JOIN", "feed_left": "LEFT", "feed_kick": "KICK",
        "feed_msg": "BROADCAST",
        "help":
            "/anons          online ids\n"
            "/accounts       users.json (login / role / pin)\n"
            "/kick <anon>    disconnect a client\n"
            "/msg <text>     red warning to everyone\n"
            "/refresh        re-check accounts\n"
            "/exit           leave panel",
    },
    "ru": {
        "online": "Онлайн ({}):",
        "accounts_header": "АККАУНТЫ",
        "col_login": "ЛОГИН", "col_role": "РОЛЬ", "col_pin": "ПИН",
        "role_admin": "АДМИН", "role_user": "польз.",
        "pin_yes": "есть", "pin_no": "-",
        "total_accounts": "всего: {} аккаунтов",
        "kick_sent": "Кик отправлен: {}",
        "warning_sent": "Предупреждение разослано",
        "type_help": "Наберите /help для команд.",
        "usage_kick": "использование: /kick <anon>",
        "usage_msg": "использование: /msg <текст>",
        "need_admin_kick": "кик требует админ-сессию",
        "need_admin_msg": "рассылка требует админ-сессию",
        "unknown": "неизвестно: {}",
        "feed_register": "НОВЫЙ АККАУНТ", "feed_passwd": "СМЕНА ПАРОЛЯ",
        "feed_rename": "ПЕРЕИМЕНОВАНИЕ", "feed_auth_failed": "ОШИБКА ВХОДА",
        "feed_join": "ВХОД", "feed_left": "ВЫХОД", "feed_kick": "КИК",
        "feed_msg": "РАССЫЛКА",
        "help":
            "/anons          кто онлайн (id)\n"
            "/accounts       users.json (логин / роль / пин)\n"
            "/kick <anon>    отключить клиента\n"
            "/msg <текст>    красное предупреждение всем\n"
            "/refresh        перечитать аккаунты\n"
            "/exit           покинуть панель",
    },
}


class AdminPanel(ChatClient):
    FEED_COLOR = {
        "register": "green", "passwd": "yellow", "rename": "magenta",
        "auth_failed": "red", "join": "green", "left": "red",
        "kick": "red", "msg": "cyan",
    }

    def _p(self, key, *args):
        lang = getattr(self.tr, "lang", "en") or "en"
        table = _UI.get(lang, _UI["en"])
        return table.get(key, _UI["en"].get(key, key)).format(*args)

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
        title = self._p("feed_" + kind)
        line = f"\U0001f4cb {title}  [{ts}]  " + " \u00b7 ".join(fields)
        self.ui.system(line, color)

    def _show_online(self):
        items = "  ".join(self.online)
        self.ui.system(f"\U0001f465 " + self._p("online", len(self.online)),
                       "cyan")

    # --- local admin tools ------------------------------------------------

    def cmd_accounts(self):
        try:
            with open(USERS_FILE) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            self.ui.err(f"users.json: {e}")
            return
        rows = [f"{self._p('col_login'):<16} {self._p('col_role'):<7} "
                f"{self._p('col_pin'):<4}",
                "-" * 34]
        for login, rec in sorted(data.items()):
            role = self._p("role_admin" if rec.get("admin") else "role_user")
            pin = self._p("pin_yes") if rec.get("pin") else self._p("pin_no")
            rows.append(f"{login:<16} {role:<7} {pin:<4}")
        self.ui.info(f"{self._p('accounts_header'):^34}\n" + "\n".join(rows))
        self.ui.system(self._p("total_accounts", len(data)), "dim")

    def send_admin(self, cmd, sig, rest=""):
        self.send_line(f"ADM {cmd} {sig} {rest}".rstrip())

    def cmd_kick(self, anon):
        if not self.admin_key:
            self.ui.err(self._p("need_admin_kick"))
            return
        sig = auth_hmac(self.admin_key.encode(), "kick:" + anon).hex()
        self.send_line(f"ADM KICK {anon} {sig}")
        self.ui.system(self._p("kick_sent", anon), "red")

    def cmd_broadcast(self, text):
        if not self.admin_key:
            self.ui.err(self._p("need_admin_msg"))
            return
        sig = auth_hmac(self.admin_key.encode(), "msg:" + text).hex()
        self.send_admin("MSG", sig, text)
        self.ui.system(self._p("warning_sent"), "cyan")

    # --- command loop ------------------------------------------------------

    def run_panel(self):
        banner = gradient_text("ADMIN PANEL", seed="admin",
                               spread=200) if truecolor() else "ADMIN PANEL"
        self.ui._write(f"{banner}  \u26a1  {self.login}")
        self.ui.info(self._p("type_help"))
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
                self.ui.err(self._p("usage_kick"))
            else:
                self.cmd_kick(parts[1].strip())
            return
        if cmd == "/msg":
            if len(parts) < 2 or not parts[1].strip():
                self.ui.err(self._p("usage_msg"))
            else:
                self.cmd_broadcast(parts[1].strip())
            return
        if line == "/help":
            self.ui.info(self._p("help"))
            return
        self.ui.err(self._p("unknown", cmd))


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