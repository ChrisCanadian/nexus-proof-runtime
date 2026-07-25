from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from threading import Lock
from typing import Any
from uuid import uuid4

from jsonschema import Draft202012Validator

from .domain import ExecutionContext, Receipt, ToolCancelled, ToolResult
from .manifests import ToolManifest
from .policy import PolicyEngine
from .receipts import ReceiptStore
from .registry import ToolHandler, ToolRegistry


class ToolRuntimeError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    execution_id: str
    status: str
    output: Mapping[str, Any]
    artifact_ids: tuple[str, ...]
    receipt_id: str
    attempt_count: int
    error_code: str | None = None
    replayed: bool = False


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        receipts: ReceiptStore,
        policy: PolicyEngine | None = None,
    ) -> None:
        self.registry = registry
        self.receipts = receipts
        self.policy = policy or PolicyEngine()
        self._locks_guard = Lock()
        self._execution_locks: dict[tuple[str, ...], Lock] = {}

    def execute(
        self,
        *,
        context: ExecutionContext,
        name: str,
        version: str,
        arguments: Mapping[str, Any],
        idempotency_key: str,
    ) -> ExecutionOutcome:
        if not idempotency_key:
            raise ToolRuntimeError("IDEMPOTENCY_KEY_REQUIRED")
        try:
            manifest, handler = self.registry.resolve(name, version)
        except LookupError as error:
            raise ToolRuntimeError("UNKNOWN_TOOL_VERSION") from error
        decision = self.policy.decide(context, manifest)
        if not decision.allowed:
            raise ToolRuntimeError(decision.code)
        self._validate(manifest.input_schema, arguments, "INVALID_ARGUMENTS")
        arguments_hash = _hash(arguments)
        lock_key = (
            idempotency_key,
            context.principal.principal_id,
            context.principal.scope,
            name,
            version,
            arguments_hash,
        )
        with self._lock_for(lock_key):
            return self._execute_locked(
                context=context,
                name=name,
                version=version,
                arguments=arguments,
                idempotency_key=idempotency_key,
                arguments_hash=arguments_hash,
                manifest=manifest,
                handler=handler,
            )

    def _execute_locked(
        self,
        *,
        context: ExecutionContext,
        name: str,
        version: str,
        arguments: Mapping[str, Any],
        idempotency_key: str,
        arguments_hash: str,
        manifest: ToolManifest,
        handler: ToolHandler,
    ) -> ExecutionOutcome:
        replay = self.receipts.replay(
            idempotency_key=idempotency_key,
            principal_id=context.principal.principal_id,
            scope=context.principal.scope,
            tool_name=name,
            tool_version=version,
            arguments_hash=arguments_hash,
        )
        if replay:
            return _outcome_from_row(replay, replayed=True)
        if context.cancellation.cancelled:
            return self._record(
                context=context,
                name=name,
                version=version,
                arguments_hash=arguments_hash,
                idempotency_key=idempotency_key,
                status="CANCELLED",
                result=ToolResult({}),
                attempts=0,
                error_code="CANCELLED_BEFORE_START",
            )

        attempts = 0
        result = ToolResult({})
        error_code: str | None = None
        status = "FAILED"
        for attempt in range(1, manifest.retry.max_attempts + 1):
            attempts = attempt
            pool = ThreadPoolExecutor(max_workers=1)
            try:
                future = pool.submit(handler, dict(arguments), context)
                result = future.result(timeout=manifest.timeout_ms / 1000)
                self._validate(manifest.output_schema, result.output, "INVALID_RESULT")
                status = "SUCCEEDED"
                error_code = None
                break
            except FutureTimeout:
                context.cancellation.cancel()
                future.cancel()
                status, error_code = "TIMED_OUT", "TOOL_TIMEOUT"
                break
            except ToolCancelled:
                status, error_code = "CANCELLED", "TOOL_CANCELLED"
                break
            except ToolRuntimeError as error:
                status, error_code = "FAILED", error.code
                retry = error.retryable or error.code in manifest.retry.retryable_codes
                if not retry:
                    break
            except Exception as error:
                status, error_code = "FAILED", type(error).__name__
                break
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
        return self._record(
            context=context,
            name=name,
            version=version,
            arguments_hash=arguments_hash,
            idempotency_key=idempotency_key,
            status=status,
            result=result if status == "SUCCEEDED" else ToolResult({}),
            attempts=attempts,
            error_code=error_code,
        )

    def _lock_for(self, key: tuple[str, ...]) -> Lock:
        with self._locks_guard:
            return self._execution_locks.setdefault(key, Lock())

    def _record(
        self,
        *,
        context: ExecutionContext,
        name: str,
        version: str,
        arguments_hash: str,
        idempotency_key: str,
        status: str,
        result: ToolResult,
        attempts: int,
        error_code: str | None,
    ) -> ExecutionOutcome:
        execution_id = str(uuid4())
        receipt = Receipt.create(
            kind="tool_execution",
            status=status,
            context=context,
            facts={
                "execution_id": execution_id,
                "tool": name,
                "version": version,
                "arguments_hash": arguments_hash,
                "artifact_ids": list(result.artifact_ids),
                "attempt_count": attempts,
                "error_code": error_code,
            },
        )
        self.receipts.save_receipt(receipt)
        self.receipts.save_execution(
            {
                "execution_id": execution_id,
                "idempotency_key": idempotency_key,
                "principal_id": context.principal.principal_id,
                "scope": context.principal.scope,
                "tool_name": name,
                "tool_version": version,
                "arguments_hash": arguments_hash,
                "status": status,
                "result_json": _json(result.output),
                "artifact_ids_json": _json(result.artifact_ids),
                "error_code": error_code,
                "receipt_id": receipt.receipt_id,
                "attempt_count": attempts,
            }
        )
        return ExecutionOutcome(
            execution_id,
            status,
            result.output,
            result.artifact_ids,
            receipt.receipt_id,
            attempts,
            error_code,
        )

    @staticmethod
    def _validate(schema: Mapping[str, Any], payload: Mapping[str, Any], code: str) -> None:
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(dict(payload)), key=lambda item: list(item.path))
        if errors:
            raise ToolRuntimeError(code)


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _outcome_from_row(row: Any, *, replayed: bool) -> ExecutionOutcome:
    return ExecutionOutcome(
        execution_id=row["execution_id"],
        status=row["status"],
        output=json.loads(row["result_json"]),
        artifact_ids=tuple(json.loads(row["artifact_ids_json"])),
        receipt_id=row["receipt_id"],
        attempt_count=row["attempt_count"],
        error_code=row["error_code"],
        replayed=replayed,
    )
