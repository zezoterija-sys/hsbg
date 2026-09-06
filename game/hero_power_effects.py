"""Audited current Hero Power runtime content.

Only powers whose live behavior maps cleanly onto existing engine primitives
belong in this module.  More complex powers stay unregistered (and therefore
unavailable as actions) until their lifecycle/effect has a conformance test.
"""

from __future__ import annotations

from .effects import EffectZone, TargetRef
from .events import GameEvent
from .hero_powers import HeroPowerSystem


# Current power IDs from game/heroes.py.
GEORGE_BOON_OF_LIGHT = 57562
NOZDORMU_CLAIRVOYANCE = 61491
OMU_EVERBLOOM = 63605
HOGGARR_IM_THE_CAPN_NOW = 101132


def _same_player(ctx):
    return ctx.event.get("player_id") == ctx.source_player_id


def _friendly_board_targets(context):
    player = context.game.get_player(context.player_id)
    return [
        TargetRef(
            player_id=context.player_id,
            zone=EffectZone.BOARD,
            index=index,
            card=card,
        )
        for index, card in enumerate(player.board)
        if isinstance(card, dict)
    ]


def _george_boon_of_light(ctx):
    if not _same_player(ctx):
        return
    target = ctx.event.get("target")
    if isinstance(target, dict):
        ctx.grant_keyword(target, "Divine Shield")


def _nozdormu_clairvoyance(ctx):
    if not _same_player(ctx):
        return
    ctx.system.grant_free_refreshes(ctx.source_player_id, 1)


def _omu_everbloom(ctx):
    if not _same_player(ctx):
        return
    ctx.system.add_gold(ctx.source_player_id, 2)


def _hoggarr_im_the_capn_now(ctx):
    if not _same_player(ctx):
        return
    card = ctx.event.get("card") or ctx.event.get("minion")
    if isinstance(card, dict) and ctx.system.is_minion_type(card, "Pirate"):
        ctx.system.add_gold(ctx.source_player_id, 1)


def register_audited_hero_power_effects(game) -> HeroPowerSystem:
    """Register the currently audited Hero Power subset exactly once."""

    hero_powers = HeroPowerSystem.for_game(game)
    if getattr(hero_powers, "_audited_content_registered", False):
        return hero_powers

    effects = game.effects

    # George the Fallen — Boon of Light
    # 1 Gold. Give a minion Divine Shield. Normal active powers are once/turn.
    hero_powers.register_active(GEORGE_BOON_OF_LIGHT)
    effects.register_target_rule(GEORGE_BOON_OF_LIGHT, _friendly_board_targets)
    effects.register_effect(
        GEORGE_BOON_OF_LIGHT,
        GameEvent.HERO_POWER_USED,
        _george_boon_of_light,
        zones=(EffectZone.HERO_POWER,),
        name="George the Fallen — Boon of Light",
    )

    # Nozdormu — Clairvoyance
    # Automatic start-of-turn free Refresh; never a clickable action.
    hero_powers.register_automatic(NOZDORMU_CLAIRVOYANCE)
    effects.register_effect(
        NOZDORMU_CLAIRVOYANCE,
        GameEvent.TURN_START,
        _nozdormu_clairvoyance,
        zones=(EffectZone.HERO_POWER,),
        name="Nozdormu — Clairvoyance",
    )

    # Forest Warden Omu — Everbloom
    # Passive: after upgrading the Tavern, gain 2 Gold.
    hero_powers.register_passive(OMU_EVERBLOOM)
    effects.register_effect(
        OMU_EVERBLOOM,
        GameEvent.TAVERN_UPGRADED,
        _omu_everbloom,
        zones=(EffectZone.HERO_POWER,),
        name="Forest Warden Omu — Everbloom",
    )

    # Cap'n Hoggarr — I'm the Cap'n Now
    # Passive: after buying a Pirate, gain 1 Gold.
    hero_powers.register_passive(HOGGARR_IM_THE_CAPN_NOW)
    effects.register_effect(
        HOGGARR_IM_THE_CAPN_NOW,
        GameEvent.CARD_BOUGHT,
        _hoggarr_im_the_capn_now,
        zones=(EffectZone.HERO_POWER,),
        name="Cap'n Hoggarr — I'm the Cap'n Now",
    )

    hero_powers._audited_content_registered = True
    return hero_powers
