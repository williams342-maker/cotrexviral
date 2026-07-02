"""Shared provider adapter contracts and helpers."""
from dataclasses import dataclass, field
from typing import Any

import httpx


class ProviderError(RuntimeError):
    """A provider failed without exposing credentials in the error."""


@dataclass
class ProviderResult:
    provider: str
    model: str
    text: str
    usage: dict[str, int] = field(default_factory=dict)
    cost_estimate: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ProviderAdapter:
    name = "base"

    def __init__(
        self,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 90.0,
    ):
        self.api_key = api_key
        self.transport = transport
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def safe_error(self, exc: Exception) -> ProviderError:
        message = str(exc)
        if self.api_key:
            message = message.replace(self.api_key, "[redacted]")
        return ProviderError(f"{self.name} request failed: {message[:500]}")

    async def generate(
        self, *, system_prompt: str, user_prompt: str, model: str
    ) -> ProviderResult:
        raise NotImplementedError

