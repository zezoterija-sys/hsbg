# Hero Power completion — replacement batch 1

This package contains complete replacement files for the first non-dependent
Hero Power batch targeting Battlegrounds 36.4.2 Solos.

## Included

- Repairs the generated Hero Power IDs for Rakanishu and Tavish Stormpike.
- Adds strict Hero Power ID validation.
- Adds canonical runtime Hero Power replacement/reset support to `Player`.
- Registers and tests:
  - Alexstrasza — Queen of Dragons
  - Doctor Holli'dae — Blessing of the Nine Frogs
  - Skycap'n Kragg — Piggy Bank

## Replacement

Extract the package over the project root and overwrite the files at the same
relative paths. Do not commit the ZIP's line-ending-only changes from the
uploaded project archive.

## Verification

The batch was verified with Python compilation and direct Bob smoke checks.
The local runtime used for preparation did not have `pytest` installed, so the
pytest suite should be run in the user's normal project environment:

```powershell
python -m pytest -q tests/test_ruleset_36_4_2.py tests/test_hero_power_ordinary_batch.py
```

Dependency-bound Hero Powers remain deliberately unregistered in this batch.
# Historical batch note

For current verified scope and limitations, see docs/hero-power-checkpoint.md.
This older note is not a full-conformance certification.
