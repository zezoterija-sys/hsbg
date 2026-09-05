"""Training controller for Brain B's policy/value network.

Normal self-play training reads ONLY completed-game replay. Live trajectories
remain quarantined exactly as before. This version adds:
- padded/masked batched policy-value training for variable legal-action counts,
- optional policy-only imitation pretraining from the generic seed teacher,
- checkpoint accounting for teacher steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import random
from typing import Any, Sequence

import torch
import torch.nn.functional as F

from agents.neural_brain import NeuralBrain
from agents.observation_encoder import EncodedObservation
from training.replay_buffer import GameTrajectory, TrainingSample


@dataclass(frozen=True)
class TrainingConfig:
    learning_rate: float = 1e-3
    weight_decay: float = 1e-5
    batch_size: int = 128

    policy_loss_weight: float = 1.0
    value_loss_weight: float = 1.0
    gradient_clip_norm: float = 5.0
    teacher_seed: int = 0

    def __post_init__(self) -> None:
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive.")
        if self.weight_decay < 0:
            raise ValueError("weight_decay cannot be negative.")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive.")
        if self.policy_loss_weight < 0:
            raise ValueError("policy_loss_weight cannot be negative.")
        if self.value_loss_weight < 0:
            raise ValueError("value_loss_weight cannot be negative.")
        if self.gradient_clip_norm <= 0:
            raise ValueError("gradient_clip_norm must be positive.")


@dataclass(frozen=True)
class TrainingStepStats:
    samples: int
    total_loss: float
    policy_loss: float
    value_loss: float
    gradient_norm: float


@dataclass(frozen=True)
class _PaddedBatch:
    observation: EncodedObservation
    action_features: torch.Tensor
    action_card_ids: torch.Tensor
    action_mask: torch.Tensor
    target_policy: torch.Tensor
    target_value: torch.Tensor | None


class NeuralMCTSTrainer:
    """Optimizer/training owner for one shared NeuralBrain."""

    CHECKPOINT_VERSION = 2

    def __init__(
        self,
        brain: NeuralBrain,
        *,
        config: TrainingConfig | None = None,
    ) -> None:
        self.brain = brain
        self.config = config or TrainingConfig()

        self.optimizer = torch.optim.AdamW(
            self.brain.model_parameters(),
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
        )

        self.training_steps_completed = 0
        self.teacher_steps_completed = 0
        self.completed_games_committed = 0
        self._teacher_rng = random.Random(self.config.teacher_seed)
        self.brain.model.eval()

    # ==================================================================
    # COMPLETED-GAME COMMIT
    # ==================================================================

    def commit_completed_game(
        self,
        trajectory: GameTrajectory,
        final_values: dict[int, float],
        *,
        shaped_reward_weight: float = 1.0,
    ) -> int:
        """Finalize one finished game and move it into shared replay."""
        samples = trajectory.finalize(
            final_values,
            shaped_reward_weight=shaped_reward_weight,
        )
        self.brain.replay_buffer.extend(samples)
        self.completed_games_committed += 1
        return len(samples)

    # ==================================================================
    # NORMAL SELF-PLAY TRAINING -- BATCHED
    # ==================================================================

    def can_train(self) -> bool:
        return len(self.brain.replay_buffer) > 0

    def train_step(
        self,
        batch_size: int | None = None,
    ) -> TrainingStepStats | None:
        requested = self._resolve_batch_size(batch_size)
        samples = self.brain.replay_buffer.sample(requested)
        if not samples:
            return None

        batch = self._collate_samples(samples, include_value=True)
        stats = self._optimizer_step(
            batch,
            policy_weight=self.config.policy_loss_weight,
            value_weight=self.config.value_loss_weight,
        )
        self.training_steps_completed += 1
        return stats

    def train_steps(
        self,
        steps: int,
        *,
        batch_size: int | None = None,
    ) -> list[TrainingStepStats]:
        """Train only from completed-game replay."""
        if steps < 0:
            raise ValueError("steps cannot be negative.")

        results: list[TrainingStepStats] = []
        for _ in range(int(steps)):
            stats = self.train_step(batch_size=batch_size)
            if stats is None:
                break
            results.append(stats)
        return results

    # ==================================================================
    # OPTIONAL TEACHER IMITATION PRETRAINING
    # ==================================================================

    def pretrain_teacher_step(
        self,
        samples: Sequence[Any],
        *,
        batch_size: int | None = None,
    ) -> TrainingStepStats | None:
        """
        Policy-only imitation step from TeacherSample-like objects.

        Teacher samples are deliberately separate from completed-game replay;
        they do not count as self-play games and cannot leak a live lobby.
        Required fields: observation, legal_actions, policy_target.
        """
        if not samples:
            return None

        requested = min(self._resolve_batch_size(batch_size), len(samples))
        chosen = self._teacher_rng.sample(list(samples), requested)
        batch = self._collate_samples(chosen, include_value=False)

        stats = self._optimizer_step(
            batch,
            policy_weight=1.0,
            value_weight=0.0,
        )
        self.teacher_steps_completed += 1
        return stats

    def pretrain_teacher_steps(
        self,
        samples: Sequence[Any],
        steps: int,
        *,
        batch_size: int | None = None,
    ) -> list[TrainingStepStats]:
        if steps < 0:
            raise ValueError("steps cannot be negative.")
        if not samples or steps == 0:
            return []

        results: list[TrainingStepStats] = []
        for _ in range(int(steps)):
            stats = self.pretrain_teacher_step(
                samples,
                batch_size=batch_size,
            )
            if stats is None:
                break
            results.append(stats)
        return results

    # ==================================================================
    # BATCH COLLATION / LOSS
    # ==================================================================

    def _resolve_batch_size(self, batch_size: int | None) -> int:
        requested = self.config.batch_size if batch_size is None else int(batch_size)
        if requested <= 0:
            raise ValueError("batch_size must be positive.")
        return requested

    def _collate_samples(
        self,
        samples: Sequence[Any],
        *,
        include_value: bool,
    ) -> _PaddedBatch:
        if not samples:
            raise ValueError("Cannot collate an empty sample list.")

        encoded = [
            self.brain.observation_encoder.encode(sample.observation)
            for sample in samples
        ]
        observation = EncodedObservation(
            scalar_features=torch.stack([item.scalar_features for item in encoded]).to(self.brain.device),
            card_ids=torch.stack([item.card_ids for item in encoded]).to(self.brain.device),
            card_features=torch.stack([item.card_features for item in encoded]).to(self.brain.device),
            card_mask=torch.stack([item.card_mask for item in encoded]).to(self.brain.device),
            identity_ids=torch.stack([item.identity_ids for item in encoded]).to(self.brain.device),
            identity_mask=torch.stack([item.identity_mask for item in encoded]).to(self.brain.device),
        )

        action_counts = [len(sample.legal_actions) for sample in samples]
        if any(count <= 0 for count in action_counts):
            raise ValueError("Every training sample must have legal actions.")
        max_actions = max(action_counts)
        batch_n = len(samples)
        feature_size = self.brain.action_encoder.feature_size()

        action_features = torch.zeros(
            (batch_n, max_actions, feature_size),
            dtype=torch.float32,
            device=self.brain.device,
        )
        action_card_ids = torch.zeros(
            (batch_n, max_actions),
            dtype=torch.long,
            device=self.brain.device,
        )
        action_mask = torch.zeros(
            (batch_n, max_actions),
            dtype=torch.bool,
            device=self.brain.device,
        )
        target_policy = torch.zeros(
            (batch_n, max_actions),
            dtype=torch.float32,
            device=self.brain.device,
        )

        for row, sample in enumerate(samples):
            count = len(sample.legal_actions)
            encoded_actions = self.brain.action_encoder.encode_many(
                sample.legal_actions,
                sample.observation,
            )
            action_features[row, :count] = torch.tensor(
                encoded_actions,
                dtype=torch.float32,
                device=self.brain.device,
            )
            action_card_ids[row, :count] = torch.tensor(
                [
                    self.brain.vocabulary.encode(
                        self.brain.action_encoder.candidate_card_id(
                            action,
                            sample.observation,
                        )
                    )
                    for action in sample.legal_actions
                ],
                dtype=torch.long,
                device=self.brain.device,
            )
            action_mask[row, :count] = True

            target = torch.tensor(
                sample.policy_target,
                dtype=torch.float32,
                device=self.brain.device,
            )
            if target.numel() != count:
                raise ValueError("Training sample policy/action length mismatch.")
            total = target.sum()
            if not torch.isfinite(total) or float(total.item()) <= 0:
                raise ValueError("Invalid policy target in training sample.")
            target_policy[row, :count] = target / total

        target_value = None
        if include_value:
            target_value = torch.tensor(
                [float(sample.value_target) for sample in samples],
                dtype=torch.float32,
                device=self.brain.device,
            )

        return _PaddedBatch(
            observation=observation,
            action_features=action_features,
            action_card_ids=action_card_ids,
            action_mask=action_mask,
            target_policy=target_policy,
            target_value=target_value,
        )

    def _optimizer_step(
        self,
        batch: _PaddedBatch,
        *,
        policy_weight: float,
        value_weight: float,
    ) -> TrainingStepStats:
        self.brain.model.train()
        self.optimizer.zero_grad(set_to_none=True)

        output = self.brain.model(
            batch.observation,
            batch.action_features,
            batch.action_card_ids,
        )

        masked_logits = output.policy_logits.masked_fill(
            ~batch.action_mask,
            torch.finfo(output.policy_logits.dtype).min,
        )
        log_probabilities = F.log_softmax(masked_logits, dim=-1)
        policy_loss = -(
            batch.target_policy * log_probabilities
        ).sum(dim=-1).mean()

        if batch.target_value is None or value_weight == 0.0:
            value_loss = output.value.sum() * 0.0
        else:
            value_loss = F.mse_loss(output.value, batch.target_value)

        total_loss = policy_weight * policy_loss + value_weight * value_loss
        if not torch.isfinite(total_loss):
            raise FloatingPointError("Training produced non-finite loss.")

        total_loss.backward()
        gradient_norm_tensor = torch.nn.utils.clip_grad_norm_(
            self.brain.model.parameters(),
            max_norm=self.config.gradient_clip_norm,
        )
        gradient_norm = float(
            gradient_norm_tensor.detach().cpu().item()
            if isinstance(gradient_norm_tensor, torch.Tensor)
            else gradient_norm_tensor
        )
        self.optimizer.step()
        self.brain.model.eval()

        return TrainingStepStats(
            samples=int(batch.action_mask.shape[0]),
            total_loss=float(total_loss.detach().cpu().item()),
            policy_loss=float(policy_loss.detach().cpu().item()),
            value_loss=float(value_loss.detach().cpu().item()),
            gradient_norm=gradient_norm,
        )

    # ==================================================================
    # CHECKPOINTING
    # ==================================================================

    def save_checkpoint(
        self,
        path: str | Path,
        *,
        extra: dict | None = None,
    ) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "checkpoint_version": self.CHECKPOINT_VERSION,
            "model_state_dict": self.brain.model.state_dict(),
            "hero_selector_state_dict": (
                self.brain.hero_selector.state_dict()
                if hasattr(self.brain, "hero_selector")
                else None
            ),
            "hero_selector_schema_version": (
                int(getattr(self.brain.hero_selector, "SCHEMA_VERSION", 1))
                if hasattr(self.brain, "hero_selector")
                else None
            ),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "training_steps_completed": self.training_steps_completed,
            "teacher_steps_completed": self.teacher_steps_completed,
            "completed_games_committed": self.completed_games_committed,
            "observation_schema_version": self.brain.observation_encoder.SCHEMA_VERSION,
            "action_schema_version": self.brain.action_encoder.SCHEMA_VERSION,
            "card_vocab_size": len(self.brain.vocabulary),
            "card_vocabulary_fingerprint": self.brain.vocabulary.fingerprint,
            "extra": dict(extra or {}),
        }
        torch.save(payload, destination)
        return destination

    def load_checkpoint(
        self,
        path: str | Path,
        *,
        map_location: str | torch.device | None = None,
    ) -> dict:
        source = Path(path)
        payload = torch.load(
            source,
            map_location=(
                map_location if map_location is not None else self.brain.device
            ),
            weights_only=False,
        )
        self._validate_checkpoint(payload)

        self.brain.model.load_state_dict(payload["model_state_dict"])

        hero_state = payload.get("hero_selector_state_dict")
        if hero_state is not None and hasattr(self.brain, "hero_selector"):
            self.brain.hero_selector.load_state_dict(hero_state)
            self.brain.hero_selector.eval()

        self.optimizer.load_state_dict(payload["optimizer_state_dict"])
        self.training_steps_completed = int(payload.get("training_steps_completed", 0))
        self.teacher_steps_completed = int(payload.get("teacher_steps_completed", 0))
        self.completed_games_committed = int(payload.get("completed_games_committed", 0))
        self.brain.model.eval()
        return dict(payload.get("extra", {}))

    def _validate_checkpoint(self, payload: dict) -> None:
        if int(payload.get("checkpoint_version", -1)) != self.CHECKPOINT_VERSION:
            raise ValueError("Unsupported trainer checkpoint version.")
        if int(payload.get("observation_schema_version", -1)) != self.brain.observation_encoder.SCHEMA_VERSION:
            raise ValueError("Observation schema mismatch.")
        if int(payload.get("action_schema_version", -1)) != self.brain.action_encoder.SCHEMA_VERSION:
            raise ValueError("Action schema mismatch.")
        if int(payload.get("card_vocab_size", -1)) != len(self.brain.vocabulary):
            raise ValueError("Card vocabulary size mismatch.")
        if payload.get("card_vocabulary_fingerprint") != self.brain.vocabulary.fingerprint:
            raise ValueError("Card vocabulary mapping mismatch.")


Trainer = NeuralMCTSTrainer
