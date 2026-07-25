from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .artifacts import ArtifactStore
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


class ClaimGate:
    """Checks structured response claims against runtime-owned evidence."""

    def __init__(self, receipts: ReceiptStore, artifacts: ArtifactStore) -> None:
        self.receipts = receipts
        self.artifacts = artifacts

    def check(self, claims: tuple[Claim, ...]) -> tuple[ClaimCheck, ...]:
        checks: list[ClaimCheck] = []
        for claim in claims:
            if claim.kind == "tool_succeeded":
                receipt = self.receipts.receipt(claim.reference_id)
                valid = bool(
                    receipt
                    and receipt["kind"] == "tool_execution"
                    and receipt["status"] == "SUCCEEDED"
                )
                checks.append(
                    ClaimCheck(valid, "VERIFIED" if valid else "UNVERIFIED_TOOL_SUCCESS", claim)
                )
            else:
                valid = self.artifacts.verify(claim.reference_id)
                checks.append(
                    ClaimCheck(
                        valid,
                        "VERIFIED" if valid else "MISSING_OR_TAMPERED_ARTIFACT",
                        claim,
                    )
                )
        return tuple(checks)
