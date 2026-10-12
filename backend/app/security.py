import re
import secrets
import string
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings

ALGO = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: int, version: int = 0) -> str:
    if not settings.secret_key:
        raise RuntimeError("STW_SECRET_KEY is not set")
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.token_minutes)
    return jwt.encode({"sub": str(user_id), "ver": version, "exp": exp}, settings.secret_key, ALGO)


def decode_token(token: str) -> tuple[int, int] | None:
    """The user id and session version inside a token, or None when it is invalid or expired."""
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[ALGO])
        return int(data["sub"]), int(data.get("ver", 0))
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


MIN_PASSWORD = 10


def check_password_rules(password: str, email: str | None = None) -> str:
    """Raises ValueError unless the password is long enough, mixes kinds of characters and does not contain the sign-in name."""
    if len(password) < MIN_PASSWORD or len(password) > 128:
        raise ValueError(f"The password must be {MIN_PASSWORD} to 128 characters")
    kinds = sum(any(check(c) for c in password) for check in (str.islower, str.isupper, str.isdigit, lambda c: not c.isalnum()))
    if kinds < 2:
        raise ValueError("Use at least two kinds of characters: letters, numbers or symbols")
    name = (email or "").split("@")[0].lower()
    if len(name) >= 4 and name in password.lower():
        raise ValueError("The password must not contain the sign-in name")
    return password


def temporary_password() -> str:
    """A random 12 character password with letters and digits, easy to read out to an employee."""
    alphabet = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(12))
        if re.search(r"[A-Za-z]", value) and re.search(r"\d", value):
            return value
