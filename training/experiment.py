"""
Experiment orchestration and metrics for A-vs-B Battlegrounds self-play.

This module aggregates results across games. "Brain A" and "Brain B" statistics
are experiment-level comparisons only; the underlying game remains an
eight-player free-for-all and rewards remain per individual player.

Outputs:
- one JSONL record per training/evaluation game,
- summary.json,
- periodic Brain-B checkpoints.

Evaluation games:
- use the current shared Brain-B weights,
- disable neural-MCTS training noise,
- do not collect replay,
- do not update model weights.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import json
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from agents.neural_brain import NeuralBrain
from training.self_play import (
    BRAIN_A,
    BRAIN_B,
    GameResult,
    SelfPlayConfig,
    SelfPlayRunner,
)
from training.trainer import NeuralMCTSTrainer


@dataclass(frozen=True)
class ExperimentConfig:
    training_games: int = 10
    evaluation_games: int = 0

    output_dir: str = "runs/bg_ai"
    checkpoint_every: int = 10

    # Write individual game records. This is useful for later plotting without
    # keeping all GameResult objects in memory.
    write_jsonl: bool = True

    def __post_init__(self) -> None:
        if self.training_games < 0:
            raise ValueError(
                "training_games cannot be negative."
            )
        if self.evaluation_games < 0:
            raise ValueError(
                "evaluation_games cannot be negative."
            )
        if self.checkpoint_every < 0:
            raise ValueError(
                "checkpoint_every cannot be negative."
            )
        if not str(self.output_dir).strip():
            raise ValueError(
                "output_dir cannot be empty."
            )


@dataclass(frozen=True)
class BrainMetrics:
    games: int
    wins: int
    win_rate: float

    seat_finishes: int
    mean_placement: float
    top4_rate: float
    mean_value: float


@dataclass(frozen=True)
class PhaseMetrics:
    games: int
    brain_a: BrainMetrics
    brain_b: BrainMetrics

    mean_rounds: float
    mean_actions: float
    mean_action_batches: float


@dataclass(frozen=True)
class ExperimentSummary:
    training: PhaseMetrics
    evaluation: PhaseMetrics | None

    replay_size: int
    trainer_steps_completed: int
    completed_games_committed: int

    latest_checkpoint: str | None = None


class ResultAccumulator:
    """Online metric accumulator for GameResult objects."""

    def __init__(self) -> None:
        self.games = 0
        self.rounds: list[int] = []
        self.actions: list[int] = []
        self.action_batches: list[int] = []

        self._wins = {
            BRAIN_A: 0,
            BRAIN_B: 0,
        }
        self._placements = {
            BRAIN_A: [],
            BRAIN_B: [],
        }
        self._values = {
            BRAIN_A: [],
            BRAIN_B: [],
        }

    def add(
        self,
        result: GameResult,
    ) -> None:
        self.games += 1
        self.rounds.append(
            int(result.rounds_played)
        )
        self.actions.append(
            int(result.actions_executed)
        )
        self.action_batches.append(
            int(result.action_batches)
        )

        seats = result.seat_assignment

        for player_id, placement in result.placements.items():
            brain = seats.brain_for(
                int(player_id)
            )

            self._placements[
                brain
            ].append(
                int(placement)
            )
            self._values[
                brain
            ].append(
                float(
                    result.final_values[
                        int(player_id)
                    ]
                )
            )

        if result.winner_id is not None:
            winner_brain = seats.brain_for(
                int(result.winner_id)
            )
            self._wins[
                winner_brain
            ] += 1

    def finalize(self) -> PhaseMetrics:
        return PhaseMetrics(
            games=self.games,
            brain_a=self._brain_metrics(
                BRAIN_A
            ),
            brain_b=self._brain_metrics(
                BRAIN_B
            ),
            mean_rounds=self._safe_mean(
                self.rounds
            ),
            mean_actions=self._safe_mean(
                self.actions
            ),
            mean_action_batches=self._safe_mean(
                self.action_batches
            ),
        )

    def _brain_metrics(
        self,
        brain: str,
    ) -> BrainMetrics:
        placements = self._placements[
            brain
        ]
        values = self._values[
            brain
        ]

        wins = self._wins[
            brain
        ]

        return BrainMetrics(
            games=self.games,
            wins=wins,
            win_rate=(
                wins / self.games
                if self.games
                else 0.0
            ),
            seat_finishes=len(
                placements
            ),
            mean_placement=self._safe_mean(
                placements
            ),
            top4_rate=(
                sum(
                    placement <= 4
                    for placement
                    in placements
                )
                / len(placements)
                if placements
                else 0.0
            ),
            mean_value=self._safe_mean(
                values
            ),
        )

    @staticmethod
    def _safe_mean(
        values: Iterable[
            int | float
        ],
    ) -> float:
        values = list(
            values
        )
        return (
            float(mean(values))
            if values
            else 0.0
        )


class ExperimentRunner:
    """Run training games, optional clean evaluation, metrics, and checkpoints."""

    def __init__(
        self,
        *,
        self_play_config: SelfPlayConfig | None = None,
        experiment_config: ExperimentConfig | None = None,
        brain: NeuralBrain | None = None,
        trainer: NeuralMCTSTrainer | None = None,
    ) -> None:
        self.self_play_config = (
            self_play_config
            or SelfPlayConfig()
        )
        self.experiment_config = (
            experiment_config
            or ExperimentConfig()
        )

        self.brain = (
            brain
            if brain is not None
            else NeuralBrain(
                cards_file=(
                    self.self_play_config
                    .cards_file
                ),
                replay_seed=(
                    self.self_play_config
                    .seed
                ),
            )
        )

        self.trainer = (
            trainer
            if trainer is not None
            else NeuralMCTSTrainer(
                self.brain
            )
        )

        if self.trainer.brain is not self.brain:
            raise ValueError(
                "Experiment trainer and brain must reference the same "
                "NeuralBrain object."
            )

        self.training_runner = SelfPlayRunner(
            config=self.self_play_config,
            brain=self.brain,
            trainer=self.trainer,
        )

        self.output_dir = Path(
            self.experiment_config.output_dir
        )
        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._latest_checkpoint: Path | None = None

    # ==================================================================
    # RUN
    # ==================================================================

    def run(self) -> ExperimentSummary:
        training_accumulator = (
            ResultAccumulator()
        )

        for game_index in range(
            self.experiment_config.training_games
        ):
            result = (
                self.training_runner
                .run_game(
                    game_index=game_index
                )
            )

            training_accumulator.add(
                result
            )
            self._write_game_result(
                "training",
                result,
            )

            game_number = game_index + 1

            if (
                self.experiment_config.checkpoint_every > 0
                and game_number
                % self.experiment_config.checkpoint_every
                == 0
            ):
                self._latest_checkpoint = (
                    self.save_checkpoint(
                        game_number
                    )
                )

        evaluation_metrics = None

        if (
            self.experiment_config
            .evaluation_games
            > 0
        ):
            evaluation_metrics = (
                self._run_evaluation()
            )

        summary = ExperimentSummary(
            training=training_accumulator.finalize(),
            evaluation=evaluation_metrics,
            replay_size=len(
                self.brain.replay_buffer
            ),
            trainer_steps_completed=(
                self.trainer
                .training_steps_completed
            ),
            completed_games_committed=(
                self.trainer
                .completed_games_committed
            ),
            latest_checkpoint=(
                str(
                    self._latest_checkpoint
                )
                if self._latest_checkpoint
                is not None
                else None
            ),
        )

        self._write_summary(
            summary
        )
        return summary

    # ==================================================================
    # EVALUATION
    # ==================================================================

    def _run_evaluation(
        self,
    ) -> PhaseMetrics:
        config = self._evaluation_config()

        runner = SelfPlayRunner(
            config=config,
            brain=self.brain,
            trainer=self.trainer,
        )

        accumulator = ResultAccumulator()

        # Use a separate seed stream from training while remaining deterministic.
        base_index = (
            self.experiment_config
            .training_games
            + 1_000_000
        )

        replay_before = len(
            self.brain.replay_buffer
        )
        steps_before = (
            self.trainer
            .training_steps_completed
        )

        for offset in range(
            self.experiment_config.evaluation_games
        ):
            result = runner.run_game(
                game_index=(
                    base_index + offset
                )
            )

            accumulator.add(
                result
            )
            self._write_game_result(
                "evaluation",
                result,
            )

        # These are hard safety assertions: evaluation is not allowed to train.
        if len(
            self.brain.replay_buffer
        ) != replay_before:
            raise RuntimeError(
                "Evaluation modified replay buffer."
            )

        if (
            self.trainer
            .training_steps_completed
            != steps_before
        ):
            raise RuntimeError(
                "Evaluation updated Brain B weights."
            )

        return accumulator.finalize()

    def _evaluation_config(
        self,
    ) -> SelfPlayConfig:
        # Preserve nested dataclass objects (notably BasicRewardConfig).
        # dataclasses.asdict() would recursively turn them into plain dicts.
        values = {
            item.name: getattr(self.self_play_config, item.name)
            for item in fields(SelfPlayConfig)
        }

        values.update(
            {
                "brain_b_training_mode": False,
                "collect_training_data": False,
                "enable_training_updates": False,
                "training_steps_between_rounds": 0,
                "training_steps_after_game": 0,
            }
        )

        return SelfPlayConfig(
            **values
        )

    # ==================================================================
    # OUTPUT
    # ==================================================================

    def save_checkpoint(
        self,
        game_number: int,
    ) -> Path:
        checkpoint_dir = (
            self.output_dir
            / "checkpoints"
        )
        checkpoint_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination = (
            checkpoint_dir
            / (
                f"brain_b_game_"
                f"{int(game_number):08d}.pt"
            )
        )

        return self.trainer.save_checkpoint(
            destination,
            extra={
                "training_game_number": int(
                    game_number
                ),
                "self_play_config": asdict(
                    self.self_play_config
                ),
                "experiment_config": asdict(
                    self.experiment_config
                ),
            },
        )

    def _write_game_result(
        self,
        phase: str,
        result: GameResult,
    ) -> None:
        if not self.experiment_config.write_jsonl:
            return

        if phase not in {
            "training",
            "evaluation",
        }:
            raise ValueError(
                f"Unknown result phase: {phase!r}"
            )

        path = self.output_dir / (
            f"{phase}_games.jsonl"
        )

        payload = self.game_result_to_dict(
            result
        )
        payload["phase"] = phase

        with path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                json.dumps(
                    payload,
                    sort_keys=True,
                )
            )
            handle.write(
                "\n"
            )

    def _write_summary(
        self,
        summary: ExperimentSummary,
    ) -> None:
        destination = (
            self.output_dir
            / "summary.json"
        )
        temporary = destination.with_suffix(
            ".json.tmp"
        )

        with temporary.open(
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                asdict(
                    summary
                ),
                handle,
                indent=2,
                sort_keys=True,
            )
            handle.write(
                "\n"
            )

        temporary.replace(
            destination
        )

    @staticmethod
    def game_result_to_dict(
        result: GameResult,
    ) -> dict[str, Any]:
        return {
            "game_id": result.game_id,
            "seed": int(
                result.seed
            ),
            "winner_id": result.winner_id,
            "rounds_played": int(
                result.rounds_played
            ),
            "action_batches": int(
                result.action_batches
            ),
            "actions_executed": int(
                result.actions_executed
            ),
            "brain_a_player_ids": list(
                result
                .seat_assignment
                .brain_a_player_ids
            ),
            "brain_b_player_ids": list(
                result
                .seat_assignment
                .brain_b_player_ids
            ),
            "placements": {
                str(player_id): int(
                    placement
                )
                for player_id, placement
                in result.placements.items()
            },
            "final_values": {
                str(player_id): float(
                    value
                )
                for player_id, value
                in result.final_values.items()
            },
            "brain_b_samples_committed": int(
                result
                .brain_b_samples_committed
            ),
            "training_steps_run": int(
                result.training_steps_run
            ),
            "latest_training_loss": (
                float(
                    result.latest_training_loss
                )
                if result.latest_training_loss
                is not None
                else None
            ),
        }

    def __repr__(self) -> str:
        return (
            f"ExperimentRunner("
            f"training_games="
            f"{self.experiment_config.training_games}, "
            f"evaluation_games="
            f"{self.experiment_config.evaluation_games}, "
            f"output_dir={str(self.output_dir)!r}"
            f")"
        )
