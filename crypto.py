#!/usr/bin/env python3
"""Encryption helpers for LAN Chat.

Uses AES (Fernet on top of AES-128-CBC) with a key derived from a
shared passphrase via PBKDF2-HMAC-SHA256.

Every client encrypts messages locally. The server only ever sees
ciphertext, so it cannot read names or message contents
(end-to-end encryption).
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

SALT = b"lan-chat-e2e-salt-v1"
ITERATIONS = 200_000


class EncryptionError(Exception):
    pass


def derive_key(passphrase: str) -> bytes:
    if not passphrase:
        raise EncryptionError("empty passphrase")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def new_fernet(passphrase: str) -> Fernet:
    return Fernet(derive_key(passphrase))


def encrypt(fernet: Fernet, text: str) -> str:
    return fernet.encrypt(text.encode("utf-8")).decode("ascii")


def decrypt(fernet: Fernet, token: str) -> str:
    try:
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as e:
        raise EncryptionError(f"wrong passphrase or corrupted data: {e}")