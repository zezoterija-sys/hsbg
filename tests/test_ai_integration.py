"""
AI architecture/integration tests.

The default tests are intentionally fast. A complete eight-player AI game is
available as an opt-in smoke test because even tiny MCTS budgets still exercise
real determinized simulations and combat.

Run the full AI smoke explicitly:

PowerShell:
    $env:RUN_AI_FULL_SMOKE="1"
    pytest tests/test_ai_integration.py -q

cmd.exe:
    set RUN_AI_FULL_SMOKE=1
    pytest tests/test_ai_integration.py -q
"""

from __future__ import annotations

import os

import pytest

from training.experiment import ResultAccumulator
from training.self_play import (
    GameResult,
    SeatAssignment,
    SelfPlayConfig,
    SelfPlayRunner,
)


def test_placement_value_scale():
    assert SelfPlayRunner.placement_value(1) == pytest.approx(1.0)
    assert SelfPlayRunner.placement_value(8) == pytest.approx(-1.0)

    values = [
        SelfPlayRunner.placement_value(
            placement
        )
        for placement in range(1, 9)
    ]

    assert all(
        earlier > later
        for earlier, later
        in zip(
            values,
            values[1:],
        )
    )


def test_seat_assignment_is_exactly_four_and_four():
    seats = SeatAssignment(
        brain_a_player_ids=(0, 2, 4, 6),
        brain_b_player_ids=(1, 3, 5, 7),
    )

    assert {
        seats.brain_for(player_id)
        for player_id
        in seats.brain_a_player_ids
    } == {"A"}

    assert {
        seats.brain_for(player_id)
        for player_id
        in seats.brain_b_player_ids
    } == {"B"}


def test_fast_smoke_budget_is_valid():
    config = SelfPlayConfig(
        per_decision_simulations=1,
        phase_simulations=1,
        brain_b_training_mode=False,
        collect_training_data=False,
        enable_training_updates=False,
        training_steps_between_rounds=0,
        training_steps_after_game=0,
    )

    assert config.per_decision_simulations == 1
    assert config.phase_simulations == 1
    assert config.collect_training_data is False


def test_experiment_metrics_aggregate_brains_without_team_reward():
    seats = SeatAssignment(
        brain_a_player_ids=(0, 1, 2, 3),
        brain_b_player_ids=(4, 5, 6, 7),
    )

    placements = {
        0: 1,
        1: 3,
        2: 5,
        3: 7,
        4: 2,
        5: 4,
        6: 6,
        7: 8,
    }

    values = {
        player_id: SelfPlayRunner.placement_value(
            placement
        )
        for player_id, placement
        in placements.items()
    }

    result = GameResult(
        game_id="test",
        seed=1,
        winner_id=0,
        rounds_played=10,
        action_batches=100,
        actions_executed=500,
        seat_assignment=seats,
        placements=placements,
        final_values=values,
        brain_b_samples_committed=0,
        training_steps_run=0,
        latest_training_loss=None,
    )

    accumulator = ResultAccumulator()
    accumulator.add(
        result
    )
    metrics = accumulator.finalize()

    assert metrics.games == 1

    assert metrics.brain_a.wins == 1
    assert metrics.brain_b.wins == 0

    # Four independent finishes are aggregated only for experiment analysis.
    assert metrics.brain_a.seat_finishes == 4
    assert metrics.brain_b.seat_finishes == 4

    assert metrics.brain_a.mean_placement == pytest.approx(4.0)
    assert metrics.brain_b.mean_placement == pytest.approx(5.0)

    assert metrics.brain_a.top4_rate == pytest.approx(0.5)
    assert metrics.brain_b.top4_rate == pytest.approx(0.5)


def test_full_eight_player_ai_game_smoke():
    if os.environ.get(
        "RUN_AI_FULL_SMOKE"
    ) != "1":
        pytest.skip(
            "Set RUN_AI_FULL_SMOKE=1 to run the expensive full AI game."
        )

    config = SelfPlayConfig(
        seed=20260905,
        per_decision_simulations=1,
        phase_simulations=1,
        brain_b_training_mode=False,
        collect_training_data=False,
        enable_training_updates=False,
        training_steps_between_rounds=0,
        training_steps_after_game=0,
        max_action_batches_per_round=180,
    )

    runner = SelfPlayRunner(
        config=config
    )

    result = runner.run_game()

    assert result.winner_id in range(8)
    assert sorted(
        result.placements.values()
    ) == list(
        range(1, 9)
    )

    assert len(
        result
        .seat_assignment
        .brain_a_player_ids
    ) == 4

    assert len(
        result
        .seat_assignment
        .brain_b_player_ids
    ) == 4

    assert result.brain_b_samples_committed == 0
    assert result.training_steps_run == 0
