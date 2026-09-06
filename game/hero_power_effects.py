"""Audited current Hero Power runtime content.

Only powers whose live behavior maps cleanly onto existing engine primitives
belong in this module. More complex powers stay unregistered (and therefore
unavailable as actions) until their lifecycle/effect has a conformance test.
"""

from __future__ import annotations

from .economy import install_economy_primitives
from .effects import EffectZone, TargetRef, TriggerFamily
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
ALEXSTRASZA_QUEEN_OF_DRAGONS = 61517
DOCTOR_HOLLIDAE_BLESSING_OF_THE_NINE_FROGS = 110472
SKYCAPN_KRAGG_PIGGY_BANK = 62269
CTHUN_SATURDAY_CTHUNS = 66246
EDWIN_SHARPEN_BLADES = 57567
SNAKE_EYES_LUCKY_ROLL = 105315
RAGNAROS_BUY_INSECT = 64424
RAGNAROS_SULFURAS = 64426
KING_MUKLA_BANANARAMA = 59815
MALYGOS_ARCANE_ALTERATION = 60378
MILLIFICENT_TINKER = 57949
PYRAMAD_BRICK_BY_BRICK = 59832
LICH_BAZHIAL_GRAVEYARD_SHIFT = 60285
XYRELLA_SEE_THE_LIGHT = 70957
DEATHWING_ALL_WILL_BURN = 61406
ALAKIR_SWATTING_INSECTS = 64402
QUEEN_WAGTOGGLE_WAX_WARBAND = 59863
LADY_VASHJ_RELICS_OF_THE_DEEP = 85126
ROCK_MASTER_VOONE_UPBEAT_HARMONY = 99034
SHUDDERWOCK_SNICKER_SNACK = 58028
RAT_KING_A_TALE_OF_KINGS = 63127
CAPTAIN_EUDORA_BURIED_TREASURE = 62250

# Generated reward IDs.
TAVERN_COIN = 104436
BRANN_BRONZEBEARD = 96786
BLOOD_GEM = 70136
BANANA = 122906


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


def _generated_tavern_spells(system):
    """Return current-patch Tavern spells eligible for generated rewards."""

    result = []
    for card in getattr(system.game.pool, "card_definitions", ()):
        if not isinstance(card, dict) or card.get("cardType") != "spell":
            continue
        if card.get("pool") is not True or card.get("isDuosOnly", False):
            continue
        categories = {str(value).casefold() for value in (card.get("categories") or [])}
        if "tavern" not in categories:
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


def _alexstrasza_queen_of_dragons(ctx):
    if not _same_player(ctx):
        return
    candidates = _generated_lobby_minions(ctx.system, minion_type="Dragon")
    ctx.system.discover_cards(
        ctx.source_player_id,
        candidates,
        count=3,
        resolver_key="add_card_to_hand",
        metadata={"hero_power": ALEXSTRASZA_QUEEN_OF_DRAGONS},
    )


def _doctor_hollidae_blessing_of_the_nine_frogs(ctx):
    if not _same_player(ctx):
        return
    candidates = _generated_tavern_spells(ctx.system)
    chosen = ctx.random_choice(candidates)
    if chosen is not None:
        ctx.add_to_hand(chosen)


def _skycapn_kragg_piggy_bank(ctx):
    if not _same_player(ctx):
        return
    # The printed value is 2 Gold and improves by 1 each turn. Round 1 is
    # therefore 2 Gold, round 2 is 3 Gold, and so on.
    round_number = max(1, int(getattr(ctx.game, "round_number", 1) or 1))
    ctx.system.add_gold(ctx.source_player_id, round_number + 1)


def _cthun_saturday_cthuns(ctx):
    if not _same_player(ctx):
        return
    if ctx.player_state().pop("hero_cthun_armed_round", None) != ctx.game.round_number:
        return
    player = ctx.game.get_player(ctx.source_player_id)
    targets = [card for card in player.board if isinstance(card, dict)]
    if not targets:
        return
    repetitions = max(1, int(getattr(ctx.game, "round_number", 1) or 1))
    for _ in range(repetitions):
        ctx.buff(ctx.random_choice(targets), attack=1, health=1)


def _cthun_arm(ctx):
    if _same_player(ctx):
        ctx.player_state()["hero_cthun_armed_round"] = ctx.game.round_number


