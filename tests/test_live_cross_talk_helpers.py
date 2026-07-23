from __future__ import annotations

import pytest

from tests.test_live_cross_talk import get_cross_talk_rounds


def test_cross_talk_rounds_defaults_to_two(monkeypatch) -> None:
    monkeypatch.delenv("CROSS_TALK_ROUNDS", raising=False)

    assert get_cross_talk_rounds() == 2


@pytest.mark.parametrize("value", ["0", "101", "invalid"])
def test_cross_talk_rounds_rejects_unsafe_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv("CROSS_TALK_ROUNDS", value)

    with pytest.raises(ValueError, match="CROSS_TALK_ROUNDS"):
        get_cross_talk_rounds()
