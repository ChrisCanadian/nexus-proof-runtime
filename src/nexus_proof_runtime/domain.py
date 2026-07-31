from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Event
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class Principal:
    """Trusted identity supplied by the host application, never by the model."""

    principal_id: str
    scope: str
    permissions: frozenset[str] = frozenset()


class CancellationToken:
    """Cooperative cancellation signal with optional parent propagation."""

    def __init__(self, parent: CancellationToken | None = None) -> None:
        self._event = Event()
        self._parent = parent

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set() or bool(self._parent and self._parent.cancelled)

    def child(self) -> CancellationToken:
        """Return an independently cancellable signal linked to this parent."""

        return CancellationToken(parent=self)

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise ToolCancelled


class ToolCancelled(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Host-owned identity and parent cancellation state for tool executions."""

    principal: Principal
    correlation_id: str
    approvals: frozenset[str] = frozenset()
    cancellation: CancellationToken = field(default_factory=CancellationToken)

    def for_execution(self) -> ExecutionContext:
        """Create a handler context whose timeout cancellation is execution-local."""

        return ExecutionContext(
            principal=self.principal,
            correlation_id=self.correlation_id,
            approvals=self.approvals,
            cancellation=self.cancellation.child(),
        )


@dataclass(frozen=True, slots=True)
class ToolResult:
    output: Mapping[str, Any]
    artifact_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Receipt:
    receipt_id: str
    kind: str
    status: str
    correlation_id: str
    principal_id: str
    scope: str
    facts: Mapping[str, Any]
    created_at: str

    @classmethod
    def create(
        cls,
        *,
        kind: str,
        status: str,
        context: ExecutionContext,
        facts: Mapping[str, Any],
    ) -> Receipt:
        return cls(
            receipt_id=str(uuid4()),
            kind=kind,
            status=status,
            correlation_id=context.correlation_id,
            principal_id=context.principal.principal_id,
            scope=context.principal.scope,
            facts=dict(facts),
            created_at=utc_now(),
        )

