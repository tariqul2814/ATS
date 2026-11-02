"""Port for reading the stored CV. The first stage of the pipeline retrieves bytes through it."""

from typing import Protocol

from app.pipeline.extract import FileType


class IFileStore(Protocol):
    """Resolves a resumeFileReference to the CV's bytes and detected type (Req 3).

    Raises FileRetrievalError when the file is absent or unreadable, ExtractionError when its
    content is not a supported type.
    """

    async def read(self, reference: str) -> tuple[bytes, FileType]:
        """Return the CV's raw bytes and detected file type for the given reference."""
        ...

    async def check_ready(self) -> bool:
        """True when the backing store is reachable (Req 18.2)."""
        ...
