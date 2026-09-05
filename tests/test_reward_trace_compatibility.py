"""Regression test: reward shaping must not remove trace configuration."""

from training.basic_rewards import BasicRewardConfig
from training.self_play import SelfPlayConfig


def test_reward_shaping_and_trace_config_can_coexist():
    config = SelfPlayConfig(
        per_decision_simulations=1,
        phase_simulations=8,
        trace_player_id=0,
        trace_file="runs/bg_ai/player_0_actions.jsonl",
        basic_reward=BasicRewardConfig(),
    )

    assert config.trace_player_id == 0
    assert config.trace_file == "runs/bg_ai/player_0_actions.jsonl"
    assert config.basic_reward.enabled is True
