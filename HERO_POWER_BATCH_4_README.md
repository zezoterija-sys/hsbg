# Hero Power completion — replacement batch 4

This is a cumulative replacement package for the non-dependent 36.4.2 Solo
Hero Power work.

## Added content

- Malygos — Arcane Alteration
  - Two uses per turn.
  - Replaces a selected Tavern minion with a random minion of the same Tier.
  - Returns the replaced physical copy to the shared pool.
- Millificent Manastorm — Tinker
  - Unlocks at Tavern Tier 4.
  - Discovers three eligible Magnetic Mechs from the current lobby pool.

The package includes the cumulative framework and earlier Hero Power batches as
complete replacement files and updated focused tests.

## Verification

Python compilation and direct Bob smoke checks passed. Run the focused pytest
tests in the normal project environment:

```powershell
python -m pytest -q tests/test_ruleset_36_4_2.py tests/test_hero_power_ordinary_batch.py
```

Trinket, Buddy, Quest, Secret, Timewarp, and Darkmoon-Prize dependencies remain
deferred.
# Historical batch note

For current verified scope and limitations, see docs/hero-power-checkpoint.md.
This older note is not a full-conformance certification.
