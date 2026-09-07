# Hero Power completion — replacement batch 7

This is a cumulative replacement package for the non-dependent 36.4.2 Solo
Hero Power work.

## Added content

- Lady Vashj — Relics of the Deep
  - Generates a random current-pool Spellcraft spell at turn start.
- Rock Master Voone — Upbeat Harmony
  - Copies the left-most hand card at the end of every third turn.

The package includes complete replacement files and cumulative focused tests.

## Verification

Python compilation and direct turn-event smoke checks passed. Run the focused
pytest tests in the normal project environment:

```powershell
python -m pytest -q tests/test_ruleset_36_4_2.py tests/test_hero_power_ordinary_batch.py
```

Dependency-bound powers remain deferred.
# Historical batch note

For current verified scope and limitations, see docs/hero-power-checkpoint.md.
This older note is not a full-conformance certification.
