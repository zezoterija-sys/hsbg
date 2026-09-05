"""
Command-line entry point for Hearthstone Battlegrounds AI experiments.

Examples:

    python scripts/run_ai_experiment.py --smoke

    python scripts/run_ai_experiment.py \
        --games 100 \
        --eval-games 10 \
        --seed 1234 \
        --output-dir runs/mcts_vs_neural_001

    python scripts/run_ai_experiment.py \
        --games 100 \
        --resume runs/mcts_vs_neural_001/checkpoints/brain_b_game_00000100.pt
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
from dataclasses import asdict
import json

from agents.neural_brain import NeuralBrain
from training.experiment import (
    ExperimentConfig,
    ExperimentRunner,
)
from training.self_play import SelfPlayConfig
from training.trainer import NeuralMCTSTrainer, TrainingConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run 4 pure-MCTS vs 4 neural-MCTS "
            "Battlegrounds self-play experiments."
        )
    )

    parser.add_argument(
        "--games",
        type=int,
        default=10,
        help="Number of training games.",
    )
    parser.add_argument(
        "--eval-games",
        type=int,
        default=0,
        help=(
            "Clean evaluation games after training. "
            "Evaluation does not train or modify replay."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--cards-file",
        default="data/raw/cards.json",
    )
    parser.add_argument(
        "--output-dir",
        default="runs/bg_ai",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=10,
        help="Save Brain B every N training games; 0 disables.",
    )

    parser.add_argument(
        "--per-decision",
        type=int,
        default=200,
        help="MCTS simulations allowed per decision.",
    )
    parser.add_argument(
        "--phase-budget",
        type=int,
        default=5000,
        help="MCTS simulations allowed per recruit phase.",
    )

    parser.add_argument(
        "--throughput",
        action="store_true",
        help=(
            "Faster imagined search profile: shorter tree/rollout horizons and "
            "earlier simulated END_TURN. Real game rules and 100 AP are unchanged."
        ),
    )

    parser.add_argument(
        "--train-between-rounds",
        type=int,
        default=1,
        help=(
            "Brain-B optimizer steps between rounds, "
            "using completed previous-game replay only."
        ),
    )
    parser.add_argument(
        "--train-after-game",
        type=int,
        default=1,
        help="Brain-B optimizer steps immediately after each completed game.",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=128,
        help="Padded/masked Brain-B training batch size.",
    )

    parser.add_argument(
        "--device",
        default=None,
        help="Torch device such as cpu, cuda, cuda:0. Default: auto.",
    )
    parser.add_argument(
        "--resume",
        default=None,
        help="Optional trainer checkpoint to load before running.",
    )

    parser.add_argument(
        "--trace-player",
        type=int,
        default=None,
        help=(
            "Write real-lobby decisions for one player ID (0..7) to JSONL. "
            "MCTS simulated actions are excluded."
        ),
    )
    parser.add_argument(
        "--trace-file",
        default=None,
        help=(
            "Optional trace JSONL path. Default when --trace-player is set: "
            "<output-dir>/player_<id>_actions.jsonl"
        ),
    )

    parser.add_argument(
        "--smoke",
        action="store_true",
        help=(
            "One very-low-search game for integration testing. "
            "Does not update model weights."
        ),
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.smoke:
        games = 1
        eval_games = 0
        per_decision = 1
        phase_budget = 1
        train_between_rounds = 0
        train_after_game = 0
        collect_training_data = False
        enable_training_updates = False
        brain_b_training_mode = False
        checkpoint_every = 0
    else:
        games = args.games
        eval_games = args.eval_games
        per_decision = args.per_decision
        phase_budget = args.phase_budget
        train_between_rounds = (
            args.train_between_rounds
        )
        train_after_game = (
            args.train_after_game
        )
        collect_training_data = True
        enable_training_updates = True
        brain_b_training_mode = True
        checkpoint_every = (
            args.checkpoint_every
        )

    trace_file = None
    if args.trace_player is not None:
        if not 0 <= int(args.trace_player) < 8:
            raise ValueError("--trace-player must be in player IDs 0..7.")
        trace_path = Path(
            args.trace_file
            if args.trace_file is not None
            else Path(args.output_dir) / f"player_{args.trace_player}_actions.jsonl"
        )
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        # Each command invocation starts a fresh trace.
        trace_path.write_text("", encoding="utf-8")
        trace_file = str(trace_path)
        print(f"Tracing player P{args.trace_player} -> {trace_file}", flush=True)

    if args.throughput:
        search_shape = {
            "mcts_max_tree_depth": 24,
            "mcts_max_rollout_steps": 72,
            "puct_max_tree_depth": 24,
            "rollout_end_turn_probability": 0.20,
            "rollout_force_end_after_actions": 12,
        }
        print(
            "Throughput profile: imagined depth 24, pure-MCTS rollout 72, "
            "simulated turn cap 12.",
            flush=True,
        )
    else:
        search_shape = {}

    self_play_config = SelfPlayConfig(
        cards_file=args.cards_file,
        seed=args.seed,
        per_decision_simulations=per_decision,
        phase_simulations=phase_budget,
        brain_b_training_mode=brain_b_training_mode,
        collect_training_data=collect_training_data,
        enable_training_updates=enable_training_updates,
        trace_player_id=args.trace_player,
        trace_file=trace_file,
        training_steps_between_rounds=(
            train_between_rounds
        ),
        training_steps_after_game=(
            train_after_game
        ),
        **search_shape,
    )

    experiment_config = ExperimentConfig(
        training_games=games,
        evaluation_games=eval_games,
        output_dir=args.output_dir,
        checkpoint_every=checkpoint_every,
    )

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

    if args.resume is not None:
        checkpoint = Path(
            args.resume
        )

        if not checkpoint.exists():
            raise FileNotFoundError(
                f"Checkpoint not found: {checkpoint}"
            )

        trainer.load_checkpoint(
            checkpoint
        )

    runner = ExperimentRunner(
        self_play_config=self_play_config,
        experiment_config=experiment_config,
        brain=brain,
        trainer=trainer,
    )

    summary = runner.run()

    print(
        json.dumps(
            asdict(summary),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
