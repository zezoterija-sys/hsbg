from training.basic_rewards import BasicRewardConfig
from training.experiment import ExperimentRunner
from training.self_play import SelfPlayConfig


def test_evaluation_preserves_nested_basic_reward_config():
    runner = object.__new__(ExperimentRunner)
    runner.self_play_config = SelfPlayConfig()
    evaluation = runner._evaluation_config()
    assert isinstance(evaluation.basic_reward, BasicRewardConfig)
    assert evaluation.collect_training_data is False
    assert evaluation.enable_training_updates is False
