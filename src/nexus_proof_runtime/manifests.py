from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 1
    retryable_codes: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")


@dataclass(frozen=True, slots=True)
class ToolManifest:
    name: str
    version: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    required_permissions: frozenset[str]
    risk: str = "read"
    required_approvals: frozenset[str] = frozenset()
    timeout_ms: int = 5_000
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.name or not self.version:
            raise ValueError("tool name and version are required")
        if self.risk not in {"read", "write", "external", "privileged"}:
            raise ValueError("unsupported risk class")
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")

    @property
    def key(self) -> tuple[str, str]:
        return self.name, self.version

