# Effect-engine integration

Replace these files with the bundle versions:

- `game/events.py`
- `game/effects.py`
- `game/actions.py`
- `game/combat.py`

Your current `game/card_effects.py` remains compatible.

## Bob changes

Keep your existing collision API exactly as it is. Only extend the action routing and shared-system wiring.

### Imports

```python
import random

from .actions import ActionType
from .card_effects import register_card_effects
from .combat import Combat
from .effects import EffectSystem
from .events import EventDispatcher, GameEvent
```

### Shared systems in `__init__`

Use one RNG for game/effects/combat:

```python
self.seed = seed
self.random = random.Random(seed)

self.events = EventDispatcher()

self.effects = EffectSystem(
    game=self,
    events=self.events,
    rng=self.random,
)
register_card_effects(self.effects)

self.combat = Combat(
    self,
    events=self.events,
    rng=self.random,
)
```

If you add `seed=None` to `Bob.__init__`, replace `random.shuffle(...)` / `random.sample(...)` in Bob with `self.random.shuffle(...)` / `self.random.sample(...)`.

### New-game reset

Do NOT recreate `EffectSystem`; registrations should survive. Add:

```python
self.effects.reset_runtime_state_for_new_game()
self.effects.random = self.random

self.combat = Combat(
    self,
    events=self.events,
    rng=self.random,
)
```

### Resolve an action target

Add this helper:

```python
def _effect_target_from_action(self, player_id, action):
    if action.effect_target_idx is None:
        return None

    target_player_id = (
        action.effect_target_player_id
        if action.effect_target_player_id is not None
        else player_id
    )

    return self.effects.resolve_target_ref(
        target_player_id,
        action.effect_target_zone,
        action.effect_target_idx,
    )
```

### Extend your existing action dispatcher

Add these branches to your current `resolve_action` / `_resolve_action`. Do not replace the collision logic around it.

```python
elif action_type == ActionType.BUY_SPELL:
    self.buy_spell(player_id)

elif action_type == ActionType.CAST_SPELL:
    self.cast_spell(player_id, action)

elif action_type == ActionType.ACTIVATE:
    self.activate(player_id, action)

elif action_type == ActionType.CHOOSE_OPTION:
    self.effects.resolve_choice(
        player_id,
        action.option_idx,
    )
```

`CHOOSE_OPTION` costs 0 AP in the new `actions.py`, so a mandatory Discover/Choose One remains resolvable after the action that opened it spends the player's last AP.

### Tavern spell purchase

```python
def buy_spell(self, player_id):
    player = self.get_player(player_id)
    spell = player.tavern.spell

    if not isinstance(spell, dict):
        raise ValueError("Tavern has no spell to buy.")

    if len(player.hand) >= player.MAX_HAND_SIZE:
        raise ValueError("Hand is full.")

    cost = int(spell.get("manaCost", 0) or 0)
    player.spend_gold(cost)

    player.hand.append(spell)
    player.tavern.spell = None

    self.events.emit(
        GameEvent.SPELL_BOUGHT,
        player_id=player_id,
        spell=spell,
        card=spell,
        cost=cost,
    )
```

### Spell casting

```python
def cast_spell(self, player_id, action):
    player = self.get_player(player_id)
    hand_idx = action.target_idx

    if hand_idx is None or not 0 <= hand_idx < len(player.hand):
        raise ValueError("Invalid spell hand position.")

    spell = player.hand[hand_idx]
    if spell.get("cardType") != "spell":
        raise ValueError("Selected card is not a spell.")

    target_ref = self._effect_target_from_action(
        player_id,
        action,
    )

    if self.effects.has_target_rule(spell.get("id")):
        if target_ref is None:
            raise ValueError("Spell requires a target.")
    elif target_ref is not None:
        raise ValueError("Spell does not take a target.")

    player.hand.pop(hand_idx)

    self.events.emit(
        GameEvent.CARD_REMOVED_FROM_HAND,
        player_id=player_id,
        card=spell,
    )

    self.events.emit(
        GameEvent.SPELL_CAST,
        player_id=player_id,
        spell=spell,
        card=spell,
        target=(target_ref.card if target_ref else None),
        target_ref=target_ref,
    )
```

