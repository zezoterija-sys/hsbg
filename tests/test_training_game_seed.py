"""Check training entry-point seeds without running games or training models."""

from types import SimpleNamespace

import pytest

from training import self_play, teacher_data


class StopBeforeInitialization(Exception):
    pass


@pytest.mark.parametrize("kind", ["self_play", "teacher"])
def test_recorded_seed_reaches_bob_before_initialization(monkeypatch, kind):
    calls = []

    def capture_bob(*args, **kwargs):
        calls.append((args, kwargs))
        raise StopBeforeInitialization

    if kind == "self_play":
        monkeypatch.setattr(self_play, "Bob", capture_bob)
        runner = self_play.SelfPlayRunner.__new__(self_play.SelfPlayRunner)
        runner.config = SimpleNamespace(cards_file="data/raw/cards.json")
        with pytest.raises(StopBeforeInitialization):
            runner.run_game(game_index=0, seed=424242)
    else:
        monkeypatch.setattr(teacher_data, "Bob", capture_bob)
        runner = teacher_data.TeacherDataGenerator.__new__(teacher_data.TeacherDataGenerator)
        runner.config = SimpleNamespace(cards_file="data/raw/cards.json")
        with pytest.raises(StopBeforeInitialization):
            runner._generate_one_game(game_index=0, game_seed=424242)

    assert calls == [((), {"cards_file": "data/raw/cards.json", "seed": 424242})]
