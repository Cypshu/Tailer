from datetime import datetime, timedelta, timezone
from typing import Optional

from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import settings

# Password hashing context
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],
    deprecated=["bcrypt"],
)


class TokenData(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    issued_at = datetime.now(timezone.utc)
    token_lifetime = (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.jwt_expiration_minutes)
    )
    to_encode.update({"iat": issued_at, "exp": issued_at + token_lifetime})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt


def decode_access_token(token: str) -> Optional[TokenData]:
    """Decode a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        token_data = TokenData(user_id=user_id)
        return token_data
    except JWTError:
        return None
