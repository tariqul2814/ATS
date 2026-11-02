import pytest

from app.adapters.local_path_file_store import LocalPathFileStore
from app.pipeline.errors import ExtractionError, FileRetrievalError, InputTooLargeError
from app.pipeline.extract import FileType
from tests.conftest import ASSETS

PDF = (ASSETS / "sample_cv.pdf").read_bytes()
DOCX = (ASSETS / "sample_cv.docx").read_bytes()


async def test_reads_absolute_path_and_detects_type(tmp_path):
    (tmp_path / "a.pdf").write_bytes(PDF)
    data, file_type = await LocalPathFileStore().read(str(tmp_path / "a.pdf"))
    assert data == PDF and file_type is FileType.PDF


async def test_type_comes_from_content_not_extension(tmp_path):
    (tmp_path / "misnamed.pdf").write_bytes(DOCX)
    _, file_type = await LocalPathFileStore().read(str(tmp_path / "misnamed.pdf"))
    assert file_type is FileType.DOCX


async def test_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileRetrievalError) as err:
        await LocalPathFileStore().read(str(tmp_path / "nope.pdf"))
    assert err.value.reason == "file_not_found"


async def test_directory_is_not_a_file(tmp_path):
    with pytest.raises(FileRetrievalError):
        await LocalPathFileStore().read(str(tmp_path))


async def test_relative_reference_rejected_without_base_root():
    with pytest.raises(FileRetrievalError, match="absolute"):
        await LocalPathFileStore().read("abc.pdf")


async def test_relative_reference_resolved_against_base_root(tmp_path):
    (tmp_path / "abc.pdf").write_bytes(PDF)
    data, _ = await LocalPathFileStore(base_root=str(tmp_path)).read("abc.pdf")
    assert data == PDF


async def test_relative_reference_cannot_escape_root(tmp_path):
    root = tmp_path / "storage"
    root.mkdir()
    (tmp_path / "secret.pdf").write_bytes(PDF)
    with pytest.raises(FileRetrievalError, match="escapes"):
        await LocalPathFileStore(base_root=str(root)).read("../secret.pdf")


async def test_oversized_file_rejected(tmp_path):
    (tmp_path / "big.pdf").write_bytes(PDF)
    with pytest.raises(InputTooLargeError):
        await LocalPathFileStore(max_file_bytes=100).read(str(tmp_path / "big.pdf"))


async def test_unsupported_content_raises_extraction_error(tmp_path):
    (tmp_path / "cv.pdf").write_bytes(b"plain text, not a pdf")
    with pytest.raises(ExtractionError):
        await LocalPathFileStore().read(str(tmp_path / "cv.pdf"))


async def test_ready_checks_base_root(tmp_path):
    assert await LocalPathFileStore().check_ready()
    assert await LocalPathFileStore(base_root=str(tmp_path)).check_ready()
    assert not await LocalPathFileStore(base_root=str(tmp_path / "missing")).check_ready()
