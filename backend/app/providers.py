"""
Provider integration boundary for LLM services.

This module defines how external LLM providers are called and mocked.
Future work: Replace MockProvider with actual provider implementations (OpenAI, Anthropic, etc.)
"""

from typing import Protocol
from dataclasses import dataclass


@dataclass
class Message:
    role: str
    content: str


@dataclass
class ChatCompletionChoice:
    index: int
    message: Message
    finish_reason: str


@dataclass
class ChatCompletionUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class ChatCompletionResult:
    id: str
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage


class Provider(Protocol):
    """Interface for LLM providers."""

    async def chat_completions(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
        **kwargs,
    ) -> ChatCompletionResult:
        """Send a chat completion request to the provider."""
        ...

    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate estimated cost in EUR for a request."""
        ...


class MockProvider:
    """Mock provider that returns placeholder responses without calling external APIs."""

    async def chat_completions(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
        **kwargs,
    ) -> ChatCompletionResult:
        """Return a mock response."""
        # Count tokens approximately (4 chars per token is common)
        message_text = " ".join(str(m.get("content", "")) for m in messages)
        input_tokens = len(message_text) // 4
        output_tokens = max(0, min(max_tokens, 100))

        return ChatCompletionResult(
            id=f"chatcmpl_mock_{hash(message_text) % 100000:05d}",
            model=model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=Message(
                        role="assistant",
                        content=f"Mock response from {model}. This is a placeholder until real provider integration is complete.",
                    ),
                    finish_reason="stop",
                )
            ],
            usage=ChatCompletionUsage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
        )

    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate mock cost (not realistic, for demo only)."""
        # Simplified: input tokens at $0.00001, output at $0.00003
        return (input_tokens * 0.00001) + (output_tokens * 0.00003)


# Global provider instance
# In production, this would be initialized based on configuration
_provider: Provider = MockProvider()


def get_provider() -> Provider:
    """Get the current LLM provider instance."""
    return _provider


def set_provider(provider: Provider) -> None:
    """Set the LLM provider instance (for testing or switching providers)."""
    global _provider
    _provider = provider
