from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from .domain import Receipt


class ReceiptStore:
    """SQLite evidence store. It records facts, not model-authored success claims."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._path = str(path)
        self._lock = RLock()
        self._connection = sqlite3.connect(self._path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS receipts (
                receipt_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                principal_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                facts_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS executions (
                execution_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL,
                principal_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                tool_version TEXT NOT NULL,
                arguments_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT NOT NULL,
                artifact_ids_json TEXT NOT NULL,
                error_code TEXT,
                receipt_id TEXT NOT NULL,
                attempt_count INTEGER NOT NULL,
                UNIQUE (
                    idempotency_key, principal_id, scope, tool_name,
                    tool_version, arguments_hash
                )
            );
            """
        )

    def save_receipt(self, receipt: Receipt) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    receipt.receipt_id,
                    receipt.kind,
                    receipt.status,
                    receipt.correlation_id,
                    receipt.principal_id,
                    receipt.scope,
                    _json(receipt.facts),
                    receipt.created_at,
                ),
            )

    def save_execution(self, record: dict[str, Any]) -> None:
        fields = (
            "execution_id",
            "idempotency_key",
            "principal_id",
            "scope",
            "tool_name",
            "tool_version",
            "arguments_hash",
            "status",
            "result_json",
            "artifact_ids_json",
            "error_code",
            "receipt_id",
            "attempt_count",
        )
        with self._lock, self._connection:
            placeholders = ",".join("?" * len(fields))
            self._connection.execute(
                f"INSERT INTO executions ({','.join(fields)}) VALUES ({placeholders})",
                tuple(record[field] for field in fields),
            )

    def replay(
        self,
        *,
        idempotency_key: str,
        principal_id: str,
        scope: str,
        tool_name: str,
        tool_version: str,
        arguments_hash: str,
    ) -> sqlite3.Row | None:
        with self._lock:
            return self._connection.execute(
                """
                SELECT * FROM executions
                WHERE idempotency_key = ? AND principal_id = ? AND scope = ?
                  AND tool_name = ? AND tool_version = ? AND arguments_hash = ?
                """,
                (
                    idempotency_key,
                    principal_id,
                    scope,
                    tool_name,
                    tool_version,
                    arguments_hash,
                ),
            ).fetchone()

    def receipt(self, receipt_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self._connection.execute(
                "SELECT * FROM receipts WHERE receipt_id = ?", (receipt_id,)
            ).fetchone()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
