"""Regression tests for teacher recruit-loop termination."""

import random
from types import SimpleNamespace

from game.actions import Action, ActionType
from training.teacher_policy import BasicTeacherPolicy, TeacherPolicyConfig


def _observation(*, gold=3, round_number=2):
    return SimpleNamespace(
        round_number=round_number,
        pending_choice=None,
        self_player=SimpleNamespace(
            board=(None,) * 7,
            hand=(),
            tavern_slots=(),
            tavern_spell=None,
            gold=gold,
            tavern_tier=1,
            hero_power_cost=0,
        ),
    )


def test_repeated_zero_cost_hero_power_yields_to_end_turn():
    policy = BasicTeacherPolicy()
    observation = _observation()
    legal = (
        Action(ActionType.HERO_POWER),
        Action(ActionType.END_TURN),
    )

    first = policy.decide(
        observation,
        legal,
        random.Random(1),
        action_type_counts={},
        actions_taken_this_turn=0,
    )
    assert first.action.action_type == ActionType.HERO_POWER

    second = policy.decide(
        observation,
        legal,
        random.Random(1),
        action_type_counts={"hero_power": 1},
        actions_taken_this_turn=1,
    )
    assert second.action.action_type == ActionType.END_TURN


def test_teacher_hard_guard_forces_end_turn():
    policy = BasicTeacherPolicy(
        TeacherPolicyConfig(max_actions_per_turn=3)
    )
    observation = _observation()
    legal = (
        Action(ActionType.REFRESH),
        Action(ActionType.END_TURN),
    )

    decision = policy.decide(
        observation,
        legal,
        random.Random(2),
        action_type_counts={},
        actions_taken_this_turn=3,
    )

    assert decision.action.action_type == ActionType.END_TURN


def test_mandatory_choice_beats_hard_end_guard():
    if not hasattr(ActionType, "CHOOSE_OPTION"):
        return

    policy = BasicTeacherPolicy(
        TeacherPolicyConfig(max_actions_per_turn=1)
    )
    observation = _observation()
    observation.pending_choice = SimpleNamespace(
        options=({"id": 1, "tier": 1, "attack": 1, "health": 1},),
    )

    legal = (
        Action(ActionType.CHOOSE_OPTION, option_idx=0),
        Action(ActionType.END_TURN),
    )

    decision = policy.decide(
        observation,
        legal,
        random.Random(3),
        action_type_counts={},
        actions_taken_this_turn=5,
    )

    assert decision.action.action_type == ActionType.CHOOSE_OPTION