def _edwin_sharpen_blades(ctx):
    if not _same_player(ctx):
        return
    target = ctx.event.get("target")
    if not isinstance(target, dict):
        return
    state = ctx.system.get_player_state(ctx.source_player_id)
    purchases = int(state.get("hero_edwin_card_purchases", 0) or 0)
    improvement = purchases // 4
    ctx.buff(target, attack=2 + improvement, health=2 + improvement)


def _edwin_purchase_counter(ctx):
    if not _same_player(ctx):
        return
    state = ctx.player_state()
    state["hero_edwin_card_purchases"] = int(
        state.get("hero_edwin_card_purchases", 0) or 0
    ) + 1


def _snake_eyes_available(game, player):
    state = game.effects.get_player_state(player.player_id)
    cooldown_until = int(state.get("hero_snake_eyes_cooldown_until", 0) or 0)
    return int(getattr(game, "round_number", 0) or 0) > cooldown_until


def _snake_eyes_lucky_roll(ctx):
    if not _same_player(ctx):
        return
    roll = ctx.rng.randint(1, 6)
    ctx.system.add_gold(ctx.source_player_id, roll)
    state = ctx.system.get_player_state(ctx.source_player_id)
    state["hero_snake_eyes_last_roll"] = roll
    state["hero_snake_eyes_cooldown_until"] = (
        int(getattr(ctx.game, "round_number", 0) or 0) + roll
    )


def _ragnaros_buy_counter(ctx):
    if not _same_player(ctx):
        return
    state = ctx.player_state()
    count = int(state.get("hero_ragnaros_card_buys", 0) or 0) + 1
    state["hero_ragnaros_card_buys"] = count
    if count < 12:
        return
    player = ctx.game.get_player(ctx.source_player_id)
    replacement = next(
        (
            card for card in getattr(ctx.game.pool, "card_definitions", ())
            if isinstance(card, dict) and card.get("id") == RAGNAROS_SULFURAS
        ),
        {"id": RAGNAROS_SULFURAS, "name": "Sulfuras", "cost": 0,
         "text": "At the end of your turn, give your left and right-most minions +8/+8."},
    )
    player.set_hero_power(replacement)


def _ragnaros_sulfuras(ctx):
    if not _same_player(ctx):
        return
    player = ctx.game.get_player(ctx.source_player_id)
    occupied = [card for card in player.board if isinstance(card, dict)]
    if not occupied:
        return
    ctx.buff(occupied[0], attack=8, health=8)
    ctx.buff(occupied[-1], attack=8, health=8)


def _king_mukla_bananarama(ctx):
    if not _same_player(ctx):
        return
    for _ in range(2):
        ctx.system.add_generated_to_hand(ctx.source_player_id, BANANA)
    for player in getattr(ctx.game, "players", ()):
        if player.player_id == ctx.source_player_id or getattr(player, "eliminated", False):
            continue
        ctx.system.add_generated_to_hand(player.player_id, BANANA)


def _tavern_targets(context):
    player = context.game.get_player(context.player_id)
    return [
        TargetRef(
            player_id=context.player_id,
            zone=EffectZone.TAVERN,
            index=index,
            card=card,
        )
        for index, card in enumerate(player.tavern.slots)
        if isinstance(card, dict)
    ]


def _malygos_arcane_alteration(ctx):
    if not _same_player(ctx):
        return
    target_ref = ctx.event.get("target_ref")
    if target_ref is None or target_ref.zone is not EffectZone.TAVERN:
        return
    player = ctx.game.get_player(ctx.source_player_id)
    if target_ref.index < 0 or target_ref.index >= len(player.tavern.slots):
        return
    old_card = player.tavern.slots[target_ref.index]
    if not isinstance(old_card, dict):
        return
    tier = old_card.get("tier")
    ctx.game.pool.return_card(old_card)
    replacement = ctx.game.pool.get_random_minion(tier=tier)
    if replacement is None:
        # Preserve the offering if the pool has no same-tier replacement.
        replacement = old_card
    player.tavern.slots[target_ref.index] = replacement


def _millificent_tinker(ctx):
    if not _same_player(ctx):
        return
    candidates = [
        card for card in _generated_lobby_minions(ctx.system, minion_type="Mech")
        if ctx.system.has_keyword(card, "Magnetic")
    ]
    ctx.system.discover_cards(
        ctx.source_player_id,
        candidates,
        count=3,
        resolver_key="add_card_to_hand",
        metadata={"hero_power": MILLIFICENT_TINKER},
    )


