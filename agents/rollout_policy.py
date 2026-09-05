"""
Cheap stochastic policies used only inside MCTS simulations.

Real training-game players do NOT use these policies. They use their real
MCTS / NeuralMCTS agents.

Uniformly sampling concrete Action objects is a bad rollout policy because
actions such as REPOSITION can have dozens of equivalent concrete choices and
would dominate probability mass. This policy first samples an action TYPE, then
one concrete action within that type.

That keeps rollouts random without accidentally turning "has many index
variants" into a strategic preference.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Sequence

from game.actions import Action, ActionType


@dataclass(frozen=True)
class RandomPolicyConfig:
    # Random rollouts need a realistic chance to finish recruit turns.
    end_turn_probability: float = 0.10

    # Hard cap prevents zero-cost/toggle/reposition loops.
    force_end_after_actions: int = 30

    def __post_init__(self) -> None:
        if not 0.0 <= self.end_turn_probability <= 1.0:
            raise ValueError(
                "end_turn_probability must be in [0, 1]."
            )
        if self.force_end_after_actions <= 0:
            raise ValueError(
                "force_end_after_actions must be positive."
            )


@dataclass(frozen=True)
class RolloutRewardConfig:
    """
    Outcome-based rollout shaping.

    These are deliberately adjustable defaults, not locked project constants.
    They use actual simulated combat outcomes rather than a hand-written board
    strength heuristic.
    """

    combat_win: float = 0.05
    combat_loss: float = -0.05
    combat_tie: float = 0.0

    def __post_init__(self) -> None:
        for value in (
            self.combat_win,
            self.combat_loss,
            self.combat_tie,
        ):
            if not -1.0 <= value <= 1.0:
                raise ValueError(
                    "Rollout reward components must be in [-1, 1]."
                )


class RandomLegalPolicy:
    """Random action-category policy for simulated players."""

    def __init__(
        self,
        config: RandomPolicyConfig | None = None,
    ) -> None:
        self.config = config or RandomPolicyConfig()

    def choose_action(
        self,
        legal_actions: Sequence[Action],
        rng: random.Random,
        *,
        actions_taken_this_turn: int = 0,
    ) -> Action:
        actions = tuple(
            legal_actions
        )

        if not actions:
            raise ValueError(
                "legal_actions cannot be empty."
            )

        # Discover / Choose One is mandatory in the engine, so if present it
        # should be resolved immediately.
        choices = [
            action
            for action in actions
            if getattr(
                action.action_type,
                "value",
                None,
            )
            == "choose_option" 
        ]

        if choices:
            return rng.choice(
                choices
            )

        end_actions = [
            action
            for action in actions
            if action.action_type
            == ActionType.END_TURN
        ]

        if (
            end_actions
            and (
                actions_taken_this_turn
                >= self.config.force_end_after_actions
                or rng.random()
                < self.config.end_turn_probability
            )
        ):
            return end_actions[0]

        by_type: dict[
            ActionType,
            list[Action],
        ] = {}

        for action in actions:
            if (
                action.action_type
                == ActionType.END_TURN
            ):
                continue

            by_type.setdefault(
                action.action_type,
                [],
            ).append(action)

        if not by_type:
            if end_actions:
                return end_actions[0]
            return rng.choice(
                actions
            )

        chosen_type = rng.choice(
            list(by_type.keys())
        )

        return rng.choice(
            by_type[chosen_type]
        )
