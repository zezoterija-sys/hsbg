"""Runtime effect corrections for the live 36.4.2 Battlegrounds Solos ruleset.

Card definitions are normalized in :mod:`patch_36_4_2`, but several existing
handlers contain balance numbers directly in Python.  This module replaces only
the registrations whose runtime behavior changed in 36.4.2, keeping patch
specific deltas out of the generic effect engine and out of Bob.
"""

from __future__ import annotations

from .patch_36_4_2 import CURRENT_RULESET
from ..effects import EffectZone
from ..events import GameEvent
from ..tier36_effects import (
    ASHEN_CORRUPTOR,
    DEVOUT_HELLCALLER,
    DRUSTFALLEN_BUTCHER,
    EREDAR_ESCAPIST,
    FIRE_FORGED_EVOKER,
    FORSAKEN_WEAVER,
    LURKING_LEVIATHAN,
    MIGHTY_DRAGONBREATH,
    NATURAL_BLESSING,
    PRIVATE_INVESTIGATOR,
    SANGUINE_CHAMPION,
    SANGUINE_REFINER,
    TASTY_LOBSTER,
    TICHONDRIUS,
    TYRAEL,
    UNLEASHED_MANA_SURGE,
    UTILITY_DRONE,
    BUTCHERING,
    _combat_side,
    _current_source_card_for_state,
    _friendly_cards,
    _friendly_of_type,
    _is_type,
    _permanent_combat_buff,
    _player,
    _state,
)


SOUL_REWINDER = 100949
CORRUPTED_CUPCAKES = 110407


def _remove_named(effects, card_id: int, *names: str) -> None:
    """Remove registrations by stable content-registration name."""

    remove = set(names)
    registrations = list(effects._effects.get(card_id, ()))
    effects._effects[card_id] = [
        registration
        for registration in registrations
        if registration.name not in remove
    ]


def _amount(ctx, normal: int, golden: int) -> int:
    return golden if ctx.is_golden else normal


def _rewind_event_once(ctx) -> None:
    """Undo one PLAYER_DAMAGED event once, even with several rewind effects.

    Multiple Soul Rewinders / Ashen Corruptors should each trigger their own
    secondary effect without healing the same damage more than once.
    """

    if ctx.event.context.get("_36_4_2_damage_rewound"):
        return

    player = _player(ctx)
    health_damage = int(ctx.event.get("health_damage", 0) or 0)
    armor_damage = int(ctx.event.get("armor_damage", 0) or 0)

    if health_damage:
        player.health = int(getattr(player, "health", 0) or 0) + health_damage
    if armor_damage:
        player.armor = int(getattr(player, "armor", 0) or 0) + armor_damage

    ctx.event.context["_36_4_2_damage_rewound"] = True


