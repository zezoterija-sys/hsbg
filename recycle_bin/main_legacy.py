"""
Main entry point for training Hearthstone Battlegrounds AI
"""
import argparse
import torch
from game.board import GameBoard
from game.heroes import HEROES
from agents.mcts_agent import MCTSAgent
from agents.neural_agent import NeuralAgent
from models.policy_network import PolicyNetwork
from training.trainer import Trainer
from utils.config import Config
from utils.logger import Logger


def create_agent(config: Config) -> any:
    """Create agent based on config"""
    if config.agent_type == "mcts":
        return MCTSAgent(simulations=config.mcts_simulations)
    elif config.agent_type == "neural":
        model = PolicyNetwork(
            state_size=config.state_size,
            action_size=config.action_size,
            hidden_size=config.hidden_size,
            learning_rate=config.learning_rate,
        )
        return NeuralAgent(model=model, epsilon=config.neural_epsilon)
    else:
        raise ValueError(f"Unknown agent type: {config.agent_type}")


def main():
    """Main training function"""
    parser = argparse.ArgumentParser(description="Train Hearthstone Battlegrounds AI")
    parser.add_argument(
        "--train",
        action="store_true",
        help="Run training",
    )
    parser.add_argument(
        "--eval",
        action="store_true",
        help="Run evaluation",
    )
    parser.add_argument(
        "--agent",
        type=str,
        default="mcts",
        choices=["mcts", "neural"],
        help="Agent type",
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=100,
        help="Number of episodes to train",
    )
    parser.add_argument(
        "--simulations",
        type=int,
        default=50,
        help="Number of MCTS simulations per move",
    )
    
    args = parser.parse_args()
    
    # Setup
    logger = Logger("main")
    logger.info("Hearthstone Battlegrounds AI Training")
    logger.info(f"PyTorch version: {torch.__version__}")
    logger.info(f"CUDA available: {torch.cuda.is_available()}")
    
    # Create config
    config = Config(
        agent_type=args.agent,
        num_episodes=args.episodes,
        mcts_simulations=args.simulations,
    )
    logger.info(f"Config: {config}")
    
    # Create agent
    agent = create_agent(config)
    logger.info(f"Created agent: {agent}")
    
    # Create trainer
    trainer = Trainer(
        agent=agent,
        num_episodes=config.num_episodes,
        max_steps=config.max_steps_per_episode,
        logger=logger,
    )
    
    # Run training
    if args.train:
        logger.info("Starting training...")
        stats = trainer.train()
        
        logger.info("Training complete!")
        logger.info(f"Final average reward: {stats['final_avg_reward']:.2f}")
        logger.info(f"Max reward: {stats['max_reward']:.2f}")
        logger.info(f"Min reward: {stats['min_reward']:.2f}")
    
    # Run evaluation
    if args.eval:
        logger.info("Starting evaluation...")
        eval_reward = trainer.evaluate(config.eval_episodes)
        logger.info(f"Evaluation complete! Average reward: {eval_reward:.2f}")


if __name__ == "__main__":
    main()
