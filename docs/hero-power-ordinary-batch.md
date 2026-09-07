# Hero Powers: first ordinary batch

Target: 36.4.2 Solos. Base: `c679e163f20fb2198866ea595532e9f216c92873`.
This is a bounded first batch, not completion of all ordinary or complex powers.

## Content delivered

| Hero | Power ID | Implementation |
|---|---|---|
| Death Speaker Blackthorn | 71459 | Bloodbound costs 1 Gold, generates two Blood Gems, twice per turn. Uses existing generated-card and hand-capacity behavior. |
| The Lich King | 58040 | Reborn Rites targets a friendly board minion, costs 0, once per turn. Grants Reborn until next turn through the existing temporary-keyword system. Native Reborn survives expiry. |
| Patchwerk | 59399 | Explicit passive registration and regression coverage. Starting 60 Health already comes from Player.set_hero; do not add another 30. |

The runtime registry now contains 12 powers, up from 9. Two have new effect
handlers; Patchwerk's pre-existing health behavior is now explicitly classified.
This count is not a percentage of the valid 36.4.2 hero pool or proof of total
mechanic coverage. All other unsupported powers stay unregistered.

## Rule evidence

Reviewed 2026-09-06. The repository definitions agree with these Blizzard sources:

- Blackthorn: [26.6 patch notes](https://news.blizzard.com/en-us/article/23973115/26-6-patch-notes)
  establish the 1-Gold/two-Gem/twice-per-turn redesign; the
  [card-library listing](https://hearthstone.blizzard.com/en-us/battlegrounds/71458-death-speaker-blackthorn?textFilter=%D0%92%D0%B5%D1%81%D1%82%D0%BD%D0%B8%D0%BA+%D1%81%D0%BC%D0%B5%D1%80%D1%82%D0%B8)
  corroborates the effect and use limit.
- Lich King: [Reborn Rites](https://playhearthstone.com/en-us/cards/58040-reborn-rites/)
  gives the expiry text; [18.0.2 notes](https://news.blizzard.com/en-us/article/23494815/18-0-2-patch-notes)
  establish its zero cost. [16.6 notes](https://playhearthstone.com/en-us/blog/23319440/)
  establish targeted friendly-minion behavior.
- Patchwerk: [29.2 notes](https://news.blizzard.com/en-us/article/24077473/29-2-patch-notes)
  establish 30 extra starting Health; the
  [card-library listing](https://hearthstone.blizzard.com/en-sg/battlegrounds/59397-patchwerk?textFilter=%E3%83%91%E3%83%83%E3%83%81%E3%82%A6%E3%82%A1%E3%83%BC%E3%82%AF)
  agrees.

Live library listings are corroboration, not immutable historical snapshots.
The frozen repository texts plus these sources define this batch's explicit
contract. Exact eligibility of all raw heroes still needs a complete inventory.

## Framework fixes

- Install the existing Hero Power registry/guard at Bob construction, so direct
  calls cannot execute an unregistered no-op power before action generation.
- Reject active powers during mandatory pending choices and after game over.
- Export/restore only the root player's own use counts, extra uses, and armed
  state. Search previously restored cost but lost lifecycle state, permitting
  extra simulated uses. Never copy real opponents' private state into search.
- Snapshot/restore deep-copies mutable state without replaying events, paying
  costs again, or copying handlers/RNGs. Restore validates identity and counts.
- Keep scheduler eligibility at the action broker: it commits budget before
  effect resolution, so the final legal budget unit must still execute.

## AI and compatibility

OwnPlayerView now carries hero_power_state. ObservationEncoder schema **v5**
adds own turn/game use counts and extra turn uses. Existing trainer validation
rejects v4 checkpoints. Old data/checkpoints are not migrated in this batch;
regenerate incompatible caches/models when training is resumed.

Armed state is owner-visible data only. Future handlers must use stable target
descriptors and purpose-built choice resolvers, not captured objects/callbacks.
Complex arm payloads have not yet been assigned neural features; do that when
their powers are implemented. Opponent hidden counters remain a belief-model
problem, not something to fetch from the real game. Multiple simultaneous or
replaced Hero Powers are not implemented by this single-power lifecycle.

## Focused verification

Run these small suites (no full games or training):

```sh
python -m pytest -q tests/test_hero_power_ordinary_batch.py tests/test_hero_power_search_state.py tests/test_hero_power_lifecycle.py tests/test_hero_power_direct_guard.py tests/test_hero_power_audited_batch1.py tests/test_hero_power_gold_gain.py tests/test_ai_encoding.py tests/test_public_lobby_observation.py tests/test_effect_copy_isolation.py
```

Coverage includes Gold/use limits, partial/full hands, generated Gem casting,
target rejection before mutation, temporary/native Reborn, combat-copy keyword
presence, final-budget execution, registration idempotence, new-game resets,
state validation, observation encoding, and independent reconstructed worlds.

## Next

Finish the per-hero eligibility/dependency inventory and expand ordinary powers
whose supporting effects are verified. Complex powers still need combat timing,
multi-step choices, changed-power state, and content-specific conformance tests.
Trinkets and Dark Gifts remain paused; no new behavior for either is included.
