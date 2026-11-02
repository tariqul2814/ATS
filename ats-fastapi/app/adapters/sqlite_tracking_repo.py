"""Local SQLite record of every analysis (Req 21).

Auxiliary, never on the critical path: every method logs and swallows its own errors (Req 21.5).
One shared aiosqlite connection in WAL mode; writes are serialised with a lock because SQLite
allows a single writer (Req 21.7).
"""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import aiosqlite

from app.ports.tracking_repo import AnalysisRecord, CallbackOutcome, TrackingStatus

log = logging.getLogger("ats.tracking")

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    analysis_id            TEXT PRIMARY KEY,
    status                 TEXT NOT NULL,
    received_at            TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    resume_file_reference  TEXT NOT NULL,
    model                  TEXT NOT NULL,
    callback_outcome       TEXT,
    failure_reason         TEXT,
    result_json            TEXT
);
CREATE INDEX IF NOT EXISTS ix_analyses_status ON analyses (status, updated_at);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class SqliteTrackingRepository:
    """ITrackingRepository backed by SQLite; swallows its own errors so it can't fail an analysis."""

    def __init__(self, path: str):
        self._path = path
        self._db: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()

    async def init(self) -> bool:
        """Open the database and create/upgrade the schema; idempotent (Req 21.6)."""
        try:
            if self._path != ":memory:":
                Path(self._path).parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(self._path)
            self._db.row_factory = aiosqlite.Row
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA busy_timeout=5000")
            await self._db.executescript(SCHEMA)
            await self._db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            await self._db.commit()
            return True
        except Exception:
            log.exception("tracking database unavailable; continuing without tracking")
            await self.close()
            return False

    async def close(self) -> None:
        """Close the database connection if open; errors are logged, not raised."""
        if self._db is not None:
            try:
                await self._db.close()
            except Exception:
                log.warning("error closing tracking database", exc_info=True)
            self._db = None

    async def upsert_received(self, analysis_id: UUID, resume_file_reference: str, model: str) -> None:
        """Insert or reset the analysis row to the RECEIVED state, clearing any prior outcome."""
        now = _now()
        await self._write(
            analysis_id,
            """INSERT INTO analyses (analysis_id, status, received_at, updated_at, resume_file_reference, model)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(analysis_id) DO UPDATE SET
                   status = excluded.status, received_at = excluded.received_at,
                   updated_at = excluded.updated_at,
                   resume_file_reference = excluded.resume_file_reference, model = excluded.model,
                   callback_outcome = NULL, failure_reason = NULL, result_json = NULL""",
            (str(analysis_id), TrackingStatus.RECEIVED.value, now, now, resume_file_reference, model),
        )

    async def mark(
        self,
        analysis_id: UUID,
        status: TrackingStatus | None = None,
        *,
        callback_outcome: CallbackOutcome | None = None,
        failure_reason: str | None = None,
        result_json: str | None = None,
    ) -> None:
        """Update the given columns on the analysis row, always bumping updated_at."""
        fields = {
            "status": status.value if status else None,
            "callback_outcome": callback_outcome.value if callback_outcome else None,
            "failure_reason": failure_reason,
            "result_json": result_json,
        }
        updates = {k: v for k, v in fields.items() if v is not None}
        updates["updated_at"] = _now()
        assignments = ", ".join(f"{column} = ?" for column in updates)  # columns are fixed names
        await self._write(
            analysis_id,
            f"UPDATE analyses SET {assignments} WHERE analysis_id = ?",
            (*updates.values(), str(analysis_id)),
        )

    async def get(self, analysis_id: UUID) -> AnalysisRecord | None:
        """Return the stored record, or None if absent or the database is unavailable."""
        if self._db is None:
            return None
        try:
            async with self._db.execute(
                "SELECT * FROM analyses WHERE analysis_id = ?", (str(analysis_id),)
            ) as cursor:
                row = await cursor.fetchone()
        except Exception:
            log.warning("tracking read failed", extra={"analysis_id": str(analysis_id)}, exc_info=True)
            return None
        if row is None:
            return None
        return AnalysisRecord(
            analysis_id=UUID(row["analysis_id"]),
            status=TrackingStatus(row["status"]),
            received_at=row["received_at"],
            updated_at=row["updated_at"],
            resume_file_reference=row["resume_file_reference"],
            model=row["model"],
            callback_outcome=CallbackOutcome(row["callback_outcome"]) if row["callback_outcome"] else None,
            failure_reason=row["failure_reason"],
            result_json=row["result_json"],
        )

    async def _write(self, analysis_id: UUID, sql: str, params: tuple) -> None:
        if self._db is None:
            return
        try:
            async with self._write_lock:
                await self._db.execute(sql, params)
                await self._db.commit()
        except Exception:
            log.warning("tracking write failed", extra={"analysis_id": str(analysis_id)}, exc_info=True)
