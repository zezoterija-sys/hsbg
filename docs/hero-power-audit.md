# Hero Power audit — cumulative Work-chat overlay

Date: 2026-09-06

Target: current live Battlegrounds Solos (`36.4.2-solos`).

This audit was started before importing `hsbg-hero-powers-batch-3-combat.zip`.
The zip is cumulative: its `game/card_effects.py` contains the earlier Work-chat
Hero Power batches plus four newly added combat-dependent powers.

## Baseline finding: data existed; runtime behavior did not

Before the Work-chat overlays, the project already had:

- hero definitions in `game/heroes.py`, including Hero Power IDs, costs and text;
- `ActionType.HERO_POWER` and neural action encoding;
- `EffectZone.HERO_POWER` and target-rule infrastructure;
- `Bob.use_hero_power()`, Gold spending, and `GameEvent.HERO_POWER_USED`.

But `register_hero_power_effects()` on `cleanup/current-architecture` was empty.
Therefore an offered Hero Power action was **not** evidence that its specific
rules were implemented. The cumulative zip is adding genuinely new runtime
behavior, not merely duplicating an existing Hero Power effect registry.

The important problem is accuracy: the old generic action path has no common
place to enforce passive/automatic powers, unlock turns/tiers, once-per-turn or
once-per-game limits, charges, delayed combat arming, or hero-specific
availability. Several Work-chat handlers therefore implement the visible effect
while missing the lifecycle that makes the power legal.

## Cumulative overlay inventory

The zip proposes runtime registrations for 48 Hero Power IDs:

`57555, 57559, 57562, 57567, 57949, 58028, 58040, 59815, 59832, 59863,
59891, 60216, 60217, 60218, 60285, 60378, 60448, 61406, 61408, 61491,
61517, 61851, 61917, 62243, 62250, 62267, 62269, 63127, 63605, 64402,
64476, 66197, 66246, 68130, 70957, 71455, 71459, 77434, 79720, 80229,
80244, 80248, 81570, 101132, 104875, 105315, 110472, 117410`.

All 48 are new Hero Power runtime registrations relative to the branch
baseline. They must be audited individually before integration.

## Verified conformance findings so far

