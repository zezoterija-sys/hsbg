"""Shared Brain B model/replay owner with single and batched inference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import torch

from agents.action_encoder import ActionEncoder
from agents.hero_selector import HeroEvaluation, HeroSelector
from agents.observation import AgentObservation
from agents.observation_encoder import CardVocabulary, EncodedObservation, ObservationEncoder
from game.actions import Action
from models.policy_network import PolicyNetwork
from training.replay_buffer import ReplayBuffer


@dataclass(frozen=True)
class BrainEvaluation:
    priors: tuple[float, ...]
    value: float


class NeuralBrain:
    """One shared Brain-B network and completed-game replay buffer."""

    def __init__(
        self,
        *,
        cards_file: str = "data/raw/cards.json",
        model: PolicyNetwork | None = None,
        replay_buffer: ReplayBuffer | None = None,
        device: str | torch.device | None = None,
        replay_seed: int | None = None,
    ) -> None:
        self.device = torch.device(
            device if device is not None else ("cuda" if torch.cuda.is_available() else "cpu")
        )
        self.vocabulary = CardVocabulary.from_cards_file(cards_file)
        self.observation_encoder = ObservationEncoder(self.vocabulary)
        self.action_encoder = ActionEncoder()
        self.model = model if model is not None else PolicyNetwork(
            card_vocab_size=len(self.vocabulary)
        )
        self.model.to(self.device)
        self.model.eval()

        # Hero selection is learned separately from the recruit policy/value
        # network. This keeps teacher-game placement outcomes out of the main
        # state-value head while still allowing Brain B to learn hero choice.
        self.hero_selector = HeroSelector(
            card_vocab_size=len(self.vocabulary)
        ).to(self.device)
        self.hero_selector.eval()

        self.replay_buffer = replay_buffer if replay_buffer is not None else ReplayBuffer(
            seed=replay_seed
        )

    @torch.inference_mode()
    def evaluate(
        self,
        observation: AgentObservation,
        legal_actions: Sequence[Action],
    ) -> BrainEvaluation:
        return self.evaluate_many(((observation, legal_actions),))[0]

    @torch.inference_mode()
    def evaluate_many(
        self,
        requests: Sequence[tuple[AgentObservation, Sequence[Action]]],
    ) -> tuple[BrainEvaluation, ...]:
        """Evaluate multiple independent states in one model forward pass."""
        items = [(obs, tuple(actions)) for obs, actions in requests]
        if not items:
            return ()
        if any(not actions for _, actions in items):
            raise ValueError("legal_actions cannot be empty.")

        encoded = [self.observation_encoder.encode(obs) for obs, _ in items]
        batched_observation = EncodedObservation(
            scalar_features=torch.stack([x.scalar_features for x in encoded]).to(self.device),
            card_ids=torch.stack([x.card_ids for x in encoded]).to(self.device),
            card_features=torch.stack([x.card_features for x in encoded]).to(self.device),
            card_mask=torch.stack([x.card_mask for x in encoded]).to(self.device),
            identity_ids=torch.stack([x.identity_ids for x in encoded]).to(self.device),
            identity_mask=torch.stack([x.identity_mask for x in encoded]).to(self.device),
        )

        counts = [len(actions) for _, actions in items]
        max_actions = max(counts)
        feature_size = self.action_encoder.feature_size()
        action_features = torch.zeros(
            (len(items), max_actions, feature_size),
            dtype=torch.float32,
            device=self.device,
        )
        action_card_ids = torch.zeros(
            (len(items), max_actions),
            dtype=torch.long,
            device=self.device,
        )
        action_mask = torch.zeros(
            (len(items), max_actions),
            dtype=torch.bool,
            device=self.device,
        )

        for row, (observation, actions) in enumerate(items):
            count = len(actions)
            action_features[row, :count] = torch.tensor(
                self.action_encoder.encode_many(actions, observation),
                dtype=torch.float32,
                device=self.device,
            )
            action_card_ids[row, :count] = torch.tensor(
                [
                    self.vocabulary.encode(
                        self.action_encoder.candidate_card_id(action, observation)
                    )
                    for action in actions
                ],
                dtype=torch.long,
                device=self.device,
            )
            action_mask[row, :count] = True

        self.model.eval()
        output = self.model(
            batched_observation,
            action_features,
            action_card_ids,
        )
        logits = output.policy_logits.masked_fill(
            ~action_mask,
            torch.finfo(output.policy_logits.dtype).min,
        )
        probabilities = torch.softmax(logits, dim=-1)

        result: list[BrainEvaluation] = []
        for row, count in enumerate(counts):
            result.append(
                BrainEvaluation(
                    priors=tuple(
                        float(v) for v in probabilities[row, :count].detach().cpu().tolist()
                    ),
                    value=float(output.value[row].detach().cpu().item()),
                )
            )
        return tuple(result)

    @torch.inference_mode()
    def evaluate_heroes(
        self,
        hero_ids: Sequence[int],
    ) -> HeroEvaluation:
        choices = tuple(int(hero_id) for hero_id in hero_ids)
        if not choices:
            raise ValueError("hero_ids cannot be empty.")

        vocab_ids = tuple(
            self.vocabulary.encode(hero_id)
            for hero_id in choices
        )
        self.hero_selector.eval()
        scores = self.hero_selector.evaluate_indices(
            vocab_ids,
            device=self.device,
        )
        return HeroEvaluation(
            hero_ids=choices,
            scores=scores,
        )

    def model_parameters(self):
        return self.model.parameters()

    def hero_parameters(self):
        return self.hero_selector.parameters()

    def state_dict(self):
        return self.model.state_dict()

    def load_state_dict(self, state_dict) -> None:
        self.model.load_state_dict(state_dict)
        self.model.eval()

    def __repr__(self) -> str:
        return (
            f"NeuralBrain(device={self.device}, "
            f"vocab_size={len(self.vocabulary)}, "
            f"replay_size={len(self.replay_buffer)})"
        )
