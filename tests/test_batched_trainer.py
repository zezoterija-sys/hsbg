from types import SimpleNamespace
import torch
from torch import nn

from agents.observation_encoder import EncodedObservation
from training.trainer import NeuralMCTSTrainer, TrainingConfig


class _ObservationEncoder:
    SCHEMA_VERSION = 2
    def encode(self, observation):
        value = float(observation)
        return EncodedObservation(
            scalar_features=torch.tensor([value, 1.0]),
            card_ids=torch.tensor([0, 0], dtype=torch.long),
            card_features=torch.zeros((2, 1)),
            card_mask=torch.tensor([False, False]),
            identity_ids=torch.tensor([0], dtype=torch.long),
            identity_mask=torch.tensor([False]),
        )


class _ActionEncoder:
    SCHEMA_VERSION = 2
    @staticmethod
    def feature_size():
        return 3
    def encode_many(self, actions, observation):
        return [[float(action), 1.0, 0.0] for action in actions]
    def candidate_card_id(self, action, observation):
        return None


class _Vocabulary:
    fingerprint = "test"
    def __len__(self):
        return 4
    def encode(self, card_id):
        return 0


class _Model(nn.Module):
    def __init__(self):
        super().__init__()
        self.weight = nn.Parameter(torch.tensor(0.1))
    def forward(self, observation, action_features, action_card_ids):
        return SimpleNamespace(
            policy_logits=action_features.sum(-1) * self.weight,
            value=observation.scalar_features.sum(-1) * self.weight,
        )


class _Replay:
    def __len__(self):
        return 0


class _Brain:
    def __init__(self):
        self.device = torch.device("cpu")
        self.model = _Model()
        self.observation_encoder = _ObservationEncoder()
        self.action_encoder = _ActionEncoder()
        self.vocabulary = _Vocabulary()
        self.replay_buffer = _Replay()
    def model_parameters(self):
        return self.model.parameters()


def test_teacher_pretraining_batches_variable_action_counts():
    trainer = NeuralMCTSTrainer(
        _Brain(),
        config=TrainingConfig(batch_size=3),
    )
    samples = [
        SimpleNamespace(observation=1, legal_actions=(1, 2), policy_target=(1.0, 0.0)),
        SimpleNamespace(observation=2, legal_actions=(1, 2, 3), policy_target=(0.0, 1.0, 0.0)),
        SimpleNamespace(observation=3, legal_actions=(1,), policy_target=(1.0,)),
    ]
    stats = trainer.pretrain_teacher_step(samples, batch_size=3)
    assert stats is not None
    assert stats.samples == 3
    assert torch.isfinite(torch.tensor(stats.total_loss))
    assert trainer.teacher_steps_completed == 1
