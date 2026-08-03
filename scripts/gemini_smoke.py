#!/usr/bin/env python3
"""Opt-in live Gemini smoke through TAILER's encrypted provider pipeline.

The ignored ``.gemini_api`` value stays in this host process.  It is submitted
once to TAILER's credential API, never passed to Docker, command arguments, or
files.  Probe rows are hard-deleted and the original Compose environment is
restored even when a check fails.
"""

from __future__ import annotations

from base64 import urlsafe_b64encode
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
KEY_FILE = PROJECT_ROOT / ".gemini_api"
# This runner mutates and cleans the local Compose database.  Never allow its
# dashboard password or provider/Sub-API credentials to be redirected to a
# different origin.
TAILER_URL = "http://127.0.0.1:8000"
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
WAIT_TIMEOUT_VALUE = os.environ.get("TAILER_COMPOSE_WAIT_TIMEOUT", "300")
_SAFE_MARKER = re.compile(r"^[a-f0-9]{12}$")
_SAFE_PROVIDER_CODES = {
    "provider_timeout",
    "provider_unavailable",
    "provider_authentication_failed",
    "provider_permission_denied",
    "provider_not_found",
    "provider_rate_limited",
    "provider_request_rejected",
    "provider_invalid_response",
}


class SmokeError(RuntimeError):
    """A deliberately sanitized live-smoke failure."""


def _read_api_key() -> str:
    if not KEY_FILE.is_file():
        raise SmokeError(".gemini_api is missing")
    raw_value = KEY_FILE.read_text(encoding="utf-8").strip()
    if not raw_value:
        raise SmokeError(".gemini_api is empty")
    if "\n" in raw_value or "\r" in raw_value:
        raise SmokeError(".gemini_api must contain exactly one line")
    if raw_value.startswith("GEMINI_API_KEY="):
        raw_value = raw_value.split("=", 1)[1].strip()
    if not raw_value or any(character.isspace() for character in raw_value):
        raise SmokeError(".gemini_api has an invalid shape")
    if os.name != "nt" and KEY_FILE.stat().st_mode & 0o077:
        raise SmokeError(".gemini_api permissions must not allow group or other access")
    return raw_value


def _wait_timeout_seconds() -> int:
    try:
        timeout = int(WAIT_TIMEOUT_VALUE)
    except (TypeError, ValueError):
        raise SmokeError("TAILER_COMPOSE_WAIT_TIMEOUT must be a positive integer") from None
    if timeout <= 0:
        raise SmokeError("TAILER_COMPOSE_WAIT_TIMEOUT must be a positive integer")
    return timeout


def _request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    label: str,
    timeout: int = 60,
) -> Any:
    body = None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            response_body = response.read()
    except HTTPError as exc:
        response_body = exc.read()
        safe_code = None
        try:
            error_payload = json.loads(response_body)
            detail = error_payload.get("detail")
            if isinstance(detail, dict) and detail.get("code") in _SAFE_PROVIDER_CODES:
                safe_code = detail["code"]
        except (AttributeError, TypeError, ValueError):
            pass
        suffix = f" ({safe_code})" if safe_code else ""
        raise SmokeError(f"{label} returned HTTP {exc.code}{suffix}") from None
    # A container restart can close an accepted socket before sending an HTTP
    # status line.  Normalize those connection-level OS errors so readiness
    # polling keeps waiting and cleanup never escapes its failure boundary.
    except (TimeoutError, URLError, OSError):
        raise SmokeError(f"{label} was unavailable") from None
    if not response_body:
        return None
    try:
        return json.loads(response_body)
    except (TypeError, ValueError):
        raise SmokeError(f"{label} returned invalid JSON") from None


def _discover_model(api_key: str) -> str:
    query = urlencode({"pageSize": "1000"})
    payload = _request_json(
        "GET",
        f"{GEMINI_MODELS_URL}?{query}",
        headers={"x-goog-api-key": api_key},
        label="Gemini model discovery",
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise SmokeError("Gemini model discovery returned an invalid response")
    available = {
        item.get("name", "").removeprefix("models/")
        for item in payload["models"]
        if isinstance(item, dict)
        and isinstance(item.get("supportedGenerationMethods"), list)
        and "generateContent" in item["supportedGenerationMethods"]
    }
    for preferred in (
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-flash-latest",
    ):
        if preferred in available:
            return preferred
    raise SmokeError("No supported Gemini Flash model is available for this key")


def _compose_command(arguments: list[str]) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-directory",
        str(PROJECT_ROOT),
        "--file",
        str(COMPOSE_FILE),
        *arguments,
    ]