def _can_take_tavern_minion(game, player):
    return len(player.hand) < player.MAX_HAND_SIZE and any(
        isinstance(card, dict) for card in player.tavern.slots
    )


def _take_tavern_minion(ctx, index):
    player = ctx.get_player()
    if len(player.hand) >= player.MAX_HAND_SIZE:
        return None
    card = player.tavern.slots[index]
    if not isinstance(card, dict):
        return None
    player.tavern.slots[index] = None
    player.hand.append(card)
    return card


def _pyramad_brick_by_brick(ctx):
    if not _same_player(ctx):
        return
    player = ctx.game.get_player(ctx.source_player_id)
    choices = [card for card in player.tavern.slots if isinstance(card, dict)]
    chosen = ctx.random_choice(choices)
    if chosen is None:
        return
    slot = player.tavern.slots.index(chosen)
    received = _take_tavern_minion(ctx, slot)
    if received is None:
        return
    received["health"] = int(received.get("health", 0) or 0) * 2
    player.tavern.slots[slot] = None


def _lich_bazhial_graveyard_shift(ctx):
    if not _same_player(ctx):
        return
    target_ref = ctx.event.get("target_ref")
    if target_ref is None or target_ref.zone is not EffectZone.TAVERN:
        return
    player = ctx.game.get_player(ctx.source_player_id)
    if target_ref.index < 0 or target_ref.index >= len(player.tavern.slots):
        return
    card = player.tavern.slots[target_ref.index]
    if not isinstance(card, dict):
        return
    if _take_tavern_minion(ctx, target_ref.index) is None:
        return
    player.tavern.slots[target_ref.index] = None
    armor_damage, health_damage = player.take_damage(2)
    ctx.system.events.emit(
        GameEvent.PLAYER_DAMAGED,
        player_id=ctx.source_player_id,
        amount=2,
        armor_damage=armor_damage,
        health_damage=health_damage,
        source_card=ctx.source,
    )


def _xyrella_see_the_light(ctx):
    if not _same_player(ctx):
        return
    target_ref = ctx.event.get("target_ref")
    if target_ref is None or target_ref.zone is not EffectZone.TAVERN:
        return
    player = ctx.game.get_player(ctx.source_player_id)
    if target_ref.index < 0 or target_ref.index >= len(player.tavern.slots):
        return
    card = player.tavern.slots[target_ref.index]
    if not isinstance(card, dict):
        return
    received = _take_tavern_minion(ctx, target_ref.index)
    if received is None:
        return
    received["attack"] = 2
    received["health"] = 2
    player.tavern.slots[target_ref.index] = None


def _deathwing_all_will_burn(ctx):
    if ctx.source_player_id is None or _source_combat_side(ctx) is None:
        return
    seen = set()
    for side_key in ("side_a", "side_b"):
        side = ctx.event.get(side_key)
        if side is None or id(side) in seen:
            continue
        seen.add(id(side))
        for minion in side.board:
            if isinstance(minion, dict):
                ctx.buff(minion, attack=2, health=0)


def _source_combat_side(ctx):
    if ctx.source_side is not None:
        return ctx.source_side
    for side_key in ("side_a", "side_b"):
        side = ctx.event.get(side_key)
        if side is not None and getattr(side, "player_id", None) == ctx.source_player_id:
            return side
    return None


def _alakir_swatting_insects(ctx):
    side = _source_combat_side(ctx)
    if side is None or not side.board:
        return
    target = side.board[0]
    if not isinstance(target, dict):
        return
    ctx.grant_keyword(target, "Windfury")
    ctx.grant_keyword(target, "Divine Shield")
    # Combat cards were prepared before COMBAT_START; a newly granted shield
    # must update the combat engine's consumable shield state too.
    target["_combat_divine_shield"] = True
    ctx.grant_keyword(target, "Taunt")


def _queen_wagtoggle_wax_warband(ctx):
    side = _source_combat_side(ctx)
    if side is None:
        return
    selected = set()
    for minion in side.board:
        if not isinstance(minion, dict):
            continue
        types = minion.get("minionTypes") or ([minion.get("minionType")] if minion.get("minionType") else [])
        for minion_type in types:
            if minion_type and minion_type not in selected:
                ctx.buff(minion, attack=1, health=1)
                selected.add(minion_type)


