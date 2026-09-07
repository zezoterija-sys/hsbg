# Solos engine audit progress — 2026-09-06

Target: the existing `36.4.2-solos` ruleset. Continue on
`cleanup/current-architecture`; game fidelity and basic AI playability precede
teacher training or further ML design.

## Verified fixes in this batch

- Generated minion/spell filters retain Solos-only content and exclude Duos-only
  content. Hero offers also exclude Duos-only heroes. Patchwerk's missing armor
  field initializes to zero.
- Copied global effect callbacks and pending-choice scheduler providers bind to
  the copied world. Spell and Gift event regressions check source isolation.
- Public observations carry the actual active tribes, Gift use limits, attached
  Gift identities and visible keywords. Encoder schema is now 3; old-schema
  neural checkpoints require rebuilding, not silent reuse.
- Imagined worlds initialize the recruitment scheduler, preserve the public
  lobby pool and restore reserved Dark Discovery offers without duplicating
  copies. Opponent advancement uses scheduler eligibility and batches.
- Gift Deathrattles/Rallies grant their required keywords; history-based Gifts
  update in hand. Playing a spell from hand emits CARD_PLAYED as well as
  SPELL_CAST. Generated auto-casts do not count as hand plays.
- Lesser and Greater Trinket overrides apply to their respective tiers even
  when names coincide. Patched base stats update corresponding golden stats.
  This data correction does not implement Trinket gameplay.
- End-turn choices block the transition to combat even after budget exhaustion.
  Self-play requests actions from scheduler-eligible seats, including mandatory
  choices for otherwise finished players.
- Purchases reserve hand space before Gold-spent generation triggers.
- Recruit-phase deaths receive placements and update ghost availability.
  Repeated self-damage after lethal damage does not crash. Eliminated seats
  remain finished when later recruitment phases rebuild scheduler state.
- The full-game test driver uses actual scheduler batches and seeds Bob's engine
  RNG, not only its own action-selection RNG.

## Validation and limits

The ten-game driver passed with master seed 20260906: 253 combat rounds and
15,140 actions, including odd-survivor rounds and all eight final placements.
These are heuristic-policy stability checks, not competitive or exhaustive
rule-conformance tests. Focused regressions additionally exercise copying,
pool reservations, Gift lifecycle events, recruitment deaths, hand limits,
end-turn Discover and an imagined-world transition through combat.

Reproduce with:

```sh
python -m pytest -q
python tests/test_bob_multigame_playtest.py --games 10 --seed 20260906
```

## Remaining game work before ML experiments

- Hero-specific behavior still needs implementation and conformance tests:
  `register_hero_power_effects()` remains empty. An offered hero-power action is
  not evidence that its effect is implemented.
- Implement the Trinket selection lifecycle and active Trinket effects. Data
  presence and generic TRINKET event infrastructure do not provide these rules.
- Complete triple collection/reward behavior; the existing pair-compatibility
  helper is not a complete triple system.
- Audit all 43 Gifts against actual engine paths and interactions. Current
  rare-Gift ordering is not a verified probability model; exact unpublished
  probabilities must not be represented as known.
- Audit golden text/effects independently of stat overrides, Reborn and
  persistent-combat interactions, and all active minion/spell registrations.
- Check full hidden-information fidelity and observation sufficiency beyond
  the concrete corrections above before treating training results as meaningful.

Reference specifications checked during this audit:

- [36.4.2 patch notes](https://news.blizzard.com/en-us/article/24296231/36-4-2-patch-notes)
- [Updated Trinket rules](https://us.forums.blizzard.com/en/hearthstone/t/battlegrounds-developer-insights-updated-trinket-rules/158955)
- [Dark Gifts developer insight](https://us.forums.blizzard.com/en/hearthstone/t/battlegrounds-developer-insight-dark-gifts/163606)
- [Season 14 Trinket updates](https://us.forums.blizzard.com/en/hearthstone/t/battlegrounds-season-14-trinket-updates/163710)
