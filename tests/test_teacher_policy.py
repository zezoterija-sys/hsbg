from types import SimpleNamespace
import random

from game.actions import Action, ActionType
from training.teacher_policy import BasicTeacherPolicy


def obs(*, board=0, hand=0, gold=3, tier=1, round_number=1, tavern=1):
    def minion(i):
        return {
            "id": 1000 + i,
            "cardType": "minion",
            "attack": 2,
            "health": 2,
            "tier": 1,
        }

    return SimpleNamespace(
        round_number=round_number,
        pending_choice=None,
        self_player=SimpleNamespace(
            board=tuple(minion(i) if i < board else None for i in range(7)),
            hand=tuple(minion(20 + i) for i in range(hand)),
            tavern_slots=tuple(minion(40 + i) if i < tavern else None for i in range(6)),
            tavern_spell=None,
            gold=gold,
            tavern_tier=tier,
            hero_power_cost=1,
        ),
    )


def test_empty_board_prefers_buy_over_end_turn():
    teacher = BasicTeacherPolicy()
    observation = obs(board=0, gold=3, tavern=1)
    actions = (
        Action(ActionType.END_TURN),
        Action(ActionType.BUY_MINION, target_idx=0),
        Action(ActionType.REFRESH),
    )
    decision = teacher.decide(observation, actions, random.Random(1))
    assert decision.action.action_type == ActionType.BUY_MINION
    assert abs(sum(decision.policy_target) - 1.0) < 1e-6


def test_minion_in_hand_prefers_playing_it():
    teacher = BasicTeacherPolicy()
    observation = obs(board=1, hand=1, gold=0, tavern=0)
    actions = (
        Action(ActionType.END_TURN),
        Action(ActionType.PLAY_MINION, target_idx=0, position_idx=1),
    )
    decision = teacher.decide(observation, actions, random.Random(2))
    assert decision.action.action_type == ActionType.PLAY_MINION


def test_selling_only_minion_is_worse_than_ending():
    teacher = BasicTeacherPolicy()
    observation = obs(board=1, hand=0, gold=0, tavern=0)
    sell = Action(ActionType.SELL_MINION, target_idx=0)
    end = Action(ActionType.END_TURN)
    actions = (sell, end)
    assert teacher.score_action(observation, sell, actions) < teacher.score_action(
        observation, end, actions
    )
