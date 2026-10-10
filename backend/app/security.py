from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings

ALGO = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: int) -> str:
    if not settings.secret_key:
        raise RuntimeError("STW_SECRET_KEY is not set")
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.token_minutes)
    return jwt.encode({"sub": str(user_id), "exp": exp}, settings.secret_key, ALGO)


def decode_token(token: str) -> int | None:
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[ALGO])
        return int(data["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
