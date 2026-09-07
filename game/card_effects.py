"""
Real Battlegrounds card-effect registrations.

This file is intentionally content-focused.  Generic mechanics live in
`effects.py`; this file maps real card IDs to those mechanics.

Batch coverage:
- Tier 1/2 recruit triggers
- Battlecries
- Deathrattles
- Rally
- Start/End of turn
- Start of combat
- Spellcraft
- Activate
- targeted spells/Battlecries
- Discover / Choose One
- generated cards
- several combat-to-hand effects
"""

from copy import deepcopy

from .effects import EffectZone, TriggerFamily
from .events import GameEvent
from .tier36_effects import register_tier36_effects


# =============================================================
# REAL CARD IDS
# =============================================================

# Tier 1 minions
BUZZING_VERMIN = 116240
FLEEING_FUGITIVE = 133451
FLIGHTY_SCOUT = 120677
FLITTERING_BAT = 132792
GLIM_GUARDIAN = 113346
LULLABOT = 98582
MINI_MYRMIDON = 80738
MOLTEN_ROCK = 64296
RAZORFEN_GEOMANCER = 70143
RIVER_SKIPPER = 122092
SOUTHSEA_BUSKER = 98501
SUSPICIOUS_PRISONGUARD = 132915
TUSKED_CAMPER = 122568
WRATH_WEAVER = 59670

# Tier 2 minions
CLEVER_CASTAWAY = 132921
CRATER_MINER = 116182
ELECTRIC_SYNTHESIZER = 100026
EXPERT_AVIATOR = 126637
HUMMING_BIRD = 98939
MECHAGNOME_INTERPRETER = 115678
MIND_MUCK = 93321
OOZELING_GLADIATOR = 103670
PRODIGIOUS_TUSKER = 122098
ROADBOAR = 70157
SCARLET_SKULL = 95280
SELLEMENTAL = 64038
SHELL_COLLECTOR = 80740
TAD = 87060
THOUSANDTH_PAPER_DRAKE = 108116
VERY_HUNGRY_WINTERFINNER = 109879

# Generated cards / tokens / spells
BEETLE = 110402
FORAGING_BAT = 133024
BLOOD_GEM = 70136
WATER_DROPLET = 64040
TAVERN_COIN = 104436
SLIMY_SHIELD = 105863
MINI_TRIDENT = 83914
GEM_DAY = 116596


# =============================================================
# GENERIC CONTENT HELPERS
# =============================================================


def _amount(ctx, normal, golden):
    return golden if ctx.is_golden else normal


def _player(ctx):
    return ctx.get_player()


def _other_friendly_board_targets(context):
    player = context.game.get_player(context.player_id)
    return [
        index
        for index, card in enumerate(player.board)
        if isinstance(card, dict) and card is not context.source_card
    ]


def _friendly_board_targets(context):
    player = context.game.get_player(context.player_id)
    return [
        index
        for index, card in enumerate(player.board)
        if isinstance(card, dict)
    ]


def _friendly_demon_targets(context):
    player = context.game.get_player(context.player_id)
    return [
        index
        for index, card in enumerate(player.board)
        if isinstance(card, dict)
        and context.game.effects.is_minion_type(card, "Demon")
    ]


def _combat_side_for_player(event, player_id):
    for key in (
        "side",
        "side_a",
        "side_b",
        "attacking_side",
        "defending_side",
        "source_side",
        "target_side",
    ):
        side = event.get(key)
        if side is not None and getattr(side, "player_id", None) == player_id:
            return side
    return None


def _add_gold(player, amount):
    amount = int(amount or 0)
    if amount <= 0:
        return
    maximum = int(getattr(player, "max_gold", 10) or 10)
    player.gold = min(
        maximum,
        int(getattr(player, "gold", 0) or 0) + amount,
    )


def _pool_definitions(system):
    return list(getattr(system.game.pool, "card_definitions", []))


def _normal_tavern_minion_definitions(system, *, tier=None, minion_type=None):
    result = []
    for card in _pool_definitions(system):
        if card.get("cardType") != "minion":
            continue
        if card.get("pool") is not True:
            continue
        if "tavern" not in card.get("categories", []):
            continue
        if card.get("isDuosOnly", False):
            continue
        if tier is not None and card.get("tier") != tier:
            continue
        if minion_type is not None and not system.is_minion_type(card, minion_type):
            continue
        result.append(card)
    return result


