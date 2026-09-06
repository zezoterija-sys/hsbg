"""Audited current Hero Power runtime content.

Only powers whose live behavior maps cleanly onto existing engine primitives
belong in this module. More complex powers stay unregistered (and therefore
unavailable as actions) until their lifecycle/effect has a conformance test.
"""

from __future__ import annotations

from .economy import install_economy_primitives
from .effects import EffectZone, TargetRef
from .events import GameEvent
from .hero_powers import HeroPowerSystem
from .lobby import is_minion_available_for_lobby


# Current power IDs from game/heroes.py.
GALLYWIX_SMART_SAVINGS = 57559
GEORGE_BOON_OF_LIGHT = 57562
DINOTAMER_BRANN_BATTLE_BRAND = 60218
FLURGL_GONE_FISHING = 60448
NOZDORMU_CLAIRVOYANCE = 61491
KAELTHAS_VERDANT_SPHERES = 61917
OMU_EVERBLOOM = 63605
HOGGARR_IM_THE_CAPN_NOW = 101132
CENARIUS_WISDOM_OF_ANCIENTS = 116921
BLACKTHORN_BLOODBOUND = 71459
LICH_KING_REBORN_RITES = 58040
PATCHWERK_ALL_PATCHED_UP = 59399

# Generated reward IDs.
TAVERN_COIN = 104436
BRANN_BRONZEBEARD = 96786
BLOOD_GEM = 70136


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


def _blackthorn_bloodbound(ctx):
    if _same_player(ctx):
        for _ in range(2):
            ctx.system.add_generated_to_hand(ctx.source_player_id, BLOOD_GEM)


def _lich_king_reborn_rites(ctx):
    if _same_player(ctx):
        ctx.system.grant_keyword(ctx.event["target"], "Reborn", until_next_turn=True)


def _gallywix_smart_savings(ctx):
    if not _same_player(ctx):
        return
    ctx.system.queue_gold_next_turn(ctx.source_player_id, 1)


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


def _cenarius_wisdom_of_ancients(ctx):
    if not _same_player(ctx):
        return
    ctx.system.increase_max_gold(ctx.source_player_id, 1)


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

    effects = game.effects
    install_economy_primitives(effects)

    # Content registration is the caller of for_game(); avoid recursively
    # re-entering the optional content-registration hook.
    hero_powers = HeroPowerSystem.for_game(game, register_content=False)
    if getattr(hero_powers, "_audited_content_registered", False):
        return hero_powers

    # Trade Prince Gallywix — Smart Savings
    # Triggered/passive economy: each sale banks +1 Gold for next turn.
    hero_powers.register_passive(GALLYWIX_SMART_SAVINGS)
    effects.register_effect(
        GALLYWIX_SMART_SAVINGS,
        GameEvent.CARD_SOLD,
        _gallywix_smart_savings,
        zones=(EffectZone.HERO_POWER,),
        name="Trade Prince Gallywix — Smart Savings",
    )

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
    # Passive: after upgrading the Tavern, gain 2 Gold immediately.
    hero_powers.register_passive(OMU_EVERBLOOM)
    effects.register_effect(
        OMU_EVERBLOOM,
        GameEvent.TAVERN_UPGRADED,
        _omu_everbloom,
        zones=(EffectZone.HERO_POWER,),
        name="Forest Warden Omu — Everbloom",
    )

    # Cap'n Hoggarr — I'm the Cap'n Now
    # Passive: after buying a Pirate, gain 1 Gold immediately.
    hero_powers.register_passive(HOGGARR_IM_THE_CAPN_NOW)
    effects.register_effect(
        HOGGARR_IM_THE_CAPN_NOW,
        GameEvent.CARD_BOUGHT,
        _hoggarr_im_the_capn_now,
        zones=(EffectZone.HERO_POWER,),
        name="Cap'n Hoggarr — I'm the Cap'n Now",
    )

    # Forest Lord Cenarius — Wisdom of Ancients
    # 3 Gold. Increase maximum Gold by 1. Standard active use limit: once/turn.
    hero_powers.register_active(CENARIUS_WISDOM_OF_ANCIENTS)
    effects.register_effect(
        CENARIUS_WISDOM_OF_ANCIENTS,
        GameEvent.HERO_POWER_USED,
        _cenarius_wisdom_of_ancients,
        zones=(EffectZone.HERO_POWER,),
        name="Forest Lord Cenarius — Wisdom of Ancients",
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

    hero_powers.register_active(BLACKTHORN_BLOODBOUND, max_uses_per_turn=2)
    effects.register_effect(
        BLACKTHORN_BLOODBOUND, GameEvent.HERO_POWER_USED, _blackthorn_bloodbound,
        zones=(EffectZone.HERO_POWER,), name="Death Speaker Blackthorn — Bloodbound",
    )
    hero_powers.register_active(LICH_KING_REBORN_RITES)
    effects.register_target_rule(LICH_KING_REBORN_RITES, _friendly_board_targets)
    effects.register_effect(
        LICH_KING_REBORN_RITES, GameEvent.HERO_POWER_USED, _lich_king_reborn_rites,
        zones=(EffectZone.HERO_POWER,), name="The Lich King — Reborn Rites",
    )
    # Player.set_hero applies Patchwerk's 60 starting Health from the ruleset.
    # Register passive classification only: an extra grant would double-count.
    hero_powers.register_passive(PATCHWERK_ALL_PATCHED_UP)

    hero_powers._audited_content_registered = True
    return hero_powers
