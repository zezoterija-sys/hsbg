"""Small learned hero preference model for Brain B.

This is intentionally separate from the recruit-phase policy/value network.
Teacher pretraining may fit hero preferences from completed teacher-game
outcomes without writing teacher targets into the main state-value head.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import torch
import torch.nn as nn


@dataclass(frozen=True)
class HeroEvaluation:
    hero_ids: tuple[int, ...]
    scores: tuple[float, ...]


class HeroSelector(nn.Module):
    """Learn one bounded expected-outcome score per card-vocabulary entry."""

    SCHEMA_VERSION = 1

    def __init__(self, *, card_vocab_size: int) -> None:
        super().__init__()
        if card_vocab_size <= 2:
            raise ValueError("card_vocab_size must include real cards.")

        # A scalar embedding is deliberate. The first version should learn a
        # stable hero preference table, not introduce a second large network.
        self.hero_score = nn.Embedding(
            num_embeddings=int(card_vocab_size),
            embedding_dim=1,
            padding_idx=0,
        )
        nn.init.zeros_(self.hero_score.weight)

    def forward(self, hero_vocab_ids: torch.Tensor) -> torch.Tensor:
        scores = self.hero_score(hero_vocab_ids.long()).squeeze(-1)
        return torch.tanh(scores)

    @torch.inference_mode()
    def evaluate_indices(
        self,
        hero_vocab_ids: Sequence[int],
        *,
        device: torch.device | str,
    ) -> tuple[float, ...]:
        if not hero_vocab_ids:
            raise ValueError("hero_vocab_ids cannot be empty.")

        was_training = self.training
        self.eval()
        tensor = torch.tensor(
            tuple(int(value) for value in hero_vocab_ids),
            dtype=torch.long,
            device=device,
        )
        values = self(tensor).detach().cpu().tolist()
        if was_training:
            self.train()
        return tuple(float(value) for value in values)
