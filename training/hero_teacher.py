"""Training helper for Brain B's separate learned hero preference model."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import random
from typing import Any, Sequence

import torch
import torch.nn.functional as F


@dataclass(frozen=True)
class HeroTrainingConfig:
    learning_rate: float = 3e-2
    weight_decay: float = 1e-5
    batch_size: int = 64
    seed: int = 0

    def __post_init__(self) -> None:
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive.")
        if self.weight_decay < 0:
            raise ValueError("weight_decay cannot be negative.")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive.")


@dataclass(frozen=True)
class HeroTrainingStepStats:
    samples: int
    mse: float


class HeroTeacherTrainer:
    """Fit hero preference from randomly explored completed-game outcomes."""

    def __init__(
        self,
        brain: Any,
        *,
        config: HeroTrainingConfig | None = None,
    ) -> None:
        if not hasattr(brain, "hero_selector"):
            raise ValueError("Brain does not expose a hero_selector.")
        self.brain = brain
        self.config = config or HeroTrainingConfig()
        self.rng = random.Random(self.config.seed)
        self.optimizer = torch.optim.AdamW(
            self.brain.hero_selector.parameters(),
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
        )
        self.steps_completed = 0

    def train_step(
        self,
        samples: Sequence[Any],
        *,
        batch_size: int | None = None,
    ) -> HeroTrainingStepStats | None:
        if not samples:
            return None
        requested = int(batch_size or self.config.batch_size)
        if requested <= 0:
            raise ValueError("batch_size must be positive.")
        count = min(requested, len(samples))
        chosen = self.rng.sample(list(samples), count)

        vocab_ids = torch.tensor(
            [
                self.brain.vocabulary.encode(sample.chosen_hero_id)
                for sample in chosen
            ],
            dtype=torch.long,
            device=self.brain.device,
        )
        targets = torch.tensor(
            [float(sample.final_value) for sample in chosen],
            dtype=torch.float32,
            device=self.brain.device,
        )

        self.brain.hero_selector.train()
        predictions = self.brain.hero_selector(vocab_ids)
        loss = F.mse_loss(predictions, targets)

        self.optimizer.zero_grad(set_to_none=True)
        loss.backward()
        self.optimizer.step()
        self.steps_completed += 1
        self.brain.hero_selector.eval()

        return HeroTrainingStepStats(
            samples=count,
            mse=float(loss.detach().cpu().item()),
        )

    def train_steps(
        self,
        samples: Sequence[Any],
        steps: int,
        *,
        batch_size: int | None = None,
    ) -> list[HeroTrainingStepStats]:
        if steps < 0:
            raise ValueError("steps cannot be negative.")
        output: list[HeroTrainingStepStats] = []
        for _ in range(int(steps)):
            stats = self.train_step(samples, batch_size=batch_size)
            if stats is None:
                break
            output.append(stats)
        return output

    def copy_state(self) -> dict[str, torch.Tensor]:
        return deepcopy(self.brain.hero_selector.state_dict())

    def load_state(self, state: dict[str, torch.Tensor]) -> None:
        self.brain.hero_selector.load_state_dict(state)
        self.brain.hero_selector.eval()
