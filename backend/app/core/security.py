"""Encrypt/decrypt data source credentials (Fernet).

Store only ciphertext in ``credential_secret_enc``. Never return secrets via API keys.
Operational note: Prefer a Fernet key from ``Fernet.generate_key()`` in ``.env``;
otherwise any non-empty ``DATA_SOURCE_SECRET_KEY`` string is hashed to derive a Fernet key.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings


def build_fernet(settings: Settings) -> Fernet:
    secret = settings.data_source_secret_key.strip()
    if not secret:
        raise ValueError("DATA_SOURCE_SECRET_KEY is empty")
    try:
        return Fernet(secret.encode("utf-8"))
    except Exception:
        key = base64.urlsafe_b64encode(
            hashlib.sha256(secret.encode("utf-8")).digest()
        )
        return Fernet(key)


def encrypt_credential_plaintext(settings: Settings, plaintext: str) -> str:
    f = build_fernet(settings)
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_credential_token(settings: Settings, token: str) -> str:
    f = build_fernet(settings)
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt stored credential") from exc
