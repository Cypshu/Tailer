import hashlib
import hmac
import secrets

from app.config import settings


KEY_PREFIX_HEAD_LENGTH = 12
KEY_PREFIX_TAIL_LENGTH = 4


def generate_sub_api_key() -> str:
    """Generate a high-entropy bearer credential with a recognizable prefix."""
    return f"tailer_sub_{secrets.token_urlsafe(32)}"


def hash_sub_api_key(raw_key: str, pepper: str | None = None) -> str:
    """Return the keyed digest stored and indexed by persistence adapters."""
    secret = (pepper or settings.sub_api_key_pepper).encode("utf-8")
    return hmac.new(secret, raw_key.encode("utf-8"), hashlib.sha256).hexdigest()


def sub_api_key_prefix(raw_key: str) -> str:
    """Return a non-secret display fragment that distinguishes similar demo keys."""
    return (
        f"{raw_key[:KEY_PREFIX_HEAD_LENGTH]}…"
        f"{raw_key[-KEY_PREFIX_TAIL_LENGTH:]}"
    )