def _run_compose(
    arguments: list[str],
    *,
    environment: dict[str, str],
    input_text: str | None = None,
    timeout: int = 600,
) -> str:
    try:
        completed = subprocess.run(
            _compose_command(arguments),
            cwd=PROJECT_ROOT,
            env=environment,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise SmokeError("Docker Compose command could not complete") from None
    if completed.returncode != 0:
        raise SmokeError(
            f"Docker Compose command failed with exit code {completed.returncode}"
        )
    return completed.stdout.strip()


def _inspect_container_environment(container_id: str) -> dict[str, str]:
    if not re.fullmatch(r"[a-f0-9]{12,64}", container_id):
        raise SmokeError("Docker Compose returned an invalid container identifier")
    try:
        completed = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{json .Config.Env}}",
                container_id,
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise SmokeError("Docker container configuration could not be inspected") from None
    if completed.returncode != 0:
        raise SmokeError("Docker container configuration could not be inspected")
    try:
        raw_environment = json.loads(completed.stdout)
    except (TypeError, ValueError):
        raise SmokeError("Docker returned invalid container configuration") from None
    if not isinstance(raw_environment, list) or not all(
        isinstance(item, str) and "=" in item for item in raw_environment
    ):
        raise SmokeError("Docker returned invalid container configuration")
    return {
        item.split("=", 1)[0]: item.split("=", 1)[1]
        for item in raw_environment
    }


def _compose_environment_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _assert_no_transient_compose_overrides(*, environment: dict[str, str]) -> None:
    try:
        config = json.loads(
            _run_compose(
                ["config", "--format", "json"],
                environment=environment,
                timeout=60,
            )
        )
    except (TypeError, ValueError):
        raise SmokeError("Docker Compose returned invalid canonical configuration") from None
    services = config.get("services") if isinstance(config, dict) else None
    if not isinstance(services, dict):
        raise SmokeError("Docker Compose returned invalid canonical configuration")

    for service_name in ("backend", "frontend"):
        service = services.get(service_name)
        expected_environment = (
            service.get("environment") if isinstance(service, dict) else None
        )
        if not isinstance(expected_environment, dict):
            raise SmokeError("Docker Compose returned invalid canonical configuration")
        container_ids = _run_compose(
            ["ps", "--quiet", service_name],
            environment=environment,
            timeout=30,
        ).splitlines()
        if not container_ids:
            continue
        if len(container_ids) != 1:
            raise SmokeError("Gemini smoke requires one canonical container per service")
        actual_environment = _inspect_container_environment(container_ids[0].strip())
        if any(
            actual_environment.get(str(key)) != _compose_environment_text(value)
            for key, value in expected_environment.items()
        ):
            raise SmokeError(
                "Gemini smoke refuses a stack started with transient Compose overrides"
            )


def _wait_for_ready() -> None:
    deadline = time.monotonic() + _wait_timeout_seconds()
    while time.monotonic() < deadline:
        try:
            payload = _request_json(
                "GET",
                f"{TAILER_URL}/ready",
                label="TAILER readiness",
                timeout=5,
            )
            if isinstance(payload, dict) and payload.get("status") == "ready":
                return
        except SmokeError:
            pass
        time.sleep(1)
    raise SmokeError("TAILER did not become ready before the smoke timeout")


def _wait_for_stack_healthy(*, environment: dict[str, str]) -> None:
    required_services = {"postgres", "redis", "backend", "frontend"}
    deadline = time.monotonic() + _wait_timeout_seconds()
    while time.monotonic() < deadline:
        try:
            output = _run_compose(
                ["ps", "--format", "json"],
                environment=environment,
                timeout=30,
            )
            records = [json.loads(line) for line in output.splitlines() if line.strip()]
            service_health = {
                record.get("Service"): (
                    record.get("State"),
                    record.get("Health"),
                )
                for record in records
                if isinstance(record, dict)
            }
            if required_services.issubset(service_health) and all(
                service_health[service] == ("running", "healthy")
                for service in required_services
            ):
                _wait_for_ready()
                return
        except (SmokeError, TypeError, ValueError):
            pass
        time.sleep(1)
    raise SmokeError("The complete TAILER stack did not become healthy before timeout")


