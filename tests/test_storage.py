from __future__ import annotations

import sqlite3

import cross_talker.storage
from cross_talker.storage import SQLiteRepository


async def test_persists_exact_exchange_metadata(tmp_path) -> None:
    repository = SQLiteRepository(tmp_path / "audit.db")
    run_id, _ = await repository.create_run("Original question", 2)
    exchange_id, requested_at = await repository.begin_exchange(
        run_id,
        "anthropic",
        "claude-test",
        1,
        "Exact engineered prompt",
    )
    responded_at = await repository.finish_exchange(exchange_id, "Model answer")
    await repository.finish_run(run_id, "completed")

    stored = await repository.get_run(run_id)

    assert stored is not None
    assert stored.original_prompt == "Original question"
    assert stored.rounds_requested == 2
    assert stored.exchanges[0].provider == "anthropic"
    assert stored.exchanges[0].model == "claude-test"
    assert stored.exchanges[0].round == 1
    assert stored.exchanges[0].kind == "response"
    assert stored.exchanges[0].prompt_sent == "Exact engineered prompt"
    assert stored.exchanges[0].answer == "Model answer"
    assert stored.exchanges[0].requested_at == requested_at
    assert stored.exchanges[0].responded_at == responded_at


async def test_migrates_existing_exchange_table_for_conclusions(tmp_path) -> None:
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                original_prompt TEXT NOT NULL,
                rounds_requested INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE exchanges (
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
            """
        )

    repository = SQLiteRepository(database_path)
    run_id, _ = await repository.create_run("Question", 0)
    exchange_id, _ = await repository.begin_exchange(
        run_id,
        "openai",
        "test-model",
        1,
        "Synthesize the responses",
        kind="conclusion",
    )
    await repository.finish_exchange(exchange_id, "Combined conclusion")

    stored = await repository.get_run(run_id)

    assert stored is not None
    assert stored.exchanges[0].kind == "conclusion"
    assert stored.exchanges[0].answer == "Combined conclusion"


async def test_reads_do_not_reapply_wal_mode(tmp_path, monkeypatch) -> None:
    repository = SQLiteRepository(tmp_path / "audit.db")
    run_id, _ = await repository.create_run("Original question", 1)
    journal_mode_calls: list[str] = []
    original_connect = sqlite3.connect

    class TrackingConnection(sqlite3.Connection):
        def execute(self, sql, parameters=(), /):
            if sql.strip().upper() == "PRAGMA JOURNAL_MODE = WAL":
                journal_mode_calls.append(sql)
            return super().execute(sql, parameters)

    def tracking_connect(*args, **kwargs):
        return original_connect(*args, **kwargs, factory=TrackingConnection)

    monkeypatch.setattr(cross_talker.storage.sqlite3, "connect", tracking_connect)

    assert await repository.get_run(run_id) is not None
    assert await repository.list_runs()
    assert journal_mode_calls == []
