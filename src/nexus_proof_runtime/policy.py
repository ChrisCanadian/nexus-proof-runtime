from __future__ import annotations

from dataclasses import dataclass

from .domain import ExecutionContext
from .manifests import ToolManifest


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    code: str
    missing: tuple[str, ...] = ()


class PolicyEngine:
    """Small deny-by-default policy kernel."""

    def decide(self, context: ExecutionContext, manifest: ToolManifest) -> PolicyDecision:
        if not manifest.enabled:
            return PolicyDecision(False, "TOOL_DISABLED")
        missing_permissions = tuple(
            sorted(manifest.required_permissions - context.principal.permissions)
        )
        if missing_permissions:
            return PolicyDecision(False, "PERMISSION_DENIED", missing_permissions)
        missing_approvals = tuple(sorted(manifest.required_approvals - context.approvals))
        if missing_approvals:
            return PolicyDecision(False, "APPROVAL_REQUIRED", missing_approvals)
        return PolicyDecision(True, "ALLOWED")

