#!/usr/bin/env python3
"""Account manager for LAN Chat.

Stores only PBKDF2 verifiers - plaintext passwords are never saved.

Usage:
    python3 manage_users.py generate 15          create 15 accounts
    python3 manage_users.py add alice            add one account
    python3 manage_users.py add bob --password s3cret
    python3 manage_users.py reset alice          reset password for alice
    python3 manage_users.py remove alice         delete account
    python3 manage_users.py list                 show accounts
"""

import argparse
import json
import os
import secrets
import string

from crypto import derive_auth_verifier

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")


def load():
    try:
        with open(USERS_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)
        f.write("\n")


def add_user(users, login, password):
    login = login.strip()
    verifier = derive_auth_verifier(login, password).hex()
    users[login] = {"verifier": verifier}
    save(users)


def random_password(n=10):
    alphabet = string.ascii_uppercase + string.digits
    return "LanChat" + "".join(secrets.choice(alphabet) for _ in range(n))


def cmd_generate(args):
    users = load()
    created = []
    for i in range(1, args.count + 1):
        login = args.prefix + str(i).zfill(2)
        password = random_password(args.password_len)
        add_user(users, login, password)
        created.append((login, password))
    print(f"created {len(created)} accounts in {USERS_FILE}")
    print("-" * 42)
    print(f"{'LOGIN':<14} {'PASSWORD':<22}  ID")
    for i, (login, password) in enumerate(created, 1):
        print(f"{login:<14} {password:<22}  user{i:02d}")
    print("-" * 42)


def cmd_add(args):
    users = load()
    if args.name in users:
        print(f"account '{args.name}' already exists")
        return 1
    if args.password:
        password = args.password
    else:
        password = random_password(args.password_len)
        print(f"generated password for '{args.name}': {password}")
    add_user(users, args.name, password)
    print(f"added '{args.name}'")
    return 0


def cmd_reset(args):
    users = load()
    if args.name not in users:
        print(f"no such account: '{args.name}'")
        return 1
    password = args.password or random_password(args.password_len)
    add_user(users, args.name, password)
    print(f"password for '{args.name}' changed: {password}")
    return 0


def cmd_remove(args):
    users = load()
    if args.name not in users:
        print(f"no such account: '{args.name}'")
        return 1
    del users[args.name]
    save(users)
    print(f"removed '{args.name}'")
    return 0


def cmd_list(args):
    users = load()
    if not users:
        print("no accounts yet - run: python3 manage_users.py generate 15")
        return 0
    print(f"{'LOGIN':<18} VERIFIER (first 16 bytes)")
    print("-" * 50)
    for login, rec in sorted(users.items()):
        print(f"{login:<18} {rec['verifier'][:32]}...")


def main():
    parser = argparse.ArgumentParser(description="LAN Chat account manager")
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="create N accounts")
    g.add_argument("count", type=int)
    g.add_argument("--prefix", default="user")
    g.add_argument("--password-len", type=int, default=10)
    g.set_defaults(fn=cmd_generate)

    a = sub.add_parser("add", help="add a single account")
    a.add_argument("name")
    a.add_argument("--password")
    a.add_argument("--password-len", type=int, default=10)
    a.set_defaults(fn=cmd_add)

    r = sub.add_parser("reset", help="reset an account password")
    r.add_argument("name")
    r.add_argument("--password")
    r.add_argument("--password-len", type=int, default=10)
    r.set_defaults(fn=cmd_reset)

    rm = sub.add_parser("remove", help="delete an account")
    rm.add_argument("name")
    rm.set_defaults(fn=cmd_remove)

    l = sub.add_parser("list", help="list accounts")
    l.set_defaults(fn=cmd_list)

    args = parser.parse_args()
    try:
        sys_exit = args.fn(args)
    except KeyboardInterrupt:
        return 1
    raise SystemExit(sys_exit or 0)


if __name__ == "__main__":
    main()