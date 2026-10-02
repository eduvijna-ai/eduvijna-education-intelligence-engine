from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class SourceStorageError(RuntimeError):
    pass


class LocalSourceStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    @staticmethod
    def sanitize_filename(filename: str | None) -> str:
        raw = Path(filename or "source.bin").name
        cleaned = _SAFE_NAME.sub("_", raw).strip("._")
        return (cleaned or "source.bin")[:180]

    def _resolve_relative(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise SourceStorageError("storage path escapes configured root")
        return candidate

    def write_revision(
        self,
        *,
        source_id: str,
        revision_number: int,
        checksum: str,
        filename: str | None,
        content: bytes,
    ) -> str:
        safe_name = self.sanitize_filename(filename)
        relative = (
            Path(source_id)
            / f"{revision_number:04d}-{checksum[:16]}-{safe_name}"
        )
        target = self._resolve_relative(relative.as_posix())
        target.parent.mkdir(parents=True, exist_ok=True)

        descriptor, temporary = tempfile.mkstemp(
            prefix=".ingest-",
            dir=target.parent,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except Exception:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

        return relative.as_posix()

    def read(self, relative_path: str) -> bytes:
        return self._resolve_relative(relative_path).read_bytes()

    def exists(self, relative_path: str) -> bool:
        return self._resolve_relative(relative_path).exists()

    def delete(self, relative_path: str) -> None:
        path = self._resolve_relative(relative_path)
        try:
            path.unlink()
        except FileNotFoundError:
            return
