"""
Brain A: pure Monte Carlo Tree Search agent.

This agent:
- receives only AgentObservation,
- uses an independent per-seat MCTS tree for every decision,
- respects ThinkingBudget,
- uses UCT selection,
- uses random expansion and random rollouts,
- never directly receives or mutates Bob.

The actual simulated world/determinization logic is supplied by an
MCTSEnvironment adapter. That adapter is responsible for fair hidden-information
sampling and cheap random simulated-opponent behavior.
"""

from __future__ import annotations

from typing import Sequence

from agents.base_agent import BaseAgent
from agents.mcts_core import (
    MCTSConfig,
    MCTSEnvironment,
    MCTSSearchResult,
    PureMCTSSearch,
)
from agents.observation import AgentObservation
from agents.thinking_budget import ThinkingBudget
from game.actions import Action


class MCTSAgent(BaseAgent):
    """Pure UCT + random-rollout Battlegrounds agent."""

    def __init__(
        self,
        player_id: int,
        environment: MCTSEnvironment,
        name: str | None = None,
        *,
        thinking_budget: ThinkingBudget | None = None,
        config: MCTSConfig | None = None,
        seed: int | None = None,
    ) -> None:
        super().__init__(
            player_id=player_id,
            name=name or f"MCTS_{player_id}",
            thinking_budget=thinking_budget,
            seed=seed,
        )

        self.environment = environment
        self.searcher = PureMCTSSearch(
            environment=environment,
            config=config,
        )
        self.last_search: MCTSSearchResult | None = None

    def choose_action(
        self,
        observation: AgentObservation,
        legal_actions: Sequence[Action],
    ) -> Action:
        actions = self.validate_legal_actions(legal_actions)

        if observation.player_id != self.player_id:
            raise ValueError(
                f"Observation belongs to player {observation.player_id}, "
                f"but this agent controls player {self.player_id}."
            )

        # Do not spend search budget when there is no decision to make.
        if len(actions) == 1:
            self.last_search = None
            return actions[0]

        allowed = self.thinking_budget.get_allowed_simulations()

        # Once the phase search budget is exhausted, the agent still has to
        # produce legal actions. Uniform fallback is deterministic under seed.
        if allowed == 0:
            selected = self.rng.choice(actions)
            self.last_search = None
            return selected

        result = self.searcher.search(
            observation=observation,
            root_legal_actions=actions,
            simulations=allowed,
            rng=self.rng,
        )

        self.thinking_budget.record_simulations_used(
            result.simulations
        )

        selected = self.validate_selected_action(
            result.action,
            actions,
        )

        self.last_search = result
        return selected

    def reset_recruit_phase(self) -> None:
        super().reset_recruit_phase()
        self.last_search = None

    def reset_game(self) -> None:
        super().reset_game()
        self.last_search = None

    def __repr__(self) -> str:
        return (
            f"MCTSAgent("
            f"player_id={self.player_id}, "
            f"budget={self.thinking_budget}"
            f")"
        )
