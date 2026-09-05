"""
Shared policy-value network for Brain B.

Scores the current variable legal-action set and predicts one state value.
Schema-v2 observation/action encodings provide hero identities, stable mechanic
state, zone/position-aware cards, and the concrete card identity associated with
each action candidate.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn

from agents.action_encoder import ActionEncoder
from agents.observation_encoder import EncodedObservation, ObservationEncoder


@dataclass(frozen=True)
class PolicyValueOutput:
    policy_logits: torch.Tensor
    value: torch.Tensor


class PolicyNetwork(nn.Module):
    """Structured candidate-scoring policy/value network."""

    def __init__(
        self,
        *,
        card_vocab_size: int,
        card_embedding_dim: int = 64,
        card_hidden_dim: int = 96,
        state_hidden_dim: int = 256,
        action_hidden_dim: int = 128,
        joint_hidden_dim: int = 192,
    ) -> None:
        super().__init__()

        if card_vocab_size <= 2:
            raise ValueError(
                "card_vocab_size must include real cards in addition to PAD/UNK entries."
            )

        self.card_vocab_size = int(card_vocab_size)
        self.card_embedding_dim = int(card_embedding_dim)
        self.action_feature_size = ActionEncoder.feature_size()
        self.scalar_feature_size = ObservationEncoder.SCALAR_FEATURE_SIZE
        self.card_feature_size = ObservationEncoder.CARD_FEATURE_SIZE

        self.card_embedding = nn.Embedding(
            num_embeddings=self.card_vocab_size,
            embedding_dim=self.card_embedding_dim,
            padding_idx=0,
        )

        self.card_encoder = nn.Sequential(
            nn.Linear(self.card_embedding_dim + self.card_feature_size, card_hidden_dim),
            nn.ReLU(),
            nn.Linear(card_hidden_dim, card_hidden_dim),
            nn.ReLU(),
        )

        # State includes:
        # - scalar features,
        # - pooled own visible cards,
        # - pooled remembered opponent cards,
        # - own hero, hero power, current-choice source, last Tavern spell,
        # - pooled public opponent hero identities.
        pooled_card_size = card_hidden_dim * 2
        identity_size = self.card_embedding_dim * 5
        self.state_encoder = nn.Sequential(
            nn.Linear(
                self.scalar_feature_size + pooled_card_size + identity_size,
                state_hidden_dim,
            ),
            nn.ReLU(),
            nn.Linear(state_hidden_dim, state_hidden_dim),
            nn.ReLU(),
        )

        self.action_encoder = nn.Sequential(
            nn.Linear(self.action_feature_size, action_hidden_dim),
            nn.ReLU(),
            nn.Linear(action_hidden_dim, action_hidden_dim),
            nn.ReLU(),
        )

        # Candidate card embedding is joined after the numeric action encoder so
        # BUY/PLAY/CAST/ACTIVATE/CHOOSE_OPTION can be scored by concrete identity.
        self.policy_head = nn.Sequential(
            nn.Linear(
                state_hidden_dim + action_hidden_dim + self.card_embedding_dim,
                joint_hidden_dim,
            ),
            nn.ReLU(),
            nn.Linear(joint_hidden_dim, 1),
        )

        self.value_head = nn.Sequential(
            nn.Linear(state_hidden_dim, state_hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(state_hidden_dim // 2, 1),
            nn.Tanh(),
        )

    def forward(
        self,
        observation: EncodedObservation,
        action_features: torch.Tensor,
        action_card_ids: torch.Tensor | None = None,
    ) -> PolicyValueOutput:
        (
            scalars,
            card_ids,
            card_features,
            card_mask,
            identity_ids,
            identity_mask,
            actions,
            candidate_card_ids,
            single,
        ) = self._normalize_batch(
            observation,
            action_features,
            action_card_ids,
        )

        card_embeddings = self.card_embedding(card_ids)
        card_input = torch.cat([card_embeddings, card_features], dim=-1)
        encoded_cards = self.card_encoder(card_input)

        own_end = ObservationEncoder.OWN_CARD_SLOTS
        own_pooled = self._masked_mean(
            encoded_cards[:, :own_end, :],
            card_mask[:, :own_end],
        )
        opponent_pooled = self._masked_mean(
            encoded_cards[:, own_end:, :],
            card_mask[:, own_end:],
        )

        identity_embeddings = self.card_embedding(identity_ids)
        own_hero = identity_embeddings[:, ObservationEncoder.OWN_HERO_IDENTITY_SLOT, :]
        own_power = identity_embeddings[:, ObservationEncoder.OWN_HERO_POWER_IDENTITY_SLOT, :]
        choice_source = identity_embeddings[:, ObservationEncoder.CHOICE_SOURCE_IDENTITY_SLOT, :]
        last_tavern_spell = identity_embeddings[:, ObservationEncoder.LAST_TAVERN_SPELL_IDENTITY_SLOT, :]

        opponent_identity = identity_embeddings[:, ObservationEncoder.OPPONENT_HERO_IDENTITY_START:, :]
        opponent_identity_mask = identity_mask[:, ObservationEncoder.OPPONENT_HERO_IDENTITY_START:]
        opponent_hero_pooled = self._masked_mean(
            opponent_identity,
            opponent_identity_mask,
        )

        state_input = torch.cat(
            [
                scalars,
                own_pooled,
                opponent_pooled,
                own_hero,
                own_power,
                choice_source,
                last_tavern_spell,
                opponent_hero_pooled,
            ],
            dim=-1,
        )
        state_embedding = self.state_encoder(state_input)

        encoded_actions = self.action_encoder(actions)
        candidate_embeddings = self.card_embedding(candidate_card_ids)
        expanded_state = state_embedding.unsqueeze(1).expand(
            -1,
            encoded_actions.shape[1],
            -1,
        )

        joint = torch.cat(
            [expanded_state, encoded_actions, candidate_embeddings],
            dim=-1,
        )
        logits = self.policy_head(joint).squeeze(-1)
        value = self.value_head(state_embedding).squeeze(-1)

        if single:
            return PolicyValueOutput(policy_logits=logits[0], value=value[0])
        return PolicyValueOutput(policy_logits=logits, value=value)

    def policy_value(
        self,
        observation: EncodedObservation,
        action_features: torch.Tensor,
        action_card_ids: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        output = self.forward(observation, action_features, action_card_ids)
        return output.policy_logits, output.value

    @staticmethod
    def _masked_mean(values: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        weights = mask.to(values.dtype).unsqueeze(-1)
        denominator = weights.sum(dim=1).clamp_min(1.0)
        return (values * weights).sum(dim=1) / denominator

    @staticmethod
    def _normalize_batch(
        observation: EncodedObservation,
        action_features: torch.Tensor,
        action_card_ids: torch.Tensor | None,
    ):
        scalars = observation.scalar_features
        card_ids = observation.card_ids
        card_features = observation.card_features
        card_mask = observation.card_mask
        identity_ids = observation.identity_ids
        identity_mask = observation.identity_mask
        actions = action_features

        single = scalars.dim() == 1
        if single:
            scalars = scalars.unsqueeze(0)
            card_ids = card_ids.unsqueeze(0)
            card_features = card_features.unsqueeze(0)
            card_mask = card_mask.unsqueeze(0)
            identity_ids = identity_ids.unsqueeze(0)
            identity_mask = identity_mask.unsqueeze(0)

        if actions.dim() == 2:
            actions = actions.unsqueeze(0)

        if action_card_ids is None:
            candidate_card_ids = torch.zeros(
                actions.shape[:2],
                dtype=torch.long,
                device=actions.device,
            )
        else:
            candidate_card_ids = action_card_ids
            if candidate_card_ids.dim() == 1:
                candidate_card_ids = candidate_card_ids.unsqueeze(0)

        if scalars.dim() != 2:
            raise ValueError("scalar_features must be [S] or [B, S].")
        if card_ids.dim() != 2:
            raise ValueError("card_ids must be [C] or [B, C].")
        if card_features.dim() != 3:
            raise ValueError("card_features must be [C, F] or [B, C, F].")
        if card_mask.dim() != 2:
            raise ValueError("card_mask must be [C] or [B, C].")
        if identity_ids.dim() != 2 or identity_mask.dim() != 2:
            raise ValueError("identity tensors must be [I] or [B, I].")
        if actions.dim() != 3:
            raise ValueError("action_features must be [A, F] or [B, A, F].")
        if candidate_card_ids.dim() != 2:
            raise ValueError("action_card_ids must be [A] or [B, A].")

        batch_size = scalars.shape[0]
        if actions.shape[0] not in (1, batch_size):
            raise ValueError("Action batch size does not match observation batch size.")
        if candidate_card_ids.shape[0] not in (1, batch_size):
            raise ValueError("Candidate-card batch size does not match observation batch size.")

        if actions.shape[0] == 1 and batch_size > 1:
            actions = actions.expand(batch_size, -1, -1)
        if candidate_card_ids.shape[0] == 1 and batch_size > 1:
            candidate_card_ids = candidate_card_ids.expand(batch_size, -1)
        if candidate_card_ids.shape[1] != actions.shape[1]:
            raise ValueError("action_card_ids length must match legal action count.")

        return (
            scalars,
            card_ids,
            card_features,
            card_mask,
            identity_ids,
            identity_mask,
            actions,
            candidate_card_ids,
            single,
        )
