# Hearthstone Battlegrounds Simulator + AI

Python research project for an eight-player Hearthstone Battlegrounds simulator
and two competing AI systems.

## Current architecture

A game contains eight independent seats:

- **Brain A:** 4 independent pure-MCTS agents.
- **Brain B:** 4 independent neural-MCTS/PUCT agents sharing one neural model.

Same-brain seats do not share observations, memories, RNG streams, thinking
budgets, or search trees. The simulator remains separate from the agents and is
coordinated by `game/bob.py`.

See `PROJECT_RULES.md` for the project-level design contract.

## Main systems

- `game/` — Bob, players, recruitment, taverns, shared card pool, effects,
  events, combat, actions, heroes, and current card-effect implementations.
- `agents/` — AI-safe observations, action/observation encoding, pure MCTS,
  neural PUCT, belief/determinization support, and per-seat thinking budgets.
- `models/` — policy/value network.
- `training/` — self-play, replay, trainer, experiment runner, reward shaping,
  and teacher-seed infrastructure.
- `scripts/` — maintenance tools and specialist experiment/data builders.
- `tests/` — active tests for the current architecture.
- `data/raw/cards.json` — local card database used by the simulator.
- `recycle_bin/` — obsolete prototype material kept only for historical
  reference.

## Canonical entry point

The root command is the supported experiment entry point:

```bash
python main.py --smoke
```

A normal training/evaluation run can be configured with the same options as the
experiment CLI, for example:

```bash
python main.py \
  --games 100 \
  --eval-games 10 \
  --seed 1234 \
  --output-dir runs/mcts_vs_neural_001
```

Brain A and Brain B use the same hero-selection method in the standard
comparison. The current default is random selection from each seat's legal hero
offer.

## Useful specialist commands

```bash
python scripts/download_cards.py
python scripts/validate_heroes.py
python scripts/build_teacher_seed.py --help
python scripts/run_ai_experiment.py --help
```

The specialist experiment script remains available for compatibility, but
`python main.py ...` is the canonical project entry point.

## Tests

```bash
pytest
```

`pytest.ini` restricts discovery to the active `tests/` tree. Historical tests
under `recycle_bin/` are intentionally excluded.

The focused engine/card suite can also be run with:

```bash
python tests/run_all_tests.py
```

## Rules and accuracy

Explicit simulator design decisions are primary. Matching the current live
Hearthstone Battlegrounds rules is a strong secondary priority. If the project
intentionally differs from the live game, that difference should be explicit
rather than silently changed.

## Python

The active codebase requires **Python 3.10+**. The project currently uses modern
Python type syntax and PyTorch.
