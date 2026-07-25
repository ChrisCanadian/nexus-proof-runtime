from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: str
    media_type: str
    filename: str
    sha256: str
    size_bytes: int
    path: Path


class ArtifactStore:
    """Atomic local artifact storage with content verification."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, ArtifactRecord] = {}

    def create(self, *, filename: str, media_type: str, content: bytes) -> ArtifactRecord:
        if not content:
            raise ValueError("an artifact must contain bytes")
        safe_name = Path(filename).name
        if safe_name != filename or safe_name in {"", ".", ".."}:
            raise ValueError("filename must be a plain basename")
        artifact_id = str(uuid4())
        target = self.root / f"{artifact_id}-{safe_name}"
        descriptor, temporary = tempfile.mkstemp(prefix=".artifact-", dir=self.root)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        record = ArtifactRecord(
            artifact_id=artifact_id,
            media_type=media_type,
            filename=safe_name,
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            path=target,
        )
        self._records[artifact_id] = record
        return record

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        return self._records.get(artifact_id)

    def verify(self, artifact_id: str) -> bool:
        record = self.get(artifact_id)
        if record is None or not record.path.is_file():
            return False
        return hashlib.sha256(record.path.read_bytes()).hexdigest() == record.sha256

