from __future__ import annotations

import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from nexus_proof_runtime import (
    ArtifactStore,
    Claim,
    ClaimGate,
    ExecutionContext,
    Principal,
    ReceiptStore,
    RetryPolicy,
    ToolExecutor,
    ToolManifest,
    ToolRegistry,
    ToolResult,
    ToolRuntimeError,
)
from nexus_proof_runtime.providers import (
    FakeProvider,
    ProviderGateway,
    ProviderRequest,
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


def manifest(**overrides) -> ToolManifest:
    values = {
        "name": "utility.echo",
        "version": "1.0.0",
        "description": "Echo text",
        "input_schema": INPUT_SCHEMA,
        "output_schema": OUTPUT_SCHEMA,
        "required_permissions": frozenset({"echo:run"}),
    }
    values.update(overrides)
    return ToolManifest(**values)


@pytest.fixture
def runtime():
    store = ReceiptStore()
    registry = ToolRegistry()
    executor = ToolExecutor(registry, store)
    allowed = ExecutionContext(
        Principal("user-1", "project-a", frozenset({"echo:run"})), "corr-1"
    )
    return store, registry, executor, allowed


def test_visibility_is_permission_filtered(runtime):
    _, registry, _, allowed = runtime
    registry.register(manifest(), lambda a, c: ToolResult({"echo": a["text"]}))
    denied = ExecutionContext(Principal("user-2", "project-a"), "corr-2")
    assert registry.visible(denied) == ()
    assert registry.visible(allowed)[0].name == "utility.echo"


def test_denies_missing_permission(runtime):
    _, registry, executor, _ = runtime
    registry.register(manifest(), lambda a, c: ToolResult({"echo": a["text"]}))
    context = ExecutionContext(Principal("user-2", "project-a"), "corr-2")
    with pytest.raises(ToolRuntimeError, match="PERMISSION_DENIED"):
        executor.execute(
            context=context,
            name="utility.echo",
            version="1.0.0",
            arguments={"text": "hi"},
            idempotency_key="one",
        )


def test_requires_approval(runtime):
    _, registry, executor, allowed = runtime
    registry.register(
        manifest(required_approvals=frozenset({"owner-approved"})),
        lambda a, c: ToolResult({"echo": a["text"]}),
    )
    with pytest.raises(ToolRuntimeError, match="APPROVAL_REQUIRED"):
        executor.execute(
            context=allowed,
            name="utility.echo",
            version="1.0.0",
            arguments={"text": "hi"},
            idempotency_key="one",
        )


@pytest.mark.parametrize(
    "arguments",
    [{}, {"text": 7}, {"text": "hi", "principal_id": "model-supplied"}],
)
def test_json_schema_rejects_malformed_arguments(runtime, arguments):
    _, registry, executor, allowed = runtime
    registry.register(manifest(), lambda a, c: ToolResult({"echo": str(a["text"])}))
    with pytest.raises(ToolRuntimeError, match="INVALID_ARGUMENTS"):
        executor.execute(
            context=allowed,
            name="utility.echo",
            version="1.0.0",
            arguments=arguments,
            idempotency_key="one",
        )


def test_unknown_tool_version_is_rejected(runtime):
    _, _, executor, allowed = runtime
    with pytest.raises(ToolRuntimeError, match="UNKNOWN_TOOL_VERSION"):
        executor.execute(
            context=allowed,
            name="missing",
            version="9",
            arguments={"text": "hi"},
            idempotency_key="one",
        )


def test_trusted_principal_cannot_be_overridden(runtime):
    _, registry, executor, allowed = runtime
    seen = []

    def handler(arguments, context):
        seen.append(context.principal.principal_id)
        return ToolResult({"echo": arguments["text"]})

    registry.register(manifest(), handler)
    executor.execute(
        context=allowed,
        name="utility.echo",
        version="1.0.0",
        arguments={"text": "hi"},
        idempotency_key="one",
    )
    assert seen == ["user-1"]


def test_idempotent_replay_is_bound_to_actor_scope_tool_version_and_arguments(runtime):
    _, registry, executor, allowed = runtime
    calls = []
    registry.register(
        manifest(), lambda a, c: calls.append(a["text"]) or ToolResult({"echo": a["text"]})
    )
    first = executor.execute(
        context=allowed,
        name="utility.echo",
        version="1.0.0",
        arguments={"text": "hi"},
        idempotency_key="same",
    )
    replay = executor.execute(
        context=allowed,
        name="utility.echo",
        version="1.0.0",
        arguments={"text": "hi"},
        idempotency_key="same",
    )
    different_arguments = executor.execute(
        context=allowed,
        name="utility.echo",
        version="1.0.0",
        arguments={"text": "different"},
        idempotency_key="same",
    )
    assert replay.execution_id == first.execution_id
    assert replay.replayed is True
    assert different_arguments.execution_id != first.execution_id
    assert calls == ["hi", "different"]


def test_concurrent_identical_invocations_execute_once(runtime):
    _, registry, executor, allowed = runtime
    calls = []

    def handler(arguments, context):
        calls.append(1)
        time.sleep(0.01)
        return ToolResult({"echo": arguments["text"]})

    registry.register(manifest(), handler)

    def invoke():
        return executor.execute(
            context=allowed,
            name="utility.echo",
            version="1.0.0",
            arguments={"text": "hi"},
            idempotency_key="concurrent",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(lambda _: invoke(), range(2))
    assert first.execution_id == second.execution_id
    assert sum((first.replayed, second.replayed)) == 1
    assert calls == [1]


def test_retry_only_for_declared_retryable_errors(runtime):
    _, registry, executor, allowed = runtime
    calls = []

    def handler(arguments, context):
        calls.append(1)
        if len(calls) == 1:
            raise ToolRuntimeError("TEMPORARY", retryable=True)
        return ToolResult({"echo": arguments["text"]})

    registry.register(manifest(retry=RetryPolicy(2, frozenset({"TEMPORARY"}))), handler)
    outcome = executor.execute(
        context=allowed,
        name="utility.echo",
        version="1.0.0",
        arguments={"text": "hi"},
        idempotency_key="retry",
    )
    assert (outcome.status, outcome.attempt_count) == ("SUCCEEDED", 2)


def test_prestart_cancellation_does_not_invoke_handler(runtime):
    _, registry, executor, allowed = runtime
    calls = []
    registry.register(
        manifest(), lambda a, c: calls.append(1) or ToolResult({"echo": a["text"]})
    )
    allowed.cancellation.cancel()
    outcome = executor.execute(
        context=allowed,
        name="utility.echo",
        version="1.0.0",
        arguments={"text": "hi"},
        idempotency_key="cancel",
    )
    assert outcome.status == "CANCELLED"
    assert calls == []


def test_timeout_signals_cooperative_cancellation(runtime):
    _, registry, executor, allowed = runtime
    observed = []

    def handler(arguments, context):
        while not context.cancellation.cancelled:
            time.sleep(0.002)
        observed.append("cancelled")
        return ToolResult({"echo": arguments["text"]})

    registry.register(manifest(timeout_ms=15), handler)
    outcome = executor.execute(
        context=allowed,
        name="utility.echo",
        version="1.0.0",
        arguments={"text": "hi"},
        idempotency_key="timeout",
    )
    for _ in range(100):
        if observed:
            break
        time.sleep(0.002)
    assert (outcome.status, outcome.error_code) == ("TIMED_OUT", "TOOL_TIMEOUT")
    assert observed == ["cancelled"]
    assert not allowed.cancellation.cancelled


def test_invalid_handler_result_is_not_reported_as_success(runtime):
    _, registry, executor, allowed = runtime
    registry.register(manifest(), lambda a, c: ToolResult({"wrong": True}))
    outcome = executor.execute(
        context=allowed,
        name="utility.echo",
        version="1.0.0",
        arguments={"text": "hi"},
        idempotency_key="bad-result",
    )
    assert (outcome.status, outcome.error_code) == ("FAILED", "INVALID_RESULT")


def test_artifact_hash_detects_tampering():
    with tempfile.TemporaryDirectory() as temporary:
        artifacts = ArtifactStore(temporary)
        record = artifacts.create(
            filename="proof.md",
            media_type="text/markdown",
            content=b"# proof\n",
            context=ExecutionContext(Principal("user-1", "project-a"), "artifact"),
        )
        assert artifacts.verify(record.artifact_id)
        record.path.write_bytes(b"tampered")
        assert not artifacts.verify(record.artifact_id)


def test_artifact_rejects_path_traversal():
    with tempfile.TemporaryDirectory() as temporary, pytest.raises(ValueError):
        ArtifactStore(temporary).create(
            filename="../escape.md",
            media_type="text/markdown",
            content=b"no",
            context=ExecutionContext(Principal("user-1", "project-a"), "artifact"),
        )


def test_claim_gate_requires_receipt_and_verified_artifact(runtime):
    receipts, registry, executor, allowed = runtime
    with tempfile.TemporaryDirectory() as temporary:
        artifacts = ArtifactStore(Path(temporary) / "artifacts")
        artifact = artifacts.create(
            filename="proof.md",
            media_type="text/markdown",
            content=b"# proof\n",
            context=allowed,
        )
        registry.register(
            manifest(),
            lambda a, c: ToolResult({"echo": a["text"]}, (artifact.artifact_id,)),
        )
        outcome = executor.execute(
            context=allowed,
            name="utility.echo",
            version="1.0.0",
            arguments={"text": "hi"},
            idempotency_key="claims",
        )
        checks = ClaimGate(receipts, artifacts).check(
            (
                Claim("tool_succeeded", outcome.receipt_id),
                Claim("artifact_exists", artifact.artifact_id),
                Claim("tool_succeeded", "invented"),
                Claim("artifact_exists", "invented"),
            ),
            context=allowed,
        )
        assert [item.valid for item in checks] == [True, True, False, False]


def test_provider_fallback_preserves_identical_tool_context():
    first = FakeProvider("first", fail=True)
    second = FakeProvider("second")
    request = ProviderRequest("hello", (("utility.echo", "1.0.0"),))
    response, failures = ProviderGateway((first, second)).generate(
        request, frozenset({"text", "tools"})
    )
    assert response.provider_id == "second"
    assert first.calls[0] == second.calls[0] == request
    assert failures == ("first:RetryableProviderError",)


def test_provider_programmer_error_is_not_hidden_by_fallback():
    class Broken(FakeProvider):
        def generate(self, request):
            raise ValueError("bug")

    second = FakeProvider("second")
    with pytest.raises(ValueError, match="bug"):
        ProviderGateway((Broken("broken"), second)).generate(
            ProviderRequest("hello", ()), frozenset({"text"})
        )
    assert second.calls == []


def test_empty_idempotency_key_is_rejected(runtime):
    _, registry, executor, allowed = runtime
    registry.register(manifest(), lambda a, c: ToolResult({"echo": a["text"]}))
    with pytest.raises(ToolRuntimeError, match="IDEMPOTENCY_KEY_REQUIRED"):
        executor.execute(
            context=allowed,
            name="utility.echo",
            version="1.0.0",
            arguments={"text": "hi"},
            idempotency_key="",
        )
