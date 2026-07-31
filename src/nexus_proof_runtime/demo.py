from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .artifacts import ArtifactStore
from .claims import Claim, ClaimGate
from .domain import ExecutionContext, Principal, ToolResult
from .executor import ToolExecutor
from .manifests import ToolManifest
from .receipts import ReceiptStore
from .registry import ToolRegistry


def main() -> None:
    with (
        tempfile.TemporaryDirectory() as temporary,
        ReceiptStore(Path(temporary) / "receipts.db") as receipts,
    ):
        artifacts = ArtifactStore(Path(temporary) / "artifacts")
        registry = ToolRegistry()

        def write_markdown(arguments: dict, context: ExecutionContext) -> ToolResult:
            context.cancellation.raise_if_cancelled()
            artifact = artifacts.create(
                filename=arguments["filename"],
                media_type="text/markdown",
                content=arguments["content"].encode(),
                context=context,
            )
            return ToolResult(
                {"artifact_id": artifact.artifact_id, "sha256": artifact.sha256},
                (artifact.artifact_id,),
            )

        registry.register(
            ToolManifest(
                name="document.write_markdown",
                version="1.0.0",
                description="Create a verified Markdown artifact.",
                input_schema={
                    "type": "object",
                    "required": ["filename", "content"],
                    "properties": {
                        "filename": {"type": "string", "pattern": r"^[^/\\]+\.md$"},
                        "content": {"type": "string", "minLength": 1},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["artifact_id", "sha256"],
                    "properties": {
                        "artifact_id": {"type": "string"},
                        "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                    },
                    "additionalProperties": False,
                },
                required_permissions=frozenset({"documents:write"}),
                risk="write",
                required_approvals=frozenset({"write-approved"}),
            ),
            write_markdown,
        )
        context = ExecutionContext(
            Principal("demo-user", "workspace:demo", frozenset({"documents:write"})),
            "demo-correlation",
            frozenset({"write-approved"}),
        )
        outcome = ToolExecutor(registry, receipts).execute(
            context=context,
            name="document.write_markdown",
            version="1.0.0",
            arguments={"filename": "proof.md", "content": "# Receipt-backed proof\n"},
            idempotency_key="demo-1",
        )
        claims = (
            Claim("tool_succeeded", outcome.receipt_id),
            Claim("artifact_exists", outcome.artifact_ids[0]),
        )
        print(
            json.dumps(
                {
                    "execution": outcome.status,
                    "receipt_id": outcome.receipt_id,
                    "artifact_ids": outcome.artifact_ids,
                    "claims": [
                        {"kind": item.claim.kind, "valid": item.valid, "code": item.code}
                        for item in ClaimGate(receipts, artifacts).check(claims, context=context)
                    ],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()

