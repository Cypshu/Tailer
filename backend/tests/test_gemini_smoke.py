import importlib.util
import json
from pathlib import Path

import pytest


_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "gemini_smoke.py"
_SPEC = importlib.util.spec_from_file_location("tailer_gemini_smoke", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
gemini_smoke = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gemini_smoke)


def _completion() -> dict:
    return {
        "model": "gemini-3.6-flash",
        "choices": [
            {
                "message": {"role": "assistant", "content": "OK"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        },
    }


def _usage_event() -> dict:
    return {
        "provider": "gemini",
        "provider_model": "gemini-3.6-flash",
        "model": "tailer-gemini-smoke-aaaaaaaaaaaa",
        "status": "success",
        "error_code": None,
        "input_tokens": 10,
        "output_tokens": 20,
        "total_tokens": 30,
        "estimated_cost_eur": 0.00005,
    }


def _install_main_fakes(monkeypatch, *, fail_after_restart: bool = False):
    monkeypatch.delenv("TAILER_CREDENTIAL_ENCRYPTION_KEYS", raising=False)
    monkeypatch.delenv("TAILER_CREDENTIAL_ACTIVE_KEY_VERSION", raising=False)
    monkeypatch.setattr(gemini_smoke, "_read_api_key", lambda: "raw-gemini-secret")
    monkeypatch.setattr(gemini_smoke.secrets, "token_hex", lambda size: "aaaaaaaaaaaa")
    monkeypatch.setattr(
        gemini_smoke.secrets,
        "token_bytes",
        lambda size: bytes(range(size)),
    )
    monkeypatch.setattr(
        gemini_smoke,
        "_discover_model",
        lambda key: "gemini-3.6-flash",
    )
    monkeypatch.setattr(gemini_smoke, "_wait_for_stack_healthy", lambda **kwargs: None)
    monkeypatch.setattr(
        gemini_smoke,
        "_assert_clean_development_baseline",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        gemini_smoke,
        "_assert_no_transient_compose_overrides",
        lambda **kwargs: None,
    )

    compose_calls = []

    def run_compose(arguments, *, environment, input_text=None, timeout=600):
        compose_calls.append((list(arguments), dict(environment)))
        return ""

    monkeypatch.setattr(gemini_smoke, "_run_compose", run_compose)

    completion_calls = 0

    def tailer_request(method, path, *, payload=None, token=None, label):
        nonlocal completion_calls
        if method == "POST" and path == "/api/auth/login":
            return {"access_token": "admin-token"}
        if method == "POST" and path == "/admin/provider-credentials":
            return {
                "id": "cred_aaaaaaaaaaaa",
                "project_id": "proj_hackathon_2026",
                "provider": "gemini",
            }
        if method == "POST" and path == "/admin/model-configs":
            return {
                "id": "modelcfg_aaaaaaaaaaaa",
                "project_id": "proj_hackathon_2026",
                "provider": "gemini",
            }
        if method == "POST" and path == "/admin/keys":
            return {"id": "subkey_aaaaaaaaaaaa", "key": "raw-sub-key"}
        if method == "POST" and path == "/v1/chat/completions":
            completion_calls += 1
            if fail_after_restart and completion_calls == 2:
                raise gemini_smoke.SmokeError("post-restart request unavailable")
            return _completion()
        if method == "GET" and path.startswith("/admin/usage?"):
            return [_usage_event(), _usage_event()]
        if method == "GET" and path == "/admin/provider-credentials":
            return []
        if method == "DELETE":
            return None
        raise AssertionError((method, path, label))

    monkeypatch.setattr(gemini_smoke, "_tailer_request", tailer_request)
    monkeypatch.setattr(
        gemini_smoke,
        "_postgres",
        lambda sql, *, environment: "encrypted-ciphertext",
    )
    return compose_calls


def test_smoke_destination_is_fixed_to_local_compose() -> None:
    assert gemini_smoke.TAILER_URL == "http://127.0.0.1:8000"
    assert "TAILER_SMOKE_BASE_URL" not in _SCRIPT_PATH.read_text(encoding="utf-8")


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_wait_timeout_must_be_positive_integer(monkeypatch, value: str) -> None:
    monkeypatch.setattr(gemini_smoke, "WAIT_TIMEOUT_VALUE", value)

    with pytest.raises(gemini_smoke.SmokeError):
        gemini_smoke._wait_timeout_seconds()


def test_wait_for_stack_requires_every_service_healthy(monkeypatch) -> None:
    records = [
        {"Service": service, "State": "running", "Health": "healthy"}
        for service in ("postgres", "redis", "backend", "frontend")
    ]
    monkeypatch.setattr(gemini_smoke, "WAIT_TIMEOUT_VALUE", "1")
    monkeypatch.setattr(
        gemini_smoke,
        "_run_compose",
        lambda *args, **kwargs: "\n".join(json.dumps(item) for item in records),
    )
    ready_calls = []
    monkeypatch.setattr(gemini_smoke, "_wait_for_ready", lambda: ready_calls.append(True))

    gemini_smoke._wait_for_stack_healthy(environment={})

    assert ready_calls == [True]


def test_clean_baseline_rejects_existing_keyring(monkeypatch) -> None:
    monkeypatch.setattr(gemini_smoke, "_run_compose", lambda *args, **kwargs: "1")

    with pytest.raises(gemini_smoke.SmokeError, match="empty credential keyring"):
        gemini_smoke._assert_clean_development_baseline(environment={})


def test_transient_compose_environment_is_rejected(monkeypatch) -> None:
    config = {
        "services": {
            "backend": {"environment": {"TAILER_DEBUG": "false"}},
            "frontend": {"environment": {"NEXT_PUBLIC_API_URL": "http://localhost:8000"}},
        }
    }

    def run_compose(arguments, **kwargs):
        if arguments[:2] == ["config", "--format"]:
            return json.dumps(config)
        return "a" * 12

    monkeypatch.setattr(gemini_smoke, "_run_compose", run_compose)
    monkeypatch.setattr(
        gemini_smoke,
        "_inspect_container_environment",
        lambda container_id: {"TAILER_DEBUG": "true"},
    )

    with pytest.raises(gemini_smoke.SmokeError, match="transient Compose overrides"):
        gemini_smoke._assert_no_transient_compose_overrides(environment={})


def test_hard_cleanup_is_scoped_to_captured_identifiers(monkeypatch) -> None:
    statements = []

    def postgres(sql, *, environment):
        statements.append(sql)
        return "0"

    monkeypatch.setattr(gemini_smoke, "_postgres", postgres)

    gemini_smoke._hard_cleanup(
        environment={},
        public_model="tailer-gemini-smoke-aaaaaaaaaaaa",
        credential_name="gemini-smoke-credential-aaaaaaaaaaaa",
        key_name="gemini-smoke-key-aaaaaaaaaaaa",
        credential_id="cred_aaaaaaaaaaaa",
        model_config_id="modelcfg_aaaaaaaaaaaa",
        sub_key_id="subkey_aaaaaaaaaaaa",
        project_id="proj_hackathon_2026",
    )

    sql = statements[0]
    assert "cred_aaaaaaaaaaaa" in sql
    assert "modelcfg_aaaaaaaaaaaa" in sql
    assert "subkey_aaaaaaaaaaaa" in sql
    assert "provider = 'gemini'" in sql
    assert "project_id = 'proj_hackathon_2026'" in sql
    assert "owner_id = 'user_1'" in sql


def test_main_keeps_provider_secret_out_of_compose_and_verifies_cleanup(
    monkeypatch,
) -> None:
    compose_calls = _install_main_fakes(monkeypatch)
    cleanup_calls = []
    monkeypatch.setattr(
        gemini_smoke,
        "_hard_cleanup",
        lambda **kwargs: cleanup_calls.append(kwargs),
    )

    assert gemini_smoke.main() == 0
    assert len(cleanup_calls) == 2
    assert all(
        "raw-gemini-secret" not in argument
        for arguments, _ in compose_calls
        for argument in arguments
    )
    assert all(
        "raw-gemini-secret" not in str(value)
        for _, environment in compose_calls
        for value in environment.values()
    )
    assert any(
        "TAILER_CREDENTIAL_ENCRYPTION_KEYS" in environment
        for _, environment in compose_calls
    )
    assert "TAILER_CREDENTIAL_ENCRYPTION_KEYS" not in compose_calls[-1][1]


def test_main_retries_cleanup_after_a_post_restart_failure(monkeypatch) -> None:
    _install_main_fakes(monkeypatch, fail_after_restart=True)
    cleanup_calls = 0

    def hard_cleanup(**kwargs):
        nonlocal cleanup_calls
        cleanup_calls += 1
        if cleanup_calls == 1:
            raise gemini_smoke.SmokeError("temporary database outage")

    monkeypatch.setattr(gemini_smoke, "_hard_cleanup", hard_cleanup)

    assert gemini_smoke.main() == 1
    assert cleanup_calls == 2
