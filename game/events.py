"""
General synchronous event system for the Battlegrounds simulator.

The event layer contains no card logic.  It only announces state changes so
other systems (effects, logging, training, debugging, etc.) can react.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class GameEvent(Enum):



    
    # Game lifecycle
    GAME_START = "game_start"
    GAME_END = "game_end"

    # Hero selection
    HERO_SELECTION_START = "hero_selection_start"
    HERO_SELECTED = "hero_selected"

    # Recruit / turn lifecycle
    RECRUIT_START = "recruit_start"
    RECRUIT_END = "recruit_end"
    TURN_START = "turn_start"
    TURN_END = "turn_end"

    # Generic actions / cards
    ACTION_RESOLVED = "action_resolved"
    GOLD_SPENT = "gold_spent"
    TRIGGER_RESOLVED = "trigger_resolved"
    CARD_BOUGHT = "card_bought"
    CARD_SOLD = "card_sold"
    CARD_PLAYED = "card_played"
    CARD_GENERATED = "card_generated"
    CARD_ADDED_TO_HAND = "card_added_to_hand"
    CARD_REMOVED_FROM_HAND = "card_removed_from_hand"

    # Spells
    SPELL_BOUGHT = "spell_bought"
    SPELL_CAST = "spell_cast"

    # Tavern
    TAVERN_REFRESHED = "tavern_refreshed"
    TAVERN_CARD_APPEARED = "tavern_card_appeared"
    TAVERN_FROZEN = "tavern_frozen"
    TAVERN_UNFROZEN = "tavern_unfrozen"
    TAVERN_UPGRADED = "tavern_upgraded"

    # Trinkets
    TRINKET_GAINED = "trinket_gained"

    # Explicit mechanics / choices
    HERO_POWER_USED = "hero_power_used"
    ACTIVATE_USED = "activate_used"
    MAGNETIZED = "magnetized"
    CHOICE_STARTED = "choice_started"
    CHOICE_RESOLVED = "choice_resolved"

    # Combat phase
    COMBAT_PHASE_START = "combat_phase_start"
    COMBAT_PHASE_END = "combat_phase_end"
    COMBAT_START = "combat_start"
    COMBAT_END = "combat_end"

    # Attacking
    BEFORE_ATTACK = "before_attack"
    ATTACK = "attack"
    AFTER_ATTACK = "after_attack"

    # Minion combat state
    MINION_DAMAGED = "minion_damaged"
    DIVINE_SHIELD_LOST = "divine_shield_lost"
    STEALTH_LOST = "stealth_lost"
    MINION_DIED = "minion_died"
    DEATHRATTLE = "deathrattle"
    AFTER_MINION_DIED = "after_minion_died"
    MINION_SUMMONED = "minion_summoned"
    REBORN = "reborn"

    # Players
    PLAYER_DAMAGED = "player_damaged"
    PLAYER_ELIMINATED = "player_eliminated"


@dataclass
class Event:
    """One emitted game event."""

    sequence: int
    event_type: GameEvent
    source: Any = None
    context: dict[str, Any] = field(default_factory=dict)

    def get(self, key, default=None):
        return self.context.get(key, default)

    def __getitem__(self, key):
        return self.context[key]

    def __repr__(self):
        return f"Event(sequence={self.sequence}, type={self.event_type.value})"


EventHandler = Callable[[Event], None]


@dataclass(frozen=True)
class _HandlerRegistration:
    order: int
    registration_id: int
    handler: EventHandler


class EventDispatcher:
    """Deterministic synchronous event dispatcher."""

    def __init__(self, record_history=False):
        self.record_history = record_history
        self._handlers = {event_type: [] for event_type in GameEvent}
        self._sequence = 0
        self._next_registration_id = 1
        self._history = []

    def register(self, event_type, handler, order=0):
        if not isinstance(event_type, GameEvent):
            raise ValueError(f"Unknown event type: {event_type}")
        if not callable(handler):
            raise ValueError("Event handler must be callable.")

        registration_id = self._next_registration_id
        self._next_registration_id += 1

        registration = _HandlerRegistration(
            order=order,
            registration_id=registration_id,
            handler=handler,
        )
        handlers = self._handlers[event_type]
        handlers.append(registration)
        handlers.sort(key=lambda item: (item.order, item.registration_id))
        return registration_id

    def unregister(self, registration_id):
        for event_type in GameEvent:
            handlers = self._handlers[event_type]
            for registration in handlers.copy():
                if registration.registration_id == registration_id:
                    handlers.remove(registration)
                    return True
        return False

    def clear_handlers(self, event_type=None):
        if event_type is None:
            for handlers in self._handlers.values():
                handlers.clear()
            return

        if not isinstance(event_type, GameEvent):
            raise ValueError(f"Unknown event type: {event_type}")
        self._handlers[event_type].clear()

    def emit(self, event_type, source=None, **context):
        if not isinstance(event_type, GameEvent):
            raise ValueError(f"Unknown event type: {event_type}")

        self._sequence += 1
        event = Event(
            sequence=self._sequence,
            event_type=event_type,
            source=source,
            context=context,
        )

        if self.record_history:
            self._history.append(event)

        # Copy so handlers may register/unregister while an event is resolving.
        for registration in self._handlers[event_type].copy():
            registration.handler(event)

        return event

    def get_history(self):
        return self._history.copy()

    def clear_history(self):
        self._history.clear()

    def handler_count(self, event_type=None):
        if event_type is None:
            return sum(len(items) for items in self._handlers.values())
        return len(self._handlers[event_type])

    def __repr__(self):
        return (
            "EventDispatcher("
            f"handlers={self.handler_count()}, "
            f"sequence={self._sequence}, "
            f"record_history={self.record_history}"
            ")"
        )
