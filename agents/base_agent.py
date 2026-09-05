"""
Base interface for Hearthstone Battlegrounds AI agents.

Agents are decision makers only.

They do NOT:
- execute actions,
- mutate Bob, Player, Tavern, CardPool, or the real game state,
- receive hidden/omniscient game information,
- own training/reward logic,
- use wall-clock time as a thinking limit.

Agents DO:
- control exactly one player seat,
- receive an AI-safe observation plus legal actions,
- own an independent MCTS thinking budget,
- own an independent RNG stream for reproducible exploration,
- return decisions to the game/training controller.

The four agents belonging to the same brain may share a model or other
brain-level learning objects, but they do not share per-game observations,
memories, MCTS trees, or hidden information.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import random
from typing import TYPE_CHECKING, Sequence

from game.actions import Action
from agents.thinking_budget import ThinkingBudget

if TYPE_CHECKING:
    from agents.observation import AgentObservation


class BaseAgent(ABC):
    """Common interface for all player-seat agents."""

    PLAYER_COUNT = 8

    def __init__(
        self,
        player_id: int,
        name: str | None = None,
        *,
        thinking_budget: ThinkingBudget | None = None,
        seed: int | None = None,
    ) -> None:
        if not isinstance(player_id, int):
            raise TypeError("player_id must be an int.")

        if not 0 <= player_id < self.PLAYER_COUNT:
            raise ValueError(
                f"player_id must be between 0 and {self.PLAYER_COUNT - 1}."
            )

        self.player_id = player_id
        self.name = name or f"{self.__class__.__name__}_{player_id}"

        # Thinking budget is per agent/seat. Even agents that share a brain or
        # neural model keep their own independent search allowance.
        self.thinking_budget = (
            thinking_budget
            if thinking_budget is not None
            else ThinkingBudget()
        )

        # Independent RNG stream. Sharing a brain/model must never implicitly
        # make same-brain agents share random state.
        self.seed = seed
        self.rng = random.Random(seed)

    @abstractmethod
    def choose_action(
        self,
        observation: "AgentObservation",
        legal_actions: Sequence[Action],
    ) -> Action:
        """
        Choose one legal recruit-phase action.

        The observation contains only information this player is allowed to
        know. The legal action list is produced by the real game engine.

        Implementations must return one member of legal_actions and must not
        mutate the observation or the real game.
        """
        raise NotImplementedError

    def choose_hero(
        self,
        hero_choices: Sequence[int],
    ) -> int:
        """
        Choose one offered hero.

        Hero selection is intentionally separate from recruit-phase Action
        objects because Bob currently exposes hero selection through
        choose_hero(player_id, hero_id), not through ActionSpace.

        The default policy is uniform random selection. Individual agent types
        may override this later with a learned or search-based hero policy.
        """
        choices = tuple(hero_choices)

        if not choices:
            raise ValueError("hero_choices cannot be empty.")

        return self.rng.choice(choices)

    @staticmethod
    def validate_legal_actions(
        legal_actions: Sequence[Action],
    ) -> tuple[Action, ...]:
        """
        Validate and normalize an engine-provided legal-action collection.

        Returning an immutable tuple makes it harder for an agent to
        accidentally alter the caller's action list.
        """
        actions = tuple(legal_actions)

        if not actions:
            raise ValueError("legal_actions cannot be empty.")

        if not all(isinstance(action, Action) for action in actions):
            raise TypeError("legal_actions must contain only Action objects.")

        return actions

    @staticmethod
    def validate_selected_action(
        selected_action: Action,
        legal_actions: Sequence[Action],
    ) -> Action:
        """Ensure an agent returned an action the engine actually offered."""
        actions = tuple(legal_actions)

        if selected_action not in actions:
            raise ValueError(
                f"Agent selected an illegal action: {selected_action}"
            )

        return selected_action

    def reset_recruit_phase(self) -> None:
        """
        Reset recruit-phase-scoped agent state.

        Subclasses that add recruit-phase state should call super().
        """
        self.thinking_budget.reset_recruit_phase()

    def reset_game(self) -> None:
        """
        Reset per-game agent state.

        The base class only owns the thinking budget. Observation memory,
        search trees, and other per-game state belong to their respective
        components/subclasses.
        """
        self.thinking_budget.reset_recruit_phase()

    def get_player_id(self) -> int:
        return self.player_id

    def get_thinking_budget(self) -> ThinkingBudget:
        return self.thinking_budget

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"player_id={self.player_id}, "
            f"name={self.name!r}"
            f")"
        )
