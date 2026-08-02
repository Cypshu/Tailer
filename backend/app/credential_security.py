"""Versioned authenticated encryption for upstream provider credentials.

The key registry is supplied explicitly by the caller so this module has no
dependency on process settings. Ciphertexts are bound to credential identity,
project, and provider with AES-GCM associated data; copying a stored value to a
different row or provider makes decryption fail authentication.
"""

from base64 import b64decode, urlsafe_b64encode
from collections.abc import Mapping
from dataclasses import dataclass
import json
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_NONCE_BYTES = 12
_AES_256_KEY_BYTES = 32


class CredentialEncryptionConfigurationError(ValueError):
    """The versioned encryption key registry is unusable."""


class CredentialKeyUnavailableError(RuntimeError):
    """A ciphertext references a key version outside the configured registry."""


class CredentialDecryptionError(RuntimeError):
    """A ciphertext failed format or authenticated-decryption checks."""


@dataclass(frozen=True, repr=False)
class EncryptedCredential:
    ciphertext: str
    key_version: str

    def __repr__(self) -> str:
        return (
            "EncryptedCredential("
            f"key_version={self.key_version!r}, ciphertext='<redacted>')"
        )


def generate_credential_encryption_key() -> str:
    """Return a URL-safe base64 encoded AES-256 key for operator configuration."""

    return urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii")


def credential_secret_hint(secret: str, *, visible_suffix: int = 4) -> str:
    """Return a display-only suffix without ever returning a short secret."""

    if not secret:
        raise ValueError("Credential secret must not be empty")
    if visible_suffix < 0:
        raise ValueError("Visible suffix length must not be negative")
    if visible_suffix == 0 or len(secret) <= visible_suffix + 4:
        return "*" * max(8, len(secret))
    return f"****{secret[-visible_suffix:]}"


def _decode_key(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        decoded = value
    else:
        try:
            decoded = b64decode(
                value.encode("ascii"), altchars=b"-_", validate=True
            )
        except (UnicodeEncodeError, ValueError) as exc:
            raise CredentialEncryptionConfigurationError(
                "Credential encryption key is not valid URL-safe base64"
            ) from exc
    if len(decoded) != _AES_256_KEY_BYTES:
        raise CredentialEncryptionConfigurationError(
            "Credential encryption keys must be 32 bytes (AES-256)"
        )
    return decoded


def _associated_data(
    *, credential_id: str, project_id: str, provider: str, key_version: str
) -> bytes:
    normalized_provider = provider.strip().lower()
    if (
        not credential_id
        or not project_id
        or not normalized_provider
        or not key_version.strip()
    ):
        raise ValueError(
            "Credential id, project id, provider, and key version are required for encryption"
        )
    return json.dumps(
        {
            "credential_id": credential_id,
            "project_id": project_id,
            "provider": normalized_provider,
            "key_version": key_version,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


class CredentialCipher:
    """Encrypt and rotate credentials against an explicit versioned keyring.

    String keys must be URL-safe base64 encoded AES-256 keys. Byte keys are
    interpreted as the raw 32 key bytes, which is useful for secret-manager
    integrations that already decode their payloads.
    """

    def __init__(
        self,
        keys: Mapping[str, str | bytes],
        active_version: str,
    ) -> None:
        if not active_version.strip():
            raise CredentialEncryptionConfigurationError(
                "Active credential key version must not be empty"
            )
        if not keys:
            raise CredentialEncryptionConfigurationError(
                "At least one credential encryption key is required"
            )

        decoded_keys: dict[str, AESGCM] = {}
        for version, key in keys.items():
            if not version.strip():
                raise CredentialEncryptionConfigurationError(
                    "Credential key versions must not be empty"
                )
            decoded_keys[version] = AESGCM(_decode_key(key))

        if active_version not in decoded_keys:
            raise CredentialEncryptionConfigurationError(
                "Active credential key version is not in the key registry"
            )
        self._keys = decoded_keys
        self._active_version = active_version

    @property
    def active_version(self) -> str:
        return self._active_version

    @property
    def available_versions(self) -> tuple[str, ...]:
        return tuple(sorted(self._keys))

    def needs_rotation(self, key_version: str) -> bool:
        return key_version != self._active_version

    def encrypt(
        self,
        secret: str,
        *,
        credential_id: str,
        project_id: str,
        provider: str,
    ) -> EncryptedCredential:
        if not secret:
            raise ValueError("Credential secret must not be empty")
        associated_data = _associated_data(
            credential_id=credential_id,
            project_id=project_id,
            provider=provider,
            key_version=self._active_version,
        )
        nonce = secrets.token_bytes(_NONCE_BYTES)
        encrypted = self._keys[self._active_version].encrypt(
            nonce, secret.encode("utf-8"), associated_data
        )
        ciphertext = urlsafe_b64encode(nonce + encrypted).decode("ascii")
        return EncryptedCredential(
            ciphertext=ciphertext,
            key_version=self._active_version,
        )

    def decrypt(
        self,
        encrypted: EncryptedCredential,
        *,
        credential_id: str,
        project_id: str,
        provider: str,
    ) -> str:
        cipher = self._keys.get(encrypted.key_version)
        if cipher is None:
            raise CredentialKeyUnavailableError(
                "Credential key version is unavailable"
            )
        associated_data = _associated_data(
            credential_id=credential_id,
            project_id=project_id,
            provider=provider,
            key_version=encrypted.key_version,
        )
        try:
            payload = b64decode(
                encrypted.ciphertext.encode("ascii"),
                altchars=b"-_",
                validate=True,
            )
            if len(payload) <= _NONCE_BYTES + 16:
                raise ValueError
            plaintext = cipher.decrypt(
                payload[:_NONCE_BYTES],
                payload[_NONCE_BYTES:],
                associated_data,
            )
            return plaintext.decode("utf-8")
        except (InvalidTag, UnicodeDecodeError, UnicodeEncodeError, ValueError) as exc:
            raise CredentialDecryptionError(
                "Credential could not be decrypted"
            ) from exc

    def rotate(
        self,
        encrypted: EncryptedCredential,
        *,
        credential_id: str,
        project_id: str,
        provider: str,
    ) -> EncryptedCredential:
        plaintext = self.decrypt(
            encrypted,
            credential_id=credential_id,
            project_id=project_id,
            provider=provider,
        )
        return self.encrypt(
            plaintext,
            credential_id=credential_id,
            project_id=project_id,
            provider=provider,
        )