def _tavern_spell_definitions(system):
    result = []
    for card in _pool_definitions(system):
        if card.get("cardType") != "spell":
            continue
        if card.get("pool") is not True:
            continue
        if "tavern" not in card.get("categories", []):
            continue
        if card.get("isDuosOnly", False):
            continue
        result.append(card)
    return result


def _add_generated_many(ctx, card_id, count):
    added = []
    for _ in range(max(0, int(count))):
        card = ctx.add_to_hand(card_id)
        if card is None:
            break
        added.append(card)
    return added


def _add_random_generated_minions(ctx, definitions, count):
    definitions = list(definitions)
    if not definitions:
        return []

    added = []
    for _ in range(max(0, int(count))):
        definition = ctx.random_choice(definitions)
        if definition is None:
            break
        card = ctx.add_to_hand(definition.get("id"))
        if card is None:
            break
        added.append(card)
    return added


def _blood_gem_values(system, player_id):
    state = system.get_player_state(player_id)
    return (
        1 + int(state.get("blood_gem_attack_bonus", 0) or 0),
        1 + int(state.get("blood_gem_health_bonus", 0) or 0),
    )


def _apply_blood_gems(ctx, target, count=1):
    attack, health = _blood_gem_values(ctx.system, ctx.source_player_id)
    count = max(0, int(count))
    ctx.buff(
        target,
        attack=attack * count,
        health=health * count,
    )
    if isinstance(target, dict) and count:
        target["_blood_gems_received"] = int(
            target.get("_blood_gems_received", 0) or 0
        ) + count


def _emit_recruit_player_damage(ctx, amount):
    player = ctx.get_player()
    if player is None or amount <= 0 or getattr(player, "eliminated", False):
        return

    if hasattr(player, "take_damage"):
        armor_damage, health_damage = player.take_damage(amount)
    else:
        armor = int(getattr(player, "armor", 0) or 0)
        armor_damage = min(armor, amount)
        player.armor = armor - armor_damage
        health_damage = amount - armor_damage
        player.health = max(0, int(getattr(player, "health", 0) or 0) - health_damage)

    ctx.system.events.emit(
        GameEvent.PLAYER_DAMAGED,
        player_id=ctx.source_player_id,
        amount=amount,
        armor_damage=armor_damage,
        health_damage=health_damage,
        self_damage=True,
        source_card=ctx.source,
    )


# =============================================================
# CHOICE RESOLVERS / GLOBAL TURN STATE
# =============================================================


def _resolve_gem_day(system, player_id, option, metadata):
    state = system.get_player_state(player_id)
    if option == "attack":
        state["blood_gem_attack_bonus"] = int(
            state.get("blood_gem_attack_bonus", 0) or 0
        ) + 1
    elif option == "health":
        state["blood_gem_health_bonus"] = int(
            state.get("blood_gem_health_bonus", 0) or 0
        ) + 1
    else:
        raise ValueError(f"Unknown Gem Day choice: {option}")


def _start_crater_choice(system, player_id, *, golden):
    return system.start_choice(
        player_id,
        "crater_miner",
        ["blood_gems", "gem_day"],
        kind="choose_one",
        source_card_id=CRATER_MINER,
        metadata={"golden": bool(golden)},
    )


def _resolve_crater_miner(system, player_id, option, metadata):
    golden = bool(metadata.get("golden", False))

    if option == "blood_gems":
        count = 4 if golden else 2
        for _ in range(count):
            system.add_generated_to_hand(player_id, BLOOD_GEM)
    elif option == "gem_day":
        count = 2 if golden else 1
        for _ in range(count):
            system.add_generated_to_hand(player_id, GEM_DAY)
    else:
        raise ValueError(f"Unknown Crater Miner choice: {option}")

    state = system.get_player_state(player_id)
    queued = int(state.get("queued_crater_choices", 0) or 0)
    if queued > 0:
        state["queued_crater_choices"] = queued - 1
        _start_crater_choice(
            system,
            player_id,
            golden=bool(state.get("queued_crater_golden", golden)),
        )


def _resolve_multi_tavern_spell_discover(system, player_id, option, metadata):
    system.add_generated_to_hand(player_id, option)

    remaining = int(metadata.get("remaining", 1) or 1) - 1
    if remaining <= 0:
        return

    candidates = [
        card.get("id")
        for card in _tavern_spell_definitions(system)
        if isinstance(card.get("id"), int)
    ]
    system.discover_cards(
        player_id,
        candidates,
        count=3,
        resolver_key="multi_tavern_spell_discover",
        metadata={"remaining": remaining},
    )