| Hero / Power | Current definition | Zip behavior | Audit |
|---|---|---|---|
| Drek'Thar — Frostwolf Fervor (80244) | When there is space in combat, summon a copy of the highest-Attack minion; unlocks Turn 7 | Only checks once at `COMBAT_START`; no Turn-7 gate | **Wrong lifecycle.** Fails if combat starts full and space opens later; also active before Turn 7. |
| Vanndar Stormpike — Stormpike Strength (80248) | Same pattern using highest Health; unlocks Turn 7 | Only checks once at `COMBAT_START`; no Turn-7 gate | **Wrong lifecycle.** Same failure as Drek'Thar. |
| Y'Shaarj — Embrace Your Rage (66197) | 2 Gold; Start of Combat: summon and get a minion of your Tier | Registered directly on every `COMBAT_START` | **Wrong.** It resolves every combat without first using/paying for the Hero Power. Needs recruit-phase arming that is consumed next combat. |
| Rokara — Glory of Combat (80229) | After a friendly minion kills an enemy, give it +1 Attack permanently | `MINION_DIED` uses `killer`/`killer_side`, buffs combat copy and persistent board copy | **Structurally sensible.** Add explicit enemy-death validation and focused combat tests before acceptance. |
| Captain Eudora — Buried Treasure (62250) | 1 Gold; Dig; reward after 4 digs | Generates a random Golden minion on every use | **Wrong.** Missing dig counter/reward cadence. |
| A. F. Kay — Procrastinate (59891) | Skip first two turns, then Discover one Tier 3 and one Tier 4 minion | Ordinary clickable `HERO_POWER_USED` handler after Turn 3; one mixed Tier 3/4 Discover | **Wrong.** This is an automatic opening sequence, not a normal clickable power, and it owes two separate rewards. |
| C'Thun — Saturday C'Thuns! (66246) | 1 Gold; at end of turn give +1/+1, repeating an improving number of times | Immediately buffs a chosen target +1/+1 on use | **Wrong.** Timing, random/target semantics, and improving repeat count are missing. |
| Ambassador Faelin — Expedition Plans (81570) | Skip first turn; choose Tier 6, 4 and 2 minions to receive when reaching those tiers | After Turn 1, one mixed Discover across Tiers 2/4/6 | **Wrong.** Missing opening sequence, three stored rewards and tier-triggered delivery. |
| Alexstrasza — Queen of Dragons (61517) | 1 Gold; Discover a Dragon; unlocks at Tavern Tier 4 | Handler checks Tier 4, but generic action generation can still offer/spend before Tier 4 | **Effect close, lifecycle wrong.** Unlock must be part of legality, not a post-payment no-op guard. |
| Galakrond — Galakrond's Greed (57555) | Choose a Tavern minion, then choose a higher-Tier replacement | Replaces target with a random higher-Tier pool minion | **Wrong choice semantics.** Requires a second choice rather than random replacement. |
| Shudderwock — Snicker-snack (58028) | Trigger a friendly minion's Battlecry; unlocks Turn 3 | Triggers Battlecry immediately, but has no unlock gate and target rule allows generic friendly minions | **Effect close, lifecycle/target legality incomplete.** |
| Reno Jackson — Gonna Be Rich! (60216) | Once per game, make a friendly minion Golden | Golden conversion exists | **Effect close, lifecycle wrong.** Missing once-per-game exhaustion and should not offer already-Golden invalid targets. |
| Bru'kan — Embrace the Elements (79720) | Choose an Element; call it at Start of Combat | Cycles an element automatically on each use and only stores state | **Wrong/incomplete.** Must present the actual choice and resolve the selected Element at combat. |

These findings are enough to reject wholesale application of the cumulative zip.
The code is useful as implementation material, but it must be ported through a
Hero Power lifecycle system and validated per power.

## Required generic Hero Power lifecycle layer

Before importing more handlers, the engine needs a first-class controller that
can express and enforce:

- active vs passive/automatic Hero Powers;
- implemented vs data-only powers (unimplemented powers must not be offered);
- unlock turn and/or Tavern tier;
- current Gold cost;
- normal once-per-turn use limits;
- extra uses granted by effects/buddies;
- max uses/charges per game, including once-per-game powers;
- valid-target-only action generation;
- delayed/armed effects that resolve later in combat;
- per-turn and per-game runtime state reset.

`ActionSpace` should ask this controller whether a Hero Power is currently a
legal player decision. `Bob.use_hero_power()` should revalidate and commit the
lifecycle use before emitting `HERO_POWER_USED`. Passive/automatic powers must
never be exposed as clickable actions merely because their printed cost is 0.

## Integration policy for the Work-chat zip

1. Do **not** overwrite `game/card_effects.py` with the cumulative zip.
2. Build and test the generic lifecycle layer first.
3. Port handlers individually or in small audited groups.
4. For every ported power, add a conformance test for legality plus effect.
5. Treat the branch's current hero definition/live source as authoritative over
   assumptions encoded in the zip.
6. Keep an unimplemented Hero Power unavailable rather than offering a legal
   action that silently no-ops or resolves approximately.

## Sources used in this pass

- `game/heroes.py` on `cleanup/current-architecture` for current generated power
  IDs/costs/text.
- `game/card_effects.py`, `game/actions.py`, and `game/bob.py` on the same branch
  for pre-overlay runtime behavior.
- The uploaded cumulative `hsbg-hero-powers-batch-3-combat.zip`.
- Blizzard 36.2 / Season 14 notes and current `hsbg.cards` data remain the
  external verification sources for live conformance where the generated file
  may be stale.
