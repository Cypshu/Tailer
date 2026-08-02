from base64 import b64decode, urlsafe_b64encode
from datetime import datetime, timezone

import pytest

from app.credential_security import (
    CredentialCipher,
    CredentialDecryptionError,
    CredentialEncryptionConfigurationError,
    CredentialKeyUnavailableError,
    EncryptedCredential,
    credential_secret_hint,
    generate_credential_encryption_key,
)
from app.domain import ProviderCredentialRecord


CONTEXT = {
    "credential_id": "cred_test",
    "project_id": "proj_hackathon_2026",
    "provider": "openai",
}


def test_aes_gcm_round_trip_is_randomized_and_repr_safe() -> None:
    raw_secret = "sk-test-never-store-this-value"
    cipher = CredentialCipher(
        {"v1": generate_credential_encryption_key()}, active_version="v1"
    )

    first = cipher.encrypt(raw_secret, **CONTEXT)
    second = cipher.encrypt(raw_secret, **CONTEXT)

    assert first.key_version == "v1"
    assert first.ciphertext != second.ciphertext
    assert raw_secret not in first.ciphertext
    assert raw_secret not in repr(first)
    assert first.ciphertext not in repr(first)
    assert cipher.decrypt(first, **CONTEXT) == raw_secret
    assert cipher.available_versions == ("v1",)


@pytest.mark.parametrize(
    "changed_context",
    [
        {**CONTEXT, "credential_id": "cred_other"},
        {**CONTEXT, "project_id": "proj_other"},
        {**CONTEXT, "provider": "anthropic"},
    ],
)
def test_associated_data_prevents_ciphertext_rebinding(
    changed_context: dict[str, str],
) -> None:
    raw_secret = "provider-secret-bound-to-one-record"
    cipher = CredentialCipher(
        {"v1": generate_credential_encryption_key()}, active_version="v1"
    )
    encrypted = cipher.encrypt(raw_secret, **CONTEXT)

    with pytest.raises(CredentialDecryptionError) as error:
        cipher.decrypt(encrypted, **changed_context)

    assert raw_secret not in str(error.value)
    assert encrypted.ciphertext not in str(error.value)


def test_tampering_fails_with_a_sanitized_error() -> None:
    raw_secret = "provider-secret-that-must-not-leak"
    cipher = CredentialCipher(
        {"v1": generate_credential_encryption_key()}, active_version="v1"
    )
    encrypted = cipher.encrypt(raw_secret, **CONTEXT)
    payload = bytearray(
        b64decode(encrypted.ciphertext.encode("ascii"), altchars=b"-_")
    )
    payload[-1] ^= 1
    tampered = EncryptedCredential(
        ciphertext=urlsafe_b64encode(payload).decode("ascii"),
        key_version=encrypted.key_version,
    )

    with pytest.raises(CredentialDecryptionError) as error:
        cipher.decrypt(tampered, **CONTEXT)

    assert raw_secret not in str(error.value)
    assert tampered.ciphertext not in str(error.value)


def test_old_key_decrypts_and_rotates_to_the_active_version() -> None:
    v1 = generate_credential_encryption_key()
    v2 = generate_credential_encryption_key()
    old_cipher = CredentialCipher({"v1": v1}, active_version="v1")
    encrypted = old_cipher.encrypt("rotate-me", **CONTEXT)
    rotating_cipher = CredentialCipher({"v1": v1, "v2": v2}, active_version="v2")

    assert rotating_cipher.needs_rotation(encrypted.key_version)
    rotated = rotating_cipher.rotate(encrypted, **CONTEXT)
    assert rotated.key_version == "v2"
    assert rotating_cipher.decrypt(rotated, **CONTEXT) == "rotate-me"
    assert not rotating_cipher.needs_rotation(rotated.key_version)

    v2_only = CredentialCipher({"v2": v2}, active_version="v2")
    with pytest.raises(
        CredentialKeyUnavailableError, match="key version is unavailable"
    ):
        v2_only.decrypt(encrypted, **CONTEXT)


def test_key_version_is_authenticated_even_if_versions_reuse_a_key() -> None:
    shared_key = generate_credential_encryption_key()
    cipher = CredentialCipher(
        {"v1": shared_key, "v2": shared_key}, active_version="v1"
    )
    encrypted = cipher.encrypt("version-bound-secret", **CONTEXT)
    rebound = EncryptedCredential(
        ciphertext=encrypted.ciphertext,
        key_version="v2",
    )

    with pytest.raises(CredentialDecryptionError):
        cipher.decrypt(rebound, **CONTEXT)


def test_key_registry_and_display_hint_fail_closed() -> None:
    with pytest.raises(CredentialEncryptionConfigurationError):
        CredentialCipher({}, active_version="v1")
    with pytest.raises(CredentialEncryptionConfigurationError):
        CredentialCipher({"v1": "not-a-key"}, active_version="v1")
    with pytest.raises(CredentialEncryptionConfigurationError):
        CredentialCipher(
            {"v1": generate_credential_encryption_key()}, active_version="v2"
        )

    long_secret = "sk-test-1234567890"
    short_secret = "tiny"
    assert credential_secret_hint(long_secret) == "****7890"
    assert long_secret not in credential_secret_hint(long_secret)
    assert credential_secret_hint(short_secret) == "********"
    assert short_secret not in credential_secret_hint(short_secret)


def test_persistence_record_repr_redacts_ciphertext() -> None:
    now = datetime.now(timezone.utc)
    record = ProviderCredentialRecord(
        id="cred_test",
        project_id="proj_test",
        provider="openai",
        name="Primary",
        ciphertext="ciphertext-that-must-not-be-logged",
        key_version="v1",
        secret_hint="****1234",
        status="active",
        created_at=now,
        updated_at=now,
    )

    rendered = repr(record)
    assert record.ciphertext not in rendered
    assert "<redacted>" in rendered