def _handle_pending_gold_turn_start(effects, event):
    player_id = event.get("player_id")
    if player_id is None:
        return

    state = effects.get_player_state(player_id)
    amount = int(state.pop("pending_gold_next_turn", 0) or 0)
    if amount <= 0:
        return

    player = effects.game.get_player(player_id)
    _add_gold(player, amount)


# =============================================================
# REGISTRATION ENTRY POINT
# =============================================================


def register_card_effects(effects):
    effects.register_choice_resolver("gem_day", _resolve_gem_day)
    effects.register_choice_resolver("crater_miner", _resolve_crater_miner)
    effects.register_choice_resolver(
        "multi_tavern_spell_discover",
        _resolve_multi_tavern_spell_discover,
    )

    # Player-scoped delayed state such as Southsea Busker survives after the
    # source minion leaves play, so this is intentionally a direct lifecycle
    # listener rather than a source-card trigger.
    effects.events.register(
        GameEvent.TURN_START,
        lambda event: _handle_pending_gold_turn_start(effects, event),
        order=-500,
    )

    register_minion_effects(effects)
    register_spell_effects(effects)
    register_tavern_spell_effects(effects)
    register_hero_power_effects(effects)

    # Tier 3-6 content and the generated/Tavern spells those cards use.
    register_tier36_effects(effects)


# =============================================================
# TIER 1 MINIONS
# =============================================================