def _generated_spellcraft_cards(system):
    result = []
    for card in getattr(system.game.pool, "card_definitions", ()):
        if not isinstance(card, dict) or card.get("cardType") != "spell":
            continue
        if card.get("pool") is not True or card.get("isDuosOnly", False):
            continue
        categories = {str(value).casefold() for value in (card.get("categories") or [])}
        if "spellcraft" in categories:
            result.append(card)
    return result


def _lady_vashj_relics_of_the_deep(ctx):
    if not _same_player(ctx):
        return
    chosen = ctx.random_choice(_generated_spellcraft_cards(ctx.system))
    if chosen is not None:
        ctx.system.add_generated_to_hand(ctx.source_player_id, chosen)


def _rock_master_voone_upbeat_harmony(ctx):
    if not _same_player(ctx):
        return
    state = ctx.player_state()
    turns = int(state.get("hero_voone_turns", 0) or 0) + 1
    state["hero_voone_turns"] = turns
    if turns % 3 != 0:
        return
    player = ctx.game.get_player(ctx.source_player_id)
    if player.hand:
        original = player.hand[0]
        ctx.system.add_generated_to_hand(
            ctx.source_player_id, original["id"],
            golden=ctx.system.is_golden(original),
        )


def _friendly_battlecry_targets(context):
    player = context.game.get_player(context.player_id)
    return [
        TargetRef(
            player_id=context.player_id,
            zone=EffectZone.BOARD,
            index=index,
            card=card,
        )
        for index, card in enumerate(player.board)
        if isinstance(card, dict) and context.game.effects.has_keyword(card, "Battlecry")
    ]


def _shudderwock_snicker_snack(ctx):
    if not _same_player(ctx):
        return
    target_ref = ctx.event.get("target_ref")
    if target_ref is None or target_ref.zone is not EffectZone.BOARD:
        return
    player = ctx.game.get_player(ctx.source_player_id)
    if target_ref.index < 0 or target_ref.index >= len(player.board):
        return
    target = player.board[target_ref.index]
    if not isinstance(target, dict) or not ctx.system.has_keyword(target, "Battlecry"):
        return
    ctx.system.trigger_card_family(
        target,
        TriggerFamily.BATTLECRY,
        player_id=ctx.source_player_id,
        zone=EffectZone.BOARD,
        position=target_ref.index,
    )


def _rat_king_a_tale_of_kings(ctx):
    if not _same_player(ctx):
        return
    types = ("Beast", "Demon", "Mech", "Murloc", "Naga", "Pirate", "Quilboar", "Undead", "Dragon", "Elemental")
    round_number = max(1, int(getattr(ctx.game, "round_number", 1) or 1))
    minion_type = types[(round_number - 1) % len(types)]
    candidates = _generated_lobby_minions(ctx.system, minion_type=minion_type)
    ctx.system.discover_cards(
        ctx.source_player_id,
        candidates,
        count=3,
        resolver_key="add_card_to_hand",
        metadata={"hero_power": RAT_KING_A_TALE_OF_KINGS, "minion_type": minion_type},
    )


