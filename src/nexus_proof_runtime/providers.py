from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class RetryableProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    prompt: str
    available_tools: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    provider_id: str
    text: str


class Provider(Protocol):
    provider_id: str
    capabilities: frozenset[str]

    def generate(self, request: ProviderRequest) -> ProviderResponse: ...


class ProviderGateway:
    """Falls back only for declared provider failures, preserving tool context."""

    def __init__(self, providers: tuple[Provider, ...]) -> None:
        self.providers = providers

    def generate(
        self, request: ProviderRequest, required_capabilities: frozenset[str]
    ) -> tuple[ProviderResponse, tuple[str, ...]]:
        failures: list[str] = []
        for provider in self.providers:
            if not required_capabilities.issubset(provider.capabilities):
                continue
            try:
                return provider.generate(request), tuple(failures)
            except RetryableProviderError as error:
                failures.append(f"{provider.provider_id}:{type(error).__name__}")
        raise RetryableProviderError("no eligible provider completed the request")


class FakeProvider:
    def __init__(self, provider_id: str, *, fail: bool = False) -> None:
        self.provider_id = provider_id
        self.fail = fail
        self.capabilities = frozenset({"text", "tools"})
        self.calls: list[ProviderRequest] = []

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        if self.fail:
            raise RetryableProviderError("synthetic outage")
        return ProviderResponse(self.provider_id, "Synthetic provider response.")

