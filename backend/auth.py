from __future__ import annotations

import bcrypt


def hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, stored_hash: str) -> bool:
    password_bytes = plain_password.encode("utf-8")
    stored_hash_bytes = stored_hash.encode("utf-8")
    return bcrypt.checkpw(password_bytes, stored_hash_bytes)
