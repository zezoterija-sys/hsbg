"""
PUCT search for Brain B's neural-guided MCTS.

The search tree is local to one player decision. The shared NeuralBrain supplies
policy priors and a value estimate, but it does not own or share trees.

Imperfect-information rule:
Every simulation starts from a fresh determinization sampled only from the
root player's AgentObservation. The environment must never inspect the real
hidden Bob state while constructing that determinization.

Training:
Optional root Dirichlet noise can be enabled for self-play exploration.
Evaluation should leave it disabled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from typing import Any, Protocol, Sequence

from agents.mcts_core import MCTSEnvironment
from agents.neural_brain import NeuralBrain
from agents.observation import AgentObservation
from game.actions import Action


class NeuralMCTSEnvironment(MCTSEnvironment, Protocol):
    """
    MCTS environment that can also expose an AI-safe observation for a
    simulated state.

    observe() must apply the same information rules as the real observation
    layer. It must not expose determinized hidden facts merely because the
    simulator internally sampled them.
    """

    def observe(
        self,
        state: Any,
        root_player_id: int,
    ) -> AgentObservation:
        """Return root player's legal information for this simulated state."""


@dataclass(frozen=True)
class PUCTConfig:
    c_puct: float = 1.5
    max_tree_depth: int = 64

    # Standard AlphaZero-style root exploration noise. Only used when the
    # caller explicitly enables it (normally training/self-play only).
    dirichlet_alpha: float = 0.30
    dirichlet_epsilon: float = 0.25

    def __post_init__(self) -> None:
        if self.c_puct < 0:
            raise ValueError("c_puct cannot be negative.")
        if self.max_tree_depth <= 0:
            raise ValueError("max_tree_depth must be positive.")
        if self.dirichlet_alpha <= 0:
            raise ValueError("dirichlet_alpha must be positive.")
        if not 0.0 <= self.dirichlet_epsilon <= 1.0:
            raise ValueError(
                "dirichlet_epsilon must be between 0 and 1."
            )


