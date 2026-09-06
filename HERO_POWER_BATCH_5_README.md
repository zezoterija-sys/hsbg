# Hero Power completion — replacement batch 5

This is a cumulative replacement package for the non-dependent 36.4.2 Solo
Hero Power work.

## Added content

- Pyramad — Brick by Brick
  - Steals a random Tavern minion.
  - Doubles its Health.
- Lich Baz'hial — Graveyard Shift
  - Targeted Tavern theft.
  - Applies the printed 2-damage cost through normal armor/Health handling.
- Xyrella — See the Light
  - Targeted Tavern theft.
  - Sets the received minion to 2/2.

These powers use the shared Tavern target references, hand-capacity handling,
and Hero Power lifecycle guard. The package contains complete replacement files
and cumulative focused tests.

## Verification

Python compilation and direct Bob smoke checks passed. Run the focused pytest
tests in the normal project environment:

```powershell
python -m pytest -q tests/test_ruleset_36_4_2.py tests/test_hero_power_ordinary_batch.py
```

Dependency-bound powers remain deferred.
# Historical batch note

For current verified scope and limitations, see docs/hero-power-checkpoint.md.
This older note is not a full-conformance certification.
