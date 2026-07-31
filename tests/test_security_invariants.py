from __future__ import annotations

import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from nexus_proof_runtime import (
    ArtifactStore,
    Claim,
    ClaimGate,
    ClaimVerificationContext,
    ExecutionContext,
    Principal,
    Receipt,
    ReceiptStore,
    ToolExecutor,
    ToolManifest,
    ToolRegistry,
    ToolResult,
)

INPUT_SCHEMA = {
    "type": "object",
    "required": ["text"],
    "properties": {"text": {"type": "string"}},
    "additionalProperties": False,
}
OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["echo"],
    "properties": {"echo": {"type": "string"}},
    "additionalProperties": False,
}


def _manifest(*, timeout_ms: int = 10_000) -> ToolManifest:
    return ToolManifest(
        name="utility.echo",
        version="1.0.0",
        description="Echo text",
        input_schema=INPUT_SCHEMA,
        output_schema=OUTPUT_SCHEMA,
        required_permissions=frozenset({"echo:run"}),
        timeout_ms=timeout_ms,
    )


def _context(principal_id: str, scope: str, correlation_id: str) -> ExecutionContext:
    return ExecutionContext(Principal(principal_id, scope, frozenset({"echo:run"})), correlation_id)


def _successful_receipt(
    receipts: ReceiptStore,
    context: ExecutionContext,
) -> str:
    registry = ToolRegistry()
    registry.register(_manifest(), lambda a, c: ToolResult({"echo": a["text"]}))
    return (
        ToolExecutor(registry, receipts)
        .execute(
            context=context,
            name="utility.echo",
            version="1.0.0",
            arguments={"text": "result"},
            idempotency_key=f"success-{context.correlation_id}",
        )
        .receipt_id
    )


def test_receipt_ownership_is_bound_to_trusted_principal_and_scope() -> None:
    receipts = ReceiptStore()
    principal_a = _context("principal-a", "workspace-1", "corr-a")
    receipt_id = _successful_receipt(receipts, principal_a)

    with tempfile.TemporaryDirectory() as temporary:
        gate = ClaimGate(receipts, ArtifactStore(temporary))
        claim = (Claim("tool_succeeded", receipt_id),)

        valid = gate.check(
            claim,
            context=ClaimVerificationContext("principal-a", "workspace-1"),
        )[0]
        wrong_principal = gate.check(
            claim,
            context=_context("principal-b", "workspace-1", "corr-b"),
        )[0]
        wrong_scope = gate.check(
            claim,
            context=_context("principal-a", "workspace-2", "corr-c"),
        )[0]

    assert (valid.valid, valid.code) == (True, "VERIFIED")
    assert (wrong_principal.valid, wrong_principal.code) == (
        False,
        "RECEIPT_PRINCIPAL_MISMATCH",
    )
    assert (wrong_scope.valid, wrong_scope.code) == (
        False,
        "RECEIPT_SCOPE_MISMATCH",
    )


def test_receipt_verification_permits_later_correlation_in_same_security_boundary() -> None:
    receipts = ReceiptStore()
    receipt_id = _successful_receipt(
        receipts, _context("principal-a", "workspace-1", "corr-original")
    )
    later_context = _context("principal-a", "workspace-1", "corr-later")

    with tempfile.TemporaryDirectory() as temporary:
        check = ClaimGate(receipts, ArtifactStore(temporary)).check(
            (Claim("tool_succeeded", receipt_id),),
            context=later_context,
        )[0]

    assert (check.valid, check.code) == (True, "VERIFIED")


def test_missing_failed_and_wrong_kind_receipts_are_unverified() -> None:
    receipts = ReceiptStore()
    context = _context("principal-a", "workspace-1", "corr-a")
    failed = Receipt.create(
        kind="tool_execution",
        status="FAILED",
        context=context,
        facts={},
    )
    wrong_kind = Receipt.create(
        kind="audit_event",
        status="SUCCEEDED",
        context=context,
        facts={},
    )
    receipts.save_receipt(failed)
    receipts.save_receipt(wrong_kind)

    with tempfile.TemporaryDirectory() as temporary:
        checks = ClaimGate(receipts, ArtifactStore(temporary)).check(
            (
                Claim("tool_succeeded", "missing"),
                Claim("tool_succeeded", failed.receipt_id),
                Claim("tool_succeeded", wrong_kind.receipt_id),
            ),
            context=context,
        )

    assert [(item.valid, item.code) for item in checks] == [
        (False, "UNVERIFIED_TOOL_SUCCESS"),
        (False, "UNVERIFIED_TOOL_SUCCESS"),
        (False, "UNVERIFIED_TOOL_SUCCESS"),
    ]


def test_model_claim_cannot_supply_identity_overrides() -> None:
    with pytest.raises(TypeError):
        Claim(
            kind="tool_succeeded",
            reference_id="receipt",
            principal_id="model-authored",
            scope="model-authored",
        )


def test_artifact_claims_are_bound_to_owner_and_scope() -> None:
    principal_a = _context("principal-a", "workspace-1", "corr-a")
    same_boundary_later = _context("principal-a", "workspace-1", "corr-later")
    wrong_principal = _context("principal-b", "workspace-1", "corr-b")
    wrong_scope = _context("principal-a", "workspace-2", "corr-c")

    with tempfile.TemporaryDirectory() as temporary:
        artifacts = ArtifactStore(Path(temporary) / "artifacts")
        artifact = artifacts.create(
            filename="proof.md",
            media_type="text/markdown",
            content=b"principal A only",
            context=principal_a,
        )
        gate = ClaimGate(ReceiptStore(), artifacts)
        claim = (Claim("artifact_exists", artifact.artifact_id),)

        valid = gate.check(claim, context=same_boundary_later)[0]
        principal_mismatch = gate.check(claim, context=wrong_principal)[0]
        scope_mismatch = gate.check(claim, context=wrong_scope)[0]

    assert (valid.valid, valid.code) == (True, "VERIFIED")
    assert (principal_mismatch.valid, principal_mismatch.code) == (
        False,
        "ARTIFACT_PRINCIPAL_MISMATCH",
    )
    assert (scope_mismatch.valid, scope_mismatch.code) == (
        False,
        "ARTIFACT_SCOPE_MISMATCH",
    )


