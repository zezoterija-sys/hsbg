"""Audited current Hero Power runtime content.

Only powers whose live behavior maps cleanly onto existing engine primitives
belong in this module. More complex powers stay unregistered (and therefore
unavailable as actions) until their lifecycle/effect has a conformance test.
"""

from __future__ import annotations

from .effects import EffectZone, TargetRef
from .events import GameEvent
from .hero_powers import HeroPowerSystem
from .lobby import is_minion_available_for_lobby


# Current power IDs from game/heroes.py.
GEORGE_BOON_OF_LIGHT = 57562
DINOTAMER_BRANN_BATTLE_BRAND = 60218
FLURGL_GONE_FISHING = 60448
NOZDORMU_CLAIRVOYANCE = 61491
KAELTHAS_VERDANT_SPHERES = 61917
OMU_EVERBLOOM = 63605
HOGGARR_IM_THE_CAPN_NOW = 101132

# Generated reward IDs.
TAVERN_COIN = 104436
BRANN_BRONZEBEARD = 96786


def _same_player(ctx):
    return ctx.event.get("player_id") == ctx.source_player_id


def _gain_gold(ctx, amount):
    """Gain shop-phase Gold without applying the 10-Gold start-turn ceiling.

    Battlegrounds has allowed earned Gold to exceed 10 since Patch 24.2. The
    player's ``max_gold`` value is the normal start-of-turn economy ceiling, not
    a cap on Gold gained during recruitment.
    """

    player = ctx.game.get_player(ctx.source_player_id)
    amount = max(0, int(amount or 0))
    player.gold = int(getattr(player, "gold", 0) or 0) + amount
    return amount


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


def _generated_lobby_minions(system, *, minion_type=None):
    game = system.game
    result = []
    for card in getattr(game.pool, "card_definitions", ()):
        if card.get("cardType") != "minion":
            continue
        if card.get("pool") is not True:
            continue
        if "tavern" not in (card.get("categories") or []):
            continue
        if card.get("isDuosOnly", False):
            continue
        if not is_minion_available_for_lobby(card, game.active_minion_types):
            continue
        if minion_type is not None and not system.is_minion_type(card, minion_type):
            continue
        result.append(card)
    return result


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
    _gain_gold(ctx, 2)


def _hoggarr_im_the_capn_now(ctx):
    if not _same_player(ctx):
        return
    card = ctx.event.get("card") or ctx.event.get("minion")
    if isinstance(card, dict) and ctx.system.is_minion_type(card, "Pirate"):
        _gain_gold(ctx, 1)


def _flurgl_gone_fishing(ctx):
    if not _same_player(ctx):
        return

    state = ctx.system.get_player_state(ctx.source_player_id)
    sells = int(state.get("hero_flurgl_sells", 0) or 0) + 1
    if sells < 5:
        state["hero_flurgl_sells"] = sells
        return

    state["hero_flurgl_sells"] = 0
    candidates = _generated_lobby_minions(ctx.system, minion_type="Murloc")
    if candidates:
        chosen = ctx.random_choice(candidates)
        ctx.system.add_generated_to_hand(ctx.source_player_id, chosen["id"])


def _kaelthas_verdant_spheres(ctx):
    if not _same_player(ctx):
        return

    card = ctx.event.get("card") or ctx.event.get("minion")
    if not isinstance(card, dict) or card.get("cardType") != "minion":
        return

    state = ctx.system.get_player_state(ctx.source_player_id)
    buys = int(state.get("hero_kaelthas_minion_buys", 0) or 0) + 1
    if buys >= 3:
        buys = 0
        ctx.system.add_generated_to_hand(ctx.source_player_id, TAVERN_COIN)
    state["hero_kaelthas_minion_buys"] = buys


def _dinotamer_brann_battle_brand(ctx):
    if not _same_player(ctx):
        return

    state = ctx.system.get_player_state(ctx.source_player_id)
    if state.get("hero_brann_battle_brand_rewarded", False):
        return

    card = ctx.event.get("card") or ctx.event.get("minion")
    if not isinstance(card, dict) or not ctx.system.has_keyword(card, "Battlecry"):
        return

    buys = int(state.get("hero_brann_battlecry_buys", 0) or 0) + 1
    state["hero_brann_battlecry_buys"] = buys
    if buys < 4:
        return

    state["hero_brann_battle_brand_rewarded"] = True
    ctx.system.add_generated_to_hand(ctx.source_player_id, BRANN_BRONZEBEARD)


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

    # Fungalmancer Flurgl — Gone Fishing
    # Passive: every fifth minion sold gets a random Murloc.
    hero_powers.register_passive(FLURGL_GONE_FISHING)
    effects.register_effect(
        FLURGL_GONE_FISHING,
        GameEvent.CARD_SOLD,
        _flurgl_gone_fishing,
        zones=(EffectZone.HERO_POWER,),
        name="Fungalmancer Flurgl — Gone Fishing",
    )

    # Kael'thas Sunstrider — Verdant Spheres
    # Passive: every third minion bought gets a Tavern Coin.
    hero_powers.register_passive(KAELTHAS_VERDANT_SPHERES)
    effects.register_effect(
        KAELTHAS_VERDANT_SPHERES,
        GameEvent.CARD_BOUGHT,
        _kaelthas_verdant_spheres,
        zones=(EffectZone.HERO_POWER,),
        name="Kael'thas Sunstrider — Verdant Spheres",
    )

    # Dinotamer Brann — Battle Brand
    # Passive: after four Battlecry minion purchases, get Brann once per game.
    hero_powers.register_passive(DINOTAMER_BRANN_BATTLE_BRAND)
    effects.register_effect(
        DINOTAMER_BRANN_BATTLE_BRAND,
        GameEvent.CARD_BOUGHT,
        _dinotamer_brann_battle_brand,
        zones=(EffectZone.HERO_POWER,),
        name="Dinotamer Brann — Battle Brand",
    )

    hero_powers._audited_content_registered = True
    return hero_powers