def register_minion_effects(effects):
    # Buzzing Vermin ---------------------------------------------------------
    effects.register_deathrattle(
        BUZZING_VERMIN,
        _buzzing_vermin_deathrattle,
        name="Buzzing Vermin",
    )

    # Fleeing Fugitive -------------------------------------------------------
    effects.register_effect(
        FLEEING_FUGITIVE,
        GameEvent.SPELL_CAST,
        _fleeing_fugitive_spell_cast,
        zones=(EffectZone.BOARD,),
        name="Fleeing Fugitive",
    )

    # Flighty Scout ----------------------------------------------------------
    effects.register_effect(
        FLIGHTY_SCOUT,
        GameEvent.COMBAT_START,
        _flighty_scout_start_of_combat,
        zones=(EffectZone.HAND,),
        family=TriggerFamily.START_OF_COMBAT,
        name="Flighty Scout",
    )

    # Flittering Bat ---------------------------------------------------------
    effects.register_rally(
        FLITTERING_BAT,
        _flittering_bat_rally,
        name="Flittering Bat",
    )

    # Glim Guardian ----------------------------------------------------------
    effects.register_rally(
        GLIM_GUARDIAN,
        _glim_guardian_rally,
        name="Glim Guardian",
    )

    # Lullabot ---------------------------------------------------------------
    effects.register_end_of_turn(
        LULLABOT,
        _lullabot_end_of_turn,
        name="Lullabot",
    )

    # Mini-Myrmidon ----------------------------------------------------------
    effects.register_spellcraft(
        MINI_MYRMIDON,
        MINI_TRIDENT,
    )

    # Molten Rock ------------------------------------------------------------
    effects.register_effect(
        MOLTEN_ROCK,
        GameEvent.CARD_PLAYED,
        _molten_rock_after_play,
        zones=(EffectZone.BOARD,),
        name="Molten Rock",
    )

    # Razorfen Geomancer -----------------------------------------------------
    effects.register_battlecry(
        RAZORFEN_GEOMANCER,
        _razorfen_geomancer_battlecry,
        name="Razorfen Geomancer",
    )

    # River Skipper ----------------------------------------------------------
    effects.register_effect(
        RIVER_SKIPPER,
        GameEvent.CARD_SOLD,
        _river_skipper_sold,
        zones=(EffectZone.EVENT_SOURCE,),
        name="River Skipper",
    )

    # Southsea Busker --------------------------------------------------------
    effects.register_battlecry(
        SOUTHSEA_BUSKER,
        _southsea_busker_battlecry,
        name="Southsea Busker",
    )

    # Suspicious Prisonguard -------------------------------------------------
    effects.register_activate(
        SUSPICIOUS_PRISONGUARD,
        1,
        _suspicious_prisonguard_activate,
        target_provider=_other_friendly_board_targets,
        name="Suspicious Prisonguard",
    )

    # Tusked Camper ----------------------------------------------------------
    effects.register_rally(
        TUSKED_CAMPER,
        _tusked_camper_rally,
        name="Tusked Camper",
    )

    # Wrath Weaver -----------------------------------------------------------
    effects.register_effect(
        WRATH_WEAVER,
        GameEvent.CARD_PLAYED,
        _wrath_weaver_after_play,
        zones=(EffectZone.BOARD,),
        name="Wrath Weaver",
    )

    # Electric Synthesizer ---------------------------------------------------
    effects.register_battlecry(
        ELECTRIC_SYNTHESIZER,
        _electric_synthesizer_battlecry,
        name="Electric Synthesizer Battlecry",
    )
    effects.register_start_of_combat(
        ELECTRIC_SYNTHESIZER,
        _electric_synthesizer_start_of_combat,
        name="Electric Synthesizer Start of Combat",
    )

    # Humming Bird -----------------------------------------------------------
    effects.register_start_of_combat(
        HUMMING_BIRD,
        _humming_bird_start_of_combat,
        name="Humming Bird",
    )

    # Clever Castaway --------------------------------------------------------
    effects.register_activate(
        CLEVER_CASTAWAY,
        2,
        _clever_castaway_activate,
        name="Clever Castaway",
    )

    # Crater Miner -----------------------------------------------------------
    effects.register_battlecry(
        CRATER_MINER,
        _crater_miner_battlecry,
        name="Crater Miner",
    )

    # Expert Aviator ---------------------------------------------------------
    effects.register_rally(
        EXPERT_AVIATOR,
        _expert_aviator_rally,
        name="Expert Aviator",
    )

    # Mechagnome Interpreter -------------------------------------------------
    effects.register_effect(
        MECHAGNOME_INTERPRETER,
        GameEvent.CARD_PLAYED,
        _mechagnome_after_play,
        zones=(EffectZone.BOARD,),
        name="Mechagnome Interpreter play",
    )
    effects.register_effect(
        MECHAGNOME_INTERPRETER,
        GameEvent.MAGNETIZED,
        _mechagnome_after_magnetize,
        zones=(EffectZone.BOARD,),
        name="Mechagnome Interpreter magnetize",
    )

    # Mind Muck --------------------------------------------------------------
    effects.register_target_rule(
        MIND_MUCK,
        _friendly_demon_targets,
    )
    effects.register_battlecry(
        MIND_MUCK,
        _mind_muck_battlecry,
        name="Mind Muck",
    )

    # Oozeling Gladiator -----------------------------------------------------
    effects.register_battlecry(
        OOZELING_GLADIATOR,
        _oozeling_gladiator_battlecry,
        name="Oozeling Gladiator",
    )

    # Prodigious Tusker ------------------------------------------------------
    effects.register_effect(
        PRODIGIOUS_TUSKER,
        GameEvent.ATTACK,
        _prodigious_tusker_friendly_attack,
        zones=(EffectZone.COMBAT,),
        name="Prodigious Tusker",
    )

    # Roadboar ---------------------------------------------------------------
    effects.register_rally(
        ROADBOAR,
        _roadboar_rally,
        name="Roadboar",
    )

    # Scarlet Skull ----------------------------------------------------------
    effects.register_deathrattle(
        SCARLET_SKULL,
        _scarlet_skull_deathrattle,
        name="Scarlet Skull",
    )

    # Sellemental ------------------------------------------------------------
    effects.register_effect(
        SELLEMENTAL,
        GameEvent.CARD_SOLD,
        _sellemental_sold,
        zones=(EffectZone.EVENT_SOURCE,),
        name="Sellemental",
    )

    # Shell Collector --------------------------------------------------------
    effects.register_battlecry(
        SHELL_COLLECTOR,
        _shell_collector_battlecry,
        name="Shell Collector",
    )

    # Tad --------------------------------------------------------------------
    effects.register_effect(
        TAD,
        GameEvent.CARD_SOLD,
        _tad_sold,
        zones=(EffectZone.EVENT_SOURCE,),
        name="Tad",
    )

    # Thousandth Paper Drake -------------------------------------------------
    effects.register_start_of_combat(
        THOUSANDTH_PAPER_DRAKE,
        _thousandth_paper_drake_start_of_combat,
        name="Thousandth Paper Drake",
    )

    # Very Hungry Winterfinner ----------------------------------------------
    effects.register_effect(
        VERY_HUNGRY_WINTERFINNER,
        GameEvent.MINION_DAMAGED,
        _winterfinner_damaged,
        zones=(EffectZone.COMBAT,),
        name="Very Hungry Winterfinner",
    )


