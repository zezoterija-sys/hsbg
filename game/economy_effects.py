"""Current Battlegrounds content that exercises the economy primitives.

This module is intentionally small and rules-focused. It upgrades the legacy
Gold handlers to the current economy semantics and implements current content
whose primary mechanic is Gold/max-Gold state.
"""

from __future__ import annotations

from .economy import (
    HASTY_EXCAVATION,
    install_economy_primitives,
    install_tavern_spell_purchase_guard,
)
from .effects import EffectZone, TriggerFamily
from .events import GameEvent


CAREFUL_INVESTMENT = 103779
STRIKE_OIL = 104029
TAVERN_COIN = 104436
OVERCONFIDENCE = 105267


def _remove_named(effects, card_id: int, *names: str) -> None:
    remove = set(names)
    registrations = list(effects._effects.get(card_id, ()))
    effects._effects[card_id] = [
        registration
        for registration in registrations
        if registration.name not in remove
    ]


def _tavern_coin(ctx):
    ctx.system.add_gold(ctx.source_player_id, 1)


def _hasty_excavation(ctx):
    ctx.system.add_gold(ctx.source_player_id, 1)


def _careful_investment(ctx):
    ctx.system.queue_gold_next_turn(ctx.source_player_id, 2)


def _strike_oil(ctx):
    ctx.system.increase_max_gold(ctx.source_player_id, 1)


def _overconfidence(ctx):
    state = ctx.system.get_player_state(ctx.source_player_id)
    state["overconfidence_pending"] = int(
        state.get("overconfidence_pending", 0) or 0
    ) + 1


def _resolve_overconfidence_after_combat(effects, event):
    result = event.get("result")
    if result is None:
        return

    player_ids = {
        int(player_id)
        for player_id in (
            getattr(result, "player_a_id", None),
            getattr(result, "player_b_id", None),
        )
        if player_id is not None
    }

    for player_id in player_ids:
        state = effects.get_player_state(player_id)
        pending = max(0, int(state.pop("overconfidence_pending", 0) or 0))
        if pending <= 0:
            continue

        if bool(getattr(result, "tie", False)):
            payout = pending
        elif getattr(result, "winner_id", None) == player_id:
            payout = 3 * pending
        else:
            payout = 0

        if payout:
            effects.queue_gold_next_turn(player_id, payout)


def register_economy_effects(game) -> None:
    """Install canonical economy behavior and current economy card effects."""

    effects = game.effects
    install_economy_primitives(effects)
    install_tavern_spell_purchase_guard(game)

    if getattr(effects, "_economy_content_registered", False):
        return

    # card_effects.py predates the uncapped shop-Gold rule and clamps Tavern
    # Coin at max_gold. Replace only that stable named registration.
    _remove_named(effects, TAVERN_COIN, "Tavern Coin")
    effects.register_effect(
        TAVERN_COIN,
        GameEvent.SPELL_CAST,
        _tavern_coin,
        zones=(EffectZone.EVENT_SOURCE,),
        family=TriggerFamily.SPELL,
        name="Tavern Coin",
    )

    effects.register_effect(
        HASTY_EXCAVATION,
        GameEvent.SPELL_CAST,
        _hasty_excavation,
        zones=(EffectZone.EVENT_SOURCE,),
        family=TriggerFamily.SPELL,
        name="Hasty Excavation",
    )

    effects.register_effect(
        CAREFUL_INVESTMENT,
        GameEvent.SPELL_CAST,
        _careful_investment,
        zones=(EffectZone.EVENT_SOURCE,),
        family=TriggerFamily.SPELL,
        name="Careful Investment",
    )

    effects.register_effect(
        STRIKE_OIL,
        GameEvent.SPELL_CAST,
        _strike_oil,
        zones=(EffectZone.EVENT_SOURCE,),
        family=TriggerFamily.SPELL,
        name="Strike Oil",
    )

    effects.register_effect(
        OVERCONFIDENCE,
        GameEvent.SPELL_CAST,
        _overconfidence,
        zones=(EffectZone.EVENT_SOURCE,),
        family=TriggerFamily.SPELL,
        name="Overconfidence",
    )
    effects.events.register(
        GameEvent.COMBAT_END,
        lambda event: _resolve_overconfidence_after_combat(effects, event),
        order=0,
    )

    effects._economy_content_registered = True
