"""Hero Power lifecycle and legality for Battlegrounds.

Hero definitions contain printed data (id, cost, text). This module owns the
runtime lifecycle that decides whether a Hero Power is an actual player action.

A power is deliberately unavailable until its runtime implementation registers
one :class:`HeroPowerRule`. This prevents data-only/passive powers from being
silently exposed as clickable no-op actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from .events import GameEvent


class HeroPowerMode(str, Enum):
    ACTIVE = "active"
    PASSIVE = "passive"
    AUTOMATIC = "automatic"


HeroPowerCondition = Callable[[Any, Any], bool]


@dataclass(frozen=True)
class HeroPowerRule:
    """Machine-readable lifecycle rules for one implemented Hero Power."""

    power_id: int
    mode: HeroPowerMode = HeroPowerMode.ACTIVE
    unlock_turn: int | None = None
    unlock_tavern_tier: int | None = None
    max_uses_per_turn: int | None = 1
    max_uses_per_game: int | None = None
    condition: HeroPowerCondition | None = None

    def __post_init__(self):
        if not isinstance(self.power_id, int):
            raise ValueError("Hero Power id must be an integer.")
        if self.unlock_turn is not None and int(self.unlock_turn) < 1:
            raise ValueError("Hero Power unlock turn must be positive.")
        if self.unlock_tavern_tier is not None and not 1 <= int(self.unlock_tavern_tier) <= 6:
            raise ValueError("Hero Power unlock Tavern tier must be between 1 and 6.")
        if self.max_uses_per_turn is not None and int(self.max_uses_per_turn) < 1:
            raise ValueError("Hero Power per-turn use limit must be positive or None.")
        if self.max_uses_per_game is not None and int(self.max_uses_per_game) < 1:
            raise ValueError("Hero Power per-game use limit must be positive or None.")


class HeroPowerSystem:
    """Runtime lifecycle controller for implemented Hero Powers.

    Content handlers remain in the normal EffectSystem. This object only owns
    legality/lifecycle state: active/passive mode, unlocks, use limits and
    delayed-effect arming.
    """

    ATTRIBUTE_NAME = "hero_powers"

    def __init__(self, game):
        self.game = game
        self._rules: dict[int, HeroPowerRule] = {}
        self._uses_game: dict[int, int] = {}
        self._uses_turn: dict[int, tuple[int, int]] = {}
        self._extra_uses_turn: dict[int, tuple[int, int]] = {}
        self._armed: dict[int, dict[str, Any]] = {}
        self._event_registration_ids: list[int] = []
        self._bind_events()

    @classmethod
    def for_game(cls, game):
        """Return/create the one HeroPowerSystem attached to a game.

        The small audited current-content registry is attached here as well as
        from normal Recruitment startup. This matters for MCTS/public-template
        Bobs, which intentionally reconstruct a recruit state without calling
        ``initialize_game()`` or ``Recruitment.start()`` for the current turn.
        """

        current = getattr(game, cls.ATTRIBUTE_NAME, None)
        if isinstance(current, cls):
            # The direct-call guard is intentionally installed lazily with the
            # lifecycle system so normal Bob, tests, and MCTS template worlds
            # all get the same legality enforcement without changing Bob's
            # core routing implementation.
            from .hero_power_guard import install_hero_power_use_guard

            install_hero_power_use_guard(game)
            return current

        system = cls(game)
        setattr(game, cls.ATTRIBUTE_NAME, system)

        # Local imports avoid module-import cycles. The content registry calls
        # for_game() again, which now returns the attached system and performs
        # one idempotent registration pass.
        from .hero_power_effects import register_audited_hero_power_effects
        from .hero_power_guard import install_hero_power_use_guard

        install_hero_power_use_guard(game)
        register_audited_hero_power_effects(game)
        return system

    def _bind_events(self):
        events = getattr(self.game, "events", None)
        if events is None or not hasattr(events, "register"):
            return
        self._event_registration_ids.append(
            events.register(GameEvent.GAME_START, self._on_game_start, order=-9000)
        )
        self._event_registration_ids.append(
            events.register(GameEvent.HERO_POWER_USED, self._on_hero_power_used, order=-9000)
        )

    def _on_game_start(self, event):
        self.reset_runtime_state()

    def _on_hero_power_used(self, event):
        player_id = event.get("player_id")
        if player_id is None:
            return
        rule = self.rule_for_player(player_id)
        if rule is None or rule.mode is not HeroPowerMode.ACTIVE:
            return
        self.record_use(player_id)

    # -----------------------------------------------------------------
    # Registration
    # -----------------------------------------------------------------

    def register(self, rule: HeroPowerRule, *, replace=False):
        if not isinstance(rule, HeroPowerRule):
            raise ValueError("Hero Power registration requires HeroPowerRule.")
        if rule.power_id in self._rules and not replace:
            raise ValueError(f"Hero Power {rule.power_id} is already registered.")
        self._rules[rule.power_id] = rule
        return rule

    def register_active(
        self,
        power_id,
        *,
        unlock_turn=None,
        unlock_tavern_tier=None,
        max_uses_per_turn=1,
        max_uses_per_game=None,
        condition=None,
        replace=False,
    ):
        return self.register(
            HeroPowerRule(
                power_id=int(power_id),
                mode=HeroPowerMode.ACTIVE,
                unlock_turn=unlock_turn,
                unlock_tavern_tier=unlock_tavern_tier,
                max_uses_per_turn=max_uses_per_turn,
                max_uses_per_game=max_uses_per_game,
                condition=condition,
            ),
            replace=replace,
        )

    def register_passive(self, power_id, *, condition=None, replace=False):
        return self.register(
            HeroPowerRule(
                power_id=int(power_id),
                mode=HeroPowerMode.PASSIVE,
                max_uses_per_turn=None,
                condition=condition,
            ),
            replace=replace,
        )

    def register_automatic(self, power_id, *, condition=None, replace=False):
        return self.register(
            HeroPowerRule(
                power_id=int(power_id),
                mode=HeroPowerMode.AUTOMATIC,
                max_uses_per_turn=None,
                condition=condition,
            ),
            replace=replace,
        )

    def get_rule(self, power_id):
        try:
            numeric = int(power_id)
        except (TypeError, ValueError):
            return None
        return self._rules.get(numeric)

    def registered_power_ids(self):
        return set(self._rules)

    # -----------------------------------------------------------------
    # Player / printed data helpers
    # -----------------------------------------------------------------

    def _player(self, player_id):
        return self.game.get_player(player_id)

    @staticmethod
    def _power(player):
        getter = getattr(player, "get_hero_power", None)
        power = getter() if callable(getter) else None
        return power if isinstance(power, dict) else None

    def power_id_for_player(self, player_id):
        power = self._power(self._player(player_id))
        if power is None:
            return None
        power_id = power.get("id")
        return power_id if isinstance(power_id, int) else None

    def rule_for_player(self, player_id):
        power_id = self.power_id_for_player(player_id)
        return self.get_rule(power_id)

    # -----------------------------------------------------------------
    # Turn/game state
    # -----------------------------------------------------------------

    def _round_number(self):
        return int(getattr(self.game, "round_number", 0) or 0)

    def uses_this_game(self, player_id):
        return int(self._uses_game.get(int(player_id), 0) or 0)

    def uses_this_turn(self, player_id):
        player_id = int(player_id)
        round_number = self._round_number()
        stored_round, count = self._uses_turn.get(player_id, (round_number, 0))
        return int(count or 0) if stored_round == round_number else 0

    def extra_uses_this_turn(self, player_id):
        player_id = int(player_id)
        round_number = self._round_number()
        stored_round, count = self._extra_uses_turn.get(player_id, (round_number, 0))
        return int(count or 0) if stored_round == round_number else 0

    def grant_extra_uses(self, player_id, amount=1):
        amount = int(amount)
        if amount < 0:
            raise ValueError("Extra Hero Power uses cannot be negative.")
        player_id = int(player_id)
        round_number = self._round_number()
        current = self.extra_uses_this_turn(player_id)
        self._extra_uses_turn[player_id] = (round_number, current + amount)
        return current + amount

    def _per_turn_limit(self, player_id, rule):
        if rule.max_uses_per_turn is None:
            return None
        return int(rule.max_uses_per_turn) + self.extra_uses_this_turn(player_id)

    # -----------------------------------------------------------------
    # Legality / use commitment
    # -----------------------------------------------------------------

    def can_use(self, player_id):
        if getattr(self.game, "phase", None) != "recruit":
            return False

        player = self._player(player_id)
        if getattr(player, "eliminated", False):
            return False

        power = self._power(player)
        if power is None:
            return False

        rule = self.get_rule(power.get("id"))
        if rule is None or rule.mode is not HeroPowerMode.ACTIVE:
            return False

        round_number = self._round_number()
        if rule.unlock_turn is not None and round_number < int(rule.unlock_turn):
            return False

        tavern_tier = int(getattr(player, "tavern_tier", 1) or 1)
        if (
            rule.unlock_tavern_tier is not None
            and tavern_tier < int(rule.unlock_tavern_tier)
        ):
            return False

        cost = int(getattr(player, "hero_power_cost", power.get("cost", 0)) or 0)
        if int(getattr(player, "gold", 0) or 0) < cost:
            return False

        per_turn_limit = self._per_turn_limit(player_id, rule)
        if per_turn_limit is not None and self.uses_this_turn(player_id) >= per_turn_limit:
            return False

        if (
            rule.max_uses_per_game is not None
            and self.uses_this_game(player_id) >= int(rule.max_uses_per_game)
        ):
            return False

        if rule.condition is not None and not bool(rule.condition(self.game, player)):
            return False

        return True

    def validate_use(self, player_id):
        if not self.can_use(player_id):
            power_id = self.power_id_for_player(player_id)
            raise ValueError(f"Hero Power {power_id} is not currently usable.")
        return True

    def record_use(self, player_id):
        """Record one active Hero Power use emitted by the game."""

        player_id = int(player_id)
        round_number = self._round_number()
        count = self.uses_this_turn(player_id) + 1
        self._uses_turn[player_id] = (round_number, count)
        self._uses_game[player_id] = self.uses_this_game(player_id) + 1
        return count

    # -----------------------------------------------------------------
    # Generic delayed-effect arming
    # -----------------------------------------------------------------

    def arm(self, player_id, key, value=True):
        if not isinstance(key, str) or not key:
            raise ValueError("Hero Power arm key must be a non-empty string.")
        state = self._armed.setdefault(int(player_id), {})
        state[key] = value
        return value

    def is_armed(self, player_id, key):
        return key in self._armed.get(int(player_id), {})

    def peek_arm(self, player_id, key, default=None):
        return self._armed.get(int(player_id), {}).get(key, default)

    def consume_arm(self, player_id, key, default=None):
        state = self._armed.get(int(player_id), {})
        value = state.pop(key, default)
        if not state:
            self._armed.pop(int(player_id), None)
        return value

    def clear_arms(self, player_id=None):
        if player_id is None:
            self._armed.clear()
        else:
            self._armed.pop(int(player_id), None)

    # -----------------------------------------------------------------
    # New-game reset
    # -----------------------------------------------------------------

    def reset_runtime_state(self):
        """Clear per-game state while preserving registered content rules."""

        self._uses_game.clear()
        self._uses_turn.clear()
        self._extra_uses_turn.clear()
        self._armed.clear()
