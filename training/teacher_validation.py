"""Held-out validation for proper Brain-B teacher pretraining."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from typing import Any, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from training.teacher_data import TeacherDataset


@dataclass(frozen=True)
class ActionTypeValidationStats:
    samples: int
    top1_accuracy: float
    top3_accuracy: float
    teacher_action_probability: float


@dataclass(frozen=True)
class TeacherValidationStats:
    samples: int
    policy_loss: float
    top1_accuracy: float
    top3_accuracy: float
    teacher_action_probability: float
    per_action_type: dict[str, ActionTypeValidationStats]


@dataclass(frozen=True)
class HeroValidationStats:
    samples: int
    mse: float
    mae: float
    sign_accuracy: float
    mean_prediction: float
    mean_target: float


def teacher_action_index(sample: Any) -> int:
    target = tuple(float(value) for value in sample.policy_target)
    if not target:
        raise ValueError("Teacher sample policy_target cannot be empty.")
    if len(target) != len(sample.legal_actions):
        raise ValueError("Teacher sample policy/action length mismatch.")
    return max(range(len(target)), key=target.__getitem__)


def teacher_action_name(sample: Any) -> str:
    index = teacher_action_index(sample)
    action = sample.legal_actions[index]
    return getattr(
        getattr(action, "action_type", None),
        "value",
        str(getattr(action, "action_type", "unknown")),
    )


def _brain_evaluate_many(brain: Any, requests: Sequence[tuple[Any, Any]]):
    evaluator = getattr(brain, "evaluate_many", None)
    if callable(evaluator):
        return tuple(evaluator(requests))
    return tuple(brain.evaluate(observation, actions) for observation, actions in requests)


def evaluate_teacher_policy(
    brain: Any,
    samples: Sequence[Any],
    *,
    batch_size: int = 256,
) -> TeacherValidationStats:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive.")
    if not samples:
        raise ValueError("Validation samples cannot be empty.")

    total_loss = 0.0
    top1_hits = 0
    top3_hits = 0
    total_teacher_probability = 0.0
    seen = 0

    per_action = defaultdict(
        lambda: {"samples": 0, "top1": 0, "top3": 0, "prob": 0.0}
    )

    for start in range(0, len(samples), int(batch_size)):
        batch = list(samples[start:start + int(batch_size)])
        requests = [
            (sample.observation, sample.legal_actions)
            for sample in batch
        ]
        evaluations = _brain_evaluate_many(brain, requests)
        if len(evaluations) != len(batch):
            raise RuntimeError("Brain returned the wrong number of evaluations.")

        for sample, evaluation in zip(batch, evaluations):
            priors = tuple(float(value) for value in evaluation.priors)
            target = tuple(float(value) for value in sample.policy_target)

            if len(priors) != len(sample.legal_actions):
                raise ValueError("Brain prior/action length mismatch.")
            if len(target) != len(priors):
                raise ValueError("Teacher target/prior length mismatch.")
            if not priors:
                raise ValueError("Validation sample has no legal actions.")

            target_sum = sum(target)
            if not math.isfinite(target_sum) or target_sum <= 0.0:
                raise ValueError("Teacher policy target must have positive mass.")
            if any(not math.isfinite(value) or value < 0.0 for value in target):
                raise ValueError("Teacher policy target contains invalid values.")
            normalized_target = tuple(value / target_sum for value in target)

            probability_sum = sum(priors)
            if not math.isfinite(probability_sum) or probability_sum <= 0.0:
                raise ValueError("Brain priors must have positive mass.")
            if any(not math.isfinite(value) or value < 0.0 for value in priors):
                raise ValueError("Brain priors contain invalid values.")
            normalized_priors = tuple(
                max(1e-12, value / probability_sum)
                for value in priors
            )

            total_loss += -sum(
                target_value * math.log(probability)
                for target_value, probability
                in zip(normalized_target, normalized_priors)
            )

            teacher_idx = max(
                range(len(normalized_target)),
                key=normalized_target.__getitem__,
            )
            predicted_idx = max(
                range(len(normalized_priors)),
                key=normalized_priors.__getitem__,
            )
            top_k = min(3, len(normalized_priors))
            top_indices = sorted(
                range(len(normalized_priors)),
                key=normalized_priors.__getitem__,
                reverse=True,
            )[:top_k]

            top1 = predicted_idx == teacher_idx
            top3 = teacher_idx in top_indices
            teacher_probability = normalized_priors[teacher_idx]

            top1_hits += int(top1)
            top3_hits += int(top3)
            total_teacher_probability += teacher_probability
            seen += 1

            name = teacher_action_name(sample)
            bucket = per_action[name]
            bucket["samples"] += 1
            bucket["top1"] += int(top1)
            bucket["top3"] += int(top3)
            bucket["prob"] += teacher_probability

    if seen == 0:
        raise RuntimeError("No validation samples were evaluated.")

    per_action_stats = {
        name: ActionTypeValidationStats(
            samples=int(bucket["samples"]),
            top1_accuracy=float(bucket["top1"]) / bucket["samples"],
            top3_accuracy=float(bucket["top3"]) / bucket["samples"],
            teacher_action_probability=float(bucket["prob"]) / bucket["samples"],
        )
        for name, bucket in sorted(per_action.items())
    }

    return TeacherValidationStats(
        samples=seen,
        policy_loss=total_loss / seen,
        top1_accuracy=top1_hits / seen,
        top3_accuracy=top3_hits / seen,
        teacher_action_probability=total_teacher_probability / seen,
        per_action_type=per_action_stats,
    )


def evaluate_hero_selector(
    brain: Any,
    samples: Sequence[Any],
) -> HeroValidationStats:
    if not samples:
        raise ValueError("Hero validation samples cannot be empty.")
    if not hasattr(brain, "evaluate_heroes"):
        raise ValueError("Brain does not expose learned hero evaluation.")

    squared = 0.0
    absolute = 0.0
    sign_hits = 0
    predictions: list[float] = []
    targets: list[float] = []

    for sample in samples:
        evaluation = brain.evaluate_heroes((sample.chosen_hero_id,))
        prediction = float(evaluation.scores[0])
        target = float(sample.final_value)
        if not math.isfinite(prediction) or not math.isfinite(target):
            raise ValueError("Hero validation contains non-finite values.")
        error = prediction - target
        squared += error * error
        absolute += abs(error)
        sign_hits += int(
            (prediction >= 0.0 and target >= 0.0)
            or (prediction < 0.0 and target < 0.0)
        )
        predictions.append(prediction)
        targets.append(target)

    count = len(samples)
    return HeroValidationStats(
        samples=count,
        mse=squared / count,
        mae=absolute / count,
        sign_accuracy=sign_hits / count,
        mean_prediction=sum(predictions) / count,
        mean_target=sum(targets) / count,
    )


def validate_teacher_dataset(dataset: "TeacherDataset") -> None:
    if not dataset.game_seeds:
        raise ValueError("Teacher dataset has no games.")
    if not dataset.recruit_samples:
        raise ValueError("Teacher dataset has no recruit samples.")
    if len(dataset.hero_samples) != 8 * len(dataset.game_seeds):
        raise ValueError("Teacher dataset must contain 8 hero samples per game.")

    known_seeds = set(int(seed) for seed in dataset.game_seeds)
    for sample in dataset.recruit_samples:
        if not sample.legal_actions:
            raise ValueError("Teacher sample has no legal actions.")
        if len(sample.policy_target) != len(sample.legal_actions):
            raise ValueError("Teacher sample policy/action length mismatch.")
        values = tuple(float(value) for value in sample.policy_target)
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise ValueError("Teacher sample has invalid policy target.")
        if sum(values) <= 0.0:
            raise ValueError("Teacher sample target has no positive mass.")
        if int(sample.game_seed) not in known_seeds:
            raise ValueError("Teacher sample references an unknown game seed.")
        if sample.chosen_action is not None and sample.chosen_action not in sample.legal_actions:
            raise ValueError("Teacher chosen action is not legal.")

    for sample in dataset.hero_samples:
        if int(sample.game_seed) not in known_seeds:
            raise ValueError("Hero sample references an unknown game seed.")
        if len(sample.offered_hero_ids) != 4:
            raise ValueError("Hero sample must contain exactly four offers.")
        if sample.chosen_hero_id not in sample.offered_hero_ids:
            raise ValueError("Chosen hero was not in the offered hero set.")
        if not 1 <= int(sample.final_placement) <= 8:
            raise ValueError("Hero sample placement is invalid.")
        if not math.isfinite(float(sample.final_value)):
            raise ValueError("Hero sample value is non-finite.")


def validate_disjoint_splits(
    train_dataset: "TeacherDataset",
    validation_dataset: "TeacherDataset",
) -> None:
    train_seeds = set(int(seed) for seed in train_dataset.game_seeds)
    validation_seeds = set(int(seed) for seed in validation_dataset.game_seeds)
    overlap = train_seeds & validation_seeds
    if overlap:
        raise ValueError(
            "Teacher train/validation game seeds overlap: "
            f"{sorted(overlap)}"
        )

    train_ids = {sample.game_id for sample in train_dataset.recruit_samples}
    validation_ids = {
        sample.game_id for sample in validation_dataset.recruit_samples
    }
    id_overlap = train_ids & validation_ids
    if id_overlap:
        raise ValueError(
            "Teacher train/validation game IDs overlap: "
            f"{sorted(id_overlap)}"
        )
