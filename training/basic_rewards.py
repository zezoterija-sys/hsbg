"""
Small, generic reward shaping for Brain B.

This module intentionally teaches only very broad Battlegrounds sanity:
- ending recruit with minions on board is better than ending empty,
- wasting less unspent gold at END_TURN is mildly better.

It does NOT encode card strength, tribes, curves, hero strategy, or hidden
information. Final placement and combat results remain the dominant targets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from game.actions import Action, ActionType


@dataclass(frozen=True)
class BasicRewardConfig:
    """Weights for intentionally weak, generic END_TURN shaping."""

    enabled: bool = True

    # Board presence: 7 minions -> +0.028 with the default weight.
    board_minion_reward: float = 0.004

    # Strongest basic correction: do not voluntarily end with no board.
    empty_board_penalty: float = -0.030

    # Small efficiency bonus. These are deliberately weaker than combat reward.
    zero_gold_reward: float = 0.012
    one_gold_reward: float = 0.008
    two_gold_reward: float = 0.003

    # Safety cap so hand-written shaping never dominates actual game outcome.
    max_abs_reward: float = 0.040

    def __post_init__(self) -> None:
        values = (
            self.board_minion_reward,
            self.empty_board_penalty,
            self.zero_gold_reward,
            self.one_gold_reward,
            self.two_gold_reward,
            self.max_abs_reward,
        )

        if any(not -1.0 <= float(value) <= 1.0 for value in values):
            raise ValueError(
                "Basic reward weights must be in [-1, 1]."
            )

        if self.board_minion_reward < 0:
            raise ValueError(
                "board_minion_reward cannot be negative."
            )

        if self.empty_board_penalty > 0:
            raise ValueError(
                "empty_board_penalty cannot be positive."
            )

        if min(
            self.zero_gold_reward,
            self.one_gold_reward,
            self.two_gold_reward,
        ) < 0:
            raise ValueError(
                "Gold-efficiency rewards cannot be negative."
            )

        if not (
            self.zero_gold_reward
            >= self.one_gold_reward
            >= self.two_gold_reward
        ):
            raise ValueError(
                "Gold-efficiency rewards must decrease as unspent gold rises."
            )

        if self.max_abs_reward <= 0:
            raise ValueError(
                "max_abs_reward must be positive."
            )


@dataclass(frozen=True)
class BasicRewardBreakdown:
    board_count: int
    unspent_gold: int
    board_reward: float
    empty_board_penalty: float
    gold_efficiency_reward: float
    total: float


def _self_view(observation: Any) -> Any:
    view = getattr(observation, "self_player", None)
    if view is None:
        raise ValueError(
            "Observation is missing self_player."
        )
    return view


def _board_count(view: Any) -> int:
    board = getattr(view, "board", ()) or ()
    return sum(
        card is not None
        for card in board
    )


def _gold_efficiency_reward(
    gold: int,
    config: BasicRewardConfig,
) -> float:
    if gold <= 0:
        return float(config.zero_gold_reward)
    if gold == 1:
        return float(config.one_gold_reward)
    if gold == 2:
        return float(config.two_gold_reward)
    return 0.0


def end_turn_reward_breakdown(
    observation: Any,
    action: Action,
    config: BasicRewardConfig | None = None,
) -> BasicRewardBreakdown:
    """
    Score broad END_TURN sanity from the exact pre-action observation.

    Non-END_TURN decisions always receive zero. This avoids accidentally
    rewarding wasteful REFRESH/SELL actions merely because they spend gold.
    """
    config = config or BasicRewardConfig()

    if (
        not config.enabled
        or action.action_type != ActionType.END_TURN
    ):
        return BasicRewardBreakdown(
            board_count=0,
            unspent_gold=0,
            board_reward=0.0,
            empty_board_penalty=0.0,
            gold_efficiency_reward=0.0,
            total=0.0,
        )

    view = _self_view(observation)

    board_count = _board_count(view)
    gold = max(
        0,
        int(getattr(view, "gold", 0) or 0),
    )

    board_reward = (
        board_count
        * float(config.board_minion_reward)
    )

    empty_penalty = (
        float(config.empty_board_penalty)
        if board_count == 0
        else 0.0
    )

    # Do not give a "good job spending gold" bonus to an empty board.
    # Otherwise an agent could learn to burn all gold and still receive
    # positive shaping despite having no combat presence.
    gold_reward = (
        _gold_efficiency_reward(
            gold,
            config,
        )
        if board_count > 0
        else 0.0
    )

    raw_total = (
        board_reward
        + empty_penalty
        + gold_reward
    )

    cap = abs(
        float(config.max_abs_reward)
    )

    total = max(
        -cap,
        min(
            cap,
            raw_total,
        ),
    )

    return BasicRewardBreakdown(
        board_count=board_count,
        unspent_gold=gold,
        board_reward=board_reward,
        empty_board_penalty=empty_penalty,
        gold_efficiency_reward=gold_reward,
        total=total,
    )


def basic_decision_reward(
    observation: Any,
    action: Action,
    config: BasicRewardConfig | None = None,
) -> float:
    """Return the scalar basic shaping reward used by self-play."""
    return end_turn_reward_breakdown(
        observation,
        action,
        config,
    ).total
