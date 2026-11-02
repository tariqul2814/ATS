import asyncio
import sqlite3
import uuid

import pytest

from app.adapters.sqlite_tracking_repo import SCHEMA_VERSION, SqliteTrackingRepository
from app.ports.tracking_repo import CallbackOutcome, TrackingStatus


@pytest.fixture
async def repo(tmp_path):
    r = SqliteTrackingRepository(str(tmp_path / "db" / "tracking.db"))
    assert await r.init()
    yield r
    await r.close()


async def test_schema_created_idempotently_with_wal(tmp_path):
    path = tmp_path / "t.db"
    for _ in range(2):
        r = SqliteTrackingRepository(str(path))
        assert await r.init()
        await r.close()
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert conn.execute("SELECT count(*) FROM analyses").fetchone()[0] == 0


async def test_received_then_lifecycle_round_trip(repo):
    aid = uuid.uuid4()
    await repo.upsert_received(aid, r"C:\cv.pdf", "qwen2.5:3b")
    rec = await repo.get(aid)
    assert rec.status is TrackingStatus.RECEIVED
    assert rec.resume_file_reference == r"C:\cv.pdf" and rec.model == "qwen2.5:3b"

    await repo.mark(aid, TrackingStatus.PROCESSING)
    await repo.mark(aid, TrackingStatus.COMPLETED, result_json='{"score": 72}')
    await repo.mark(aid, callback_outcome=CallbackOutcome.DELIVERED)
    rec = await repo.get(aid)
    assert rec.status is TrackingStatus.COMPLETED
    assert rec.result_json == '{"score": 72}'
    assert rec.callback_outcome is CallbackOutcome.DELIVERED
    assert rec.updated_at >= rec.received_at


async def test_failure_recorded(repo):
    aid = uuid.uuid4()
    await repo.upsert_received(aid, "ref", "m")
    await repo.mark(aid, TrackingStatus.FAILED, failure_reason="llm_timeout")
    await repo.mark(aid, callback_outcome=CallbackOutcome.UNDELIVERED)
    rec = await repo.get(aid)
    assert rec.status is TrackingStatus.FAILED
    assert rec.failure_reason == "llm_timeout"
    assert rec.callback_outcome is CallbackOutcome.UNDELIVERED


async def test_redispatch_resets_previous_outcome(repo):
    aid = uuid.uuid4()
    await repo.upsert_received(aid, "ref", "m")
    await repo.mark(aid, TrackingStatus.FAILED, failure_reason="llm_timeout")
    await repo.upsert_received(aid, "ref2", "m")
    rec = await repo.get(aid)
    assert rec.status is TrackingStatus.RECEIVED
    assert rec.failure_reason is None and rec.resume_file_reference == "ref2"


async def test_unknown_id_returns_none(repo):
    assert await repo.get(uuid.uuid4()) is None


async def test_concurrent_writes_are_serialised(repo):
    ids = [uuid.uuid4() for _ in range(25)]
    await asyncio.gather(*(repo.upsert_received(i, "ref", "m") for i in ids))
    await asyncio.gather(*(repo.mark(i, TrackingStatus.COMPLETED) for i in ids))
    records = await asyncio.gather(*(repo.get(i) for i in ids))
    assert all(r.status is TrackingStatus.COMPLETED for r in records)


async def test_db_errors_are_swallowed(repo, caplog):
    aid = uuid.uuid4()
    await repo._db.execute("DROP TABLE analyses")  # simulate a broken database
    await repo.upsert_received(aid, "ref", "m")
    await repo.mark(aid, TrackingStatus.FAILED, failure_reason="x")
    assert await repo.get(aid) is None
    assert "tracking write failed" in caplog.text


async def test_unusable_path_does_not_raise(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    r = SqliteTrackingRepository(str(blocker / "sub" / "t.db"))
    assert await r.init() is False
    aid = uuid.uuid4()
    await r.upsert_received(aid, "ref", "m")  # no-ops without a database
    assert await r.get(aid) is None
