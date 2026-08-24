import json

import pytest

from app.config import Settings
from app.credential_security import generate_credential_encryption_key


def test_credential_keyring_parses_from_environment_and_redacts_repr(
    monkeypatch,
) -> None:
    raw_key = generate_credential_encryption_key()
    monkeypatch.setenv(
        "TAILER_CREDENTIAL_ENCRYPTION_KEYS",
        json.dumps({"rotation-v2": raw_key}),
    )
    monkeypatch.setenv(
        "TAILER_CREDENTIAL_ACTIVE_KEY_VERSION",
        "rotation-v2",
    )

    configured = Settings(_env_file=None)

    assert (
        configured.credential_encryption_keys[
            "rotation-v2"
        ].get_secret_value()
        == raw_key
    )
    assert configured.credential_active_key_version == "rotation-v2"
    assert raw_key not in repr(configured)
    assert raw_key not in configured.model_dump_json()


def test_gemini_base_url_has_secure_default_and_environment_override(
    monkeypatch,
) -> None:
    default_settings = Settings(_env_file=None)
    assert default_settings.gemini_base_url == (
        "https://generativelanguage.googleapis.com/v1"
    )

    monkeypatch.setenv(
        "TAILER_GEMINI_BASE_URL",
        "https://gemini.example.test/v1",
    )
    configured = Settings(_env_file=None)
    assert configured.gemini_base_url == "https://gemini.example.test/v1"


def test_idempotency_settings_have_safe_defaults_and_redact_pepper(
    monkeypatch,
) -> None:
    sentinel = "idempotency-pepper-SENTINEL-never-print"
    monkeypatch.setenv("TAILER_IDEMPOTENCY_KEY_PEPPER", sentinel)
    monkeypatch.setenv("TAILER_IDEMPOTENCY_RETENTION_DAYS", "45")

    configured = Settings(_env_file=None)

    assert configured.idempotency_key_pepper.get_secret_value() == sentinel
    assert configured.idempotency_retention_days == 45
    assert sentinel not in repr(configured)
    assert sentinel not in configured.model_dump_json()
    monkeypatch.delenv("TAILER_IDEMPOTENCY_KEY_PEPPER")
    monkeypatch.delenv("TAILER_IDEMPOTENCY_RETENTION_DAYS")
    assert Settings(_env_file=None).idempotency_retention_days == 30


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("TAILER_IDEMPOTENCY_KEY_PEPPER", "   "),
        ("TAILER_IDEMPOTENCY_RETENTION_DAYS", "0"),
    ],
)
def test_invalid_idempotency_settings_fail_closed(
    monkeypatch,
    name: str,
    value: str,
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError):
        Settings(_env_file=None)
