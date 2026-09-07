# Hero Power completion — replacement batch 6

This is a cumulative replacement package for the non-dependent 36.4.2 Solo
Hero Power work.

## Added content

- Deathwing — ALL Will Burn!
  - Gives all combat minions +2 Attack permanently at combat start.
- Al'Akir — Swatting Insects
  - Gives the left-most friendly combat minion Windfury, Divine Shield, and
    Taunt.
- Queen Wagtoggle — Wax Warband
  - Gives one friendly minion of each represented minion type +1/+1 at combat
    start.

The package includes complete replacement files and cumulative focused tests.
Summon-on-space and attack-immediately powers remain deferred until their exact
combat timing primitives are implemented.

## Verification

Python compilation and direct combat-event smoke checks passed. Run the focused
pytest tests in the normal project environment:

```powershell
python -m pytest -q tests/test_ruleset_36_4_2.py tests/test_hero_power_ordinary_batch.py
```
# Historical batch note

For current verified scope and limitations, see docs/hero-power-checkpoint.md.
This older note is not a full-conformance certification.
