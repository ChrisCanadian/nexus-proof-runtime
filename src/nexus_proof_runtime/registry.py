from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias

from .domain import ExecutionContext, ToolResult
from .manifests import ToolManifest

ToolHandler: TypeAlias = Callable[[dict, ExecutionContext], ToolResult]


class ToolRegistry:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], tuple[ToolManifest, ToolHandler]] = {}

    def register(self, manifest: ToolManifest, handler: ToolHandler) -> None:
        if manifest.key in self._entries:
            raise ValueError(f"tool version already registered: {manifest.key}")
        self._entries[manifest.key] = (manifest, handler)

    def resolve(self, name: str, version: str) -> tuple[ToolManifest, ToolHandler]:
        try:
            return self._entries[(name, version)]
        except KeyError as error:
            raise LookupError("UNKNOWN_TOOL_VERSION") from error

    def visible(self, context: ExecutionContext) -> tuple[ToolManifest, ...]:
        manifests = [
            manifest
            for manifest, _ in self._entries.values()
            if manifest.enabled
            and manifest.required_permissions.issubset(context.principal.permissions)
        ]
        return tuple(sorted(manifests, key=lambda item: item.key))

