# Hero Power Completion Preparation

Target branch: `cleanup/current-architecture`
Target ruleset: Hearthstone Battlegrounds patch **36.4.2 Solos** (user confirmed).
Preparation baseline: `cea9acf7dd171f2c4e65c4ce7971fdcd638afd9e`.

## Objective

Complete Hero Powers for the selected Battlegrounds ruleset without creating
separate “simple” and “complex” implementations. Simple powers are the first
content batches; every batch uses the same lifecycle, event, targeting, choice,
state, and observation contracts needed by complex powers.

The P0 RNG fix was applied in `c679e16`. This is a staged plan, not an
authoritative per-hero coverage audit. Framework hardening and the first ordinary
batch have now started; see `hero-power-ordinary-batch.md` for delivered scope,
sources, tests, and remaining limitations.

## Current baseline

- `game/hero_powers.py` provides active/passive/automatic modes, unlocks,
  per-turn and per-game limits, delayed arming, and runtime reset.
- `game/hero_power_effects.py` contains the currently audited content subset.
- `game/actions.py` exposes an active Hero Power only when its runtime rule is
  registered and currently legal; data-only powers stay unavailable.
- The repository contains 121 hero definitions. The present audited subset is
  much smaller, so the project is not yet close to complete coverage.

## Non-negotiable shared contract

Every power implementation must declare or use:

1. Printed identity, cost, mode, unlock condition, and use limits.
2. A legal-action rule, including all target and zone restrictions.
3. An effect/event handler with explicit ownership of state.
4. A deterministic random source supplied by the game/search world.
5. Turn-start, turn-end, combat, and game-start reset behavior where relevant.
6. Pending choices as first-class continuations, not hidden Python callbacks.
7. AI observation fields for visible counters, armed effects, choices, and
   currently legal actions.
8. Copy-safe state so a determinized MCTS world cannot mutate its source world.
9. A deliberate failure mode: unimplemented or ambiguous powers are not
   offered as actions.

## Complexity ladder

### Batch 0 — framework gates

Before adding large content batches, verify registration idempotence, action
legality, target validation, costs, use limits, event ordering, turn/game reset,
pending-choice continuation, RNG ownership, observation serialization, and
copy isolation. The P0 RNG patch belongs here.

### Batch 1 — ordinary direct powers

One action, one clear result, no persistent counter or discover choice. Examples
include direct keyword/stat effects and simple economy changes. These establish
the normal active/passive registration and target pipeline.

### Batch 2 — ordinary triggered/economy powers

Powers reacting to buy, sell, play, refresh, or turn events; discounts,
refunds, and simple generated cards. These establish event filters, counters,
and economy integration.

### Batch 3 — persistent counters and improving powers

Powers that track progress across turns, unlock at a threshold, increase cost,
grant extra uses, or reward once per game. Counters must be named state with
explicit reset and observation rules.

### Batch 4 — choices and discover

Single and multi-option discover, choose-one, type/tier filters, and mandatory
choice continuations. Choice generation, resolution, and cancellation must be
generic rather than hero-specific action hacks.

### Batch 5 — delayed and combat powers

Start-of-combat setup, next-combat armed effects, death/summon interactions,
combat-result history, and effects that persist until a later phase. This batch
depends on the earlier event and state contracts.

### Batch 6 — exceptional powers

Opening-sequence powers, transformations, opponent-history powers, and other
multi-step or cross-system behavior within the pinned Solos ruleset. Plan their
state and timing needs from Batch 0 onward. Duos powers are out of scope, not a
later Solos batch. Trinket/Dark Gift-dependent powers are dependency-blocked
until those systems are opened; they must not be faked to claim full coverage.

## Per-power completion gate

Do not mark a power implemented until all are present:

- authoritative text and target-ruleset interpretation;
- registered runtime rule and effect;
- legal-action and illegal-action tests;
- cost, unlock, use-limit, and state-reset tests;
- effect result tests, including empty/edge states;
- deterministic random-choice test where applicable;
- copied-world isolation test where state is involved;
- AI observation/legal-action coverage;
- real-Bob integration smoke test.

## Ordering rules

- Keep Trinkets and Dark Gifts out of this implementation sequence unless a
  Hero Power explicitly depends on them; such powers remain unavailable until
  those systems are deliberately opened.
- Do not enable a power merely because its ID exists in `heroes.py`.
- Do not use hand-written hero rankings or AI-only exceptions to compensate for
  missing engine behavior.
- If a complicated power exposes a missing generic primitive, improve that
  primitive and add a focused regression test before continuing the batch.
- Report progress as coverage by completed conformance gates, not just number
  of registered IDs.

## Confirmed scope and next preparation step

- Use 36.4.2 Solos, progressing ordinary to complex with complex cases in mind.
- Keep Trinkets and Dark Gifts paused. Their dependent powers remain blocked;
  this prevents claiming literal 100% coverage before dependencies are ready.
- Do not assume all 121 raw hero definitions belong to this target pool.
- Next: build a per-hero inventory with ID, ruleset eligibility, source of
  verified behavior, complexity batch, dependencies, runtime status, and test
  gaps. Repository text alone is not authoritative historical-patch evidence.
- Buddy, Secret, quest/reward, and special-card dependencies require explicit
  coverage assessment. Listing a power does not authorize whole new systems.

## P0 implementation notes

- Self-play and teacher generation pass the recorded seed into Bob before any
  lobby initialization.
- Search world reseeding visits game, pool, effects, combat controller, and
  combat engine in a stable order, seeding each distinct RNG object once.
- Normal Bob already shares these RNG objects; the older effects-seeding path
  therefore indirectly seeded the pool. Initialization without the recorded
  seed was the definite reproducibility defect. Separate-RNG support and
  avoiding redundant reseeding are additional hardening.
- Tests cover constructor seed forwarding, repeatable initial lobbies/shops,
  distinct seeds, copy isolation, shared/separate generators, and global RNG
  preservation. Different actions can consume randomness differently: the
  same initial seed does not promise identical games under different policies.
- Large simulations, full local suites, benchmarks, and training remain user-run.
