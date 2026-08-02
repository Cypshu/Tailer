from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.credential_security import (
    CredentialCipher,
    credential_secret_hint,
    generate_credential_encryption_key,
)
from app.domain import ModelConfigRecord, ProviderCredentialRecord
from app.repositories.base import PersistenceConflictError, UnitOfWorkFactory


def _records() -> tuple[ProviderCredentialRecord, ModelConfigRecord, str]:
    now = datetime.now(timezone.utc)
    raw_secret = "sk-test-provider-persistence-secret"
    cipher = CredentialCipher(
        {"v1": generate_credential_encryption_key()}, active_version="v1"
    )
    encrypted = cipher.encrypt(
        raw_secret,
        credential_id="cred_test_openai",
        project_id="proj_hackathon_2026",
        provider="openai",
    )
    credential = ProviderCredentialRecord(
        id="cred_test_openai",
        project_id="proj_hackathon_2026",
        provider="openai",
        name="Primary OpenAI",
        ciphertext=encrypted.ciphertext,
        key_version=encrypted.key_version,
        secret_hint=credential_secret_hint(raw_secret),
        status="active",
        created_at=now,
        updated_at=now,
    )
    model_config = ModelConfigRecord(
        id="modelcfg_test_openai",
        project_id="proj_hackathon_2026",
        public_model="tailer-fast",
        provider="openai",
        provider_model="provider-model-id",
        credential_id=credential.id,
        input_cost_per_million_eur=Decimal("1.25000000"),
        output_cost_per_million_eur=Decimal("5.00000000"),
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    return credential, model_config, raw_secret


def test_provider_credential_and_model_config_round_trip(
    uow_factory: UnitOfWorkFactory,
) -> None:
    credential, model_config, raw_secret = _records()

    with uow_factory() as uow:
        uow.provider_credentials.add(credential)
        uow.model_configs.add(model_config)
        uow.commit()

    with uow_factory() as uow:
        persisted_credential = uow.provider_credentials.get_by_id(credential.id)
        persisted_config = uow.model_configs.get_enabled(
            model_config.project_id, model_config.public_model
        )
        provider_credentials = uow.provider_credentials.list(
            project_id=credential.project_id,
            provider=" OpenAI ",
            status="active",
        )
        enabled_configs = uow.model_configs.list(
            project_id=model_config.project_id, enabled=True
        )

    assert persisted_credential is not None
    assert persisted_credential.ciphertext == credential.ciphertext
    assert persisted_credential.key_version == "v1"
    assert persisted_credential.secret_hint == credential.secret_hint
    assert raw_secret not in persisted_credential.ciphertext
    assert raw_secret not in repr(persisted_credential)
    assert [item.id for item in provider_credentials] == [credential.id]
    assert persisted_config is not None
    assert persisted_config.credential_id == credential.id
    assert persisted_config.input_cost_per_million_eur == Decimal("1.25000000")
    assert [item.id for item in enabled_configs] == [model_config.id]


def test_soft_delete_and_disable_are_durable(
    uow_factory: UnitOfWorkFactory,
) -> None:
    credential, model_config, _ = _records()
    with uow_factory() as uow:
        uow.provider_credentials.add(credential)
        uow.model_configs.add(model_config)
        uow.commit()

    with uow_factory() as uow:
        revoked = uow.provider_credentials.set_status(credential.id, "revoked")
        disabled = uow.model_configs.set_enabled(model_config.id, False)
        assert revoked is not None
        assert disabled is not None
        uow.commit()

    with uow_factory() as uow:
        persisted_credential = uow.provider_credentials.get_by_id(credential.id)
        persisted_config = uow.model_configs.get_by_id(model_config.id)
        resolved = uow.model_configs.get_enabled(
            model_config.project_id, model_config.public_model
        )

    assert persisted_credential is not None
    assert persisted_credential.status == "revoked"
    assert persisted_config is not None
    assert persisted_config.enabled is False
    assert resolved is None


def test_provider_persistence_requires_explicit_commit(
    uow_factory: UnitOfWorkFactory,
) -> None:
    credential, model_config, _ = _records()
    with uow_factory() as uow:
        uow.provider_credentials.add(credential)
        uow.model_configs.add(model_config)

    with uow_factory() as uow:
        assert uow.provider_credentials.get_by_id(credential.id) is None
        assert uow.model_configs.get_by_id(model_config.id) is None


def test_non_mock_model_requires_a_credential(
    uow_factory: UnitOfWorkFactory,
) -> None:
    _, model_config, _ = _records()
    model_config.credential_id = None

    with pytest.raises(PersistenceConflictError):
        with uow_factory() as uow:
            uow.model_configs.add(model_config)


def test_mock_model_requires_no_credential(
    uow_factory: UnitOfWorkFactory,
) -> None:
    _, model_config, _ = _records()
    model_config.id = "modelcfg_test_mock"
    model_config.public_model = "tailer-mock"
    model_config.provider = "mock"
    model_config.provider_model = "mock-model"
    model_config.credential_id = None

    with uow_factory() as uow:
        uow.model_configs.add(model_config)
        uow.commit()

    with uow_factory() as uow:
        persisted = uow.model_configs.get_enabled(
            model_config.project_id, model_config.public_model
        )
    assert persisted is not None
    assert persisted.credential_id is None


def test_provider_names_and_model_aliases_are_unique_per_project(
    uow_factory: UnitOfWorkFactory,
) -> None:
    credential, model_config, _ = _records()
    with uow_factory() as uow:
        uow.provider_credentials.add(credential)
        uow.model_configs.add(model_config)
        uow.commit()

    duplicate_credential, _, _ = _records()
    duplicate_credential.id = "cred_duplicate"
    with pytest.raises(PersistenceConflictError):
        with uow_factory() as uow:
            uow.provider_credentials.add(duplicate_credential)

    _, duplicate_config, _ = _records()
    duplicate_config.id = "modelcfg_duplicate"
    with pytest.raises(PersistenceConflictError):
        with uow_factory() as uow:
            uow.model_configs.add(duplicate_config)
