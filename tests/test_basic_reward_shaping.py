"""Tests for intentionally weak basic Brain-B reward shaping."""

from types import SimpleNamespace

from game.actions import Action, ActionType
from training.basic_rewards import (
    BasicRewardConfig,
    basic_decision_reward,
    end_turn_reward_breakdown,
)


def _observation(*, board_count: int, gold: int):
    board = tuple(
        {"id": index + 1}
        if index < board_count
        else None
        for index in range(7)
    )

    return SimpleNamespace(
        self_player=SimpleNamespace(
            board=board,
            gold=gold,
        )
    )


def _action(action_type: ActionType):
    return Action(
        action_type=action_type,
    )


def test_non_end_turn_action_gets_no_basic_reward():
    observation = _observation(
        board_count=7,
        gold=0,
    )

    reward = basic_decision_reward(
        observation,
        _action(ActionType.REFRESH),
    )

    assert reward == 0.0


def test_empty_board_end_turn_is_penalized():
    observation = _observation(
        board_count=0,
        gold=3,
    )

    breakdown = end_turn_reward_breakdown(
        observation,
        _action(ActionType.END_TURN),
    )

    assert breakdown.board_count == 0
    assert breakdown.gold_efficiency_reward == 0.0
    assert breakdown.total < 0.0


def test_more_board_presence_scores_higher():
    end_turn = _action(
        ActionType.END_TURN
    )

    one = basic_decision_reward(
        _observation(
            board_count=1,
            gold=1,
        ),
        end_turn,
    )

    five = basic_decision_reward(
        _observation(
            board_count=5,
            gold=1,
        ),
        end_turn,
    )

    assert five > one


def test_less_unspent_gold_scores_higher_when_board_is_not_empty():
    end_turn = _action(
        ActionType.END_TURN
    )

    zero_gold = basic_decision_reward(
        _observation(
            board_count=3,
            gold=0,
        ),
        end_turn,
    )

    one_gold = basic_decision_reward(
        _observation(
            board_count=3,
            gold=1,
        ),
        end_turn,
    )

    three_gold = basic_decision_reward(
        _observation(
            board_count=3,
            gold=3,
        ),
        end_turn,
    )

    assert zero_gold > one_gold > three_gold


def test_reward_is_small_and_capped():
    config = BasicRewardConfig(
        board_minion_reward=0.5,
        empty_board_penalty=-0.03,
        zero_gold_reward=0.02,
        one_gold_reward=0.01,
        two_gold_reward=0.005,
        max_abs_reward=0.04,
    )

    reward = basic_decision_reward(
        _observation(
            board_count=7,
            gold=0,
        ),
        _action(ActionType.END_TURN),
        config,
    )

    assert reward == 0.04
