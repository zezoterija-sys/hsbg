# Hero Power completion — replacement batch 2

This package contains complete replacement files for the second non-dependent
Hero Power batch targeting Battlegrounds 36.4.2 Solos.

## Added content

- C'Thun — Saturday C'Thuns!
  - End-of-turn random friendly-minion buffs.
  - Scaling repetitions by turn.
- Edwin VanCleef — Sharpen Blades
  - Friendly-board targeting.
  - Persistent purchase counter.
  - Improving +1/+1 after each four purchased cards.
- Snake Eyes — Lucky Roll
  - Deterministic game/search RNG d6 roll.
  - Gold gain equal to the roll.
  - Roll-length cooldown.

The package includes full replacement source files and updated focused tests.
It does not include deferred Trinket, Buddy, Quest, Secret, Timewarp, or
Darkmoon-Prize powers.

## Verification

Python compilation and direct Bob smoke checks passed during preparation.
Run the focused pytest suite in the normal project environment:

```powershell
python -m pytest -q tests/test_ruleset_36_4_2.py tests/test_hero_power_ordinary_batch.py
```
# Historical batch note

For current verified scope and limitations, see docs/hero-power-checkpoint.md.
This older note is not a full-conformance certification.
