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

Deathwing, Queen Wagtoggle and Captain Eudora are unavailable: neither rules nor
event handlers are installed for their retained draft functions. Deathwing
needs permanent combat-to-recruit stat transfer; Wagtoggle needs spending
progression and complete type-selection semantics; Eudora needs a verified dig
cycle and reward pool accounting. Tests enforce their unavailable status.

## Remaining audit work

Other registered additions are implementation candidates, not individually
certified conformance. In particular, Malygos' full card-target coverage,
Lich Bazhial's spell targeting, Rat King's type selection/rotation, Vashj's
Spellcraft eligibility/lifetime, Discover pool and tier constraints, complex
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