@dataclass
class PUCTNode:
    parent: "PUCTNode | None" = None
    action_from_parent: Action | None = None
    prior: float = 0.0

    visits: int = 0
    value_sum: float = 0.0

    children: dict[Action, "PUCTNode"] = field(
        default_factory=dict
    )

    @property
    def mean_value(self) -> float:
        if self.visits == 0:
            return 0.0
        return self.value_sum / self.visits

    def update(self, value: float) -> None:
        self.visits += 1
        self.value_sum += float(value)

    def expanded_legal_children(
        self,
        legal_actions: Sequence[Action],
    ) -> list[tuple[Action, "PUCTNode"]]:
        return [
            (action, self.children[action])
            for action in legal_actions
            if action in self.children
        ]

    def select_puct(
        self,
        legal_actions: Sequence[Action],
        *,
        c_puct: float,
        rng: random.Random,
    ) -> tuple[Action, "PUCTNode"]:
        candidates = self.expanded_legal_children(
            legal_actions
        )

        if not candidates:
            raise ValueError(
                "No expanded legal children available for PUCT."
            )

        sqrt_parent = math.sqrt(max(1, self.visits))

        scored: list[
            tuple[Action, PUCTNode, float]
        ] = []

        for action, child in candidates:
            q_value = child.mean_value
            exploration = (
                c_puct
                * child.prior
                * sqrt_parent
                / (1 + child.visits)
            )
            scored.append(
                (
                    action,
                    child,
                    q_value + exploration,
                )
            )

        best_score = max(
            score
            for _, _, score in scored
        )

        tied = [
            (action, child)
            for action, child, score in scored
            if math.isclose(
                score,
                best_score,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
        ]

        return rng.choice(tied)


@dataclass(frozen=True)
class PUCTSearchResult:
    action: Action
    simulations: int
    root: PUCTNode

    root_actions: tuple[Action, ...]
    visit_policy: tuple[float, ...]

    def policy_for(
        self,
        legal_actions: Sequence[Action],
    ) -> tuple[float, ...]:
        """
        Return visit probabilities aligned to legal_actions.

        This is useful when the caller preserved the same action objects but
        changed collection type.
        """
        lookup = {
            action: probability
            for action, probability in zip(
                self.root_actions,
                self.visit_policy,
            )
        }

        return tuple(
            float(lookup.get(action, 0.0))
            for action in legal_actions
        )


class NeuralPUCTSearch:
    """Neural policy/value guided MCTS."""

    def __init__(
        self,
        environment: NeuralMCTSEnvironment,
        brain: NeuralBrain,
        config: PUCTConfig | None = None,
    ) -> None:
        self.environment = environment
        self.brain = brain
        self.config = config or PUCTConfig()

    def search(
        self,
        observation: AgentObservation,
        root_legal_actions: Sequence[Action],
        simulations: int,
        rng: random.Random,
        *,
        add_root_noise: bool = False,
        temperature: float = 0.0,
    ) -> PUCTSearchResult:
        root_actions = tuple(root_legal_actions)

        if not root_actions:
            raise ValueError(
                "root_legal_actions cannot be empty."
            )
        if simulations < 0:
            raise ValueError(
                "simulations cannot be negative."
            )
        if temperature < 0:
            raise ValueError(
                "temperature cannot be negative."
            )

        root = PUCTNode()

        # Expand root once from the actual root observation. This gives the
        # search policy priors even if simulations == 0.
        root_evaluation = self.brain.evaluate(
            observation,
            root_actions,
        )

        root_priors = self._normalized_priors(
            root_evaluation.priors,
            len(root_actions),
        )

        if add_root_noise and len(root_actions) > 1:
            root_priors = self._mix_dirichlet_noise(
                root_priors,
                rng,
            )

        self._expand_node(
            root,
            root_actions,
            root_priors,
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

            leaf_value: float | None = None

            while (
                depth < self.config.max_tree_depth
                and not self.environment.is_terminal(
                    state,
                    observation.player_id,
                )
            ):
                legal_actions = tuple(
                    root_actions
                    if node is root
                    else self.environment.legal_actions(
                        state,
                        observation.player_id,
                    )
                )

                if not legal_actions:
                    leaf_value = 0.0
                    break

                # If a determinization exposes a legal action sequence that
                # this node has not seen yet, expand/refresh legal children from
                # the AI-safe simulated observation.
                missing = [
                    action
                    for action in legal_actions
                    if action not in node.children
                ]

                if missing:
                    simulated_observation = (
                        observation
                        if node is root
                        else self.environment.observe(
                            state,
                            observation.player_id,
                        )
                    )

                    evaluation = self.brain.evaluate(
                        simulated_observation,
                        legal_actions,
                    )

                    priors = self._normalized_priors(
                        evaluation.priors,
                        len(legal_actions),
                    )

                    self._expand_node(
                        node,
                        legal_actions,
                        priors,
                    )

                    # Standard neural MCTS stops at newly evaluated leaf.
                    leaf_value = float(evaluation.value)
                    break

                action, child = node.select_puct(
                    legal_actions,
                    c_puct=self.config.c_puct,
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

                # First visit to an already-expanded child: evaluate the
                # resulting state rather than descending needlessly.
                if child.visits == 0:
                    if self.environment.is_terminal(
                        state,
                        observation.player_id,
                    ):
                        simulated_observation = (
                            self.environment.observe(
                                state,
                                observation.player_id,
                            )
                        )
                        leaf_value = self._terminal_value(
                            simulated_observation,
                            observation.player_id,
                        )
                    else:
                        next_legal = tuple(
                            self.environment.legal_actions(
                                state,
                                observation.player_id,
                            )
                        )

                        if not next_legal:
                            leaf_value = 0.0
                        else:
                            simulated_observation = (
                                self.environment.observe(
                                    state,
                                    observation.player_id,
                                )
                            )
                            evaluation = self.brain.evaluate(
                                simulated_observation,
                                next_legal,
                            )
                            priors = self._normalized_priors(
                                evaluation.priors,
                                len(next_legal),
                            )
                            self._expand_node(
                                child,
                                next_legal,
                                priors,
                            )
                            leaf_value = float(
                                evaluation.value
                            )
                    break

            if leaf_value is None:
                # Depth limit or terminal root reached without a fresh leaf
                # evaluation. Evaluate the AI-safe current state.
                simulated_observation = (
                    self.environment.observe(
                        state,
                        observation.player_id,
                    )
                )

                if self.environment.is_terminal(
                    state,
                    observation.player_id,
                ):
                    leaf_value = self._terminal_value(
                        simulated_observation,
                        observation.player_id,
                    )
                else:
                    legal = tuple(
                        self.environment.legal_actions(
                            state,
                            observation.player_id,
                        )
                    )
                    if legal:
                        leaf_value = float(
                            self.brain.evaluate(
                                simulated_observation,
                                legal,
                            ).value
                        )
                    else:
                        leaf_value = 0.0

            if not math.isfinite(leaf_value):
                raise ValueError(
                    "Neural MCTS produced a non-finite "
                    f"leaf value: {leaf_value!r}"
                )

            leaf_value = max(
                -1.0,
                min(1.0, float(leaf_value)),
            )

            for visited in path:
                visited.update(leaf_value)

            completed += 1

        visit_policy = self._visit_policy(
            root,
            root_actions,
        )

        selected = self._select_action(
            root_actions,
            visit_policy,
            root_priors,
            temperature=temperature,
            rng=rng,
        )

        return PUCTSearchResult(
            action=selected,
            simulations=completed,
            root=root,
            root_actions=root_actions,
            visit_policy=visit_policy,
        )

    @staticmethod
    def _expand_node(
        node: PUCTNode,
        legal_actions: Sequence[Action],
        priors: Sequence[float],
    ) -> None:
        if len(legal_actions) != len(priors):
            raise ValueError(
                "legal_actions and priors must have equal length."
            )

        for action, prior in zip(
            legal_actions,
            priors,
        ):
            if action in node.children:
                # Preserve visit/value statistics. Refreshing a prior from a
                # different determinization is intentionally avoided; the first
                # AI-visible estimate defines this action-sequence node.
                continue

            node.children[action] = PUCTNode(
                parent=node,
                action_from_parent=action,
                prior=float(prior),
            )

    @staticmethod
    def _normalized_priors(
        priors: Sequence[float],
        expected_length: int,
    ) -> tuple[float, ...]:
        if len(priors) != expected_length:
            raise ValueError(
                "Brain prior count does not match legal action count."
            )

        cleaned = [
            max(0.0, float(value))
            if math.isfinite(float(value))
            else 0.0
            for value in priors
        ]

        total = sum(cleaned)

        if total <= 0:
            uniform = 1.0 / expected_length
            return tuple(
                uniform
                for _ in range(expected_length)
            )

        return tuple(
            value / total
            for value in cleaned
        )

    def _mix_dirichlet_noise(
        self,
        priors: Sequence[float],
        rng: random.Random,
    ) -> tuple[float, ...]:
        """
        Sample Dirichlet using gamma variates from the agent's seeded RNG.

        This avoids NumPy/global RNG state and keeps self-play reproducible.
        """
        samples = [
            rng.gammavariate(
                self.config.dirichlet_alpha,
                1.0,
            )
            for _ in priors
        ]

        total = sum(samples)

        if total <= 0:
            noise = [
                1.0 / len(samples)
                for _ in samples
            ]
        else:
            noise = [
                sample / total
                for sample in samples
            ]

        epsilon = self.config.dirichlet_epsilon

        mixed = [
            (1.0 - epsilon) * prior
            + epsilon * noisy
            for prior, noisy in zip(
                priors,
                noise,
            )
        ]

        total_mixed = sum(mixed)

        return tuple(
            value / total_mixed
            for value in mixed
        )

    @staticmethod
    def _visit_policy(
        root: PUCTNode,
        root_actions: Sequence[Action],
    ) -> tuple[float, ...]:
        visits = [
            float(root.children[action].visits)
            if action in root.children
            else 0.0
            for action in root_actions
        ]

        total = sum(visits)

        if total <= 0:
            uniform = 1.0 / len(root_actions)
            return tuple(
                uniform
                for _ in root_actions
            )

        return tuple(
            count / total
            for count in visits
        )

    @staticmethod
    def _select_action(
        root_actions: Sequence[Action],
        visit_policy: Sequence[float],
        priors: Sequence[float],
        *,
        temperature: float,
        rng: random.Random,
    ) -> Action:
        if len(root_actions) == 1:
            return root_actions[0]

        # Evaluation/default play: robust child.
        if temperature == 0:
            max_visit = max(visit_policy)
            candidates = [
                index
                for index, value in enumerate(
                    visit_policy
                )
                if math.isclose(
                    value,
                    max_visit,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
            ]

            if len(candidates) > 1:
                best_prior = max(
                    priors[index]
                    for index in candidates
                )
                candidates = [
                    index
                    for index in candidates
                    if math.isclose(
                        priors[index],
                        best_prior,
                        rel_tol=1e-12,
                        abs_tol=1e-12,
                    )
                ]

            return root_actions[
                rng.choice(candidates)
            ]

        # Training exploration: sample from visit counts^(1/T).
        exponent = 1.0 / temperature
        weights = [
            max(0.0, probability) ** exponent
            for probability in visit_policy
        ]

        total = sum(weights)

        if total <= 0:
            weights = list(priors)
            total = sum(weights)

        threshold = rng.random() * total
        cumulative = 0.0

        for action, weight in zip(
            root_actions,
            weights,
        ):
            cumulative += weight
            if cumulative >= threshold:
                return action

        return root_actions[-1]

    @staticmethod
    def _terminal_value(
        observation: AgentObservation,
        root_player_id: int,
    ) -> float:
        """
        Exact terminal placement value when the simulated game is over.

        1st -> +1.0
        8th -> -1.0
        linearly spaced in between.
        """
        if observation.player_id != root_player_id:
            raise ValueError(
                "Terminal observation belongs to wrong player."
            )

        placement = observation.self_player.placement

        if placement is None:
            # Terminal adapter should normally provide placement. Neutral is
            # safer than inventing hidden information if it does not.
            return 0.0

        placement = max(
            1,
            min(8, int(placement)),
        )

        return 1.0 - (
            2.0 * (placement - 1) / 7.0
        )
