# HSBG project rules

This file records project-level decisions that should remain stable unless they
are deliberately changed.

## Architecture

- The simulator is independent from the AI systems.
- A standard game has 8 independent player seats.
- Brain A controls 4 independent pure-MCTS agents.
- Brain B controls 4 independent neural-MCTS/PUCT agents that may share the
  Brain-B model, but do not share per-seat observations, memories, RNG streams,
  thinking budgets, or search trees.
- There is no team reward or same-brain cooperation.

## Fair comparison

- Brain A and Brain B use the same hero-selection method in controlled A-vs-B
  comparisons.
- The current default is random selection from each seat's legal hero offer.
- Learned hero-selection machinery may exist for separate experiments, but it
  must not silently give one brain a different hero-selection policy in the
  standard comparison.

## Rules priority

1. Explicit simulator/project design decisions are primary.
2. Accuracy with the current live Hearthstone Battlegrounds game is a strong
   secondary priority.
3. When the simulator intentionally differs from the live game, the difference
   should be documented rather than silently changed.

## Repository hygiene

- `main.py` is the canonical project entry point for the active experiment CLI.
- Special-purpose maintenance/data/training builders may live under `scripts/`.
- Obsolete prototype files are moved to `recycle_bin/` rather than deleted.
- Files under `recycle_bin/` are historical reference only and must not be
  imported by active code or collected as active tests.
