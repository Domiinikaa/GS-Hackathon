import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict
import jwt

SECRET_KEY = os.getenv("SECRET_KEY", "gs-hackathon-super-secret-jwt-key-2024-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours

# Password hashing with bcrypt, fallback to hashlib PBKDF2 if bcrypt is not compiled
try:
    import bcrypt

    def hash_password(password: str) -> str:
        """Hashes plain password using bcrypt with automatic salt."""
        pwd_bytes = password.encode("utf-8")[:72]
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(pwd_bytes, salt)
        return hashed.decode("utf-8")

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verifies plain password against bcrypt hash."""
        try:
            pwd_bytes = plain_password.encode("utf-8")[:72]
            hashed_bytes = hashed_password.encode("utf-8")
            return bcrypt.checkpw(pwd_bytes, hashed_bytes)
        except Exception:
            return False

except ImportError:
    import hashlib
    import secrets

    def hash_password(password: str) -> str:
        """PBKDF2-HMAC-SHA256 fallback using Python standard library."""
        salt = secrets.token_hex(16)
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return f"pbkdf2:{salt}:{key.hex()}"

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verifies PBKDF2 hashed password."""
        try:
            parts = hashed_password.split(":")
            if len(parts) != 3 or parts[0] != "pbkdf2":
                return False
            salt = parts[1]
            original_key = parts[2]
            key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), 100000)
            return secrets.compare_digest(key.hex(), original_key)
        except Exception:
            return False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Creates signed JWT token with claims and expiration time."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": now,
        "nbf": now
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and validates JWT token."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
