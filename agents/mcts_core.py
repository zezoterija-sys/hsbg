"""
Reusable Monte Carlo Tree Search core.

This module deliberately knows nothing about Bob or hidden simulator state.
Search is performed only through MCTSEnvironment, whose job is to sample a
plausible determinization from an AgentObservation and advance that simulated
world.

Brain A uses UCT + random rollout evaluation.
Brain B can reuse the node/search infrastructure later with neural priors/value
evaluation (PUCT) without exposing hidden real-game state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from typing import Any, Protocol, Sequence

from game.actions import Action
from agents.observation import AgentObservation


class MCTSEnvironment(Protocol):
    """
    Imperfect-information search adapter.

    sample_determinization MUST use only AgentObservation plus public game rules.
    It must not peek at Bob's true hidden hands, shops, or exact remaining pool.
    """

    def sample_determinization(
        self,
        observation: AgentObservation,
        root_player_id: int,
        rng: random.Random,
    ) -> Any:
        """Create one plausible mutable simulated world."""

    def legal_actions(
        self,
        state: Any,
        root_player_id: int,
    ) -> Sequence[Action]:
        """Return root player's legal actions at this simulated decision."""

    def step(
        self,
        state: Any,
        root_player_id: int,
        action: Action,
        rng: random.Random,
    ) -> Any:
        """
        Apply one root-player action and advance to its next decision point.

        Cheap simulated opponent behavior belongs here. Real opponents in the
        actual training game still use their real agents.
        """

    def is_terminal(
        self,
        state: Any,
        root_player_id: int,
    ) -> bool:
        """Whether no further tree decisions should be expanded."""

    def random_rollout(
        self,
        state: Any,
        root_player_id: int,
        rng: random.Random,
        max_steps: int,
    ) -> float:
        """
        Randomly simulate forward and return root-player value.

        Recommended value scale is [-1, 1], with higher always better for the
        root player. Reward shaping (combat wins, final placement, etc.) belongs
        in the environment/training reward design, not in MCTS bookkeeping.
        """


@dataclass(frozen=True)
class MCTSConfig:
    exploration_constant: float = math.sqrt(2.0)
    max_tree_depth: int = 64
    max_rollout_steps: int = 256

    def __post_init__(self) -> None:
        if self.exploration_constant < 0:
            raise ValueError("exploration_constant cannot be negative.")
        if self.max_tree_depth <= 0:
            raise ValueError("max_tree_depth must be positive.")
        if self.max_rollout_steps <= 0:
            raise ValueError("max_rollout_steps must be positive.")


@dataclass
class MCTSNode:
    parent: "MCTSNode | None" = None
    action_from_parent: Action | None = None
    visits: int = 0
    value_sum: float = 0.0
    children: dict[Action, "MCTSNode"] = field(default_factory=dict)

    @property
    def mean_value(self) -> float:
        return self.value_sum / self.visits if self.visits else 0.0

    def update(self, value: float) -> None:
        self.visits += 1
        self.value_sum += float(value)

    def unexpanded_actions(
        self,
        legal_actions: Sequence[Action],
    ) -> list[Action]:
        return [
            action
            for action in legal_actions
            if action not in self.children
        ]

    def best_uct_child(
        self,
        legal_actions: Sequence[Action],
        exploration_constant: float,
        rng: random.Random,
    ) -> tuple[Action, "MCTSNode"]:
        candidates: list[tuple[Action, MCTSNode, float]] = []

        parent_visits = max(1, self.visits)

        for action in legal_actions:
            child = self.children.get(action)
            if child is None:
                continue

            if child.visits == 0:
                score = math.inf
            else:
                exploitation = child.mean_value
                exploration = exploration_constant * math.sqrt(
                    math.log(parent_visits + 1) / child.visits
                )
                score = exploitation + exploration

            candidates.append((action, child, score))

        if not candidates:
            raise ValueError("No expanded legal children available.")

        best_score = max(score for _, _, score in candidates)
        tied = [
            (action, child)
            for action, child, score in candidates
            if score == best_score
        ]
        return rng.choice(tied)


@dataclass(frozen=True)
class MCTSSearchResult:
    action: Action
    simulations: int
    root: MCTSNode


class PureMCTSSearch:
    """UCT search with uniform random expansion and random rollouts."""

    def __init__(
        self,
        environment: MCTSEnvironment,
        config: MCTSConfig | None = None,
    ) -> None:
        self.environment = environment
        self.config = config or MCTSConfig()

    def search(
        self,
        observation: AgentObservation,
        root_legal_actions: Sequence[Action],
        simulations: int,
        rng: random.Random,
    ) -> MCTSSearchResult:
        actions = tuple(root_legal_actions)

        if not actions:
            raise ValueError("root_legal_actions cannot be empty.")
        if simulations < 0:
            raise ValueError("simulations cannot be negative.")

        root = MCTSNode()

        if simulations == 0:
            return MCTSSearchResult(
                action=rng.choice(actions),
                simulations=0,
                root=root,
            )

        completed = 0

        for _ in range(simulations):
            state = self.environment.sample_determinization(
                observation,
                observation.player_id,
                rng,
            )

            node = root
            path = [root]
            depth = 0

            while (
                depth < self.config.max_tree_depth
                and not self.environment.is_terminal(
                    state,
                    observation.player_id,
                )
            ):
                if node is root:
                    legal = actions
                else:
                    legal = tuple(
                        self.environment.legal_actions(
                            state,
                            observation.player_id,
                        )
                    )

                if not legal:
                    break

                unexpanded = node.unexpanded_actions(legal)

                if unexpanded:
                    action = rng.choice(unexpanded)
                    state = self.environment.step(
                        state,
                        observation.player_id,
                        action,
                        rng,
                    )

                    child = MCTSNode(
                        parent=node,
                        action_from_parent=action,
                    )
                    node.children[action] = child
                    node = child
                    path.append(node)
                    depth += 1
                    break

                action, child = node.best_uct_child(
                    legal_actions=legal,
                    exploration_constant=self.config.exploration_constant,
                    rng=rng,
                )

                state = self.environment.step(
                    state,
                    observation.player_id,
                    action,
                    rng,
                )
                node = child
                path.append(node)
                depth += 1

            value = self.environment.random_rollout(
                state,
                observation.player_id,
                rng,
                self.config.max_rollout_steps,
            )

            if not math.isfinite(value):
                raise ValueError(
                    f"MCTS rollout returned non-finite value: {value!r}"
                )

            for visited in path:
                visited.update(value)

            completed += 1

        selected = self._select_root_action(
            root,
            actions,
            rng,
        )

        return MCTSSearchResult(
            action=selected,
            simulations=completed,
            root=root,
        )

    @staticmethod
    def _select_root_action(
        root: MCTSNode,
        legal_actions: Sequence[Action],
        rng: random.Random,
    ) -> Action:
        """
        Standard robust-child choice: highest visit count.

        Mean value breaks visit-count ties; RNG breaks any remaining exact tie.
        """
        expanded = [
            (action, root.children[action])
            for action in legal_actions
            if action in root.children
        ]

        if not expanded:
            return rng.choice(tuple(legal_actions))

        max_visits = max(child.visits for _, child in expanded)
        by_visits = [
            (action, child)
            for action, child in expanded
            if child.visits == max_visits
        ]

        max_value = max(child.mean_value for _, child in by_visits)
        finalists = [
            action
            for action, child in by_visits
            if child.mean_value == max_value
        ]

        return rng.choice(finalists)
