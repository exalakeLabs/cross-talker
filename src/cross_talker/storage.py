from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from cross_talker.models import StoredExchange, StoredRun


def utc_now() -> datetime:
    return datetime.now(UTC)


class SQLiteRepository:
    """Durable audit storage for runs, prompts, and provider answers."""

    def __init__(self, database_path: str | Path) -> None:
        self._write_lock = asyncio.Lock()
        requested_path = str(database_path)
        self._use_uri = requested_path == ":memory:"
        self.database_path = (
            f"file:cross_talker_{uuid4().hex}?mode=memory&cache=shared"
            if self._use_uri
            else requested_path
        )
        if not self._use_uri:
            Path(self.database_path).expanduser().parent.mkdir(
                parents=True,
                exist_ok=True,
            )
        self._keeper = (
            sqlite3.connect(self.database_path, uri=True, check_same_thread=False)
            if self._use_uri
            else None
        )
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=30,
            uri=self._use_uri,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    original_prompt TEXT NOT NULL,
                    rounds_requested INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS exchanges (
                    exchange_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    round INTEGER NOT NULL,
                    prompt_sent TEXT NOT NULL,
                    answer TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    requested_at TEXT NOT NULL,
                    responded_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_exchanges_run_round
                    ON exchanges(run_id, round, provider);
                CREATE INDEX IF NOT EXISTS idx_runs_created_at
                    ON runs(created_at DESC);
                """
            )

    async def create_run(self, original_prompt: str, rounds_requested: int) -> tuple[str, datetime]:
        run_id = str(uuid4())
        created_at = utc_now()
        async with self._write_lock:
            await asyncio.to_thread(
                self._create_run_sync, run_id, original_prompt, rounds_requested, created_at
            )
        return run_id, created_at

    def _create_run_sync(
        self, run_id: str, original_prompt: str, rounds_requested: int, created_at: datetime
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, original_prompt, rounds_requested, status, created_at
                ) VALUES (?, ?, ?, 'running', ?)
                """,
                (run_id, original_prompt, rounds_requested, created_at.isoformat()),
            )

    async def begin_exchange(
        self, run_id: str, provider: str, model: str, round_number: int, prompt: str
    ) -> tuple[str, datetime]:
        exchange_id = str(uuid4())
        requested_at = utc_now()
        async with self._write_lock:
            await asyncio.to_thread(
                self._begin_exchange_sync,
                exchange_id,
                run_id,
                provider,
                model,
                round_number,
                prompt,
                requested_at,
            )
        return exchange_id, requested_at

    def _begin_exchange_sync(
        self,
        exchange_id: str,
        run_id: str,
        provider: str,
        model: str,
        round_number: int,
        prompt: str,
        requested_at: datetime,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO exchanges (
                    exchange_id, run_id, provider, model, round, prompt_sent,
                    status, requested_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    exchange_id,
                    run_id,
                    provider,
                    model,
                    round_number,
                    prompt,
                    requested_at.isoformat(),
                ),
            )

    async def finish_exchange(self, exchange_id: str, answer: str) -> datetime:
        responded_at = utc_now()
        async with self._write_lock:
            await asyncio.to_thread(
                self._finish_exchange_sync, exchange_id, answer, responded_at
            )
        return responded_at

    def _finish_exchange_sync(
        self, exchange_id: str, answer: str, responded_at: datetime
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE exchanges
                SET answer = ?, status = 'completed', responded_at = ?
                WHERE exchange_id = ?
                """,
                (answer, responded_at.isoformat(), exchange_id),
            )

    async def fail_exchange(self, exchange_id: str, error: str) -> None:
        responded_at = utc_now()
        async with self._write_lock:
            await asyncio.to_thread(
                self._fail_exchange_sync, exchange_id, error, responded_at
            )

    def _fail_exchange_sync(
        self, exchange_id: str, error: str, responded_at: datetime
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE exchanges
                SET status = 'failed', error = ?, responded_at = ?
                WHERE exchange_id = ?
                """,
                (error, responded_at.isoformat(), exchange_id),
            )

    async def finish_run(self, run_id: str, status: str) -> None:
        async with self._write_lock:
            await asyncio.to_thread(self._finish_run_sync, run_id, status, utc_now())

    def _finish_run_sync(self, run_id: str, status: str, completed_at: datetime) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE runs SET status = ?, completed_at = ? WHERE run_id = ?",
                (status, completed_at.isoformat(), run_id),
            )

    async def get_run(self, run_id: str) -> StoredRun | None:
        return await asyncio.to_thread(self._get_run_sync, run_id)

    def _get_run_sync(self, run_id: str) -> StoredRun | None:
        with self._connect() as connection:
            run = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if run is None:
                return None
            exchanges = connection.execute(
                """
                SELECT * FROM exchanges
                WHERE run_id = ?
                ORDER BY round, requested_at, provider
                """,
                (run_id,),
            ).fetchall()
        return self._map_run(run, exchanges)

    async def list_runs(self, limit: int = 50) -> list[StoredRun]:
        return await asyncio.to_thread(self._list_runs_sync, limit)

    def _list_runs_sync(self, limit: int) -> list[StoredRun]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._map_run(row, []) for row in rows]

    @staticmethod
    def _map_run(
        run: sqlite3.Row, exchanges: list[sqlite3.Row]
    ) -> StoredRun:
        return StoredRun(
            run_id=run["run_id"],
            original_prompt=run["original_prompt"],
            rounds_requested=run["rounds_requested"],
            status=run["status"],
            created_at=run["created_at"],
            completed_at=run["completed_at"],
            exchanges=[
                StoredExchange(
                    exchange_id=row["exchange_id"],
                    run_id=row["run_id"],
                    provider=row["provider"],
                    model=row["model"],
                    round=row["round"],
                    prompt_sent=row["prompt_sent"],
                    answer=row["answer"],
                    status=row["status"],
                    error=row["error"],
                    requested_at=row["requested_at"],
                    responded_at=row["responded_at"],
                )
                for row in exchanges
            ],
        )
