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

## Work order

- Current authorized change: apply the prepared P0 RNG ownership fix and record
  Hero Power preparation. Hero Power content implementation is not started by
  this change. Trinkets and Dark Gifts remain on hold.
- Hero Power target: Battlegrounds patch 36.4.2 Solos, implemented from ordinary
  to complex using shared engine primitives. See `docs/hero-power-preparation.md`.
- Run focused checks for changes; leave full suites, multi-game simulations,
  benchmarks and training runs to the user.
- Complete and validate current Solos game rules and active mechanics first.
- Maintain a basic AI interface/skeleton that can observe legal public/own
  state and play the game correctly while that work proceeds.
- Add focused regressions with game fixes, then run broad seeded full-game
  validation before calling the simulator synchronized.
- Defer teacher training, ML experiments, and deeper AI-method design until the
  game is complete and the basic AI skeleton is working.
- Keep work on `cleanup/current-architecture` / PR #1. Do not merge or modify
  `main` without explicit user authorization.

## Fair comparison

- Brain A and Brain B use the same hero-selection method in controlled A-vs-B
  comparisons.
- The current default is random selection from each seat's legal hero offer.
- Learned hero-selection machinery may exist for separate experiments, but it
  must not silently give one brain a different hero-selection policy in the
  standard comparison.

## Rules priority

1. Preserve simulator/AI infrastructure that is necessary for execution,
   determinism, performance, and fair agent interaction.
2. Within those constraints, match the agreed Hearthstone Battlegrounds patch
   36.4.2 Solos target as accurately as practical. Updates to later patches are
   separate decisions; do not silently mix newer behavior into this target.
3. Infrastructure abstractions such as action budgets and collision scheduling
   are implementation tools, not Hearthstone mechanics, and may be redesigned
   if their purpose is preserved more cleanly.
4. Any intentional deviation from the live game should be explicit and
   documented rather than silently embedded in game rules.

## Repository hygiene

- `main.py` is the canonical project entry point for the active experiment CLI.
- Special-purpose maintenance/data/training builders may live under `scripts/`.
- Obsolete prototype files are moved to `recycle_bin/` rather than deleted.
- Files under `recycle_bin/` are historical reference only and must not be
  imported by active code or collected as active tests.
