from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .artifacts import ArtifactStore
from .domain import ExecutionContext
from .receipts import ReceiptStore


@dataclass(frozen=True, slots=True)
class Claim:
    kind: Literal["tool_succeeded", "artifact_exists"]
    reference_id: str


@dataclass(frozen=True, slots=True)
class ClaimCheck:
    valid: bool
    code: str
    claim: Claim


@dataclass(frozen=True, slots=True)
class ClaimVerificationContext:
    """Trusted host identity used to authorize evidence-backed claims."""

    principal_id: str
    scope: str

    @classmethod
    def from_execution_context(cls, context: ExecutionContext) -> ClaimVerificationContext:
        return cls(context.principal.principal_id, context.principal.scope)


class ClaimGate:
    """Checks structured response claims against runtime-owned evidence and identity."""

    def __init__(self, receipts: ReceiptStore, artifacts: ArtifactStore) -> None:
        self.receipts = receipts
        self.artifacts = artifacts

    def check(
        self,
        claims: tuple[Claim, ...],
        *,
        context: ExecutionContext | ClaimVerificationContext,
    ) -> tuple[ClaimCheck, ...]:
        trusted = _trusted_context(context)
        checks: list[ClaimCheck] = []
        for claim in claims:
            if claim.kind == "tool_succeeded":
                checks.append(self._check_tool_receipt(claim, trusted))
            else:
                checks.append(self._check_artifact(claim, trusted))
        return tuple(checks)

    def _check_tool_receipt(
        self,
        claim: Claim,
        trusted: ClaimVerificationContext,
    ) -> ClaimCheck:
        receipt = self.receipts.receipt(claim.reference_id)
        if (
            receipt is None
            or receipt["kind"] != "tool_execution"
            or receipt["status"] != "SUCCEEDED"
        ):
            return ClaimCheck(False, "UNVERIFIED_TOOL_SUCCESS", claim)
        if receipt["principal_id"] != trusted.principal_id:
            return ClaimCheck(False, "RECEIPT_PRINCIPAL_MISMATCH", claim)
        if receipt["scope"] != trusted.scope:
            return ClaimCheck(False, "RECEIPT_SCOPE_MISMATCH", claim)
        return ClaimCheck(True, "VERIFIED", claim)

    def _check_artifact(
        self,
        claim: Claim,
        trusted: ClaimVerificationContext,
    ) -> ClaimCheck:
        artifact = self.artifacts.get(claim.reference_id)
        if artifact is None:
            return ClaimCheck(False, "MISSING_OR_TAMPERED_ARTIFACT", claim)
        if artifact.principal_id != trusted.principal_id:
            return ClaimCheck(False, "ARTIFACT_PRINCIPAL_MISMATCH", claim)
        if artifact.scope != trusted.scope:
            return ClaimCheck(False, "ARTIFACT_SCOPE_MISMATCH", claim)
        if not self.artifacts.verify(claim.reference_id):
            return ClaimCheck(False, "MISSING_OR_TAMPERED_ARTIFACT", claim)
        return ClaimCheck(True, "VERIFIED", claim)


def _trusted_context(
    context: ExecutionContext | ClaimVerificationContext,
) -> ClaimVerificationContext:
    if isinstance(context, ClaimVerificationContext):
        return context
    if isinstance(context, ExecutionContext):
        return ClaimVerificationContext.from_execution_context(context)
    raise TypeError("context must be supplied by the trusted host")
