"""Reads the CV from the absolute path the orchestrator sends (Req 3.2, resolved Q1)."""

from pathlib import Path

import anyio

from app.pipeline.errors import FileRetrievalError, InputTooLargeError
from app.pipeline.extract import FileType, detect_file_type


class LocalPathFileStore:
    """IFileStore that reads the CV from a local filesystem path; see the port for the contract."""

    def __init__(self, base_root: str | None = None, max_file_bytes: int = 20 * 1024 * 1024):
        # base_root is a compatibility shim for orchestrators that still send a relative key.
        self._root = Path(base_root).resolve() if base_root else None
        self._max_bytes = max_file_bytes

    async def read(self, reference: str) -> tuple[bytes, FileType]:
        """Read the referenced file off disk and detect its type from the content."""
        path = self._resolve(reference)
        file_bytes = await anyio.to_thread.run_sync(self._read_bytes, path)
        return file_bytes, detect_file_type(file_bytes)

    async def check_ready(self) -> bool:
        """True when the storage root is reachable (always true for absolute-path mode)."""
        if self._root is None:
            return True  # absolute paths: nothing fixed to probe
        return await anyio.to_thread.run_sync(self._root.is_dir)

    def _resolve(self, reference: str) -> Path:
        path = Path(reference)
        if path.is_absolute():
            return path
        if self._root is None:
            raise FileRetrievalError("resumeFileReference is not an absolute path")
        resolved = (self._root / path).resolve()
        if not resolved.is_relative_to(self._root):
            raise FileRetrievalError("resumeFileReference escapes the storage root")
        return resolved

    def _read_bytes(self, path: Path) -> bytes:
        try:
            if not path.is_file():
                raise FileRetrievalError("resume file not found")
            if path.stat().st_size > self._max_bytes:
                raise InputTooLargeError("resume file exceeds the size limit")
            return path.read_bytes()
        except OSError as exc:
            raise FileRetrievalError(f"resume file unreadable: {type(exc).__name__}") from None
