"""
Configuration management
"""
from dataclasses import dataclass, asdict
from typing import Optional
import json
import os


@dataclass
class Config:
    """Configuration for training and evaluation"""
    
    # Training parameters
    num_episodes: int = 1000
    max_steps_per_episode: int = 100
    batch_size: int = 32
    learning_rate: float = 1e-3
    
    # Agent parameters
    agent_type: str = "mcts"  # "mcts", "neural", "random"
    mcts_simulations: int = 50
    neural_epsilon: float = 0.1
    
    # Model parameters
    hidden_size: int = 256
    state_size: int = 121
    action_size: int = 100
    
    # Replay buffer
    replay_buffer_size: int = 100000
    
    # Evaluation
    eval_episodes: int = 10
    eval_frequency: int = 50
    
    # Logging
    log_dir: str = "./logs"
    checkpoint_dir: str = "./checkpoints"
    
    def save(self, path: str):
        """Save config to JSON file"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)
    
    @staticmethod
    def load(path: str) -> "Config":
        """Load config from JSON file"""
        with open(path, "r") as f:
            data = json.load(f)
        return Config(**data)
    
    def __repr__(self) -> str:
        return f"Config(agent={self.agent_type}, episodes={self.num_episodes})"
