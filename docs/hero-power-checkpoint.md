# Hero Power development checkpoint — 2026-09-06

This checkpoint supersedes completion claims in the historical batch READMEs.
The target remains 36.4.2 Solos. It is work in progress, not a certification of
all registered powers or of the complete simulator. Trinkets, Dark Gifts and
dependency-bound powers remain deferred.

## Corrections and verification

- Runtime power identity is independently owned by each player and restored in
  sampled search worlds (including Ragnaros switching to Sulfuras).
- C'Thun requires activation and consumes its armed effect on its owner's turn.
- Pyramad, Lich Bazhial and Xyrella retain the physical Tavern card and reject
  full hands before spending resources.
- Al'Akir activates the combat engine's consumable Divine Shield flag.
- Edwin and Ragnaros count both minion and Tavern-spell purchases. Focused tests
  cover Gold-paid and Health-paid spells, failed purchases and other players.
- Voone's generated plain copy does not inherit the original card's buffs.
- Tests were repaired for paid activation, Snake Eyes' 1-Gold cost, Sulfuras'
  two end-position buffs, and Pyramad's in-place card transfer.
- Hero validation checks the effective ruleset catalog and exits nonzero on
  validation errors. Missing buddies are informational, not validation errors.

Queen Wagtoggle and Captain Eudora are unavailable: neither rules nor
event handlers are installed for their retained draft functions. Wagtoggle needs spending
progression and complete type-selection semantics; Eudora needs a verified dig
cycle and reward pool accounting. Tests enforce their unavailable status.

## Remaining audit work

Other registered additions are implementation candidates, not individually
certified conformance. In particular, Malygos' full card-target coverage,
Rat King's type selection/rotation, Vashj's
Spellcraft eligibility, Discover tier constraints, complex
Battlecry targets, and history-dependent opponent search state require follow-up.
Do not infer a completed-hero percentage from the registration count.

## Focused local results

121 tests passed using Python 3.12 and CPU PyTorch 2.14.0:

```
python -m pytest -q tests/test_hero_power_ordinary_batch.py tests/test_hero_power_correction_batch.py tests/test_hero_power_search_state.py tests/test_hero_power_lifecycle.py tests/test_hero_power_direct_guard.py tests/test_hero_power_audited_batch1.py tests/test_ruleset_36_4_2.py tests/test_economy_hasty_excavation.py tests/test_hero_power_gold_gain.py tests/test_economy_primitives.py tests/test_effect_copy_isolation.py tests/test_ai_encoding.py
```

`python scripts/validate_heroes.py` passed for 121 hero definitions. That validates
catalog structure, not the number of implemented powers. No full suite,
multi-game validation, benchmark or training run was performed locally.

## Local continuation — 2026-09-07

These changes are local, subsequent to the pushed checkpoint. They are not a
certification that all independent powers are complete.

- Bazhial can steal the physical Tavern spell through the common target API;
  stale, foreign and full-hand targets are rejected before payment. Self-damage
  includes the event flag used by damage reactions.
- Vashj uses the common temporary Spellcraft grant path. Unused cards expire on
  the owner's turn end. Candidate eligibility still requires an audit.
- Deathwing is enabled with permanent combat gains mapped to each participant's
  original board. Ghosts cannot write gains to an eliminated player's board.
  Copied games remain isolated. Exotic persistence multipliers remain unaudited.
- Alexstrasza and Millificent reserve physical pool offers. Unchosen cards, and
  rewards lost to hand capacity or elimination, return to the pool. Search-world
  reconstruction accounts for the reserved cards. Candidate/tier rules remain
  subject to the pinned-ruleset audit.
- Tavern spell affordability and payment share a pure purchase-cost function.
  This is preparation for discount powers; no new discount hero is enabled.

145 focused tests passed across the hero, ruleset, economy, copy-isolation,
encoding and triple-pool regression files. A subsequent scarcity regression and
the shared cost function passed 41 focused tests covering research batches,
economy primitives, Hasty Excavation, hero Gold gains and the direct-call guard.
The larger set was not rerun after those final changes. No full suite, games,
benchmarks or training were run.

Next: audit and implement spell-discount state, unlock timing, consumption and
search restoration for the economy batch. Defer unresolved rule questions
individually and continue other independent powers. Dependency systems remain
for a later batch. Keep cumulative work local; provide replacement files only
when requested.

## Spell-purchase batch — 2026-09-07

Tae'thelan Bloodwatcher is now registered as passive. Successful Tavern spell
purchases advance a modulo-three counter; every third purchase has a quoted
cost of zero. Failed purchases, minion purchases and other players do not
advance it. Zero-cost purchases still count. Progress is owned by the runtime
power and survives observation reconstruction and deep copies. The shared
cost path also supports Health-paid spells; zero Health payments do not emit
a damage event. This interaction is tested as the literal cost-zero rule,
but is not independently certified against a live-game replay.

Observation schema is now v6, with a named spell-purchase-progress scalar.
Earlier v5 feature layouts are incompatible. Existing historical v5 notes
describe the earlier batch, not the current layout.

Evidence: Blizzard's [36.2 patch notes](https://news.blizzard.com/en-us/article/24290432/36-2-patch-notes)
change Reliquary Research from every fourth to every third Tavern spell.
The local 36.4.2 catalog agrees. This establishes the base rule, not every
cross-system interaction.

41 targeted tests passed for the new power, encoding, economy, Hero Power search
state, direct guards and Gold gains. After the zero-Health-payment correction,
10 discount and Hasty Excavation tests passed. No broad suite was run.

Othaar remains deferred: the research draft calls Arcane Knowledge automatic
and once-per-game, but its printed text alone does not establish that activation
model. Verify activation and repeatability before enabling it. Other independent
powers may proceed while that question is researched.

## Verified checkpoint — 2026-09-07

Base remote commit: `2c41196298e502fca62a25a4ddf06553a3cc1a70`, branch
`cleanup/current-architecture`. The complete current focused set passed:

```sh
python -m pytest -q tests/test_hero_power_spell_discounts.py tests/test_hero_power_research_batches.py tests/test_hero_power_ordinary_batch.py tests/test_hero_power_correction_batch.py tests/test_hero_power_search_state.py tests/test_hero_power_lifecycle.py tests/test_hero_power_direct_guard.py tests/test_hero_power_audited_batch1.py tests/test_ruleset_36_4_2.py tests/test_economy_hasty_excavation.py tests/test_hero_power_gold_gain.py tests/test_economy_primitives.py tests/test_effect_copy_isolation.py tests/test_ai_encoding.py tests/test_triple_pool_accounting.py
```

Result: **151 passed**. `python scripts/validate_heroes.py` passed for 121
definitions; missing buddies remain informational. The test environment reported
one PyTorch warning because NumPy is absent; no test failed. No full suite,
multi-game simulation, benchmark or training was run.

32 catalog heroes have registered implementations (33 rules including Sulfuras).
This is implementation coverage, not a completion or conformance certificate.
Chenvaala has not been added to this checkpoint. The next batch resumes with
its Tavern-upgrade cost primitive and play counter. Schema v6 and the limitations
listed above remain part of the checkpoint contract.
