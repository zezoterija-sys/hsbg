# Hearthstone Battlegrounds AI

A machine learning framework for training AI agents to play Hearthstone Battlegrounds. Built with Python, PyTorch, and designed from the ground up for research and experimentation.

## 🎯 Project Overview

This project implements:
- **Game Simulator**: A simplified but extensible Hearthstone Battlegrounds game engine
- **Monte Carlo Tree Search (MCTS)**: Decision making using tree search with UCB1 selection
- **Neural Networks**: Policy and value networks built with PyTorch
- **Minimal Prototype**: Start simple, scale gradually to full game complexity

## 📋 Project Structure

```
hs-battlegrounds-ai/
├── game/                    # Core game engine
│   ├── board.py            # GameBoard and GameState classes
│   ├── minion.py           # Minion definitions and mechanics
│   ├── heroes.py           # Heroes and hero powers
│   └── actions.py          # Action space and action types
├── agents/                 # AI agents
│   ├── base_agent.py       # Abstract base agent
│   ├── mcts_agent.py       # Monte Carlo Tree Search agent
│   └── neural_agent.py     # Neural network agent
├── models/                 # Machine learning models
│   └── policy_network.py   # Actor-critic networks
├── training/               # Training pipeline
│   ├── trainer.py          # Main training loop
│   └── replay_buffer.py    # Experience replay buffer
├── utils/                  # Utilities
│   ├── config.py           # Configuration management
│   └── logger.py           # Logging utilities
├── tests/                  # Unit tests
│   └── test_game.py        # Game engine tests
├── main.py                 # Entry point
├── setup.py                # Package setup
└── requirements.txt        # Dependencies
```

## 🚀 Quick Start

### Installation

1. **Install Python 3.8+**
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

### Training with MCTS Agent

```bash
python main.py --train --agent mcts --episodes 1000 --simulations 50
```

### Training with Neural Agent

```bash
python main.py --train --agent neural --episodes 1000
```

### Evaluation

```bash
python main.py --eval --agent mcts
```

## 📊 Current Features

### Game Mechanics (Minimal Prototype)
- ✅ Hero selection
- ✅ Gold and tavern level system
- ✅ Shop with buyable minions
- ✅ Board placement (up to 7 minions)
- ✅ Hand management
- ✅ Basic minion stats (attack, health, type)
- ⏳ Battles (simplified collision detection)
- ⏳ Special abilities (taunt, divine shield, windfury)
- ⏳ Tier scaling and minion pools by tier

### AI Agents
- ✅ **MCTS Agent**: Monte Carlo Tree Search with UCB1
- ✅ **Neural Agent**: Policy network with epsilon-greedy exploration
- ✅ **Random Agent**: Baseline for comparison

### Training Infrastructure
- ✅ Episode simulation
- ✅ Reward calculation
- ✅ Experience replay
- ✅ Logging and metrics
- ⏳ Hyperparameter tuning
- ⏳ Model checkpointing

## 🔧 Configuration

Edit `utils/config.py` or pass command-line arguments:

```python
config = Config(
    num_episodes=1000,           # Training episodes
    max_steps_per_episode=100,   # Max steps per episode
    agent_type="mcts",           # "mcts" or "neural"
    mcts_simulations=50,         # Simulations per MCTS move
    neural_epsilon=0.1,          # Exploration rate for neural agent
    learning_rate=1e-3,          # Neural network learning rate
)
```

## 🎓 Understanding the Code

### Game Loop
```python
from game.board import GameBoard
from game.heroes import HEROES

# Initialize
hero = list(HEROES.values())[0]
board = GameBoard(hero)

# Get legal actions
actions = board.state.get_legal_actions()

# Execute action
action = actions[0]
board.execute_action(action)

# Access state
state = board.state
print(f"Gold: {state.gold}, Board: {state.board}")
```

### Training Loop
```python
from agents.mcts_agent import MCTSAgent
from training.trainer import Trainer
from utils.logger import Logger

agent = MCTSAgent(simulations=50)
trainer = Trainer(agent, num_episodes=100)
stats = trainer.train()
```

### Custom Agent
```python
from agents.base_agent import BaseAgent
from game.actions import Action

class MyAgent(BaseAgent):
    def choose_action(self, state):
        # Implement your logic
        actions = state.get_legal_actions()
        return actions[0]
    
    def reset(self):
        pass
```

## 🔬 Experimentation Ideas

1. **Monte Carlo Variants**
   - Experiment with UCB1 exploration constant
   - Try different playout strategies
   - Implement alpha-beta pruning

2. **Neural Networks**
   - Try different architectures (Transformer, CNN)
   - Implement A3C or PPO
   - Add attention mechanisms for hero composition

3. **Game Complexity**
   - Add minion synergies (tribal bonuses)
   - Implement spell system
   - Add more heroes with unique powers
   - Implement actual combat simulation

4. **Multi-Agent**
   - Implement multiplayer games
   - Use self-play for training
   - Tournament evaluation

5. **Optimization**
   - Use GPU acceleration
   - Implement batch processing
   - Parallelize simulations

## 📈 Monitoring Progress

Logs are saved to `logs/` directory with timestamps. Check console output for real-time progress:

```
[INFO] Starting training for 1000 episodes
[INFO] Agent: MCTS(simulations=50)
[INFO] Episode 10/1000, Avg Reward (last 10): 24.53
[INFO] Episode 20/1000, Avg Reward (last 10): 26.11
```

## 🧪 Running Tests

```bash
pytest tests/ -v
```

## 📚 Further Reading

- [Monte Carlo Tree Search](https://en.wikipedia.org/wiki/Monte_Carlo_tree_search)
- [PyTorch Documentation](https://pytorch.org/docs/)
- [Hearthstone Battlegrounds Guide](https://www.playhearthstone.com/en-us/battlegrounds)
- [Reinforcement Learning Introduction](https://spinningup.openai.com/)

## 🤝 Next Steps

1. Run the basic MCTS agent to verify the setup works
2. Experiment with different numbers of simulations
3. Train a neural agent and compare performance
4. Extend the game mechanics (add more minions, heroes, abilities)
5. Implement self-play training
6. Optimize with GPU acceleration

## 📝 Notes

- This is a **minimal prototype** to test the ML pipeline—not a complete game
- Reward function is simplified (board value only)
- Combat is abstracted away initially
- Focus is on agent decision-making in the shop phase

## ⚠️ Known Limitations

- No actual combat simulation yet
- Reward function is basic
- No minion synergies/tribes
- Limited hero pool
- Single-player simulation only

---

**Happy training! 🎮🤖**
