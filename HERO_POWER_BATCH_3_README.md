# Hero Power completion — replacement batch 3

This is a cumulative replacement package for the non-dependent 36.4.2 Solo
Hero Power work.

## Added content

- Ragnaros the Firelord — BUY, INSECT! and the dynamic Sulfuras replacement
  after 12 purchased cards.
- King Mukla — Bananarama automatic start-of-turn distribution.
- The previous Batch 1 and Batch 2 framework and Hero Power content remain in
  the same full replacement files.

## Verification

Python compilation and direct Bob smoke checks passed. Run the focused pytest
tests in the normal project environment:

```powershell
python -m pytest -q tests/test_ruleset_36_4_2.py tests/test_hero_power_ordinary_batch.py
```

Trinket, Buddy, Quest, Secret, Timewarp, and Darkmoon-Prize dependencies remain
deliberately deferred.
# Historical batch note

For current verified scope and limitations, see docs/hero-power-checkpoint.md.
This older note is not a full-conformance certification.
