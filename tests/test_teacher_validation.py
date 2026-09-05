"""Tests for held-out teacher policy and hero validation metrics."""

from types import SimpleNamespace

import pytest

from training.teacher_validation import (
    evaluate_hero_selector,
    evaluate_teacher_policy,
    teacher_action_index,
)


class _ActionType:
    def __init__(self, value):
        self.value = value


class _Action:
    def __init__(self, value):
        self.action_type = _ActionType(value)


class _FakeBrain:
    def __init__(self, priors, hero_scores=None):
        self._priors = list(priors)
        self._hero_scores = dict(hero_scores or {})

    def evaluate_many(self, requests):
        output = []
        for _observation, _actions in requests:
            priors = self._priors.pop(0)
            output.append(SimpleNamespace(priors=priors, value=0.0))
        return tuple(output)

    def evaluate_heroes(self, hero_ids):
        return SimpleNamespace(
            hero_ids=tuple(hero_ids),
            scores=tuple(self._hero_scores.get(hero_id, 0.0) for hero_id in hero_ids),
        )


def _sample(target, action_names):
    return SimpleNamespace(
        observation=object(),
        legal_actions=tuple(_Action(name) for name in action_names),
        policy_target=tuple(target),
    )


def test_teacher_action_index_uses_target_argmax():
    sample = _sample((0.01, 0.98, 0.01), ("buy_minion", "play_minion", "end_turn"))
    assert teacher_action_index(sample) == 1


def test_validation_reports_global_and_per_action_metrics():
    samples = [
        _sample((1.0, 0.0, 0.0, 0.0), ("buy_minion", "play_minion", "refresh", "end_turn")),
        _sample((0.0, 1.0, 0.0, 0.0), ("buy_minion", "play_minion", "refresh", "end_turn")),
        _sample((0.0, 0.0, 0.0, 1.0), ("buy_minion", "play_minion", "refresh", "end_turn")),
    ]
    brain = _FakeBrain(
        [
            (0.70, 0.10, 0.10, 0.10),
            (0.40, 0.30, 0.20, 0.10),
            (0.40, 0.30, 0.20, 0.10),
        ]
    )

    stats = evaluate_teacher_policy(brain, samples, batch_size=2)

    assert stats.samples == 3
    assert stats.top1_accuracy == pytest.approx(1 / 3)
    assert stats.top3_accuracy == pytest.approx(2 / 3)
    assert stats.teacher_action_probability == pytest.approx((0.70 + 0.30 + 0.10) / 3)
    assert stats.policy_loss > 0.0
    assert stats.per_action_type["buy_minion"].samples == 1
    assert stats.per_action_type["play_minion"].samples == 1
    assert stats.per_action_type["end_turn"].samples == 1


def test_hero_validation_uses_separate_outcome_model():
    samples = [
        SimpleNamespace(chosen_hero_id=10, final_value=1.0),
        SimpleNamespace(chosen_hero_id=20, final_value=-1.0),
    ]
    brain = _FakeBrain([], hero_scores={10: 0.5, 20: -0.5})

    stats = evaluate_hero_selector(brain, samples)

    assert stats.samples == 2
    assert stats.mse == pytest.approx(0.25)
    assert stats.mae == pytest.approx(0.5)
    assert stats.sign_accuracy == 1.0


def test_validation_rejects_empty_dataset():
    with pytest.raises(ValueError, match="cannot be empty"):
        evaluate_teacher_policy(_FakeBrain([]), [], batch_size=2)
