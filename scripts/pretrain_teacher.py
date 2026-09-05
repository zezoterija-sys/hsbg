#!/usr/bin/env python3
"""Warm-start Brain B from the generic rule teacher, then save a normal checkpoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.neural_brain import NeuralBrain
from training.teacher_data import TeacherDataConfig, TeacherDataGenerator
from training.trainer import NeuralMCTSTrainer, TrainingConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate generic Battlegrounds teacher games and imitate them."
    )
    parser.add_argument("--games", type=int, default=12)
    parser.add_argument("--steps", type=int, default=250)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--cards-file", default="data/raw/cards.json")
    parser.add_argument("--device", default=None)
    parser.add_argument("--resume", default=None)
    parser.add_argument(
        "--output",
        default="runs/bg_ai/teacher_seed.pt",
        help="Checkpoint usable directly with run_ai_experiment.py --resume.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.games <= 0 or args.steps < 0 or args.batch_size <= 0:
        raise ValueError("games/batch-size must be positive and steps non-negative.")

    brain = NeuralBrain(
        cards_file=args.cards_file,
        device=args.device,
        replay_seed=args.seed,
    )
    trainer = NeuralMCTSTrainer(
        brain,
        config=TrainingConfig(
            batch_size=args.batch_size,
            teacher_seed=args.seed,
        ),
    )

    if args.resume:
        trainer.load_checkpoint(args.resume)

    generator = TeacherDataGenerator(
        config=TeacherDataConfig(
            cards_file=args.cards_file,
            seed=args.seed,
        )
    )
    samples = generator.generate_games(args.games)
    print(f"Teacher samples generated: {len(samples)}", flush=True)

    stats = trainer.pretrain_teacher_steps(
        samples,
        args.steps,
        batch_size=args.batch_size,
    )

    output = trainer.save_checkpoint(
        args.output,
        extra={
            "teacher_pretraining": True,
            "teacher_games": args.games,
            "teacher_samples": len(samples),
            "teacher_steps_this_run": len(stats),
            "teacher_steps_total": trainer.teacher_steps_completed,
        },
    )

    summary = {
        "checkpoint": str(output),
        "teacher_games": args.games,
        "teacher_samples": len(samples),
        "teacher_steps_completed": trainer.teacher_steps_completed,
        "last_policy_loss": stats[-1].policy_loss if stats else None,
        "device": str(brain.device),
    }
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
