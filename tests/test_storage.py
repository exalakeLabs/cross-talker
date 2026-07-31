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
    assert stored.exchanges[0].prompt_sent == "Exact engineered prompt"
    assert stored.exchanges[0].answer == "Model answer"
    assert stored.exchanges[0].requested_at == requested_at
    assert stored.exchanges[0].responded_at == responded_at


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
