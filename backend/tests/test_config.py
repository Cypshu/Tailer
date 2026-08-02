import json

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
