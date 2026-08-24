from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal


PolicyCode = Literal[
    "model_not_allowed",
    "max_tokens_per_request_exceeded",
]


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Provider-independent result of evaluating static request policy."""

    allowed: bool
    code: PolicyCode | None = None
    message: str | None = None


def evaluate_static_request_policy(
    *,
    allowed_models: Collection[str],
    requested_model: str,
    max_tokens_per_request: int | None,
    requested_max_tokens: int,
) -> PolicyDecision:
    if requested_model not in allowed_models:
        return PolicyDecision(
            allowed=False,
            code="model_not_allowed",
            message=f"Model {requested_model} not allowed for this key",
        )

    if (
        max_tokens_per_request is not None
        and requested_max_tokens > max_tokens_per_request
    ):
        return PolicyDecision(
            allowed=False,
            code="max_tokens_per_request_exceeded",
            message=(
                f"Requested max_tokens ({requested_max_tokens}) exceeds "
                f"this key's limit ({max_tokens_per_request})"
            ),
        )

    return PolicyDecision(allowed=True)
