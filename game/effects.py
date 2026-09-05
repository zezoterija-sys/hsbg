"""
General executable effect framework for the Battlegrounds simulator.

This module contains mechanics infrastructure, not individual card scripts.
Card-specific behavior belongs in card_effects.py and is registered by card ID.

Supported infrastructure includes:
- deterministic event-triggered effects
- Battlecry / Deathrattle / Rally / turn / combat trigger families
- trigger multipliers (Brann/Titus-style infrastructure)
- targeted effects
- dynamic auras
- permanent and until-next-turn stat/keyword changes
- generated cards that do not touch the shared Tavern pool
- combat summons
- Spellcraft generation
- paid once-per-turn Activate abilities
- Magnetic attachment and inherited attached effects
- counters (including Avenge helper)
- pending choices / Discover / Choose One plumbing
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
import random
import re
from typing import Any, Callable, Optional

from .events import Event, EventDispatcher, GameEvent


# =============================================================
# ENUMS / SIMPLE DATA
# =============================================================


class EffectZone(Enum):
    EVENT_SOURCE = "event_source"
    BOARD = "board"
    HAND = "hand"
    TAVERN = "tavern"
    COMBAT = "combat"
    HERO_POWER = "hero_power"
    TRINKET = "trinket"


class TriggerFamily(Enum):
    OTHER = "other"
    BATTLECRY = "battlecry"
    DEATHRATTLE = "deathrattle"
    RALLY = "rally"
    START_OF_COMBAT = "start_of_combat"
    START_OF_TURN = "start_of_turn"
    END_OF_TURN = "end_of_turn"
    SPELL = "spell"
    ACTIVATE = "activate"


@dataclass(frozen=True)
class TargetRef:
    """One legal target returned by a target provider."""

    player_id: int
    zone: EffectZone
    index: int
    card: dict


@dataclass
class TargetContext:
    game: Any
    player_id: int
    source_card: dict
    source_zone: EffectZone
    action_kind: str


@dataclass
class PendingChoice:
    player_id: int
    resolver_key: str
    options: list[Any]
    kind: str = "choice"
    source_card_id: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)


EffectHandler = Callable[["EffectContext"], None]
TargetProvider = Callable[[Any], list]
ChoiceResolver = Callable[["EffectSystem", int, Any, dict[str, Any]], None]
AuraModifier = Callable[["EffectContext", dict], tuple[int, int]]
AuraTargetFilter = Callable[["EffectContext", dict], bool]


@dataclass(frozen=True)
class RegisteredEffect:
    card_id: int
    event_type: GameEvent
    handler: EffectHandler
    zones: tuple[EffectZone, ...]
    family: TriggerFamily = TriggerFamily.OTHER
    name: Optional[str] = None


@dataclass(frozen=True)
class TargetRule:
    card_id: int
    provider: TargetProvider


@dataclass(frozen=True)
class AuraDefinition:
    card_id: int
    modifier: AuraModifier
    target_filter: Optional[AuraTargetFilter] = None
    include_source: bool = False
    zones: tuple[EffectZone, ...] = (
        EffectZone.BOARD,
        EffectZone.COMBAT,
    )
    name: Optional[str] = None


@dataclass(frozen=True)
class ActivatedAbility:
    card_id: int
    cost: int
    target_provider: Optional[TargetProvider] = None
    name: Optional[str] = None


@dataclass(frozen=True)
class SpellcraftDefinition:
    card_id: int
    spell_card_id: int


@dataclass(frozen=True)
class TriggerMultiplierDefinition:
    card_id: int
    families: tuple[TriggerFamily, ...]
    extra_normal: int
    extra_golden: int
    zones: tuple[EffectZone, ...]
    condition: Optional[Callable[[Any, Event, Any], bool]] = None
    name: Optional[str] = None


@dataclass
class _EffectSource:
    """
    Internal effect source.

    card is always the physical host minion/card in the zone.  effect_state is
    either that same card or an attached Magnetic card whose effects are now
    hosted by card.
    """

    card: dict
    effect_state: dict
    effect_card_id: int
    effect_golden: bool
    player_id: Optional[int]
    position: Optional[int]
    zone: EffectZone
    side: Any = None
    identity_order: int = 0


# =============================================================
# EFFECT CONTEXT
# =============================================================


@dataclass
class EffectContext:
    system: "EffectSystem"
    event: Event
    source: dict
    effect_state: dict
    effect_card_id: int
    effect_golden: bool
    source_player_id: Optional[int]
    source_position: Optional[int]
    source_zone: EffectZone
    source_side: Any = None

    @property
    def game(self):
        return self.system.game

    @property
    def rng(self):
        return self.system.random

    @property
    def is_golden(self):
        return self.effect_golden

    def get_player(self):
        if self.game is None or self.source_player_id is None:
            return None
        return self.game.get_player(self.source_player_id)

    def buff(
        self,
        target,
        attack=0,
        health=0,
        *,
        until_next_turn=False,
    ):
        # Some Battlegrounds effects make Elementals give additional stats.
        # Apply that rider centrally so individual Elemental handlers stay
        # content-focused. Self-gains are not treated as "giving" stats.
        if (
            target is not self.source
            and self.source_player_id is not None
            and isinstance(self.effect_state, dict)
            and self.system.is_minion_type(self.effect_state, "Elemental")
            and (int(attack or 0) > 0 or int(health or 0) > 0)
        ):
            state = self.system.get_player_state(self.source_player_id)
            attack = int(attack or 0) + int(
                state.get("elemental_effect_attack_bonus", 0) or 0
            )
            health = int(health or 0) + int(
                state.get("elemental_effect_health_bonus", 0) or 0
            )

        return self.system.apply_buff(
            target,
            attack=attack,
            health=health,
            until_next_turn=until_next_turn,
        )

    def grant_keyword(self, target, keyword, *, until_next_turn=False):
        return self.system.grant_keyword(
            target,
            keyword,
            until_next_turn=until_next_turn,
        )

    def create_card(self, card_id, *, golden=False, generated=True):
        return self.system.create_card(
            card_id,
            golden=golden,
            generated=generated,
        )

    def add_to_hand(self, card_or_id, *, golden=False):
        if self.source_player_id is None:
            raise ValueError("Effect has no owning player.")
        return self.system.add_generated_to_hand(
            self.source_player_id,
            card_or_id,
            golden=golden,
        )

    def summon(self, card_or_id, count=1, *, golden=False, position=None):
        side = self.source_side or self.event.get("side")
        if side is None:
            raise ValueError("Combat summon requires a CombatSide in the event.")
        if position is None:
            position = self.event.get("death_position")
        return self.system.summon(
            side,
            card_or_id,
            count=count,
            golden=golden,
            position=position,
            event=self.event,
        )

    def random_choice(self, values):
        values = list(values)
        if not values:
            return None
        return self.rng.choice(values)

    def get_counter(self, key, default=0):
        counters = self.effect_state.setdefault("_effect_counters", {})
        return counters.get(key, default)

    def set_counter(self, key, value):
        counters = self.effect_state.setdefault("_effect_counters", {})
        counters[key] = value
        return value

    def increment_counter(self, key, amount=1):
        return self.set_counter(key, self.get_counter(key, 0) + amount)

    def player_state(self):
        if self.source_player_id is None:
            raise ValueError("Effect has no owning player.")
        return self.system.get_player_state(self.source_player_id)

    def start_choice(
        self,
        resolver_key,
        options,
        *,
        kind="choice",
        metadata=None,
    ):
        if self.source_player_id is None:
            raise ValueError("Effect has no owning player.")
        return self.system.start_choice(
            self.source_player_id,
            resolver_key,
            options,
            kind=kind,
            source_card_id=self.effect_card_id,
            metadata=metadata,
        )


# =============================================================
# EFFECT SYSTEM
# =============================================================


class EffectSystem:
    AURA_HANDLER_ORDER = 10000
    INTERNAL_TURN_START_ORDER = -10000
    INTERNAL_TURN_END_ORDER = 10000
    MAX_HAND_SIZE = 10

    def __init__(self, game=None, events=None, rng=None):
        self.game = game

        if events is not None:
            self.events = events
        elif game is not None and hasattr(game, "events"):
            self.events = game.events
        else:
            self.events = EventDispatcher()

        self.random = rng if rng is not None else random.Random(0)

        self._effects: dict[int, list[RegisteredEffect]] = {}
        self._target_rules: dict[int, TargetRule] = {}
        self._auras: dict[int, list[AuraDefinition]] = {}
        self._activated: dict[int, ActivatedAbility] = {}
        self._spellcraft: dict[int, SpellcraftDefinition] = {}
        self._trigger_multipliers: dict[int, list[TriggerMultiplierDefinition]] = {}
        self._choice_resolvers: dict[str, ChoiceResolver] = {}
        self._pending_choices: dict[int, PendingChoice] = {}
        self._player_state: dict[int, dict[str, Any]] = {}

        self._event_registrations = {}
        self._aura_event_registrations = {}

        # Generic lifecycle maintenance exists even before any cards are
        # registered.
        self.events.register(
            GameEvent.TURN_START,
            self._internal_turn_start,
            order=self.INTERNAL_TURN_START_ORDER,
        )
        self.events.register(
            GameEvent.TURN_END,
            self._internal_turn_end,
            order=self.INTERNAL_TURN_END_ORDER,
        )
        self.events.register(
            GameEvent.CARD_PLAYED,
            self._spellcraft_on_play,
            order=9000,
        )

        self.register_choice_resolver(
            "add_card_to_hand",
            self._resolve_add_card_to_hand_choice,
        )

    def _resolve_add_card_to_hand_choice(self, system, player_id, option, metadata):
        if isinstance(option, int):
            system.add_generated_to_hand(player_id, option)
        elif isinstance(option, dict):
            system.add_generated_to_hand(player_id, option)
        else:
            raise ValueError("Discover option must be a card ID or card dictionary.")

    # =========================================================
    # CARD / KEYWORD HELPERS
    # =========================================================

    def can_triple_together(self, left, right):
        """Return whether two minions may count toward the same triple.

        Normal minions require the same card ID. Elemental of Surprise can
        triple with any Elemental, matching its explicit card rule. The actual
        three-copy collection/reward flow remains owned by the player/triple
        subsystem.
        """
        if not isinstance(left, dict) or not isinstance(right, dict):
            return False
        if left.get("id") == right.get("id"):
            return True
        surprise_id = 101280
        if left.get("id") == surprise_id and self.is_minion_type(right, "Elemental"):
            return True
        if right.get("id") == surprise_id and self.is_minion_type(left, "Elemental"):
            return True
        return False

    @staticmethod
    def is_golden(card):
        if not isinstance(card, dict):
            return False
        return bool(card.get("isGolden", False) or card.get("golden", False))

    @staticmethod
    def has_keyword(card, keyword):
        if not isinstance(card, dict):
            return False
        wanted = keyword.casefold()
        return any(str(value).casefold() == wanted for value in card.get("keywords", []))

    @staticmethod
    def is_minion_type(card, minion_type):
        if not isinstance(card, dict):
            return False
        types = list(card.get("minionTypes") or [])
        if not types and card.get("minionType"):
            types = [card["minionType"]]
        wanted = minion_type.casefold()
        normalized = {str(value).casefold() for value in types}
        return wanted in normalized or "all" in normalized

    @staticmethod
    def parse_activate_cost(card):
        """Fallback parser; explicit registered costs remain authoritative."""
        text = str(card.get("text", ""))
        match = re.search(r"Activate\s*\((\d+)\)", text, flags=re.IGNORECASE)
        return int(match.group(1)) if match else None

    # =========================================================
    # CARD FACTORY / GENERATED CARDS
    # =========================================================

    def _definition_by_id(self, card_id):
        if self.game is None or not hasattr(self.game, "pool"):
            raise ValueError("Card generation requires a game with a CardPool.")

        pool = self.game.pool
        mapping = getattr(pool, "card_definitions_by_id", None)
        if mapping is not None and card_id in mapping:
            return mapping[card_id]

        for definition in getattr(pool, "card_definitions", []):
            if definition.get("id") == card_id:
                return definition

        raise KeyError(f"Unknown card ID: {card_id}")

    def create_card(self, card_id, *, golden=False, generated=True):
        """
        Create a fresh runtime card from a definition without touching the
        shared Tavern pool.
        """

        card = deepcopy(self._definition_by_id(card_id))

        if golden:
            card["isGolden"] = True
            if card.get("attackGold") is not None:
                card["attack"] = card["attackGold"]
            if card.get("healthGold") is not None:
                card["health"] = card["healthGold"]
            if card.get("textGold") is not None:
                card["text"] = card["textGold"]
        else:
            card["isGolden"] = False

        if generated:
            card["_generated"] = True

        # Definitions must never carry runtime combat state into a new copy.
        for key in list(card):
            if key.startswith("_combat_") or key.startswith("_aura_"):
                card.pop(key, None)

        return card

    def add_generated_to_hand(self, player_id, card_or_id, *, golden=False):
        player = self.game.get_player(player_id)
        if len(player.hand) >= self.MAX_HAND_SIZE:
            return None

        if isinstance(card_or_id, int):
            card = self.create_card(card_or_id, golden=golden, generated=True)
        else:
            card = deepcopy(card_or_id)
            card["_generated"] = True

        player.hand.append(card)
        self.events.emit(
            GameEvent.CARD_GENERATED,
            player_id=player_id,
            card=card,
        )
        self.events.emit(
            GameEvent.CARD_ADDED_TO_HAND,
            player_id=player_id,
            card=card,
        )
        return card

    # =========================================================
    # BUFFS / TEMPORARY MODIFIERS
    # =========================================================

    def apply_buff(self, target, *, attack=0, health=0, until_next_turn=False):
        if not isinstance(target, dict):
            raise ValueError("Buff target must be a card/minion dictionary.")

        attack = int(attack or 0)
        health = int(health or 0)

        target["attack"] = int(target.get("attack", 0) or 0) + attack
        target["health"] = int(target.get("health", 0) or 0) + health

        if until_next_turn and (attack or health):
            current_round = int(getattr(self.game, "round_number", 0) or 0)
            target.setdefault("_temporary_stat_modifiers", []).append(
                {
                    "attack": attack,
                    "health": health,
                    "expires_round": current_round + 1,
                }
            )

        return target

    def grant_keyword(self, target, keyword, *, until_next_turn=False):
        if not isinstance(target, dict):
            raise ValueError("Keyword target must be a card/minion dictionary.")

        keywords = target.setdefault("keywords", [])
        already_present = self.has_keyword(target, keyword)

        if not already_present:
            keywords.append(keyword)

        if until_next_turn:
            current_round = int(getattr(self.game, "round_number", 0) or 0)
            info = target.setdefault("_temporary_keywords", {})
            entry = info.setdefault(
                keyword,
                {
                    "original_present": already_present,
                    "expiries": [],
                },
            )
            entry["expiries"].append(current_round + 1)
        else:
            permanent = target.setdefault("_permanent_keyword_grants", [])
            if keyword not in permanent:
                permanent.append(keyword)

        return target

    def _expire_temporary_modifiers(self, card, round_number):
        if not isinstance(card, dict):
            return

        remaining = []
        for modifier in card.get("_temporary_stat_modifiers", []):
            if modifier["expires_round"] <= round_number:
                card["attack"] = int(card.get("attack", 0) or 0) - modifier["attack"]
                card["health"] = int(card.get("health", 0) or 0) - modifier["health"]
                # Recruit-phase minions are not destroyed by temporary-health
                # expiry in this representation.
                card["health"] = max(1, card["health"])
            else:
                remaining.append(modifier)
        card["_temporary_stat_modifiers"] = remaining

        temporary_keywords = card.get("_temporary_keywords", {})
        for keyword, info in list(temporary_keywords.items()):
            info["expiries"] = [
                value for value in info["expiries"] if value > round_number
            ]
            if info["expiries"]:
                continue

            permanent = keyword in card.get("_permanent_keyword_grants", set())
            if not info["original_present"] and not permanent:
                card["keywords"] = [
                    value
                    for value in card.get("keywords", [])
                    if str(value).casefold() != keyword.casefold()
                ]
            temporary_keywords.pop(keyword, None)

    def _internal_turn_start(self, event):
        player_id = event.get("player_id")
        if player_id is None or self.game is None:
            return

        player = self.game.get_player(player_id)
        round_number = int(getattr(self.game, "round_number", 0) or 0)
        self.get_player_state(player_id)["gold_spent_turn"] = 0

        for card in list(player.board) + list(player.hand):
            self._expire_temporary_modifiers(card, round_number)

        self._grant_spellcraft_for_player(player_id)

    def _internal_turn_end(self, event):
        player_id = event.get("player_id")
        if player_id is None or self.game is None:
            return

        player = self.game.get_player(player_id)
        player.hand[:] = [
            card
            for card in player.hand
            if not (
                isinstance(card, dict)
                and card.get("_spellcraft_temporary", False)
            )
        ]

    # =========================================================
    # PLAYER-SCOPED MECHANIC STATE
    # =========================================================

    def get_player_state(self, player_id):
        return self._player_state.setdefault(player_id, {})

    def spend_gold(self, player_id, amount, *, reason=None, source=None):
        """Spend Gold and emit one canonical GOLD_SPENT event."""
        amount = max(0, int(amount or 0))
        player = self.game.get_player(player_id)
        if amount <= 0:
            return 0
        player.spend_gold(amount)
        state = self.get_player_state(player_id)
        state["gold_spent_turn"] = int(state.get("gold_spent_turn", 0) or 0) + amount
        state["gold_spent_game"] = int(state.get("gold_spent_game", 0) or 0) + amount
        self.events.emit(
            GameEvent.GOLD_SPENT,
            player_id=player_id,
            amount=amount,
            reason=reason,
            source_card=source,
        )
        return amount

    def add_gold(self, player_id, amount):
        player = self.game.get_player(player_id)
        amount = max(0, int(amount or 0))
        maximum = int(getattr(player, "max_gold", 10) or 10)
        player.gold = min(maximum, int(getattr(player, "gold", 0) or 0) + amount)
        return amount

    def add_max_gold(self, player_id, amount):
        player = self.game.get_player(player_id)
        player.max_gold = int(getattr(player, "max_gold", 10) or 10) + int(amount or 0)
        return player.max_gold

    def grant_free_refreshes(self, player_id, amount):
        state = self.get_player_state(player_id)
        state["free_refreshes"] = int(state.get("free_refreshes", 0) or 0) + max(0, int(amount or 0))
        return state["free_refreshes"]

    def pay_refresh_cost(self, player_id, *, source=None):
        """Pay one Refresh, honoring free and Health-based refresh effects."""
        state = self.get_player_state(player_id)
        free = int(state.get("free_refreshes", 0) or 0)
        if free > 0:
            state["free_refreshes"] = free - 1
            return "free"

        health_refreshes = int(state.get("health_refreshes_remaining", 0) or 0)
        if health_refreshes > 0:
            state["health_refreshes_remaining"] = health_refreshes - 1
            player = self.game.get_player(player_id)
            if hasattr(player, "take_damage"):
                armor_damage, health_damage = player.take_damage(1)
            else:
                armor_damage = 0
                health_damage = 1
                player.health = max(0, int(getattr(player, "health", 0) or 0) - 1)
            self.events.emit(
                GameEvent.PLAYER_DAMAGED,
                player_id=player_id,
                amount=1,
                armor_damage=armor_damage,
                health_damage=health_damage,
                self_damage=True,
                refresh_payment=True,
                source_card=source,
            )
            return "health"

        self.spend_gold(player_id, 1, reason="refresh", source=source)
        return "gold"

    def get_sell_value(self, player_id, card):
        if isinstance(card, dict) and card.get("id") == 92406:
            player = self.game.get_player(player_id)
            if getattr(player, "last_combat_won", None) is False and not getattr(player, "last_combat_tied", False):
                return 10 if self.is_golden(card) else 5
        return 1

    def reset_runtime_state_for_new_game(self):
        """Clear game-instance state while keeping effect registrations."""
        self._pending_choices.clear()
        self._player_state.clear()

    # =========================================================
    # MAGNETIC
    # =========================================================

    def is_magnetic(self, card):
        return self.has_keyword(card, "Magnetic")

    def can_magnetize(self, source, target):
        if not self.is_magnetic(source) or not isinstance(target, dict):
            return False
        target_types = source.get("_magnetic_target_types")
        if not target_types:
            # Prosthetic Hand is the current exception: it can Magnetize to
            # either Mechs or Undead.  The metadata form above keeps future
            # exceptions content-driven.
            target_types = ("Mech", "Undead") if source.get("id") == 112364 else ("Mech",)
        return any(self.is_minion_type(target, minion_type) for minion_type in target_types)

    def magnetize(self, source, target):
        if not self.can_magnetize(source, target):
            raise ValueError("That minion cannot be Magnetized to that target.")

        target["attack"] = int(target.get("attack", 0) or 0) + int(source.get("attack", 0) or 0)
        target["health"] = int(target.get("health", 0) or 0) + int(source.get("health", 0) or 0)

        for keyword in source.get("keywords", []):
            if str(keyword).casefold() == "magnetic":
                continue
            if not self.has_keyword(target, keyword):
                target.setdefault("keywords", []).append(keyword)

        # Keep the full attached runtime object.  Its card ID, golden state,
        # counters, and registered effects remain independently discoverable,
        # while the physical host receives the stats/keywords.
        target.setdefault("_attachments", []).append(deepcopy(source))
        return target

    def _iter_effect_identities(self, card):
        """Yield (card_id, golden, effect_state, identity_order)."""
        if not isinstance(card, dict):
            return

        order = 0
        stack = [card]
        while stack:
            state = stack.pop(0)
            card_id = state.get("id")
            if isinstance(card_id, int):
                yield card_id, self.is_golden(state), state, order
                order += 1
            for attachment in state.get("_attachments", []):
                if isinstance(attachment, dict):
                    stack.append(attachment)

    # =========================================================
    # COMBAT SUMMONS
    # =========================================================

    def summon(
        self,
        side,
        card_or_id,
        *,
        count=1,
        golden=False,
        position=None,
        event=None,
    ):
        engine = event.get("engine") if event is not None else None
        if engine is None:
            raise ValueError("Combat summon requires event context containing engine.")

        summoned = []
        insert_position = position

        for _ in range(max(0, int(count))):
            if isinstance(card_or_id, int):
                card = self.create_card(card_or_id, golden=golden, generated=True)
            else:
                card = deepcopy(card_or_id)
                card["_generated"] = True

            result = engine.summon(side, card, position=insert_position)
            if result is None:
                break
            summoned.append(result)
            if insert_position is not None:
                insert_position += 1

        return summoned

    # =========================================================
    # EFFECT REGISTRATION
    # =========================================================

    def register_effect(
        self,
        card_id,
        event_type,
        handler,
        zones=(EffectZone.EVENT_SOURCE,),
        name=None,
        family=TriggerFamily.OTHER,
    ):
        if not isinstance(card_id, int):
            raise ValueError("card_id must be an integer.")
        if not isinstance(event_type, GameEvent):
            raise ValueError("event_type must be a GameEvent.")
        if not callable(handler):
            raise ValueError("Effect handler must be callable.")
        if not isinstance(family, TriggerFamily):
            raise ValueError("family must be a TriggerFamily.")

        zones = tuple(zones)
        if not zones or any(not isinstance(zone, EffectZone) for zone in zones):
            raise ValueError("Effect zones must contain EffectZone values.")

        effect = RegisteredEffect(
            card_id=card_id,
            event_type=event_type,
            handler=handler,
            zones=zones,
            family=family,
            name=name,
        )
        self._effects.setdefault(card_id, []).append(effect)
        self._ensure_event_subscription(event_type)
        return effect

    # Convenience registrations --------------------------------

    def register_battlecry(self, card_id, handler, *, name=None):
        def wrapped(ctx):
            if ctx.event.get("card") is not ctx.source:
                return False
            handler(ctx)
            return True

        return self.register_effect(
            card_id,
            GameEvent.CARD_PLAYED,
            wrapped,
            zones=(EffectZone.EVENT_SOURCE,),
            family=TriggerFamily.BATTLECRY,
            name=name,
        )

    def register_deathrattle(self, card_id, handler, *, name=None):
        def wrapped(ctx):
            if ctx.event.get("minion") is not ctx.source:
                return False
            handler(ctx)
            return True

        return self.register_effect(
            card_id,
            GameEvent.DEATHRATTLE,
            wrapped,
            zones=(EffectZone.EVENT_SOURCE,),
            family=TriggerFamily.DEATHRATTLE,
            name=name,
        )

    def register_rally(self, card_id, handler, *, name=None):
        def wrapped(ctx):
            if ctx.event.get("attacker") is not ctx.source:
                return False
            handler(ctx)
            return True

        return self.register_effect(
            card_id,
            GameEvent.ATTACK,
            wrapped,
            zones=(EffectZone.EVENT_SOURCE,),
            family=TriggerFamily.RALLY,
            name=name,
        )

    def register_start_of_combat(self, card_id, handler, *, name=None):
        return self.register_effect(
            card_id,
            GameEvent.COMBAT_START,
            handler,
            zones=(EffectZone.COMBAT,),
            family=TriggerFamily.START_OF_COMBAT,
            name=name,
        )

    def register_start_of_turn(self, card_id, handler, *, name=None):
        def wrapped(ctx):
            if ctx.event.get("player_id") != ctx.source_player_id:
                return False
            handler(ctx)
            return True

        return self.register_effect(
            card_id,
            GameEvent.TURN_START,
            wrapped,
            zones=(EffectZone.BOARD,),
            family=TriggerFamily.START_OF_TURN,
            name=name,
        )

    def register_end_of_turn(self, card_id, handler, *, name=None):
        def wrapped(ctx):
            if ctx.event.get("player_id") != ctx.source_player_id:
                return False
            handler(ctx)
            return True

        return self.register_effect(
            card_id,
            GameEvent.TURN_END,
            wrapped,
            zones=(EffectZone.BOARD,),
            family=TriggerFamily.END_OF_TURN,
            name=name,
        )

    def register_avenge(self, card_id, threshold, handler, *, name=None):
        threshold = int(threshold)
        if threshold <= 0:
            raise ValueError("Avenge threshold must be positive.")
        counter_key = f"avenge:{card_id}:{name or ''}"

        def wrapped(ctx):
            dead_side = ctx.event.get("side")
            if dead_side is None or dead_side.player_id != ctx.source_player_id:
                return False

            count = ctx.increment_counter(counter_key, 1)
            if count >= threshold:
                ctx.set_counter(counter_key, count - threshold)
                handler(ctx)
                return True
            return False

        return self.register_effect(
            card_id,
            GameEvent.MINION_DIED,
            wrapped,
            zones=(EffectZone.COMBAT,),
            family=TriggerFamily.OTHER,
            name=name,
        )

    # =========================================================
    # TARGETING
    # =========================================================

    def register_target_rule(self, card_id, provider):
        if not callable(provider):
            raise ValueError("Target provider must be callable.")
        self._target_rules[card_id] = TargetRule(card_id=card_id, provider=provider)

    def has_target_rule(self, card_id):
        return card_id in self._target_rules

    def get_valid_targets(self, card_id, context):
        rule = self._target_rules.get(card_id)
        if rule is None:
            return []
        result = rule.provider(context)
        return [] if result is None else list(result)

    def _card_for_target(self, player_id, zone, index):
        player = self.game.get_player(player_id)
        if zone == EffectZone.BOARD:
            return player.board[index]
        if zone == EffectZone.HAND:
            return player.hand[index]
        if zone == EffectZone.TAVERN:
            return player.tavern.slots[index]
        raise ValueError(f"Unsupported indexed target zone: {zone}")

    def resolve_target_ref(self, player_id, zone, index):
        if isinstance(zone, str):
            zone = EffectZone(zone)
        if not isinstance(zone, EffectZone):
            raise ValueError("Target zone must be EffectZone or its string value.")
        card = self._card_for_target(player_id, zone, index)
        return TargetRef(player_id=player_id, zone=zone, index=index, card=card)

    def get_valid_target_refs(self, card_id, context):
        refs = []
        for target in self.get_valid_targets(card_id, context):
            if isinstance(target, TargetRef):
                refs.append(target)
                continue

            if isinstance(target, int):
                refs.append(
                    TargetRef(
                        player_id=context.player_id,
                        zone=EffectZone.BOARD,
                        index=target,
                        card=self._card_for_target(
                            context.player_id,
                            EffectZone.BOARD,
                            target,
                        ),
                    )
                )
                continue

            if isinstance(target, tuple):
                if len(target) == 2 and isinstance(target[0], EffectZone):
                    zone, index = target
                    player_id = context.player_id
                elif len(target) == 3:
                    player_id, zone, index = target
                    if not isinstance(zone, EffectZone):
                        raise ValueError("Target tuple zone must be EffectZone.")
                else:
                    raise ValueError(f"Unsupported target tuple: {target}")

                refs.append(
                    TargetRef(
                        player_id=player_id,
                        zone=zone,
                        index=index,
                        card=self._card_for_target(player_id, zone, index),
                    )
                )
                continue

            raise ValueError(f"Unsupported target reference: {target!r}")

        return refs

    def get_valid_target_indices(self, card_id, context):
        """Backward-compatible helper for board-index-only effects."""
        return [target.index for target in self.get_valid_target_refs(card_id, context)]

    # =========================================================
    # ACTIVATE
    # =========================================================

    def register_activate(
        self,
        card_id,
        cost,
        handler,
        *,
        target_provider=None,
        name=None,
    ):
        cost = int(cost)
        if cost < 0:
            raise ValueError("Activate cost cannot be negative.")
        if target_provider is not None and not callable(target_provider):
            raise ValueError("Activate target_provider must be callable.")

        self._activated[card_id] = ActivatedAbility(
            card_id=card_id,
            cost=cost,
            target_provider=target_provider,
            name=name,
        )
        self.register_effect(
            card_id,
            GameEvent.ACTIVATE_USED,
            handler,
            zones=(EffectZone.EVENT_SOURCE,),
            family=TriggerFamily.ACTIVATE,
            name=name,
        )

    def get_activate_ability(self, card):
        if not isinstance(card, dict):
            return None
        return self._activated.get(card.get("id"))

    def can_activate(self, player_id, board_index):
        if self.game is None:
            return False
        player = self.game.get_player(player_id)
        if board_index < 0 or board_index >= len(player.board):
            return False
        card = player.board[board_index]
        ability = self.get_activate_ability(card)
        if ability is None:
            return False
        if card.get("_activate_used_round") == getattr(self.game, "round_number", None):
            return False
        return player.gold >= ability.cost

    def get_activate_target_refs(self, player_id, board_index):
        if not self.can_activate(player_id, board_index):
            return []
        player = self.game.get_player(player_id)
        card = player.board[board_index]
        ability = self.get_activate_ability(card)
        if ability.target_provider is None:
            return []
        context = TargetContext(
            game=self.game,
            player_id=player_id,
            source_card=card,
            source_zone=EffectZone.BOARD,
            action_kind="activate",
        )
        raw = ability.target_provider(context) or []
        # Temporarily expose the provider through the normal normalizer.
        refs = []
        for target in raw:
            if isinstance(target, TargetRef):
                refs.append(target)
            elif isinstance(target, int):
                refs.append(
                    TargetRef(
                        player_id=player_id,
                        zone=EffectZone.BOARD,
                        index=target,
                        card=self._card_for_target(player_id, EffectZone.BOARD, target),
                    )
                )
            elif isinstance(target, tuple):
                if len(target) == 2 and isinstance(target[0], EffectZone):
                    zone, index = target
                    target_player_id = player_id
                elif len(target) == 3:
                    target_player_id, zone, index = target
                else:
                    raise ValueError(f"Unsupported Activate target: {target}")
                refs.append(
                    TargetRef(
                        player_id=target_player_id,
                        zone=zone,
                        index=index,
                        card=self._card_for_target(target_player_id, zone, index),
                    )
                )
        return refs

    def get_activate_target_indices(self, player_id, board_index):
        return [target.index for target in self.get_activate_target_refs(player_id, board_index)]

    def resolve_activate(
        self,
        player_id,
        board_index,
        target_index=None,
        *,
        target_ref=None,
    ):
        if not self.can_activate(player_id, board_index):
            raise ValueError("Activate ability is not currently legal.")

        player = self.game.get_player(player_id)
        card = player.board[board_index]
        ability = self.get_activate_ability(card)
        legal_refs = self.get_activate_target_refs(player_id, board_index)

        if target_ref is None and target_index is not None:
            # Backward-compatible board target.
            target_ref = self.resolve_target_ref(
                player_id,
                EffectZone.BOARD,
                target_index,
            )

        if ability.target_provider is None:
            if target_ref is not None:
                raise ValueError("This Activate ability does not take a target.")
        else:
            legal_key_set = {
                (ref.player_id, ref.zone, ref.index)
                for ref in legal_refs
            }
            if target_ref is None or (
                target_ref.player_id,
                target_ref.zone,
                target_ref.index,
            ) not in legal_key_set:
                raise ValueError("Invalid Activate target.")

        self.spend_gold(
            player_id,
            ability.cost,
            reason="activate",
            source=card,
        )
        card["_activate_used_round"] = getattr(self.game, "round_number", 0)
        target = target_ref.card if target_ref is not None else None

        self.events.emit(
            GameEvent.ACTIVATE_USED,
            player_id=player_id,
            card=card,
            target=target,
            target_ref=target_ref,
            target_idx=(target_ref.index if target_ref is not None else None),
            board_index=board_index,
        )
        return True

    # =========================================================
    # SPELLCRAFT
    # =========================================================

    def register_spellcraft(self, card_id, spell_card_id):
        self._spellcraft[card_id] = SpellcraftDefinition(
            card_id=card_id,
            spell_card_id=spell_card_id,
        )

    def _grant_spellcraft_from_card(self, player_id, source_card):
        definition = self._spellcraft.get(source_card.get("id"))
        if definition is None:
            return None
        if len(self.game.get_player(player_id).hand) >= self.MAX_HAND_SIZE:
            return None

        spell = self.create_card(
            definition.spell_card_id,
            golden=self.is_golden(source_card),
            generated=True,
        )
        spell["_spellcraft_temporary"] = True
        spell["_spellcraft_source_id"] = source_card.get("id")
        self.game.get_player(player_id).hand.append(spell)
        self.events.emit(GameEvent.CARD_GENERATED, player_id=player_id, card=spell)
        self.events.emit(GameEvent.CARD_ADDED_TO_HAND, player_id=player_id, card=spell)
        return spell

    def _grant_spellcraft_for_player(self, player_id):
        if self.game is None:
            return
        player = self.game.get_player(player_id)
        for card in player.board:
            if isinstance(card, dict) and card.get("id") in self._spellcraft:
                self._grant_spellcraft_from_card(player_id, card)

    def _spellcraft_on_play(self, event):
        player_id = event.get("player_id")
        card = event.get("card")
        if player_id is None or not isinstance(card, dict):
            return
        if card.get("id") in self._spellcraft:
            self._grant_spellcraft_from_card(player_id, card)

    # =========================================================
    # CHOICES / DISCOVER / CHOOSE ONE
    # =========================================================

    def register_choice_resolver(self, key, resolver):
        if not isinstance(key, str) or not key:
            raise ValueError("Choice resolver key must be a non-empty string.")
        if not callable(resolver):
            raise ValueError("Choice resolver must be callable.")
        self._choice_resolvers[key] = resolver

    def start_choice(
        self,
        player_id,
        resolver_key,
        options,
        *,
        kind="choice",
        source_card_id=None,
        metadata=None,
    ):
        if player_id in self._pending_choices:
            raise ValueError("Player already has a pending choice.")
        if resolver_key not in self._choice_resolvers:
            raise KeyError(f"Unknown choice resolver: {resolver_key}")

        choice = PendingChoice(
            player_id=player_id,
            resolver_key=resolver_key,
            options=list(options),
            kind=kind,
            source_card_id=source_card_id,
            metadata=dict(metadata or {}),
        )
        if not choice.options:
            return None

        self._pending_choices[player_id] = choice
        self.events.emit(
            GameEvent.CHOICE_STARTED,
            player_id=player_id,
            choice=choice,
        )
        return choice

    def get_pending_choice(self, player_id):
        return self._pending_choices.get(player_id)

    def resolve_choice(self, player_id, option_index):
        choice = self._pending_choices.get(player_id)
        if choice is None:
            raise ValueError("Player has no pending choice.")
        if option_index < 0 or option_index >= len(choice.options):
            raise ValueError("Invalid choice option.")

        option = choice.options[option_index]
        resolver = self._choice_resolvers[choice.resolver_key]
        self._pending_choices.pop(player_id, None)

        state = self.get_player_state(player_id)
        combine = (
            choice.kind == "choose_one"
            and len(choice.options) == 2
            and int(state.get("choose_one_both_remaining", 0) or 0) > 0
        )
        if combine:
            state["choose_one_both_remaining"] -= 1
            for combined_option in choice.options:
                resolver(self, player_id, combined_option, choice.metadata)
            resolved_option = tuple(choice.options)
        else:
            resolver(self, player_id, option, choice.metadata)
            resolved_option = option

        self.events.emit(
            GameEvent.CHOICE_RESOLVED,
            player_id=player_id,
            choice=choice,
            option_index=option_index,
            option=resolved_option,
        )
        return resolved_option

    def discover_cards(
        self,
        player_id,
        candidates,
        *,
        count=3,
        resolver_key="add_card_to_hand",
        metadata=None,
    ):
        candidates = list(candidates)
        if not candidates:
            return None
        count = min(int(count), len(candidates))
        options = self.random.sample(candidates, count)
        return self.start_choice(
            player_id,
            resolver_key,
            options,
            kind="discover",
            metadata=metadata,
        )

    # =========================================================
    # TRIGGER MULTIPLIERS
    # =========================================================

    def register_trigger_multiplier(
        self,
        card_id,
        families,
        *,
        extra_normal=1,
        extra_golden=2,
        zones=(EffectZone.BOARD, EffectZone.COMBAT),
        condition=None,
        name=None,
    ):
        definition = TriggerMultiplierDefinition(
            card_id=card_id,
            families=tuple(families),
            extra_normal=int(extra_normal),
            extra_golden=int(extra_golden),
            zones=tuple(zones),
            condition=condition,
            name=name,
        )
        self._trigger_multipliers.setdefault(card_id, []).append(definition)
        return definition

    def _extra_triggers_for(self, source, family, event):
        if family == TriggerFamily.OTHER or source.player_id is None:
            return 0

        combat_events = {
            GameEvent.COMBAT_START,
            GameEvent.COMBAT_END,
            GameEvent.BEFORE_ATTACK,
            GameEvent.ATTACK,
            GameEvent.AFTER_ATTACK,
            GameEvent.MINION_DAMAGED,
            GameEvent.DIVINE_SHIELD_LOST,
            GameEvent.STEALTH_LOST,
            GameEvent.MINION_DIED,
            GameEvent.DEATHRATTLE,
            GameEvent.AFTER_MINION_DIED,
            GameEvent.MINION_SUMMONED,
            GameEvent.REBORN,
        }
        in_combat = event.event_type in combat_events

        total = 0
        for card_id, definitions in self._trigger_multipliers.items():
            for definition in definitions:
                if family not in definition.families:
                    continue

                if in_combat:
                    active_zones = tuple(
                        zone for zone in definition.zones if zone == EffectZone.COMBAT
                    )
                else:
                    active_zones = tuple(
                        zone for zone in definition.zones if zone != EffectZone.COMBAT
                    )
                if not active_zones:
                    continue

                multiplier_sources = self._find_sources(
                    card_id,
                    active_zones,
                    event,
                )
                for multiplier_source in multiplier_sources:
                    if multiplier_source.player_id != source.player_id:
                        continue
                    if not self._source_still_exists(multiplier_source):
                        continue
                    if (
                        definition.condition is not None
                        and not definition.condition(source, event, multiplier_source)
                    ):
                        continue
                    total += (
                        definition.extra_golden
                        if multiplier_source.effect_golden
                        else definition.extra_normal
                    )
        return max(0, total)

    # =========================================================
    # AURAS
    # =========================================================

    def register_aura(
        self,
        card_id,
        modifier,
        target_filter=None,
        include_source=False,
        zones=(EffectZone.BOARD, EffectZone.COMBAT),
        name=None,
    ):
        if not callable(modifier):
            raise ValueError("Aura modifier must be callable.")
        if target_filter is not None and not callable(target_filter):
            raise ValueError("Aura target_filter must be callable.")

        aura = AuraDefinition(
            card_id=card_id,
            modifier=modifier,
            target_filter=target_filter,
            include_source=include_source,
            zones=tuple(zones),
            name=name,
        )
        self._auras.setdefault(card_id, []).append(aura)
        self._ensure_aura_subscriptions()
        return aura

    def _ensure_aura_subscriptions(self):
        aura_events = (
            GameEvent.CARD_PLAYED,
            GameEvent.CARD_SOLD,
            GameEvent.MAGNETIZED,
            GameEvent.TURN_START,
            GameEvent.COMBAT_START,
            GameEvent.MINION_DIED,
            GameEvent.MINION_SUMMONED,
            GameEvent.REBORN,
            GameEvent.COMBAT_END,
        )
        for event_type in aura_events:
            if event_type in self._aura_event_registrations:
                continue
            registration_id = self.events.register(
                event_type,
                self._on_aura_event,
                order=self.AURA_HANDLER_ORDER,
            )
            self._aura_event_registrations[event_type] = registration_id

    def _on_aura_event(self, event):
        self.recompute_auras(event=event)

    @staticmethod
    def _clear_aura_bonus(card):
        attack_bonus = int(card.pop("_aura_attack_bonus", 0) or 0)
        health_bonus = int(card.pop("_aura_health_bonus", 0) or 0)
        card["attack"] = int(card.get("attack", 0) or 0) - attack_bonus
        card["health"] = int(card.get("health", 0) or 0) - health_bonus

    @staticmethod
    def _apply_aura_bonus(card, attack_bonus, health_bonus):
        attack_bonus = int(attack_bonus or 0)
        health_bonus = int(health_bonus or 0)
        card["attack"] = int(card.get("attack", 0) or 0) + attack_bonus
        card["health"] = int(card.get("health", 0) or 0) + health_bonus
        card["_aura_attack_bonus"] = attack_bonus
        card["_aura_health_bonus"] = health_bonus

    def _aura_sources_from_cards(self, cards, player_id, zone, side=None):
        sources = []
        for position, host in enumerate(cards):
            if not isinstance(host, dict):
                continue
            for card_id, golden, effect_state, identity_order in self._iter_effect_identities(host):
                for aura in self._auras.get(card_id, []):
                    if zone not in aura.zones:
                        continue
                    sources.append(
                        (
                            position,
                            identity_order,
                            _EffectSource(
                                card=host,
                                effect_state=effect_state,
                                effect_card_id=card_id,
                                effect_golden=golden,
                                player_id=player_id,
                                position=position,
                                zone=zone,
                                side=side,
                                identity_order=identity_order,
                            ),
                            aura,
                        )
                    )
        sources.sort(key=lambda item: (item[0], item[1]))
        return sources

    def _recompute_auras_on_cards(self, cards, player_id, zone, event, side=None):
        for card in cards:
            if isinstance(card, dict):
                self._clear_aura_bonus(card)

        attack_totals = {}
        health_totals = {}
        sources = self._aura_sources_from_cards(cards, player_id, zone, side=side)

        for _, _, source, aura in sources:
            ctx = self._make_context(source, event)
            for target in cards:
                if not isinstance(target, dict):
                    continue
                if target is source.card and not aura.include_source:
                    continue
                if aura.target_filter is not None and not aura.target_filter(ctx, target):
                    continue
                attack_bonus, health_bonus = aura.modifier(ctx, target)
                key = id(target)
                attack_totals[key] = attack_totals.get(key, 0) + int(attack_bonus or 0)
                health_totals[key] = health_totals.get(key, 0) + int(health_bonus or 0)

        for card in cards:
            if not isinstance(card, dict):
                continue
            key = id(card)
            self._apply_aura_bonus(
                card,
                attack_totals.get(key, 0),
                health_totals.get(key, 0),
            )

    def recompute_auras(self, event=None):
        if not self._auras:
            return

        if self.game is not None:
            for player in self.game.players:
                if getattr(player, "eliminated", False):
                    continue
                self._recompute_auras_on_cards(
                    player.board,
                    player.player_id,
                    EffectZone.BOARD,
                    event,
                )

        if event is not None:
            for side in self._get_combat_sides_from_event(event):
                self._recompute_auras_on_cards(
                    side.board,
                    side.player_id,
                    EffectZone.COMBAT,
                    event,
                    side=side,
                )

    # =========================================================
    # EVENT RESOLUTION
    # =========================================================

    def _ensure_event_subscription(self, event_type):
        if event_type in self._event_registrations:
            return
        registration_id = self.events.register(event_type, self._on_event, order=0)
        self._event_registrations[event_type] = registration_id

    def _on_event(self, event):
        candidates = []

        for card_id, effects in self._effects.items():
            for effect in effects:
                if effect.event_type != event.event_type:
                    continue
                for source in self._find_sources(card_id, effect.zones, event):
                    candidates.append((source, effect))

        candidates.sort(key=lambda item: self._source_sort_key(item[0]))

        for source, effect in candidates:
            if not self._source_still_exists(source):
                continue

            repetitions = 1 + self._extra_triggers_for(source, effect.family, event)
            for _ in range(repetitions):
                # An earlier repetition can remove the source.
                if not self._source_still_exists(source):
                    break
                handled = effect.handler(self._make_context(source, event))
                if handled is not False and effect.family != TriggerFamily.OTHER:
                    self._emit_trigger_resolved(source, effect.family, event)

    def _emit_trigger_resolved(self, source, family, original_event):
        self.events.emit(
            GameEvent.TRIGGER_RESOLVED,
            player_id=source.player_id,
            family=family,
            card=source.card,
            effect_card_id=source.effect_card_id,
            side=source.side,
            original_event=original_event,
        )

    def trigger_card_family(
        self,
        card,
        family,
        *,
        player_id,
        zone=EffectZone.EVENT_SOURCE,
        side=None,
        **context,
    ):
        """Trigger only one card's registered family without faking a play/attack/death."""
        if not isinstance(card, dict):
            return 0
        event_type = {
            TriggerFamily.BATTLECRY: GameEvent.CARD_PLAYED,
            TriggerFamily.DEATHRATTLE: GameEvent.DEATHRATTLE,
            TriggerFamily.RALLY: GameEvent.ATTACK,
            TriggerFamily.START_OF_COMBAT: GameEvent.COMBAT_START,
            TriggerFamily.START_OF_TURN: GameEvent.TURN_START,
            TriggerFamily.END_OF_TURN: GameEvent.TURN_END,
            TriggerFamily.SPELL: GameEvent.SPELL_CAST,
            TriggerFamily.ACTIVATE: GameEvent.ACTIVATE_USED,
        }.get(family)
        if event_type is None:
            return 0

        event_context = dict(context)
        event_context.setdefault("player_id", player_id)
        if family == TriggerFamily.BATTLECRY:
            event_context.setdefault("card", card)
            event_context.setdefault("minion", card)
        elif family == TriggerFamily.DEATHRATTLE:
            event_context.setdefault("minion", card)
            event_context.setdefault("side", side)
        elif family == TriggerFamily.RALLY:
            event_context.setdefault("attacker", card)
            event_context.setdefault("attacking_side", side)
            event_context.setdefault("source_side", side)
        elif family == TriggerFamily.SPELL:
            event_context.setdefault("spell", card)
            event_context.setdefault("card", card)

        synthetic = Event(
            sequence=-1,
            event_type=event_type,
            source=card,
            context=event_context,
        )

        triggered = 0
        for effect_card_id, golden, effect_state, identity_order in self._iter_effect_identities(card):
            for effect in self._effects.get(effect_card_id, []):
                if effect.family != family:
                    continue
                source = _EffectSource(
                    card=card,
                    effect_state=effect_state,
                    effect_card_id=effect_card_id,
                    effect_golden=golden,
                    player_id=player_id,
                    position=context.get("position"),
                    zone=zone,
                    side=side,
                    identity_order=identity_order,
                )
                repetitions = 1 + self._extra_triggers_for(source, family, synthetic)
                for _ in range(repetitions):
                    handled = effect.handler(self._make_context(source, synthetic))
                    if handled is False:
                        continue
                    triggered += 1
                    self._emit_trigger_resolved(source, family, synthetic)
        return triggered

    def _make_context(self, source, event):
        return EffectContext(
            system=self,
            event=event,
            source=source.card,
            effect_state=source.effect_state,
            effect_card_id=source.effect_card_id,
            effect_golden=source.effect_golden,
            source_player_id=source.player_id,
            source_position=source.position,
            source_zone=source.zone,
            source_side=source.side,
        )

    # =========================================================
    # SOURCE DISCOVERY
    # =========================================================

    def _sources_from_host(self, host, card_id, player_id, position, zone, side=None):
        sources = []
        for effect_card_id, golden, effect_state, identity_order in self._iter_effect_identities(host):
            if effect_card_id != card_id:
                continue
            sources.append(
                _EffectSource(
                    card=host,
                    effect_state=effect_state,
                    effect_card_id=effect_card_id,
                    effect_golden=golden,
                    player_id=player_id,
                    position=position,
                    zone=zone,
                    side=side,
                    identity_order=identity_order,
                )
            )
        return sources

    def _find_sources(self, card_id, zones, event):
        sources = []
        for zone in zones:
            if zone == EffectZone.EVENT_SOURCE:
                sources.extend(self._find_event_sources(card_id, event))
            elif zone == EffectZone.BOARD:
                sources.extend(self._find_board_sources(card_id))
            elif zone == EffectZone.HAND:
                sources.extend(self._find_hand_sources(card_id))
            elif zone == EffectZone.TAVERN:
                sources.extend(self._find_tavern_sources(card_id))
            elif zone == EffectZone.COMBAT:
                sources.extend(self._find_combat_sources(card_id, event))
            elif zone == EffectZone.HERO_POWER:
                sources.extend(self._find_hero_power_sources(card_id))
            elif zone == EffectZone.TRINKET:
                sources.extend(self._find_trinket_sources(card_id))

        unique = {}
        for source in sources:
            key = (
                id(source.card),
                id(source.effect_state),
                source.zone,
                source.player_id,
            )
            unique[key] = source
        return list(unique.values())

    def _event_player_id(self, event):
        player_id = event.get("player_id")
        if player_id is not None:
            return player_id
        for key in ("side", "source_side", "attacking_side", "target_side"):
            side = event.get(key)
            if side is not None and hasattr(side, "player_id"):
                return side.player_id
        return None

    def _find_event_sources(self, card_id, event):
        sources = []
        possible_keys = (
            "card",
            "minion",
            "spell",
            "attacker",
            "target",
            "source_minion",
            "original_minion",
        )
        player_id = self._event_player_id(event)

        for key in possible_keys:
            host = event.get(key)
            if not isinstance(host, dict):
                continue
            side = None
            if key in ("attacker", "source_minion"):
                side = event.get("attacking_side") or event.get("source_side") or event.get("side")
            elif key == "target":
                side = event.get("defending_side") or event.get("target_side")
            elif key in ("minion", "original_minion"):
                side = event.get("side")

            actual_player_id = player_id
            if side is not None and hasattr(side, "player_id"):
                actual_player_id = side.player_id

            sources.extend(
                self._sources_from_host(
                    host,
                    card_id,
                    actual_player_id,
                    event.get("position"),
                    EffectZone.EVENT_SOURCE,
                    side=side,
                )
            )
        return sources

    def _find_board_sources(self, card_id):
        if self.game is None:
            return []
        sources = []
        for player in self.game.players:
            if getattr(player, "eliminated", False):
                continue
            for position, host in enumerate(player.board):
                if isinstance(host, dict):
                    sources.extend(
                        self._sources_from_host(
                            host,
                            card_id,
                            player.player_id,
                            position,
                            EffectZone.BOARD,
                        )
                    )
        return sources

    def _find_hand_sources(self, card_id):
        if self.game is None:
            return []
        sources = []
        for player in self.game.players:
            if getattr(player, "eliminated", False):
                continue
            for position, host in enumerate(player.hand):
                if isinstance(host, dict):
                    sources.extend(
                        self._sources_from_host(
                            host,
                            card_id,
                            player.player_id,
                            position,
                            EffectZone.HAND,
                        )
                    )
        return sources

    def _find_tavern_sources(self, card_id):
        if self.game is None:
            return []
        sources = []
        for player in self.game.players:
            if getattr(player, "eliminated", False):
                continue
            tavern = getattr(player, "tavern", None)
            if tavern is None:
                continue
            for position, host in enumerate(tavern.slots):
                if isinstance(host, dict):
                    sources.extend(
                        self._sources_from_host(
                            host,
                            card_id,
                            player.player_id,
                            position,
                            EffectZone.TAVERN,
                        )
                    )
            spell = getattr(tavern, "spell", None)
            if isinstance(spell, dict):
                sources.extend(
                    self._sources_from_host(
                        spell,
                        card_id,
                        player.player_id,
                        None,
                        EffectZone.TAVERN,
                    )
                )
        return sources

    def _hero_power_for_player(self, player):
        getter = getattr(player, "get_hero_power", None)
        if callable(getter):
            return getter()
        hero = getattr(player, "hero", None)
        if isinstance(hero, dict):
            return hero.get("power")
        return None

    def _find_hero_power_sources(self, card_id):
        if self.game is None:
            return []
        sources = []
        for player in self.game.players:
            if getattr(player, "eliminated", False):
                continue
            power = self._hero_power_for_player(player)
            if not isinstance(power, dict):
                continue
            sources.extend(
                self._sources_from_host(
                    power,
                    card_id,
                    player.player_id,
                    None,
                    EffectZone.HERO_POWER,
                )
            )
        return sources

    def _find_trinket_sources(self, card_id):
        if self.game is None:
            return []
        sources = []
        for player in self.game.players:
            if getattr(player, "eliminated", False):
                continue
            trinkets = getattr(player, "trinkets", None)
            if trinkets is None:
                continue
            if isinstance(trinkets, dict):
                trinkets = list(trinkets.values())
            for position, trinket in enumerate(trinkets):
                if not isinstance(trinket, dict):
                    continue
                sources.extend(
                    self._sources_from_host(
                        trinket,
                        card_id,
                        player.player_id,
                        position,
                        EffectZone.TRINKET,
                    )
                )
        return sources

    def _get_combat_sides_from_event(self, event):
        possible_keys = (
            "side",
            "side_a",
            "side_b",
            "attacking_side",
            "defending_side",
            "source_side",
            "target_side",
        )
        sides = []
        seen = set()
        for key in possible_keys:
            side = event.get(key)
            if side is None or not hasattr(side, "board"):
                continue
            identity = id(side)
            if identity in seen:
                continue
            seen.add(identity)
            sides.append(side)
        return sides

    def _find_combat_sources(self, card_id, event):
        sources = []
        for side in self._get_combat_sides_from_event(event):
            for position, host in enumerate(side.board):
                if isinstance(host, dict):
                    sources.extend(
                        self._sources_from_host(
                            host,
                            card_id,
                            side.player_id,
                            position,
                            EffectZone.COMBAT,
                            side=side,
                        )
                    )
        return sources

    # =========================================================
    # ORDER / SOURCE VALIDITY
    # =========================================================

    def _priority_position(self, player_id):
        if self.game is None or player_id is None:
            return 999
        try:
            return self.game.priority_order.index(player_id)
        except ValueError:
            return 999

    def _source_sort_key(self, source):
        return (
            self._priority_position(source.player_id),
            source.position if source.position is not None else 999,
            source.identity_order,
        )

    def _source_still_exists(self, source):
        if source.zone == EffectZone.EVENT_SOURCE:
            return True

        if source.zone == EffectZone.COMBAT:
            return source.side is not None and any(
                host is source.card for host in source.side.board
            )

        if self.game is None or source.player_id is None:
            return False
        player = self.game.get_player(source.player_id)

        if source.zone == EffectZone.BOARD:
            return any(host is source.card for host in player.board)
        if source.zone == EffectZone.HAND:
            return any(host is source.card for host in player.hand)
        if source.zone == EffectZone.TAVERN:
            tavern = player.tavern
            return any(host is source.card for host in tavern.slots) or tavern.spell is source.card
        if source.zone == EffectZone.HERO_POWER:
            return self._hero_power_for_player(player) is source.card
        if source.zone == EffectZone.TRINKET:
            trinkets = getattr(player, "trinkets", None)
            if isinstance(trinkets, dict):
                trinkets = list(trinkets.values())
            return trinkets is not None and any(
                item is source.card for item in trinkets
            )
        return False

    # =========================================================
    # INFORMATION
    # =========================================================

    def get_effects_for_card(self, card_id):
        return list(self._effects.get(card_id, []))

    def get_auras_for_card(self, card_id):
        return list(self._auras.get(card_id, []))

    def registered_card_ids(self):
        return (
            set(self._effects)
            | set(self._auras)
            | set(self._target_rules)
            | set(self._activated)
            | set(self._spellcraft)
            | set(self._trigger_multipliers)
        )

    def __repr__(self):
        effect_count = sum(len(items) for items in self._effects.values())
        aura_count = sum(len(items) for items in self._auras.values())
        return (
            "EffectSystem("
            f"effects={effect_count}, "
            f"auras={aura_count}, "
            f"targets={len(self._target_rules)}, "
            f"activate={len(self._activated)}, "
            f"spellcraft={len(self._spellcraft)}"
            ")"
        )