Card-specific Tavern-spell behavior registers against `GameEvent.SPELL_CAST`.

### Activate

```python
def activate(self, player_id, action):
    target_ref = self._effect_target_from_action(
        player_id,
        action,
    )

    self.effects.resolve_activate(
        player_id,
        action.target_idx,
        target_ref=target_ref,
    )
```

### Replace only the occupied-destination part of `play_minion`

After validating `hand_idx` and `position_idx` and getting `card`, use:

```python
destination = player.board[position_idx]

if destination is not None:
    if not self.effects.can_magnetize(card, destination):
        raise ValueError("Board position is occupied.")

    magnetic = player.hand.pop(hand_idx)
    self.effects.magnetize(
        magnetic,
        destination,
    )

    self.events.emit(
        GameEvent.MAGNETIZED,
        player_id=player_id,
        card=magnetic,
        minion=destination,
        target=destination,
        position=position_idx,
    )
    return

played = player.hand.pop(hand_idx)
player.board[position_idx] = played

target_ref = self._effect_target_from_action(
    player_id,
    action,
)

self.events.emit(
    GameEvent.CARD_PLAYED,
    player_id=player_id,
    card=played,
    minion=played,
    position=position_idx,
    target=(target_ref.card if target_ref else None),
    target_ref=target_ref,
)
```

Because `play_minion` currently receives separate indices instead of the full `Action`, change its signature to:

```python
def play_minion(self, player_id, action):
```

and route it with:

```python
self.play_minion(player_id, action)
```

This is necessary so a targeted Battlecry can carry both its board destination and its separate effect target.

### Hero power target

Your current hero-power method can remain a stub for hero-specific behavior, but emit the target:

```python
def use_hero_power(self, player_id, action=None):
    player = self.get_player(player_id)
    player.spend_gold(player.hero_power_cost)

    target_ref = (
        self._effect_target_from_action(player_id, action)
        if action is not None
        else None
    )

    power = None
    getter = getattr(player, "get_hero_power", None)
    if callable(getter):
        power = getter()

    self.events.emit(
        GameEvent.HERO_POWER_USED,
        player_id=player_id,
        card=power,
        target=(target_ref.card if target_ref else None),
        target_ref=target_ref,
    )
```

and route it with the whole action:

```python
self.use_hero_power(player_id, action)
```

## Recruitment changes

At the start of a recruit phase, after player resources/taverns have been prepared, emit one turn-start event for each living player in priority order:

```python
self.bob.events.emit(
    GameEvent.RECRUIT_START,
    round_number=self.bob.round_number,
)

for player_id in self.bob.priority_order:
    player = self.bob.get_player(player_id)
    if player.eliminated:
        continue

    self.bob.events.emit(
        GameEvent.TURN_START,
        player_id=player_id,
        round_number=self.bob.round_number,
    )
```

Wherever `END_TURN` is finally resolved, emit `TURN_END` immediately before `player.end_turn()`:

```python
self.bob.events.emit(
    GameEvent.TURN_END,
    player_id=player_id,
    round_number=self.bob.round_number,
)

player.end_turn()
```

End-of-turn card effects run synchronously before the player locks.

## Pool RNG

For full game determinism, make `CardPool` use the same RNG rather than module-level `random`:

```python
def __init__(self, cards_file="data/raw/cards.json", rng=None):
    ...
    self.random = rng if rng is not None else random.Random()
```

and use:

```python
self.random.choice(...)
```

instead of `random.choice(...)`.

Then construct it from Bob with:

```python
self.pool = CardPool(
    cards_file=cards_file,
    rng=self.random,
)
```

Keep your current exact-copy `pop(index)` pool behavior.

## Existing card_effects.py

Your already-tested Molten Rock / Electric Synthesizer / Humming Bird registrations remain compatible with this EffectSystem. You do not need to rewrite them before integrating this pass.
