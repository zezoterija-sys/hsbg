from training.self_play import SelfPlayConfig


def test_default_search_shape_preserves_original_values():
    config = SelfPlayConfig()
    assert config.mcts_max_tree_depth == 64
    assert config.mcts_max_rollout_steps == 256
    assert config.puct_max_tree_depth == 64
    assert config.rollout_force_end_after_actions == 30
    assert config.rollout_end_turn_probability == 0.10


def test_fast_search_shape_is_valid_without_changing_ap_rules():
    config = SelfPlayConfig(
        mcts_max_tree_depth=24,
        mcts_max_rollout_steps=72,
        puct_max_tree_depth=24,
        rollout_force_end_after_actions=12,
        rollout_end_turn_probability=0.20,
    )
    assert config.mcts_max_rollout_steps == 72
    assert config.rollout_force_end_after_actions == 12
