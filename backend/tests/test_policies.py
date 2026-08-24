from app.policies import PolicyDecision, evaluate_static_request_policy


def test_static_policy_uses_stable_model_denial_code_and_message() -> None:
    decision = evaluate_static_request_policy(
        allowed_models=["gpt-4o-mini"],
        requested_model="gpt-4-preview",
        max_tokens_per_request=None,
        requested_max_tokens=64,
    )

    assert decision == PolicyDecision(
        allowed=False,
        code="model_not_allowed",
        message="Model gpt-4-preview not allowed for this key",
    )


def test_static_max_tokens_policy_allows_boundary_and_denies_one_above() -> None:
    boundary = evaluate_static_request_policy(
        allowed_models=["gpt-4o-mini"],
        requested_model="gpt-4o-mini",
        max_tokens_per_request=64,
        requested_max_tokens=64,
    )
    exceeded = evaluate_static_request_policy(
        allowed_models=["gpt-4o-mini"],
        requested_model="gpt-4o-mini",
        max_tokens_per_request=64,
        requested_max_tokens=65,
    )

    assert boundary == PolicyDecision(allowed=True)
    assert exceeded == PolicyDecision(
        allowed=False,
        code="max_tokens_per_request_exceeded",
        message="Requested max_tokens (65) exceeds this key's limit (64)",
    )


def test_static_policy_preserves_model_denial_precedence() -> None:
    decision = evaluate_static_request_policy(
        allowed_models=["gpt-4o-mini"],
        requested_model="gpt-4-preview",
        max_tokens_per_request=64,
        requested_max_tokens=65,
    )

    assert decision.code == "model_not_allowed"
    assert decision.message == "Model gpt-4-preview not allowed for this key"