def _tailer_request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    label: str,
) -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token else None
    return _request_json(
        method,
        f"{TAILER_URL}{path}",
        payload=payload,
        headers=headers,
        label=label,
    )


def _require_identifier(value: Any, prefix: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        rf"{re.escape(prefix)}[a-f0-9]{{12}}", value
    ):
        raise SmokeError("TAILER returned an invalid probe identifier")
    return value


def _assert_no_secret(value: Any, secret_values: list[str], label: str) -> None:
    serialized = json.dumps(value, ensure_ascii=False, default=str)
    if any(secret_value and secret_value in serialized for secret_value in secret_values):
        raise SmokeError(f"{label} exposed a probe secret")


def _assert_completion(payload: Any, model: str) -> None:
    if not isinstance(payload, dict) or payload.get("model") != model:
        raise SmokeError("TAILER returned an invalid Gemini completion")
    choices = payload.get("choices")
    usage = payload.get("usage")
    if not isinstance(choices, list) or not choices:
        raise SmokeError("TAILER Gemini completion has no choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    # The adapter can faithfully normalize a legitimate thought-only length
    # stop, but this live gate deliberately proves user-visible functionality.
    if not isinstance(content, str) or not content.strip():
        raise SmokeError("TAILER Gemini completion has no user-visible text")
    if not isinstance(usage, dict):
        raise SmokeError("TAILER Gemini completion has no usage")
    token_values = [
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
        usage.get("total_tokens"),
    ]
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in token_values
    ) or token_values[2] <= 0:
        raise SmokeError("TAILER Gemini completion has invalid usage")


def _postgres(
    sql: str,
    *,
    environment: dict[str, str],
) -> str:
    return _run_compose(
        [
            "exec",
            "-T",
            "postgres",
            "sh",
            "-c",
            'exec psql -X -At -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
        ],
        environment=environment,
        input_text=sql,
        timeout=60,
    )


def _hard_cleanup(
    *,
    environment: dict[str, str],
    public_model: str,
    credential_name: str,
    key_name: str,
    credential_id: str | None,
    model_config_id: str | None,
    sub_key_id: str | None,
    project_id: str | None,
) -> None:
    for value in (public_model, credential_name, key_name):
        if not re.fullmatch(r"[a-z0-9-]+", value):
            raise SmokeError("Refusing cleanup for an invalid probe marker")
    for value, prefix in (
        (credential_id, "cred_"),
        (model_config_id, "modelcfg_"),
        (sub_key_id, "subkey_"),
    ):
        if value is not None and not re.fullmatch(
            rf"{re.escape(prefix)}[a-f0-9]{{12}}", value
        ):
            raise SmokeError("Refusing cleanup for an invalid probe identifier")
    if project_id is not None and not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", project_id
    ):
        raise SmokeError("Refusing cleanup for an invalid project identifier")

    project_scope = f"project_id = '{project_id}'" if project_id else "TRUE"
    credential_selector = f"name = '{credential_name}'"
    model_selector = f"public_model = '{public_model}'"
    key_selector = f"name = '{key_name}'"
    if credential_id is not None:
        credential_selector = (
            f"(id = '{credential_id}' OR name = '{credential_name}')"
        )
    if model_config_id is not None:
        model_selector = (
            f"(id = '{model_config_id}' OR public_model = '{public_model}')"
        )
    if sub_key_id is not None:
        key_selector = f"(id = '{sub_key_id}' OR name = '{key_name}')"
    usage_selector = (
        "sub_api_key_id IN ("
        "SELECT id FROM sub_api_keys "
        f"WHERE {key_selector} AND {project_scope} AND owner_id = 'user_1'"
        ")"
    )
    if sub_key_id is not None:
        usage_selector = (
            f"(sub_api_key_id = '{sub_key_id}' OR {usage_selector})"
        )

    sql = f"""
BEGIN;
DELETE FROM usage_events
WHERE {usage_selector} AND {project_scope};
DELETE FROM model_configs
WHERE {model_selector} AND {project_scope} AND provider = 'gemini';
DELETE FROM provider_credentials
WHERE provider = 'gemini' AND {project_scope} AND {credential_selector};
DELETE FROM sub_api_keys
WHERE {key_selector} AND {project_scope} AND owner_id = 'user_1';
COMMIT;
SELECT
  (SELECT count(*) FROM usage_events
   WHERE {usage_selector} AND {project_scope})
  + (SELECT count(*) FROM model_configs
     WHERE {model_selector} AND {project_scope} AND provider = 'gemini')
  + (SELECT count(*) FROM provider_credentials
     WHERE provider = 'gemini' AND {project_scope} AND {credential_selector})
  + (SELECT count(*) FROM sub_api_keys
     WHERE {key_selector} AND {project_scope} AND owner_id = 'user_1');
"""
    output = _postgres(sql, environment=environment)
    if not output.splitlines() or output.splitlines()[-1].strip() != "0":
        raise SmokeError("Gemini smoke probe rows were not fully removed")


