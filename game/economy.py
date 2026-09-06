"""Battlegrounds Gold/economy primitives.

This module keeps four different mechanics distinct:

- normal start-of-turn Gold progression (3, 4, ... up to a player's max Gold),
- immediate Gold gains during recruitment (which may exceed max Gold),
- permanent increases to a player's max Gold,
- deferred Gold gains/losses that resolve at the start of a later recruit turn.

The separation matters because Battlegrounds has allowed shop-phase Gold gains
to exceed 10 since Patch 24.2, while the normal start-of-turn amount is still
bounded by the player's current maximum Gold.
"""

from __future__ import annotations

from types import MethodType

from .events import GameEvent


STARTING_GOLD = 3
DEFAULT_MAX_GOLD = 10
GOLD_INCREASE_PER_TURN = 1

# Run before the legacy card_effects pending-Gold listener (-500) so old
# content that already writes ``pending_gold_next_turn`` is upgraded to the
# correct uncapped gain semantics without paying twice.
DEFERRED_GOLD_TURN_START_ORDER = -600


def normal_turn_gold(round_number: int, max_gold: int = DEFAULT_MAX_GOLD) -> int:
    """Return the normal recruit-start Gold for a round/player maximum."""

    round_number = max(1, int(round_number))
    max_gold = max(0, int(max_gold))
    progression = STARTING_GOLD + (round_number - 1) * GOLD_INCREASE_PER_TURN
    return min(progression, max_gold)


def gain_gold(player, amount: int) -> int:
    """Gain Gold immediately.

    Immediate shop-phase Gold gains are deliberately *not* capped by max_gold.
    ``max_gold`` only limits the normal amount established at the start of a
    recruit turn.
    """

    amount = max(0, int(amount or 0))
    player.gold = int(getattr(player, "gold", 0) or 0) + amount
    return amount


def lose_gold(player, amount: int) -> int:
    """Lose up to ``amount`` current Gold without going below zero."""

    amount = max(0, int(amount or 0))
    before = int(getattr(player, "gold", 0) or 0)
    lost = min(before, amount)
    player.gold = before - lost
    return lost


def increase_max_gold(player, amount: int) -> int:
    """Permanently increase the player's start-of-turn maximum Gold."""

    amount = max(0, int(amount or 0))
    current = int(getattr(player, "max_gold", DEFAULT_MAX_GOLD) or DEFAULT_MAX_GOLD)
    player.max_gold = current + amount
    return player.max_gold


def queue_gold_next_turn(effects, player_id: int, amount: int) -> int:
    """Queue an uncapped Gold gain for the player's next TURN_START."""

    amount = max(0, int(amount or 0))
    state = effects.get_player_state(player_id)
    state["pending_gold_next_turn"] = int(
        state.get("pending_gold_next_turn", 0) or 0
    ) + amount
    return state["pending_gold_next_turn"]


def queue_gold_loss_next_turn(effects, player_id: int, amount: int) -> int:
    """Queue a Gold loss for the player's next TURN_START."""

    amount = max(0, int(amount or 0))
    state = effects.get_player_state(player_id)
    state["pending_gold_loss_next_turn"] = int(
        state.get("pending_gold_loss_next_turn", 0) or 0
    ) + amount
    return state["pending_gold_loss_next_turn"]


def _resolve_deferred_gold(effects, event) -> None:
    player_id = event.get("player_id")
    if player_id is None or effects.game is None:
        return

    state = effects.get_player_state(player_id)
    gain = max(0, int(state.pop("pending_gold_next_turn", 0) or 0))
    loss = max(0, int(state.pop("pending_gold_loss_next_turn", 0) or 0))
    player = effects.game.get_player(player_id)

    if gain:
        gain_gold(player, gain)
    if loss:
        lose_gold(player, loss)


def _effect_gain_gold(self, player_id, amount):
    return gain_gold(self.game.get_player(player_id), amount)


def _effect_increase_max_gold(self, player_id, amount):
    return increase_max_gold(self.game.get_player(player_id), amount)


def _effect_queue_gold_next_turn(self, player_id, amount):
    return queue_gold_next_turn(self, player_id, amount)


def _effect_queue_gold_loss_next_turn(self, player_id, amount):
    return queue_gold_loss_next_turn(self, player_id, amount)


def install_economy_primitives(effects) -> None:
    """Install the canonical economy API on one EffectSystem instance.

    EffectSystem already exposed ``add_gold``/``add_max_gold`` compatibility
    methods before the economy model was separated.  Rebinding those instance
    methods here lets existing card handlers use the corrected semantics while
    new content can use the clearer queue/max-Gold methods directly.
    """

    if getattr(effects, "_economy_primitives_installed", False):
        return

    effects.add_gold = MethodType(_effect_gain_gold, effects)
    effects.add_max_gold = MethodType(_effect_increase_max_gold, effects)
    effects.increase_max_gold = MethodType(_effect_increase_max_gold, effects)
    effects.queue_gold_next_turn = MethodType(_effect_queue_gold_next_turn, effects)
    effects.queue_gold_loss_next_turn = MethodType(
        _effect_queue_gold_loss_next_turn,
        effects,
    )

    effects.events.register(
        GameEvent.TURN_START,
        lambda event: _resolve_deferred_gold(effects, event),
        order=DEFERRED_GOLD_TURN_START_ORDER,
    )
    effects._economy_primitives_installed = True