def _captain_eudora_buried_treasure(ctx):
    if not _same_player(ctx):
        return
    player = ctx.game.get_player(ctx.source_player_id)
    dug = ctx.game.pool.get_random_minion(max_tier=max(1, int(player.tavern_tier)))
    if dug is None:
        return
    golden = ctx.system.create_card(dug["id"], golden=True, generated=True)
    ctx.system.add_generated_to_hand(ctx.source_player_id, golden)


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

    hero_powers.register_active(ALEXSTRASZA_QUEEN_OF_DRAGONS, unlock_tavern_tier=4)
    effects.register_effect(
        ALEXSTRASZA_QUEEN_OF_DRAGONS,
        GameEvent.HERO_POWER_USED,
        _alexstrasza_queen_of_dragons,
        zones=(EffectZone.HERO_POWER,),
        name="Alexstrasza — Queen of Dragons",
    )

    hero_powers.register_active(DOCTOR_HOLLIDAE_BLESSING_OF_THE_NINE_FROGS)
    effects.register_effect(
        DOCTOR_HOLLIDAE_BLESSING_OF_THE_NINE_FROGS,
        GameEvent.HERO_POWER_USED,
        _doctor_hollidae_blessing_of_the_nine_frogs,
        zones=(EffectZone.HERO_POWER,),
        name="Doctor Holli'dae — Blessing of the Nine Frogs",
    )

    hero_powers.register_active(SKYCAPN_KRAGG_PIGGY_BANK, max_uses_per_game=1)
    effects.register_effect(
        SKYCAPN_KRAGG_PIGGY_BANK,
        GameEvent.HERO_POWER_USED,
        _skycapn_kragg_piggy_bank,
        zones=(EffectZone.HERO_POWER,),
        name="Skycap'n Kragg — Piggy Bank",
    )

    hero_powers.register_active(CTHUN_SATURDAY_CTHUNS)
    effects.register_effect(CTHUN_SATURDAY_CTHUNS, GameEvent.HERO_POWER_USED,
                            _cthun_arm, zones=(EffectZone.HERO_POWER,))
    effects.register_effect(
        CTHUN_SATURDAY_CTHUNS,
        GameEvent.TURN_END,
        _cthun_saturday_cthuns,
        zones=(EffectZone.HERO_POWER,),
        name="C'Thun — Saturday C'Thuns!",
    )

    hero_powers.register_active(EDWIN_SHARPEN_BLADES)
    effects.register_target_rule(EDWIN_SHARPEN_BLADES, _friendly_board_targets)
    effects.register_effect(
        EDWIN_SHARPEN_BLADES, GameEvent.SPELL_BOUGHT,
        _edwin_purchase_counter, zones=(EffectZone.HERO_POWER,),
        name="Edwin VanCleef — spell purchase counter",
    )
    effects.register_effect(
        EDWIN_SHARPEN_BLADES,
        GameEvent.CARD_BOUGHT,
        _edwin_purchase_counter,
        zones=(EffectZone.HERO_POWER,),
        name="Edwin VanCleef — purchase counter",
    )
    effects.register_effect(
        EDWIN_SHARPEN_BLADES,
        GameEvent.HERO_POWER_USED,
        _edwin_sharpen_blades,
        zones=(EffectZone.HERO_POWER,),
        name="Edwin VanCleef — Sharpen Blades",
    )

    hero_powers.register_active(
        SNAKE_EYES_LUCKY_ROLL,
        condition=_snake_eyes_available,
    )
    effects.register_effect(
        SNAKE_EYES_LUCKY_ROLL,
        GameEvent.HERO_POWER_USED,
        _snake_eyes_lucky_roll,
        zones=(EffectZone.HERO_POWER,),
        name="Snake Eyes — Lucky Roll",
    )

    hero_powers.register_passive(RAGNAROS_BUY_INSECT)
    effects.register_effect(
        RAGNAROS_BUY_INSECT, GameEvent.SPELL_BOUGHT,
        _ragnaros_buy_counter, zones=(EffectZone.HERO_POWER,),
        name="Ragnaros — spell purchase counter",
    )
    effects.register_effect(
        RAGNAROS_BUY_INSECT,
        GameEvent.CARD_BOUGHT,
        _ragnaros_buy_counter,
        zones=(EffectZone.HERO_POWER,),
        name="Ragnaros — BUY, INSECT!",
    )
    hero_powers.register_passive(RAGNAROS_SULFURAS)
    effects.register_effect(
        RAGNAROS_SULFURAS,
        GameEvent.TURN_END,
        _ragnaros_sulfuras,
        zones=(EffectZone.HERO_POWER,),
        name="Ragnaros — Sulfuras",
    )

    hero_powers.register_automatic(KING_MUKLA_BANANARAMA)
    effects.register_effect(
        KING_MUKLA_BANANARAMA,
        GameEvent.TURN_START,
        _king_mukla_bananarama,
        zones=(EffectZone.HERO_POWER,),
        name="King Mukla — Bananarama",
    )

    hero_powers.register_active(MALYGOS_ARCANE_ALTERATION, max_uses_per_turn=2)
    effects.register_target_rule(MALYGOS_ARCANE_ALTERATION, _tavern_targets)
    effects.register_effect(
        MALYGOS_ARCANE_ALTERATION,
        GameEvent.HERO_POWER_USED,
        _malygos_arcane_alteration,
        zones=(EffectZone.HERO_POWER,),
        name="Malygos — Arcane Alteration",
    )

    hero_powers.register_active(MILLIFICENT_TINKER, unlock_tavern_tier=4)
    effects.register_effect(
        MILLIFICENT_TINKER,
        GameEvent.HERO_POWER_USED,
        _millificent_tinker,
        zones=(EffectZone.HERO_POWER,),
        name="Millificent Manastorm — Tinker",
    )

    hero_powers.register_active(PYRAMAD_BRICK_BY_BRICK, condition=_can_take_tavern_minion)
    effects.register_effect(
        PYRAMAD_BRICK_BY_BRICK,
        GameEvent.HERO_POWER_USED,
        _pyramad_brick_by_brick,
        zones=(EffectZone.HERO_POWER,),
        name="Pyramad — Brick by Brick",
    )

    hero_powers.register_active(LICH_BAZHIAL_GRAVEYARD_SHIFT, condition=_can_take_tavern_minion)
    effects.register_target_rule(LICH_BAZHIAL_GRAVEYARD_SHIFT, _tavern_targets)
    effects.register_effect(
        LICH_BAZHIAL_GRAVEYARD_SHIFT,
        GameEvent.HERO_POWER_USED,
        _lich_bazhial_graveyard_shift,
        zones=(EffectZone.HERO_POWER,),
        name="Lich Baz'hial — Graveyard Shift",
    )

    hero_powers.register_active(XYRELLA_SEE_THE_LIGHT, condition=_can_take_tavern_minion)
    effects.register_target_rule(XYRELLA_SEE_THE_LIGHT, _tavern_targets)
    effects.register_effect(
        XYRELLA_SEE_THE_LIGHT,
        GameEvent.HERO_POWER_USED,
        _xyrella_see_the_light,
        zones=(EffectZone.HERO_POWER,),
        name="Xyrella — See the Light",
    )

    # Deathwing's draft does not persist combat Attack to recruitment cards.
    # Do not install either its rule or its event handler until that is fixed.

    hero_powers.register_passive(ALAKIR_SWATTING_INSECTS)
    effects.register_effect(
        ALAKIR_SWATTING_INSECTS,
        GameEvent.COMBAT_START,
        _alakir_swatting_insects,
        zones=(EffectZone.HERO_POWER,),
        name="Al'Akir — Swatting Insects",
    )

    # Wagtoggle's draft lacks spending progression and complete type selection.

    hero_powers.register_automatic(LADY_VASHJ_RELICS_OF_THE_DEEP)
    effects.register_effect(
        LADY_VASHJ_RELICS_OF_THE_DEEP,
        GameEvent.TURN_START,
        _lady_vashj_relics_of_the_deep,
        zones=(EffectZone.HERO_POWER,),
        name="Lady Vashj — Relics of the Deep",
    )

    hero_powers.register_passive(ROCK_MASTER_VOONE_UPBEAT_HARMONY)
    effects.register_effect(
        ROCK_MASTER_VOONE_UPBEAT_HARMONY,
        GameEvent.TURN_END,
        _rock_master_voone_upbeat_harmony,
        zones=(EffectZone.HERO_POWER,),
        name="Rock Master Voone — Upbeat Harmony",
    )

    hero_powers.register_active(SHUDDERWOCK_SNICKER_SNACK, unlock_turn=3)
    effects.register_target_rule(SHUDDERWOCK_SNICKER_SNACK, _friendly_battlecry_targets)
    effects.register_effect(
        SHUDDERWOCK_SNICKER_SNACK,
        GameEvent.HERO_POWER_USED,
        _shudderwock_snicker_snack,
        zones=(EffectZone.HERO_POWER,),
        name="Shudderwock — Snicker-snack",
    )

    hero_powers.register_active(RAT_KING_A_TALE_OF_KINGS)
    effects.register_effect(
        RAT_KING_A_TALE_OF_KINGS,
        GameEvent.HERO_POWER_USED,
        _rat_king_a_tale_of_kings,
        zones=(EffectZone.HERO_POWER,),
        name="The Rat King — A Tale of Kings",
    )

    # Not enabled: the draft below incorrectly rewards every dig. Restore
    # registration only with a verified multi-dig cycle and pool provenance.

    hero_powers._audited_content_registered = True
    return hero_powers