def _assert_clean_development_baseline(*, environment: dict[str, str]) -> None:
    key_version_count = _run_compose(
        [
            "exec",
            "-T",
            "backend",
            "python",
            "-c",
            (
                "from app.config import settings; "
                "print(len(settings.credential_encryption_keys))"
            ),
        ],
        environment=environment,
        timeout=60,
    ).strip()
    if key_version_count != "0":
        raise SmokeError(
            "Gemini smoke requires the canonical development stack's empty credential keyring"
        )

    provider_route_count = _postgres(
        "SELECT (SELECT count(*) FROM provider_credentials) "
        "+ (SELECT count(*) FROM model_configs);\n",
        environment=environment,
    ).strip()
    if provider_route_count != "0":
        raise SmokeError(
            "Gemini smoke requires an exclusive development database without provider routes"
        )


def main() -> int:
    gemini_key = _read_api_key()
    marker = secrets.token_hex(6)
    if not _SAFE_MARKER.fullmatch(marker):
        raise SmokeError("Could not generate a safe smoke marker")
    public_model = f"tailer-gemini-smoke-{marker}"
    credential_name = f"gemini-smoke-credential-{marker}"
    key_name = f"gemini-smoke-key-{marker}"

    original_environment = os.environ.copy()
    smoke_environment = original_environment.copy()
    encryption_version = f"gemini-smoke-{marker}"
    encryption_key = urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    smoke_environment["TAILER_CREDENTIAL_ENCRYPTION_KEYS"] = json.dumps(
        {encryption_version: encryption_key}, separators=(",", ":")
    )
    smoke_environment["TAILER_CREDENTIAL_ACTIVE_KEY_VERSION"] = encryption_version

    admin_token: str | None = None
    credential_id: str | None = None
    model_config_id: str | None = None
    sub_key_id: str | None = None
    project_id: str | None = None
    raw_sub_key: str | None = None
    stack_reconfigured = False
    primary_failure: SmokeError | None = None
    cleanup_failure: SmokeError | None = None
    restoration_failure: SmokeError | None = None

    try:
        provider_model = _discover_model(gemini_key)
        print(f"[1/9] Gemini key can access {provider_model}")

        _assert_no_transient_compose_overrides(environment=original_environment)
        _run_compose(
            ["up", "--detach", "backend", "frontend"],
            environment=original_environment,
        )
        _wait_for_stack_healthy(environment=original_environment)
        _assert_clean_development_baseline(environment=original_environment)
        print("[2/9] Exclusive canonical development baseline is clean")

        stack_reconfigured = True
        _run_compose(
            [
                "up",
                "--build",
                "--detach",
                "--force-recreate",
                "backend",
                "frontend",
            ],
            environment=smoke_environment,
        )
        _wait_for_stack_healthy(environment=smoke_environment)
        print("[3/9] TAILER is healthy with an ephemeral credential keyring")

        login = _tailer_request(
            "POST",
            "/api/auth/login",
            payload={
                "email": "organizer@hackathon.dev",
                "password": "Hackathon Organizer",
            },
            label="TAILER admin login",
        )
        if not isinstance(login, dict) or not isinstance(login.get("access_token"), str):
            raise SmokeError("TAILER admin login returned an invalid response")
        admin_token = login["access_token"]

        credential = _tailer_request(
            "POST",
            "/admin/provider-credentials",
            token=admin_token,
            payload={
                "provider": "gemini",
                "name": credential_name,
                "credential": gemini_key,
            },
            label="Gemini credential creation",
        )
        credential_id = _require_identifier(credential.get("id"), "cred_")
        raw_project_id = credential.get("project_id")
        if not isinstance(raw_project_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", raw_project_id
        ):
            raise SmokeError("TAILER returned an invalid credential project")
        project_id = raw_project_id
        if credential.get("provider") != "gemini":
            raise SmokeError("TAILER stored the wrong provider identity")
        _assert_no_secret(credential, [gemini_key], "Credential response")
        if "credential" in credential or "ciphertext" in credential:
            raise SmokeError("Credential response was not metadata-only")
        print("[4/9] Gemini credential is encrypted and metadata-only")

        model_config = _tailer_request(
            "POST",
            "/admin/model-configs",
            token=admin_token,
            payload={
                "public_model": public_model,
                "provider_model": provider_model,
                "credential_id": credential_id,
                "input_cost_per_million_eur": "1",
                "output_cost_per_million_eur": "2",
            },
            label="Gemini model configuration",
        )
        model_config_id = _require_identifier(model_config.get("id"), "modelcfg_")
        if (
            model_config.get("provider") != "gemini"
            or model_config.get("project_id") != project_id
        ):
            raise SmokeError("Gemini alias has the wrong provider identity")

        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        created_key = _tailer_request(
            "POST",
            "/admin/keys",
            token=admin_token,
            payload={
                "name": key_name,
                "owner_user_id": "user_1",
                "allowed_models": [public_model],
                "daily_request_limit": 10,
                "monthly_token_limit": 10000,
                "monthly_budget_eur": 1,
                "expires_at": expires_at,
            },
            label="Gemini smoke Sub-API key creation",
        )
        sub_key_id = _require_identifier(created_key.get("id"), "subkey_")
        raw_sub_key = created_key.get("key")
        if not isinstance(raw_sub_key, str) or not raw_sub_key:
            raise SmokeError("TAILER did not reveal the new Sub-API key once")
        print("[5/9] Encrypted Gemini alias and one-time Sub-API key are ready")

        runtime_payload = {
            "model": public_model,
            "messages": [
                {
                    "role": "system",
                    "content": "Respond briefly and do not repeat the prompt.",
                },
                {
                    "role": "user",
                    "content": "Confirm this TAILER Gemini pipeline smoke test.",
                },
            ],
            # Leave room for Gemini 3.6 Flash thought tokens as well as a
            # visible answer.  Small budgets can legitimately end with only
            # an incomplete thought step and no user-visible text.
            "max_tokens": 256,
        }
        completion = _tailer_request(
            "POST",
            "/v1/chat/completions",
            token=raw_sub_key,
            payload=runtime_payload,
            label="TAILER Gemini completion",
        )
        _assert_completion(completion, provider_model)
        _assert_no_secret(completion, [gemini_key, raw_sub_key], "Completion response")
        print("[6/9] Live Gemini completion succeeded through TAILER")

        ciphertext = _postgres(
            "SELECT ciphertext FROM provider_credentials "
            f"WHERE id = '{credential_id}' AND provider = 'gemini' "
            f"AND name = '{credential_name}';\n",
            environment=smoke_environment,
        ).strip()
        if not ciphertext or ciphertext == gemini_key or gemini_key in ciphertext:
            raise SmokeError("Gemini credential is not safely encrypted at rest")

        _run_compose(
            ["restart", "backend"],
            environment=smoke_environment,
            timeout=120,
        )
        _wait_for_stack_healthy(environment=smoke_environment)
        completion_after_restart = _tailer_request(
            "POST",
            "/v1/chat/completions",
            token=raw_sub_key,
            payload=runtime_payload,
            label="TAILER Gemini completion after restart",
        )
        _assert_completion(completion_after_restart, provider_model)
        _assert_no_secret(
            completion_after_restart,
            [gemini_key, raw_sub_key],
            "Completion-after-restart response",
        )
        print("[7/9] Encrypted Gemini routing survived backend restart")

        usage = _tailer_request(
            "GET",
            f"/admin/usage?{urlencode({'key_id': sub_key_id, 'limit': 20})}",
            token=admin_token,
            label="Gemini usage ledger",
        )
        matching_usage = [
            item
            for item in usage
            if isinstance(item, dict)
            and item.get("provider") == "gemini"
            and item.get("model") == public_model
            and item.get("status") == "success"
        ] if isinstance(usage, list) else []
        if len(matching_usage) < 2:
            raise SmokeError("Gemini successes were not durably recorded")
        for item in matching_usage:
            input_tokens = item.get("input_tokens")
            output_tokens = item.get("output_tokens")
            total_tokens = item.get("total_tokens")
            estimated_cost = item.get("estimated_cost_eur")
            if (
                item.get("provider_model") != provider_model
                or item.get("error_code") is not None
                or isinstance(input_tokens, bool)
                or not isinstance(input_tokens, int)
                or input_tokens <= 0
                or isinstance(output_tokens, bool)
                or not isinstance(output_tokens, int)
                or output_tokens <= 0
                or total_tokens != input_tokens + output_tokens
                or isinstance(estimated_cost, bool)
                or not isinstance(estimated_cost, (int, float))
            ):
                raise SmokeError("Gemini usage ledger contained invalid metering data")
            expected_cost = (input_tokens + (2 * output_tokens)) / 1_000_000
            if abs(float(estimated_cost) - expected_cost) > 1e-12:
                raise SmokeError("Gemini usage ledger contained an invalid configured cost")

        credential_listing = _tailer_request(
            "GET",
            "/admin/provider-credentials",
            token=admin_token,
            label="Gemini credential listing",
        )
        _assert_no_secret(
            credential_listing,
            [gemini_key, ciphertext, raw_sub_key, admin_token],
            "Credential listing",
        )
        logs = _run_compose(
            ["logs", "--no-color", "backend"],
            environment=smoke_environment,
            timeout=60,
        )
        if any(
            secret in logs
            for secret in (gemini_key, raw_sub_key, ciphertext, admin_token)
            if secret
        ):
            raise SmokeError("Backend logs exposed Gemini smoke secrets")
        print("[8/9] Usage, pricing, and API/database/log redaction passed")
    except SmokeError as exc:
        primary_failure = exc
    except Exception as exc:  # pragma: no cover - defensive live-run boundary
        primary_failure = SmokeError(
            f"Unexpected live-smoke failure: {type(exc).__name__}"
        )
    finally:
        if admin_token:
            for path in (
                f"/admin/model-configs/{model_config_id}" if model_config_id else None,
                f"/admin/provider-credentials/{credential_id}" if credential_id else None,
                f"/admin/keys/{sub_key_id}" if sub_key_id else None,
            ):
                if path is None:
                    continue
                try:
                    _tailer_request(
                        "DELETE",
                        path,
                        token=admin_token,
                        label="Gemini smoke soft cleanup",
                    )
                except SmokeError:
                    pass
        if stack_reconfigured:
            try:
                _hard_cleanup(
                    environment=smoke_environment,
                    public_model=public_model,
                    credential_name=credential_name,
                    key_name=key_name,
                    credential_id=credential_id,
                    model_config_id=model_config_id,
                    sub_key_id=sub_key_id,
                    project_id=project_id,
                )
            except SmokeError as exc:
                cleanup_failure = exc
            try:
                _run_compose(
                    [
                        "up",
                        "--detach",
                        "--force-recreate",
                        "backend",
                        "frontend",
                    ],
                    environment=original_environment,
                )
                _wait_for_stack_healthy(environment=original_environment)
            except SmokeError as exc:
                restoration_failure = SmokeError(
                    f"Canonical stack restoration failed: {exc}"
                )
            try:
                # Retry and verify exact cleanup after restoration.  This is
                # idempotent when the first attempt succeeded and recovers from
                # a transient PostgreSQL outage during the first attempt.
                _hard_cleanup(
                    environment=original_environment,
                    public_model=public_model,
                    credential_name=credential_name,
                    key_name=key_name,
                    credential_id=credential_id,
                    model_config_id=model_config_id,
                    sub_key_id=sub_key_id,
                    project_id=project_id,
                )
                cleanup_failure = None
            except SmokeError as exc:
                cleanup_failure = SmokeError(f"Probe cleanup failed: {exc}")

        gemini_key = None
        raw_sub_key = None
        admin_token = None
        encryption_key = None
        smoke_environment.pop("TAILER_CREDENTIAL_ENCRYPTION_KEYS", None)
        smoke_environment.pop("TAILER_CREDENTIAL_ACTIVE_KEY_VERSION", None)

    failures = [
        failure
        for failure in (primary_failure, cleanup_failure, restoration_failure)
        if failure is not None
    ]
    if failures:
        print(
            "Gemini smoke failed: " + " | ".join(str(failure) for failure in failures),
            file=sys.stderr,
        )
        return 1
    print("[9/9] Probe rows removed and complete canonical stack restored")
    print("TAILER Gemini live smoke passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeError as exc:
        print(f"Gemini smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
