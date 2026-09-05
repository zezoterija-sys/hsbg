"""
Brain B player-seat agent: neural-guided MCTS.

Four NeuralMCTSAgent instances may share one NeuralBrain, but each agent owns:
- its own player ID,
- its own RNG,
- its own thinking budget,
- its own decision-local tree/search result.

No search tree or current-game observation is shared between seats.
"""

from __future__ import annotations

from typing import Sequence

from agents.base_agent import BaseAgent
from agents.neural_brain import NeuralBrain
from agents.observation import AgentObservation
from agents.puct_core import (
    NeuralMCTSEnvironment,
    NeuralPUCTSearch,
    PUCTConfig,
    PUCTSearchResult,
)
from agents.thinking_budget import ThinkingBudget
from game.actions import Action


class NeuralMCTSAgent(BaseAgent):
    """Policy/value-guided PUCT agent."""

    def __init__(
        self,
        player_id: int,
        environment: NeuralMCTSEnvironment,
        brain: NeuralBrain,
        name: str | None = None,
        *,
        thinking_budget: ThinkingBudget | None = None,
        config: PUCTConfig | None = None,
        seed: int | None = None,
        training_mode: bool = True,
        training_temperature: float = 1.0,
        hero_temperature: float = 1.0,
    ) -> None:
        super().__init__(
            player_id=player_id,
            name=name or f"NeuralMCTS_{player_id}",
            thinking_budget=thinking_budget,
            seed=seed,
        )

        if training_temperature < 0:
            raise ValueError(
                "training_temperature cannot be negative."
            )
        if hero_temperature < 0:
            raise ValueError(
                "hero_temperature cannot be negative."
            )

        self.environment = environment
        self.brain = brain

        self.searcher = NeuralPUCTSearch(
            environment=environment,
            brain=brain,
            config=config,
        )

        self.training_mode = bool(training_mode)
        self.training_temperature = float(
            training_temperature
        )
        self.hero_temperature = float(hero_temperature)

        self.last_search: PUCTSearchResult | None = None
        self._last_policy_target: tuple[float, ...] | None = None

    def choose_hero(
        self,
        hero_choices: Sequence[int],
    ) -> int:
        choices = tuple(int(hero_id) for hero_id in hero_choices)
        if not choices:
            raise ValueError("hero_choices cannot be empty.")
        if len(choices) == 1:
            return choices[0]

        evaluation = self.brain.evaluate_heroes(choices)
        scores = tuple(float(value) for value in evaluation.scores)

        # Evaluation mode is deterministic except for exact learned ties.
        if not self.training_mode or self.hero_temperature == 0.0:
            best = max(scores)
            indices = [
                index for index, value in enumerate(scores)
                if value == best
            ]
            return choices[self.rng.choice(indices)]

        # Training mode retains exploration. Before hero learning all scores are
        # exactly zero, so this reduces to uniform random selection.
        import math

        temperature = max(1e-6, self.hero_temperature)
        scaled = [value / temperature for value in scores]
        offset = max(scaled)
        weights = [math.exp(value - offset) for value in scaled]
        total = sum(weights)
        threshold = self.rng.random() * total
        cumulative = 0.0
        for hero_id, weight in zip(choices, weights):
            cumulative += weight
            if cumulative >= threshold:
                return hero_id
        return choices[-1]

    def choose_action(
        self,
        observation: AgentObservation,
        legal_actions: Sequence[Action],
    ) -> Action:
        actions = self.validate_legal_actions(
            legal_actions
        )

        if observation.player_id != self.player_id:
            raise ValueError(
                f"Observation belongs to player "
                f"{observation.player_id}, but this agent "
                f"controls player {self.player_id}."
            )

        if len(actions) == 1:
            self.last_search = None
            self._last_policy_target = (1.0,)
            return actions[0]

        allowed = (
            self.thinking_budget
            .get_allowed_simulations()
        )

        # If the phase budget is exhausted, still use the neural policy rather
        # than degrading Brain B to uniform random play.
        if allowed == 0:
            evaluation = self.brain.evaluate(
                observation,
                actions,
            )
            best_probability = max(
                evaluation.priors
            )
            best_indices = [
                index
                for index, probability
                in enumerate(evaluation.priors)
                if probability == best_probability
            ]
            selected = actions[
                self.rng.choice(best_indices)
            ]
            self.last_search = None
            self._last_policy_target = tuple(float(p) for p in evaluation.priors)
            return selected

        result = self.searcher.search(
            observation=observation,
            root_legal_actions=actions,
            simulations=allowed,
            rng=self.rng,
            add_root_noise=self.training_mode,
            temperature=(
                self.training_temperature
                if self.training_mode
                else 0.0
            ),
        )

        self.thinking_budget.record_simulations_used(
            result.simulations
        )

        selected = self.validate_selected_action(
            result.action,
            actions,
        )

        self.last_search = result
        self._last_policy_target = result.policy_for(actions)
        return selected

    def get_last_policy_target(
        self,
        legal_actions: Sequence[Action],
    ) -> tuple[float, ...] | None:
        """
        Return the latest MCTS visit distribution aligned to legal_actions.

        The self-play controller can stage this in GameTrajectory. The agent
        itself does not write to shared replay.
        """
        if self._last_policy_target is None:
            return None

        if len(self._last_policy_target) != len(tuple(legal_actions)):
            return None

        return self._last_policy_target

    def set_training_mode(
        self,
        enabled: bool,
    ) -> None:
        self.training_mode = bool(enabled)

    def reset_recruit_phase(self) -> None:
        super().reset_recruit_phase()
        self.last_search = None
        self._last_policy_target = None

    def reset_game(self) -> None:
        super().reset_game()
        self.last_search = None
        self._last_policy_target = None

    def __repr__(self) -> str:
        return (
            f"NeuralMCTSAgent("
            f"player_id={self.player_id}, "
            f"training_mode={self.training_mode}, "
            f"budget={self.thinking_budget}"
            f")"
        )
