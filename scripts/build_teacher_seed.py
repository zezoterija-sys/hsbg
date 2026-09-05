#!/usr/bin/env python3
"""Build Brain B's validated teacher-seed checkpoint.

Production flow:
1. generate/load whole-game train and validation caches,
2. validate split/data integrity,
3. measure fresh-model baseline,
4. policy-only recruit imitation with early stopping,
5. separately learn hero preferences from random hero outcomes,
6. save LAST and BEST checkpoints,
7. reload BEST into a fresh Brain B and verify held-out metrics,
8. write a provenance-rich JSON summary.

The main state-value head receives no teacher value loss. Actual self-play owns
state-value learning.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
from pathlib import Path
import random
import sys
from typing import Any

import torch

# Allow `python scripts/build_teacher_seed.py` from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.neural_brain import NeuralBrain
from training.hero_teacher import HeroTeacherTrainer, HeroTrainingConfig
from training.teacher_cache import (
    git_is_dirty,
    git_revision,
    load_teacher_dataset,
    save_teacher_dataset,
    sha256_file,
    summarize_teacher_dataset,
    write_json,
)
from training.teacher_data import (
    TEACHER_DATA_VERSION,
    TeacherDataConfig,
    TeacherDataGenerator,
)
from training.teacher_validation import (
    evaluate_hero_selector,
    evaluate_teacher_policy,
    validate_disjoint_splits,
    validate_teacher_dataset,
)
from training.trainer import NeuralMCTSTrainer, TrainingConfig


PRE_SYNC_BASELINE_PREFIX = "59010b6"
MODEL_SCHEMA_VERSION = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a held-out-validated generic teacher seed for Brain B."
    )
    parser.add_argument("--train-games", type=int, default=32)
    parser.add_argument("--val-games", type=int, default=8)

    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--min-steps", type=int, default=150)
    parser.add_argument("--eval-every", type=int, default=25)
    parser.add_argument("--patience", type=int, default=6)
    parser.add_argument("--min-delta", type=float, default=1e-4)

    parser.add_argument("--hero-steps", type=int, default=250)
    parser.add_argument("--hero-min-steps", type=int, default=75)
    parser.add_argument("--hero-eval-every", type=int, default=25)
    parser.add_argument("--hero-patience", type=int, default=5)
    parser.add_argument("--hero-min-delta", type=float, default=1e-4)
    parser.add_argument("--hero-learning-rate", type=float, default=3e-2)

    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--hero-batch-size", type=int, default=64)
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--cards-file", default="data/raw/cards.json")
    parser.add_argument("--ruleset", default="36.4.2")
    parser.add_argument("--device", default=None)

    parser.add_argument(
        "--cache-dir",
        default="runs/bg_ai/teacher",
        help="Local ignored directory for datasets/checkpoints/summary.",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Ignore compatible dataset caches and regenerate teacher games.",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow a dirty Git worktree (debug only; production should be clean).",
    )
    parser.add_argument(
        "--allow-pre-sync",
        action="store_true",
        help="Allow running while HEAD is still the old pre-sync 59010b6 baseline.",
    )
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    positive = {
        "train-games": args.train_games,
        "val-games": args.val_games,
        "eval-every": args.eval_every,
        "patience": args.patience,
        "batch-size": args.batch_size,
        "hero-eval-every": args.hero_eval_every,
        "hero-patience": args.hero_patience,
        "hero-batch-size": args.hero_batch_size,
    }
    for name, value in positive.items():
        if int(value) <= 0:
            raise ValueError(f"{name} must be positive.")

    nonnegative = {
        "steps": args.steps,
        "min-steps": args.min_steps,
        "hero-steps": args.hero_steps,
        "hero-min-steps": args.hero_min_steps,
        "min-delta": args.min_delta,
        "hero-min-delta": args.hero_min_delta,
    }
    for name, value in nonnegative.items():
        if float(value) < 0:
            raise ValueError(f"{name} cannot be negative.")

    if args.min_steps > args.steps:
        raise ValueError("min-steps cannot exceed steps.")
    if args.hero_min_steps > args.hero_steps:
        raise ValueError("hero-min-steps cannot exceed hero-steps.")
    if args.hero_learning_rate <= 0:
        raise ValueError("hero-learning-rate must be positive.")


def _seed_runtime(seed: int) -> None:
    random.seed(int(seed))
    torch.manual_seed(int(seed))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(seed))


def _derive_seed(master_seed: int, label: str) -> int:
    payload = f"{int(master_seed)}:{label}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _policy_record(step: int, stats, train_loss: float | None = None) -> dict[str, Any]:
    record = {
        "step": int(step),
        "samples": int(stats.samples),
        "policy_loss": float(stats.policy_loss),
        "top1_accuracy": float(stats.top1_accuracy),
        "top3_accuracy": float(stats.top3_accuracy),
        "teacher_action_probability": float(stats.teacher_action_probability),
        "per_action_type": {
            name: asdict(bucket)
            for name, bucket in stats.per_action_type.items()
        },
    }
    if train_loss is not None:
        record["train_policy_loss"] = float(train_loss)
    return record


def _hero_record(step: int, stats, train_mse: float | None = None) -> dict[str, Any]:
    record = {"step": int(step), **asdict(stats)}
    if train_mse is not None:
        record["train_mse"] = float(train_mse)
    return record


def _states_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.keys() != right.keys():
        return False
    for key in left:
        a, b = left[key], right[key]
        if isinstance(a, torch.Tensor) and isinstance(b, torch.Tensor):
            if not torch.equal(a.detach().cpu(), b.detach().cpu()):
                return False
        elif a != b:
            return False
    return True


def _load_or_generate_dataset(
    *,
    path: Path,
    kind: str,
    games: int,
    seed: int,
    cards_file: str,
    ruleset: str,
    cards_sha256: str,
    revision: str,
    regenerate: bool,
):
    metadata = {
        "kind": kind,
        "games": int(games),
        "seed": int(seed),
        "ruleset": str(ruleset),
        "cards_sha256": cards_sha256,
        "git_revision": revision,
        "teacher_data_version": TEACHER_DATA_VERSION,
    }

    if path.exists() and not regenerate:
        try:
            dataset, _ = load_teacher_dataset(
                path,
                expected_metadata=metadata,
            )
            print(f"Loaded compatible {kind} cache: {path}", flush=True)
            return dataset, metadata, True
        except ValueError as exc:
            print(
                f"Ignoring incompatible {kind} cache ({exc}); regenerating.",
                flush=True,
            )

    generator = TeacherDataGenerator(
        config=TeacherDataConfig(
            cards_file=cards_file,
            seed=seed,
        )
    )
    dataset = generator.generate_dataset(games)
    validate_teacher_dataset(dataset)
    save_teacher_dataset(path, dataset, metadata=metadata)
    print(f"Saved {kind} cache: {path}", flush=True)
    return dataset, metadata, False


def _train_policy(
    *,
    brain: NeuralBrain,
    trainer: NeuralMCTSTrainer,
    train_samples,
    val_samples,
    steps: int,
    min_steps: int,
    eval_every: int,
    patience: int,
    min_delta: float,
    batch_size: int,
):
    baseline = evaluate_teacher_policy(brain, val_samples, batch_size=batch_size)
    history = [_policy_record(0, baseline)]
    best_loss = float(baseline.policy_loss)
    best_step = 0
    best_state = deepcopy(brain.model.state_dict())
    no_improvement = 0
    completed = 0
    stopped_early = False

    print(
        "Policy validation step 0 | "
        f"loss={baseline.policy_loss:.4f} | "
        f"top1={baseline.top1_accuracy:.3f} | "
        f"top3={baseline.top3_accuracy:.3f} | "
        f"P(teacher)={baseline.teacher_action_probability:.3f}",
        flush=True,
    )

    while completed < steps:
        block = min(eval_every, steps - completed)
        training = trainer.pretrain_teacher_steps(
            train_samples,
            block,
            batch_size=batch_size,
        )
        if not training:
            break
        completed += len(training)

        validation = evaluate_teacher_policy(
            brain,
            val_samples,
            batch_size=batch_size,
        )
        history.append(
            _policy_record(
                completed,
                validation,
                train_loss=training[-1].policy_loss,
            )
        )
        print(
            f"Policy validation step {completed} | "
            f"train={training[-1].policy_loss:.4f} | "
            f"val={validation.policy_loss:.4f} | "
            f"top1={validation.top1_accuracy:.3f} | "
            f"top3={validation.top3_accuracy:.3f}",
            flush=True,
        )

        if validation.policy_loss < best_loss - min_delta:
            best_loss = float(validation.policy_loss)
            best_step = int(completed)
            best_state = deepcopy(brain.model.state_dict())
            no_improvement = 0
        else:
            no_improvement += 1

        if completed >= min_steps and no_improvement >= patience:
            stopped_early = True
            break

    final = evaluate_teacher_policy(brain, val_samples, batch_size=batch_size)
    return {
        "baseline": baseline,
        "final": final,
        "history": history,
        "best_loss": best_loss,
        "best_step": best_step,
        "best_state": best_state,
        "steps_completed": completed,
        "stopped_early": stopped_early,
    }


def _train_heroes(
    *,
    brain: NeuralBrain,
    train_samples,
    val_samples,
    seed: int,
    learning_rate: float,
    batch_size: int,
    steps: int,
    min_steps: int,
    eval_every: int,
    patience: int,
    min_delta: float,
):
    trainer = HeroTeacherTrainer(
        brain,
        config=HeroTrainingConfig(
            learning_rate=learning_rate,
            batch_size=batch_size,
            seed=seed,
        ),
    )
    baseline = evaluate_hero_selector(brain, val_samples)
    history = [_hero_record(0, baseline)]
    best_mse = float(baseline.mse)
    best_step = 0
    best_state = trainer.copy_state()
    no_improvement = 0
    completed = 0
    stopped_early = False

    print(
        "Hero validation step 0 | "
        f"mse={baseline.mse:.4f} | mae={baseline.mae:.4f}",
        flush=True,
    )

    while completed < steps:
        block = min(eval_every, steps - completed)
        training = trainer.train_steps(
            train_samples,
            block,
            batch_size=batch_size,
        )
        if not training:
            break
        completed += len(training)
        validation = evaluate_hero_selector(brain, val_samples)
        history.append(
            _hero_record(
                completed,
                validation,
                train_mse=training[-1].mse,
            )
        )
        print(
            f"Hero validation step {completed} | "
            f"train={training[-1].mse:.4f} | val={validation.mse:.4f} | "
            f"mae={validation.mae:.4f}",
            flush=True,
        )

        if validation.mse < best_mse - min_delta:
            best_mse = float(validation.mse)
            best_step = int(completed)
            best_state = trainer.copy_state()
            no_improvement = 0
        else:
            no_improvement += 1

        if completed >= min_steps and no_improvement >= patience:
            stopped_early = True
            break

    final = evaluate_hero_selector(brain, val_samples)
    return {
        "baseline": baseline,
        "final": final,
        "history": history,
        "best_mse": best_mse,
        "best_step": best_step,
        "best_state": best_state,
        "steps_completed": completed,
        "stopped_early": stopped_early,
    }


def main() -> None:
    args = build_parser().parse_args()
    _validate_args(args)

    cards_path = (PROJECT_ROOT / args.cards_file).resolve()
    if not cards_path.exists():
        raise FileNotFoundError(f"Card database not found: {cards_path}")

    revision = git_revision(PROJECT_ROOT)
    dirty = git_is_dirty(PROJECT_ROOT)
    cards_sha = sha256_file(cards_path)

    if dirty and not args.allow_dirty:
        raise RuntimeError(
            "Git worktree is dirty. Commit the synchronized simulator/teacher "
            "stage first, or use --allow-dirty only for a debug run."
        )
    if (
        revision != "unknown"
        and revision.startswith(PRE_SYNC_BASELINE_PREFIX)
        and not args.allow_pre_sync
    ):
        raise RuntimeError(
            "HEAD is still the pre-sync 59010b6 baseline. Complete the current "
            "rules/data audit and create the new clean Git checkpoint before "
            "building the production teacher seed."
        )

    cache_dir = (PROJECT_ROOT / args.cache_dir).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    train_cache = cache_dir / "train_dataset.pt"
    validation_cache = cache_dir / "validation_dataset.pt"
    best_output = cache_dir / "teacher_seed.pt"
    last_output = cache_dir / "teacher_seed_last.pt"
    summary_output = cache_dir / "teacher_seed_summary.json"

    seeds = {
        "master": int(args.seed),
        "model_init": _derive_seed(args.seed, "model_init"),
        "train_games": _derive_seed(args.seed, "train_games"),
        "validation_games": _derive_seed(args.seed, "validation_games"),
        "teacher_minibatches": _derive_seed(args.seed, "teacher_minibatches"),
        "hero_training": _derive_seed(args.seed, "hero_training"),
    }

    train_dataset, train_metadata, train_cache_hit = _load_or_generate_dataset(
        path=train_cache,
        kind="train",
        games=args.train_games,
        seed=seeds["train_games"],
        cards_file=str(cards_path),
        ruleset=args.ruleset,
        cards_sha256=cards_sha,
        revision=revision,
        regenerate=args.regenerate,
    )
    validation_dataset, validation_metadata, validation_cache_hit = _load_or_generate_dataset(
        path=validation_cache,
        kind="validation",
        games=args.val_games,
        seed=seeds["validation_games"],
        cards_file=str(cards_path),
        ruleset=args.ruleset,
        cards_sha256=cards_sha,
        revision=revision,
        regenerate=args.regenerate,
    )

    validate_teacher_dataset(train_dataset)
    validate_teacher_dataset(validation_dataset)
    validate_disjoint_splits(train_dataset, validation_dataset)

    print(
        f"Teacher dataset ready | train={len(train_dataset.recruit_samples)} "
        f"recruit/{len(train_dataset.hero_samples)} hero | "
        f"val={len(validation_dataset.recruit_samples)} "
        f"recruit/{len(validation_dataset.hero_samples)} hero",
        flush=True,
    )

    # Model initialization has its own deterministic stream, independent of
    # teacher-game generation/cache use.
    _seed_runtime(seeds["model_init"])
    brain = NeuralBrain(
        cards_file=str(cards_path),
        device=args.device,
        replay_seed=seeds["teacher_minibatches"],
    )
    trainer = NeuralMCTSTrainer(
        brain,
        config=TrainingConfig(
            batch_size=args.batch_size,
            teacher_seed=seeds["teacher_minibatches"],
        ),
    )

    initial_value_head = (
        deepcopy(brain.model.value_head.state_dict())
        if hasattr(brain.model, "value_head")
        else None
    )

    policy_result = _train_policy(
        brain=brain,
        trainer=trainer,
        train_samples=train_dataset.recruit_samples,
        val_samples=validation_dataset.recruit_samples,
        steps=args.steps,
        min_steps=args.min_steps,
        eval_every=args.eval_every,
        patience=args.patience,
        min_delta=args.min_delta,
        batch_size=args.batch_size,
    )

    value_head_unchanged = True
    if initial_value_head is not None:
        value_head_unchanged = _states_equal(
            initial_value_head,
            brain.model.value_head.state_dict(),
        )
        if not value_head_unchanged:
            raise RuntimeError(
                "Teacher policy pretraining changed value-head parameters."
            )

    hero_result = _train_heroes(
        brain=brain,
        train_samples=train_dataset.hero_samples,
        val_samples=validation_dataset.hero_samples,
        seed=seeds["hero_training"],
        learning_rate=args.hero_learning_rate,
        batch_size=args.hero_batch_size,
        steps=args.hero_steps,
        min_steps=args.hero_min_steps,
        eval_every=args.hero_eval_every,
        patience=args.hero_patience,
        min_delta=args.hero_min_delta,
    )

    provenance = {
        "teacher_seed_version": 1,
        "teacher_data_version": TEACHER_DATA_VERSION,
        "ruleset": str(args.ruleset),
        "git_revision": revision,
        "git_dirty": dirty,
        "cards_file": str(cards_path),
        "cards_sha256": cards_sha,
        "model_schema_version": MODEL_SCHEMA_VERSION,
        "observation_schema_version": int(brain.observation_encoder.SCHEMA_VERSION),
        "action_schema_version": int(brain.action_encoder.SCHEMA_VERSION),
        "hero_selector_schema_version": int(brain.hero_selector.SCHEMA_VERSION),
        "card_vocabulary_fingerprint": getattr(
            brain.vocabulary, "fingerprint", "unknown"
        ),
        "seeds": seeds,
        "config": {
            key: value
            for key, value in vars(args).items()
            if key not in {"device"}
        },
    }

    # LAST = actual final optimizer state, useful for diagnostics.
    trainer.save_checkpoint(
        last_output,
        extra={
            **provenance,
            "teacher_seed_kind": "last",
            "policy_steps_completed": policy_result["steps_completed"],
            "hero_steps_completed": hero_result["steps_completed"],
        },
    )

    # BEST = independently best held-out policy + best held-out hero model.
    brain.model.load_state_dict(policy_result["best_state"])
    brain.hero_selector.load_state_dict(hero_result["best_state"])
    brain.model.eval()
    brain.hero_selector.eval()

    best_policy = evaluate_teacher_policy(
        brain,
        validation_dataset.recruit_samples,
        batch_size=args.batch_size,
    )
    best_hero = evaluate_hero_selector(
        brain,
        validation_dataset.hero_samples,
    )

    # Use a fresh optimizer in the seed checkpoint: self-play starts from the
    # selected weights, not stale teacher-optimizer moments.
    seed_trainer = NeuralMCTSTrainer(
        brain,
        config=TrainingConfig(
            batch_size=args.batch_size,
            teacher_seed=seeds["teacher_minibatches"],
        ),
    )
    seed_trainer.save_checkpoint(
        best_output,
        extra={
            **provenance,
            "teacher_seed_kind": "best_validation",
            "best_policy_step": policy_result["best_step"],
            "best_policy_loss": float(best_policy.policy_loss),
            "best_hero_step": hero_result["best_step"],
            "best_hero_mse": float(best_hero.mse),
            "teacher_value_loss_enabled": False,
        },
    )

    # Reload verification into a genuinely new Brain/Trainer.
    _seed_runtime(_derive_seed(args.seed, "reload_check"))
    reload_brain = NeuralBrain(
        cards_file=str(cards_path),
        device=args.device,
        replay_seed=_derive_seed(args.seed, "reload_replay"),
    )
    reload_trainer = NeuralMCTSTrainer(
        reload_brain,
        config=TrainingConfig(batch_size=args.batch_size),
    )
    reload_extra = reload_trainer.load_checkpoint(best_output)
    reload_policy = evaluate_teacher_policy(
        reload_brain,
        validation_dataset.recruit_samples,
        batch_size=args.batch_size,
    )
    reload_hero = evaluate_hero_selector(
        reload_brain,
        validation_dataset.hero_samples,
    )

    reload_policy_match = abs(reload_policy.policy_loss - best_policy.policy_loss) <= 1e-7
    reload_hero_match = abs(reload_hero.mse - best_hero.mse) <= 1e-7
    if not reload_policy_match or not reload_hero_match:
        raise RuntimeError("Best checkpoint reload metrics do not match saved model.")

    policy_improved = (
        best_policy.policy_loss
        < policy_result["baseline"].policy_loss - args.min_delta
    )
    hero_improved = (
        best_hero.mse
        < hero_result["baseline"].mse - args.hero_min_delta
    )

    summary = {
        "status": {
            "policy_improved_from_fresh": bool(policy_improved),
            "hero_model_improved_from_neutral": bool(hero_improved),
            "value_head_parameters_unchanged": bool(value_head_unchanged),
            "train_validation_disjoint": True,
            "checkpoint_reload_policy_match": bool(reload_policy_match),
            "checkpoint_reload_hero_match": bool(reload_hero_match),
            "ready_for_integration_smoke": bool(policy_improved),
        },
        "provenance": provenance,
        "cache": {
            "directory": str(cache_dir),
            "train_cache": str(train_cache),
            "validation_cache": str(validation_cache),
            "train_cache_hit": bool(train_cache_hit),
            "validation_cache_hit": bool(validation_cache_hit),
            "train_metadata": train_metadata,
            "validation_metadata": validation_metadata,
        },
        "datasets": {
            "train": summarize_teacher_dataset(train_dataset),
            "validation": summarize_teacher_dataset(validation_dataset),
        },
        "policy": {
            "baseline": _policy_record(0, policy_result["baseline"]),
            "best": _policy_record(policy_result["best_step"], best_policy),
            "final_before_restore": _policy_record(
                policy_result["steps_completed"], policy_result["final"]
            ),
            "history": policy_result["history"],
            "best_step": int(policy_result["best_step"]),
            "steps_completed": int(policy_result["steps_completed"]),
            "stopped_early": bool(policy_result["stopped_early"]),
        },
        "hero_selection": {
            "method": (
                "random hero exploration in teacher games -> separate learned "
                "hero expected-placement preference model"
            ),
            "baseline": _hero_record(0, hero_result["baseline"]),
            "best": _hero_record(hero_result["best_step"], best_hero),
            "final_before_restore": _hero_record(
                hero_result["steps_completed"], hero_result["final"]
            ),
            "history": hero_result["history"],
            "best_step": int(hero_result["best_step"]),
            "steps_completed": int(hero_result["steps_completed"]),
            "stopped_early": bool(hero_result["stopped_early"]),
        },
        "reload_verification": {
            "checkpoint_extra": reload_extra,
            "policy": _policy_record(policy_result["best_step"], reload_policy),
            "hero": _hero_record(hero_result["best_step"], reload_hero),
        },
        "outputs": {
            "best_checkpoint": str(best_output),
            "last_checkpoint": str(last_output),
            "summary": str(summary_output),
        },
    }

    write_json(summary_output, summary)

    print("", flush=True)
    print(f"Best teacher seed: {best_output}", flush=True)
    print(f"Last teacher state: {last_output}", flush=True)
    print(f"Summary: {summary_output}", flush=True)
    print(
        "Teacher acceptance | "
        f"policy_improved={policy_improved} | "
        f"hero_improved={hero_improved} | "
        f"value_head_unchanged={value_head_unchanged} | "
        "reload_verified=True",
        flush=True,
    )


if __name__ == "__main__":
    main()