def _soul_rewinder(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    if int(ctx.event.get("amount", 0) or 0) <= 0:
        return

    _rewind_event_once(ctx)
    ctx.buff(ctx.source, health=_amount(ctx, 2, 4))


def _ashen_corruptor(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    if int(ctx.event.get("amount", 0) or 0) <= 0:
        return

    _rewind_event_once(ctx)
    amount = _amount(ctx, 2, 4)
    for card in getattr(_player(ctx).tavern, "slots", ()):
        if isinstance(card, dict):
            ctx.buff(
                card,
                attack=amount,
                health=amount,
                until_next_turn=True,
            )


def _tichondrius(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    if int(ctx.event.get("amount", 0) or 0) <= 0:
        return

    amount = _amount(ctx, 4, 8)
    for card in _friendly_of_type(ctx.system, _player(ctx), "Demon"):
        ctx.buff(card, attack=amount, health=amount)


def _devout_hellcaller(ctx):
    source_minion = ctx.event.get("source_minion")
    source_side = ctx.event.get("source_side")

    if source_side is None:
        return
    if getattr(source_side, "player_id", None) != ctx.source_player_id:
        return
    if source_minion is ctx.source:
        return
    if not _is_type(ctx.system, source_minion, "Demon"):
        return

    a, h = ((4, 4) if ctx.is_golden else (2, 2))
    _permanent_combat_buff(ctx, ctx.source, a, h)


def _tasty_lobster(ctx):
    side = _combat_side(ctx)
    if side is not None:
        beasts = [
            card
            for card in side.board
            if card is not ctx.source and _is_type(ctx.system, card, "Beast")
        ]
        if beasts:
            # The golden card doubles the ordinary numeric buff.
            attack = _amount(ctx, 2, 4)
            health = _amount(ctx, 1, 2)
            target = ctx.random_choice(beasts)
            ctx.buff(target, attack=attack, health=health)

    # Existing engine semantics model "improve future Tasty Lobsters" as a
    # playerbound stat improvement applied when later copies enter a zone.
    state = _state(ctx)
    state["tasty_lobster_future_attack"] = int(
        state.get("tasty_lobster_future_attack", 0) or 0
    ) + _amount(ctx, 2, 4)
    state["tasty_lobster_future_health"] = int(
        state.get("tasty_lobster_future_health", 0) or 0
    ) + _amount(ctx, 1, 2)


def _lurking_leviathan(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return

    summoned = ctx.event.get("minion")
    if summoned is ctx.source or not _is_type(ctx.system, summoned, "Beast"):
        return

    source = _current_source_card_for_state(ctx)
    improvement = int(source.get("_leviathan_improvement", 0) or 0)
    base = 6 if ctx.is_golden else 3
    step = 2 if ctx.is_golden else 1
    ctx.buff(summoned, attack=base + improvement)
    source["_leviathan_improvement"] = improvement + step

    index = ctx.source.get("_persistent_board_index")
    if index is not None:
        player = _player(ctx)
        if 0 <= index < len(player.board) and isinstance(player.board[index], dict):
            player.board[index]["_leviathan_improvement"] = source[
                "_leviathan_improvement"
            ]


def _eredar_escapist(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return

    damage = int(ctx.event.get("amount", 0) or 0)
    if damage <= 0:
        return

    source = _current_source_card_for_state(ctx)
    current = int(source.get("_eredar_damage", 0) or 0) + damage
    triggers, remainder = divmod(current, 4)
    source["_eredar_damage"] = remainder

    for _ in range(triggers * _amount(ctx, 1, 2)):
        ctx.system.add_generated_to_hand(
            ctx.source_player_id,
            CORRUPTED_CUPCAKES,
        )


def _private_investigator(ctx):
    state = _state(ctx)
    state["pending_gold_next_turn"] = int(
        state.get("pending_gold_next_turn", 0) or 0
    ) + _amount(ctx, 2, 4)


def _forsaken_weaver(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return

    spell = ctx.event.get("spell") or ctx.event.get("card")
    if not isinstance(spell, dict) or "tavern" not in spell.get("categories", []):
        return

    amount = _amount(ctx, 3, 6)
    state = _state(ctx)
    state["undead_global_attack"] = int(
        state.get("undead_global_attack", 0) or 0
    ) + amount

    player = _player(ctx)
    for card in list(player.board) + list(player.hand) + list(player.tavern.slots):
        if _is_type(ctx.system, card, "Undead"):
            ctx.system.apply_buff(card, attack=amount)
            card["_undead_global_applied"] = int(
                card.get("_undead_global_applied", 0) or 0
            ) + amount


def _fire_forged_improve(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return

    spell = ctx.event.get("spell") or ctx.event.get("card")
    if not isinstance(spell, dict) or "tavern" not in spell.get("categories", []):
        return

    source = _current_source_card_for_state(ctx)
    source["_fire_forged_attack"] = int(
        source.get("_fire_forged_attack", 0) or 0
    ) + _amount(ctx, 2, 4)
    source["_fire_forged_health"] = int(
        source.get("_fire_forged_health", 0) or 0
    ) + _amount(ctx, 1, 2)


def _fire_forged_start(ctx):
    source = _current_source_card_for_state(ctx)
    attack = _amount(ctx, 2, 4) + int(
        source.get("_fire_forged_attack", 0) or 0
    )
    # 36.4.2 raised the starting Health component from +1 to +2. The existing
    # permanent improvement step remains +1 Health per Tavern spell.
    health = _amount(ctx, 2, 4) + int(
        source.get("_fire_forged_health", 0) or 0
    )

    side = _combat_side(ctx)
    if side is None:
        return
    for card in side.board:
        if _is_type(ctx.system, card, "Dragon"):
            ctx.buff(card, attack=attack, health=health)


def _unleashed_mana_surge(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    if not _is_type(ctx.system, ctx.event.get("card"), "Elemental"):
        return

    a, h = ((4, 6) if ctx.is_golden else (2, 3))
    for card in _friendly_of_type(ctx.system, _player(ctx), "Elemental"):
        ctx.buff(card, attack=a, health=h)


def _utility_drone(ctx):
    a, h = ((8, 10) if ctx.is_golden else (4, 5))
    for card in _friendly_cards(_player(ctx)):
        count = int(card.get("_magnetization_count", 0) or 0)
        if count:
            ctx.buff(card, attack=a * count, health=h * count)


def _sanguine_refiner(ctx):
    state = _state(ctx)
    state["blood_gem_attack_bonus"] = int(
        state.get("blood_gem_attack_bonus", 0) or 0
    ) + _amount(ctx, 1, 2)
    state["blood_gem_health_bonus"] = int(
        state.get("blood_gem_health_bonus", 0) or 0
    ) + _amount(ctx, 2, 4)


def _sanguine_champion(ctx):
    state = _state(ctx)
    state["blood_gem_attack_bonus"] = int(
        state.get("blood_gem_attack_bonus", 0) or 0
    ) + _amount(ctx, 2, 4)
    state["blood_gem_health_bonus"] = int(
        state.get("blood_gem_health_bonus", 0) or 0
    ) + _amount(ctx, 1, 2)


def _drustfallen_butcher(ctx):
    for _ in range(_amount(ctx, 1, 2)):
        ctx.system.add_generated_to_hand(ctx.source_player_id, BUTCHERING)


def _tyrael(ctx):
    target = ctx.event.get("target")
    if not isinstance(target, dict) or target is ctx.source:
        return
    value = 100 if ctx.is_golden else 50
    target["attack"] = value
    target["health"] = value


def _mighty_dragonbreath(ctx):
    for card in _friendly_cards(_player(ctx)):
        ctx.buff(card, attack=3, health=2)
        if _is_type(ctx.system, card, "Dragon"):
            ctx.buff(card, attack=3, health=2)
        if ctx.system.has_keyword(card, "Divine Shield"):
            ctx.buff(card, attack=3, health=2)


def _natural_blessing(ctx):
    target = ctx.event.get("target")
    if not isinstance(target, dict):
        return

    target_types = [
        value
        for value in (target.get("minionTypes") or [target.get("minionType")])
        if value
    ]
    if not target_types:
        return

    for card in _friendly_cards(_player(ctx)):
        if any(_is_type(ctx.system, card, value) for value in target_types):
            ctx.buff(card, attack=2, health=1)


def register_36_4_2_effect_overrides(effects) -> None:
    """Replace hard-coded effect values with the current 36.4.2 behavior."""

    if CURRENT_RULESET.ruleset_id != "36.4.2-solos":
        return

    # Tier 2 / lower content not present in the original Tier 3-6 registry.
    _remove_named(effects, SOUL_REWINDER, "Soul Rewinder")
    effects.register_effect(
        SOUL_REWINDER,
        GameEvent.PLAYER_DAMAGED,
        _soul_rewinder,
        zones=(EffectZone.BOARD,),
        name="Soul Rewinder",
    )

    _remove_named(effects, DEVOUT_HELLCALLER, "Devout Hellcaller")
    effects.register_effect(
        DEVOUT_HELLCALLER,
        GameEvent.MINION_DAMAGED,
        _devout_hellcaller,
        zones=(EffectZone.COMBAT,),
        name="Devout Hellcaller",
    )

    _remove_named(effects, TASTY_LOBSTER, "Tasty Lobster")
    effects.register_deathrattle(
        TASTY_LOBSTER,
        _tasty_lobster,
        name="Tasty Lobster",
    )

    _remove_named(effects, PRIVATE_INVESTIGATOR, "Private Investigator")
    effects.register_activate(
        PRIVATE_INVESTIGATOR,
        1,
        _private_investigator,
        name="Private Investigator",
    )

    _remove_named(effects, ASHEN_CORRUPTOR, "Ashen Corruptor")
    effects.register_effect(
        ASHEN_CORRUPTOR,
        GameEvent.PLAYER_DAMAGED,
        _ashen_corruptor,
        zones=(EffectZone.BOARD,),
        name="Ashen Corruptor",
    )

    _remove_named(effects, TICHONDRIUS, "Tichondrius")
    effects.register_effect(
        TICHONDRIUS,
        GameEvent.PLAYER_DAMAGED,
        _tichondrius,
        zones=(EffectZone.BOARD,),
        name="Tichondrius",
    )

    _remove_named(effects, LURKING_LEVIATHAN, "Lurking Leviathan")
    effects.register_effect(
        LURKING_LEVIATHAN,
        GameEvent.MINION_SUMMONED,
        _lurking_leviathan,
        zones=(EffectZone.COMBAT,),
        name="Lurking Leviathan",
    )

    _remove_named(effects, EREDAR_ESCAPIST, "Eredar Escapist")
    effects.register_effect(
        EREDAR_ESCAPIST,
        GameEvent.PLAYER_DAMAGED,
        _eredar_escapist,
        zones=(EffectZone.BOARD,),
        name="Eredar Escapist",
    )

    _remove_named(
        effects,
        FIRE_FORGED_EVOKER,
        "Fire-forged Evoker improve",
        "Fire-forged Evoker",
    )
    effects.register_effect(
        FIRE_FORGED_EVOKER,
        GameEvent.SPELL_CAST,
        _fire_forged_improve,
        zones=(EffectZone.BOARD,),
        name="Fire-forged Evoker improve",
    )
    effects.register_start_of_combat(
        FIRE_FORGED_EVOKER,
        _fire_forged_start,
        name="Fire-forged Evoker",
    )

    _remove_named(effects, FORSAKEN_WEAVER, "Forsaken Weaver")
    effects.register_effect(
        FORSAKEN_WEAVER,
        GameEvent.SPELL_CAST,
        _forsaken_weaver,
        zones=(EffectZone.BOARD,),
        name="Forsaken Weaver",
    )

    _remove_named(effects, UNLEASHED_MANA_SURGE, "Unleashed Mana Surge")
    effects.register_effect(
        UNLEASHED_MANA_SURGE,
        GameEvent.CARD_PLAYED,
        _unleashed_mana_surge,
        zones=(EffectZone.BOARD,),
        name="Unleashed Mana Surge",
    )

    _remove_named(effects, UTILITY_DRONE, "Utility Drone")
    effects.register_end_of_turn(
        UTILITY_DRONE,
        _utility_drone,
        name="Utility Drone",
    )

    _remove_named(effects, SANGUINE_REFINER, "Sanguine Refiner")
    effects.register_rally(
        SANGUINE_REFINER,
        _sanguine_refiner,
        name="Sanguine Refiner",
    )

    _remove_named(
        effects,
        SANGUINE_CHAMPION,
        "Sanguine Champion Battlecry",
        "Sanguine Champion Deathrattle",
    )
    effects.register_battlecry(
        SANGUINE_CHAMPION,
        _sanguine_champion,
        name="Sanguine Champion Battlecry",
    )
    effects.register_deathrattle(
        SANGUINE_CHAMPION,
        _sanguine_champion,
        name="Sanguine Champion Deathrattle",
    )

    _remove_named(effects, DRUSTFALLEN_BUTCHER, "Drustfallen Butcher")
    effects.register_avenge(
        DRUSTFALLEN_BUTCHER,
        3,
        _drustfallen_butcher,
        name="Drustfallen Butcher",
    )

    tyrael_ability = effects._activated.get(TYRAEL)
    target_provider = (
        tyrael_ability.target_provider
        if tyrael_ability is not None
        else None
    )
    _remove_named(effects, TYRAEL, "Tyrael")
    effects.register_activate(
        TYRAEL,
        1,
        _tyrael,
        target_provider=target_provider,
        name="Tyrael",
    )

    _remove_named(effects, MIGHTY_DRAGONBREATH, f"Tier 3-6 spell {MIGHTY_DRAGONBREATH}")
    effects.register_effect(
        MIGHTY_DRAGONBREATH,
        GameEvent.SPELL_CAST,
        _mighty_dragonbreath,
        zones=(EffectZone.EVENT_SOURCE,),
        name=f"Tier 3-6 spell {MIGHTY_DRAGONBREATH}",
    )

    _remove_named(effects, NATURAL_BLESSING, f"Tier 3-6 spell {NATURAL_BLESSING}")
    effects.register_effect(
        NATURAL_BLESSING,
        GameEvent.SPELL_CAST,
        _natural_blessing,
        zones=(EffectZone.EVENT_SOURCE,),
        name=f"Tier 3-6 spell {NATURAL_BLESSING}",
    )