def test_missing_and_tampered_artifacts_are_unverified() -> None:
    context = _context("principal-a", "workspace-1", "corr-a")
    with tempfile.TemporaryDirectory() as temporary:
        artifacts = ArtifactStore(Path(temporary) / "artifacts")
        artifact = artifacts.create(
            filename="proof.md",
            media_type="text/markdown",
            content=b"original",
            context=context,
        )
        artifact.path.write_bytes(b"tampered")
        checks = ClaimGate(ReceiptStore(), artifacts).check(
            (
                Claim("artifact_exists", "missing"),
                Claim("artifact_exists", artifact.artifact_id),
            ),
            context=context,
        )

    assert [(item.valid, item.code) for item in checks] == [
        (False, "MISSING_OR_TAMPERED_ARTIFACT"),
        (False, "MISSING_OR_TAMPERED_ARTIFACT"),
    ]


def test_idempotency_isolated_across_principal_and_scope() -> None:
    receipts = ReceiptStore()
    registry = ToolRegistry()
    calls: list[tuple[str, str]] = []

    def handler(arguments, context):
        calls.append((context.principal.principal_id, context.principal.scope))
        return ToolResult({"echo": arguments["text"]})

    registry.register(_manifest(), handler)
    executor = ToolExecutor(registry, receipts)
    contexts = (
        _context("principal-a", "workspace-1", "corr-a"),
        _context("principal-b", "workspace-1", "corr-b"),
        _context("principal-a", "workspace-2", "corr-c"),
    )
    outcomes = [
        executor.execute(
            context=context,
            name="utility.echo",
            version="1.0.0",
            arguments={"text": "same"},
            idempotency_key="same",
        )
        for context in contexts
    ]

    assert len({outcome.execution_id for outcome in outcomes}) == 3
    assert not any(outcome.replayed for outcome in outcomes)
    assert calls == [
        ("principal-a", "workspace-1"),
        ("principal-b", "workspace-1"),
        ("principal-a", "workspace-2"),
    ]


def test_timeout_cancels_handler_but_not_later_execution_context() -> None:
    receipts = ReceiptStore()
    registry = ToolRegistry()
    context = _context("principal-a", "workspace-1", "corr-shared")
    observed = Event()

    def handler(arguments, active_context):
        if arguments["text"] == "timeout":
            while not active_context.cancellation.cancelled:
                time.sleep(0.001)
            observed.set()
        return ToolResult({"echo": arguments["text"]})

    registry.register(_manifest(timeout_ms=20), handler)
    executor = ToolExecutor(registry, receipts)
    timed_out = executor.execute(
        context=context,
        name="utility.echo",
        version="1.0.0",
        arguments={"text": "timeout"},
        idempotency_key="timeout",
    )
    later = executor.execute(
        context=context,
        name="utility.echo",
        version="1.0.0",
        arguments={"text": "later"},
        idempotency_key="later",
    )

    assert observed.wait(timeout=1)
    assert (timed_out.status, timed_out.error_code) == ("TIMED_OUT", "TOOL_TIMEOUT")
    assert later.status == "SUCCEEDED"
    assert not context.cancellation.cancelled


def test_timeout_is_isolated_from_concurrent_execution() -> None:
    receipts = ReceiptStore()
    registry = ToolRegistry()
    context = _context("principal-a", "workspace-1", "corr-shared")

    def handler(arguments, active_context):
        if arguments["text"] == "timeout":
            while not active_context.cancellation.cancelled:
                time.sleep(0.001)
        return ToolResult({"echo": arguments["text"]})

    registry.register(_manifest(timeout_ms=25), handler)
    executor = ToolExecutor(registry, receipts)

    def invoke(text: str):
        return executor.execute(
            context=context,
            name="utility.echo",
            version="1.0.0",
            arguments={"text": text},
            idempotency_key=text,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        timeout_future = pool.submit(invoke, "timeout")
        success_future = pool.submit(invoke, "concurrent")
        timed_out = timeout_future.result()
        concurrent = success_future.result()

    assert timed_out.status == "TIMED_OUT"
    assert concurrent.status == "SUCCEEDED"
    assert not context.cancellation.cancelled


def test_explicit_parent_cancellation_blocks_later_calls() -> None:
    receipts = ReceiptStore()
    registry = ToolRegistry()
    calls: list[str] = []
    registry.register(
        _manifest(),
        lambda a, c: calls.append(a["text"]) or ToolResult({"echo": a["text"]}),
    )
    context = _context("principal-a", "workspace-1", "corr-parent")
    context.cancellation.cancel()

    outcome = ToolExecutor(registry, receipts).execute(
        context=context,
        name="utility.echo",
        version="1.0.0",
        arguments={"text": "blocked"},
        idempotency_key="blocked",
    )

    assert (outcome.status, outcome.error_code) == (
        "CANCELLED",
        "CANCELLED_BEFORE_START",
    )
    assert calls == []