# =============================================================
# TIER 1 HANDLERS
# =============================================================


def _buzzing_vermin_deathrattle(ctx):
    ctx.summon(BEETLE, count=2 if ctx.is_golden else 1)


def _fleeing_fugitive_spell_cast(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    if ctx.event.get("target") is not ctx.source:
        return
    ctx.buff(ctx.source, health=_amount(ctx, 1, 2))


def _flighty_scout_start_of_combat(ctx):
    side = _combat_side_for_player(ctx.event, ctx.source_player_id)
    if side is None or len(side.board) >= 7:
        return

    copy = deepcopy(ctx.source)
    if ctx.is_golden:
        copy["attack"] = int(copy.get("attack", 0) or 0) * 2
        copy["health"] = int(copy.get("health", 0) or 0) * 2

    ctx.system.summon(
        side,
        copy,
        count=1,
        event=ctx.event,
    )


def _flittering_bat_rally(ctx):
    ctx.summon(
        FORAGING_BAT,
        count=2 if ctx.is_golden else 1,
        position=(ctx.source_position + 1 if ctx.source_position is not None else None),
    )


def _glim_guardian_rally(ctx):
    ctx.buff(
        ctx.source,
        attack=_amount(ctx, 2, 4),
    )


def _lullabot_end_of_turn(ctx):
    # If Lullabot was Magnetized, ctx.source is the physical host Mech, which
    # is exactly where the attached Lullabot's end-of-turn health belongs.
    ctx.buff(
        ctx.source,
        health=_amount(ctx, 1, 2),
    )


def _molten_rock_after_play(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    if not ctx.system.is_minion_type(ctx.event.get("card"), "Elemental"):
        return
    ctx.buff(ctx.source, health=_amount(ctx, 1, 2))


def _razorfen_geomancer_battlecry(ctx):
    _add_generated_many(
        ctx,
        BLOOD_GEM,
        4 if ctx.is_golden else 2,
    )


def _river_skipper_sold(ctx):
    definitions = _normal_tavern_minion_definitions(
        ctx.system,
        tier=1,
    )
    _add_random_generated_minions(
        ctx,
        definitions,
        2 if ctx.is_golden else 1,
    )


def _southsea_busker_battlecry(ctx):
    state = ctx.player_state()
    state["pending_gold_next_turn"] = int(
        state.get("pending_gold_next_turn", 0) or 0
    ) + _amount(ctx, 1, 2)


def _suspicious_prisonguard_activate(ctx):
    target = ctx.event.get("target")
    if not isinstance(target, dict):
        return
    amount = _amount(ctx, 3, 6)
    ctx.buff(target, attack=amount, health=amount)


def _tusked_camper_rally(ctx):
    _apply_blood_gems(
        ctx,
        ctx.source,
        count=2 if ctx.is_golden else 1,
    )


def _wrath_weaver_after_play(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    played = ctx.event.get("card")
    if not ctx.system.is_minion_type(played, "Demon"):
        return

    repetitions = 2 if ctx.is_golden else 1
    for _ in range(repetitions):
        _emit_recruit_player_damage(ctx, 1)
        ctx.buff(ctx.source, attack=2, health=2)


# =============================================================
# TIER 2 HANDLERS
# =============================================================


def _electric_synthesizer_battlecry(ctx):
    player = ctx.get_player()
    if player is None:
        return
    amount = _amount(ctx, 1, 2)
    for minion in player.board:
        if (
            isinstance(minion, dict)
            and minion is not ctx.source
            and ctx.system.is_minion_type(minion, "Dragon")
        ):
            ctx.buff(minion, attack=amount, health=amount)


def _electric_synthesizer_start_of_combat(ctx):
    side = ctx.source_side
    if side is None:
        return
    amount = _amount(ctx, 1, 2)
    for minion in side.board:
        if minion is not ctx.source and ctx.system.is_minion_type(minion, "Dragon"):
            ctx.buff(minion, attack=amount, health=amount)


def _humming_bird_start_of_combat(ctx):
    side = ctx.source_side
    if side is None:
        return
    amount = _amount(ctx, 1, 2)
    for minion in side.board:
        if ctx.system.is_minion_type(minion, "Beast"):
            ctx.buff(minion, attack=amount)


def _clever_castaway_activate(ctx):
    candidates = [
        card.get("id")
        for card in _tavern_spell_definitions(ctx.system)
        if isinstance(card.get("id"), int)
    ]
    if not candidates:
        return

    ctx.system.discover_cards(
        ctx.source_player_id,
        candidates,
        count=3,
        resolver_key="multi_tavern_spell_discover",
        metadata={"remaining": 2 if ctx.is_golden else 1},
    )


def _crater_miner_battlecry(ctx):
    pending = ctx.system.get_pending_choice(ctx.source_player_id)
    if pending is not None:
        state = ctx.player_state()
        state["queued_crater_choices"] = int(
            state.get("queued_crater_choices", 0) or 0
        ) + 1
        state["queued_crater_golden"] = ctx.is_golden
        return

    _start_crater_choice(
        ctx.system,
        ctx.source_player_id,
        golden=ctx.is_golden,
    )


def _expert_aviator_rally(ctx):
    player = ctx.get_player()
    side = ctx.source_side
    if player is None or side is None:
        return

    candidates = [
        (index, card)
        for index, card in enumerate(player.hand)
        if isinstance(card, dict) and card.get("cardType") == "minion"
    ]
    candidates.sort(
        key=lambda item: (
            -int(item[1].get("attack", 0) or 0),
            item[0],
        )
    )

    count = 2 if ctx.is_golden else 1
    for _, card in candidates[:count]:
        if len(side.board) >= 7:
            break
        ctx.system.summon(
            side,
            card,
            count=1,
            event=ctx.event,
        )


def _mechagnome_after_play(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    played = ctx.event.get("card")
    if not ctx.system.is_minion_type(played, "Mech"):
        return

    attack = _amount(ctx, 3, 6)
    health = _amount(ctx, 1, 2)
    ctx.buff(played, attack=attack, health=health)


def _mechagnome_after_magnetize(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    magnetic_card = ctx.event.get("card")
    target = ctx.event.get("minion") or ctx.event.get("target")
    if not ctx.system.is_minion_type(magnetic_card, "Mech"):
        return
    if not isinstance(target, dict):
        return

    ctx.buff(
        target,
        attack=_amount(ctx, 3, 6),
        health=_amount(ctx, 1, 2),
    )


def _mind_muck_battlecry(ctx):
    target = ctx.event.get("target")
    if not isinstance(target, dict):
        return

    player = ctx.get_player()
    if player is None or player.tavern is None:
        return

    occupied = [
        (index, card)
        for index, card in enumerate(player.tavern.slots)
        if isinstance(card, dict)
    ]
    if not occupied:
        return

    tavern_index, consumed = ctx.random_choice(occupied)
    player.tavern.slots[tavern_index] = None

    multiplier = 2 if ctx.is_golden else 1
    ctx.buff(
        target,
        attack=int(consumed.get("attack", 0) or 0) * multiplier,
        health=int(consumed.get("health", 0) or 0) * multiplier,
    )


def _oozeling_gladiator_battlecry(ctx):
    _add_generated_many(
        ctx,
        SLIMY_SHIELD,
        4 if ctx.is_golden else 2,
    )


def _prodigious_tusker_friendly_attack(ctx):
    attacker = ctx.event.get("attacker")
    attacking_side = ctx.event.get("attacking_side")

    if attacking_side is None or attacking_side.player_id != ctx.source_player_id:
        return
    if attacker is ctx.source or not isinstance(attacker, dict):
        return

    _apply_blood_gems(
        ctx,
        attacker,
        count=2 if ctx.is_golden else 1,
    )


def _roadboar_rally(ctx):
    _add_generated_many(
        ctx,
        BLOOD_GEM,
        2 if ctx.is_golden else 1,
    )


def _scarlet_skull_deathrattle(ctx):
    side = ctx.source_side
    if side is None:
        return

    undead = [
        minion
        for minion in side.board
        if ctx.system.is_minion_type(minion, "Undead")
    ]
    target = ctx.random_choice(undead)
    if target is None:
        return

    if ctx.is_golden:
        ctx.buff(target, attack=2, health=4)
    else:
        ctx.buff(target, attack=1, health=2)


def _sellemental_sold(ctx):
    _add_generated_many(
        ctx,
        WATER_DROPLET,
        2 if ctx.is_golden else 1,
    )


def _shell_collector_battlecry(ctx):
    _add_generated_many(
        ctx,
        TAVERN_COIN,
        2 if ctx.is_golden else 1,
    )


def _tad_sold(ctx):
    definitions = _normal_tavern_minion_definitions(
        ctx.system,
        minion_type="Murloc",
    )
    _add_random_generated_minions(
        ctx,
        definitions,
        2 if ctx.is_golden else 1,
    )


def _thousandth_paper_drake_start_of_combat(ctx):
    side = ctx.source_side
    if side is None:
        return

    dragons = [
        minion
        for minion in side.board
        if ctx.system.is_minion_type(minion, "Dragon")
    ]
    count = 2 if ctx.is_golden else 1

    for target in dragons[:count]:
        ctx.buff(target, attack=1, health=2)
        ctx.grant_keyword(target, "Windfury")


def _winterfinner_damaged(ctx):
    if ctx.event.get("minion") is not ctx.source:
        return

    player = ctx.get_player()
    if player is None:
        return

    hand_minions = [
        card
        for card in player.hand
        if isinstance(card, dict) and card.get("cardType") == "minion"
    ]
    target = ctx.random_choice(hand_minions)
    if target is None:
        return

    if ctx.is_golden:
        ctx.buff(target, attack=4, health=2)
    else:
        ctx.buff(target, attack=2, health=1)


# =============================================================
# SPELLS / GENERATED SPELLS
# =============================================================


def register_spell_effects(effects):
    # Target rules
    for card_id in (
        BLOOD_GEM,
        SLIMY_SHIELD,
        MINI_TRIDENT,
    ):
        effects.register_target_rule(
            card_id,
            _friendly_board_targets,
        )

    # Blood Gem
    effects.register_effect(
        BLOOD_GEM,
        GameEvent.SPELL_CAST,
        _blood_gem_cast,
        zones=(EffectZone.EVENT_SOURCE,),
        family=TriggerFamily.SPELL,
        name="Blood Gem",
    )

    # Slimy Shield
    effects.register_effect(
        SLIMY_SHIELD,
        GameEvent.SPELL_CAST,
        _slimy_shield_cast,
        zones=(EffectZone.EVENT_SOURCE,),
        family=TriggerFamily.SPELL,
        name="Slimy Shield",
    )

    # Mini-Trident / golden Mini-Trident from golden Spellcraft
    effects.register_effect(
        MINI_TRIDENT,
        GameEvent.SPELL_CAST,
        _mini_trident_cast,
        zones=(EffectZone.EVENT_SOURCE,),
        family=TriggerFamily.SPELL,
        name="Mini-Trident",
    )

    # Tavern Coin
    effects.register_effect(
        TAVERN_COIN,
        GameEvent.SPELL_CAST,
        _tavern_coin_cast,
        zones=(EffectZone.EVENT_SOURCE,),
        family=TriggerFamily.SPELL,
        name="Tavern Coin",
    )

    # Gem Day
    effects.register_effect(
        GEM_DAY,
        GameEvent.SPELL_CAST,
        _gem_day_cast,
        zones=(EffectZone.EVENT_SOURCE,),
        family=TriggerFamily.SPELL,
        name="Gem Day",
    )


def _blood_gem_cast(ctx):
    target = ctx.event.get("target")
    if not isinstance(target, dict):
        return
    _apply_blood_gems(ctx, target, count=1)


def _slimy_shield_cast(ctx):
    target = ctx.event.get("target")
    if not isinstance(target, dict):
        return
    ctx.buff(target, attack=1, health=1)
    ctx.grant_keyword(target, "Taunt")


def _mini_trident_cast(ctx):
    target = ctx.event.get("target")
    if not isinstance(target, dict):
        return
    ctx.buff(
        target,
        attack=4 if ctx.is_golden else 2,
        until_next_turn=True,
    )


def _tavern_coin_cast(ctx):
    player = ctx.get_player()
    if player is not None:
        _add_gold(player, 1)


def _gem_day_cast(ctx):
    ctx.start_choice(
        "gem_day",
        ["attack", "health"],
        kind="choose_one",
    )


# =============================================================
# EMPTY CONTENT CATEGORIES FOR NOW
# =============================================================


def register_tavern_spell_effects(effects):
    """Current batch adds generated spells; pool Tavern spells come next."""


def register_hero_power_effects(effects):
    """Hero-power content is intentionally separate from this minion batch."""
