"""
Replay storage for neural-guided MCTS training.

Critical anti-leak rule:
Current-game decisions are NOT inserted into the shared replay buffer while
that game is still running. They live in a GameTrajectory. Only after the game
ends are finalized samples committed to ReplayBuffer.

This allows Brain B to train between rounds from *previous completed games*
without indirectly transmitting current-lobby private information through
shared model weights.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import random
from typing import Iterable, Sequence

from agents.observation import AgentObservation
from game.actions import Action


@dataclass(frozen=True)
class PendingDecision:
    """One neural-MCTS decision before its final value target is known."""

    game_id: str
    player_id: int
    round_number: int
    observation: AgentObservation
    legal_actions: tuple[Action, ...]
    policy_target: tuple[float, ...]
    shaped_reward: float = 0.0

    def __post_init__(self) -> None:
        if not self.legal_actions:
            raise ValueError("legal_actions cannot be empty.")

        if len(self.policy_target) != len(self.legal_actions):
            raise ValueError(
                "policy_target must align exactly with legal_actions."
            )

        total = sum(self.policy_target)

        if total <= 0:
            raise ValueError(
                "policy_target probabilities must have positive mass."
            )


@dataclass(frozen=True)
class TrainingSample:
    """Finalized sample safe to place in shared completed-game replay."""

    game_id: str
    player_id: int
    round_number: int
    observation: AgentObservation
    legal_actions: tuple[Action, ...]
    policy_target: tuple[float, ...]
    value_target: float


class GameTrajectory:
    """
    Private staging buffer for one live game.

    A Brain B controller may own one GameTrajectory containing decisions from
    its four seats. This object must not be sampled for training until finalize
    is called after game end.
    """

    def __init__(self, game_id: str) -> None:
        if not game_id:
            raise ValueError("game_id cannot be empty.")

        self.game_id = game_id
        self._decisions: list[PendingDecision] = []
        self._finalized = False

    def add(self, decision: PendingDecision) -> None:
        if self._finalized:
            raise RuntimeError(
                "Cannot add to a finalized GameTrajectory."
            )

        if decision.game_id != self.game_id:
            raise ValueError(
                "Decision game_id does not match trajectory game_id."
            )

        self._decisions.append(decision)

    def finalize(
        self,
        final_values: dict[int, float],
        *,
        shaped_reward_weight: float = 1.0,
    ) -> list[TrainingSample]:
        """
        Convert staged decisions into immutable training samples.

        final_values is per PLAYER, not per brain. Typical values may be based
        on final placement in [-1, 1]. Optional accumulated shaped rewards are
        added per decision/player rather than sharing reward among Brain B's
        four seats.
        """
        if self._finalized:
            raise RuntimeError(
                "GameTrajectory has already been finalized."
            )

        samples: list[TrainingSample] = []

        for decision in self._decisions:
            if decision.player_id not in final_values:
                raise ValueError(
                    f"Missing final value for player "
                    f"{decision.player_id}."
                )

            final_value = float(
                final_values[decision.player_id]
            )

            target = final_value + (
                shaped_reward_weight
                * float(decision.shaped_reward)
            )

            # Keep the value target on the network's tanh scale.
            target = max(-1.0, min(1.0, target))

            normalized_policy = self._normalize_policy(
                decision.policy_target
            )

            samples.append(
                TrainingSample(
                    game_id=decision.game_id,
                    player_id=decision.player_id,
                    round_number=decision.round_number,
                    observation=decision.observation,
                    legal_actions=decision.legal_actions,
                    policy_target=normalized_policy,
                    value_target=target,
                )
            )

        self._finalized = True
        return samples

    def clear(self) -> None:
        if self._finalized:
            return
        self._decisions.clear()

    def __len__(self) -> int:
        return len(self._decisions)

    @staticmethod
    def _normalize_policy(
        policy: Sequence[float],
    ) -> tuple[float, ...]:
        clipped = [
            max(0.0, float(value))
            for value in policy
        ]
        total = sum(clipped)

        if total <= 0:
            raise ValueError(
                "policy_target must contain positive probability mass."
            )

        return tuple(value / total for value in clipped)


class ReplayBuffer:
    """Completed-game replay buffer only."""

    def __init__(
        self,
        max_size: int = 100_000,
        *,
        seed: int | None = None,
    ) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be positive.")

        self.max_size = int(max_size)
        self._buffer: deque[TrainingSample] = deque(
            maxlen=self.max_size
        )
        self._rng = random.Random(seed)

    def add(self, sample: TrainingSample) -> None:
        self._buffer.append(sample)

    def extend(
        self,
        samples: Iterable[TrainingSample],
    ) -> None:
        for sample in samples:
            self.add(sample)

    def sample(
        self,
        batch_size: int,
    ) -> list[TrainingSample]:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive.")

        count = min(
            int(batch_size),
            len(self._buffer),
        )

        if count == 0:
            return []

        return self._rng.sample(
            list(self._buffer),
            count,
        )

    def clear(self) -> None:
        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)

    @property
    def is_full(self) -> bool:
        return len(self._buffer) == self.max_size
