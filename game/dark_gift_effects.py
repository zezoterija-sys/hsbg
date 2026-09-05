"""Runtime effects for Season 14 Dark Gifts.

Dark Gifts are attached effect identities. The physical minion remains the
``EffectContext.source`` while ``effect_state`` is the Gift attachment, so the
normal effect registry resolves Gift triggers in hand, recruit, and combat.

The unusual Gifts are implemented through generic event capabilities instead
of card-name branches inside CombatEngine: durable Divine Shield reacts to
shield-loss events, special Reborn reacts to REBORN, combat persistence diffs
back to the persistent board copy, and permanent Spellcraft uses pre/post spell
resolution bookkeeping.
"""

from __future__ import annotations

from copy import deepcopy

from .effects import EffectZone, TriggerFamily
from .events import GameEvent


SUNKEN_PERSISTENCE = 133310
HARPYS_TALONS = 132279
JAWS_OF_DEATH = 132443
FORTITUDE = 133421
AFFINITY = 133860
SHARPENED_SWORD = 133423
TOUGHENED_SHIELD = 133424
STEADY_GROWTH = 132733
TIME_TURNING = 132448
FURTIVENESS = 133472
CONSANGUINITY = 133474
FRESH_PERSPECTIVE = 132734
REPLICATION = 132445
BATTLE_SCARS_EARLY = 133476
DEATHS_EMBRACE_EARLY = 133478
SPELL_SIPHON_EARLY = 133480
GILDING = 132441
DOUBLE_VISION = 132485
TORETHS_BLESSING = 132442
AMALGAMATION = 132790
DEMONOLOGY = 133351
POLARIZATION = 133344
MYSTIC_ESSENCE = 132203
TARECGOSAS_BLESSING = 132732
DEXTERITY_EARLY = 133361
INCUBATION = 132202
ECHOING_VOICE = 132208
OFFENSIVE_SACRIFICE = 132192
DEFENSIVE_SACRIFICE = 132200
TRANSCENDENCE = 133482
BATTLE_SCARS_LATE = 132553
DEATHS_EMBRACE_LATE = 132554
SPELL_SIPHON_LATE = 132555
ADMIRATION = 132207
TOXICITY = 133353
CHARISMA = 132201
RESISTANCE = 132205
HOSTILITY = 133359
DEXTERITY_LATE = 133457
GOLEMANCY = 132835
PERSISTING_HORROR = 132276
TITANIC_STRENGTH = 133363
INVULNERABILITY = 132833

BLOOD_GEM = 70136
DEMON_FODDER = 130084

ALL_DARK_GIFT_IDS = frozenset(
    {
        SUNKEN_PERSISTENCE,
        HARPYS_TALONS,
        JAWS_OF_DEATH,
        FORTITUDE,
        AFFINITY,
        SHARPENED_SWORD,
        TOUGHENED_SHIELD,
        STEADY_GROWTH,
        TIME_TURNING,
        FURTIVENESS,
        CONSANGUINITY,
        FRESH_PERSPECTIVE,
        REPLICATION,
        BATTLE_SCARS_EARLY,
        DEATHS_EMBRACE_EARLY,
        SPELL_SIPHON_EARLY,
        GILDING,
        DOUBLE_VISION,
        TORETHS_BLESSING,
        AMALGAMATION,
        DEMONOLOGY,
        POLARIZATION,
        MYSTIC_ESSENCE,
        TARECGOSAS_BLESSING,
        DEXTERITY_EARLY,
        INCUBATION,
        ECHOING_VOICE,
        OFFENSIVE_SACRIFICE,
        DEFENSIVE_SACRIFICE,
        TRANSCENDENCE,
        BATTLE_SCARS_LATE,
        DEATHS_EMBRACE_LATE,
        SPELL_SIPHON_LATE,
        ADMIRATION,
        TOXICITY,
        CHARISMA,
        RESISTANCE,
        HOSTILITY,
        DEXTERITY_LATE,
        GOLEMANCY,
        PERSISTING_HORROR,
        TITANIC_STRENGTH,
        INVULNERABILITY,
    }
)


# ---------------------------------------------------------------------------
# Acquisition / static Gift state
# ---------------------------------------------------------------------------


def _attachment(gift: dict, acquired_turn: int) -> dict:
    attached = deepcopy(gift)
    attached["_dark_gift"] = True
    attached["_dark_gift_acquired_turn"] = int(acquired_turn)
    return attached


def _ensure_registered(effects) -> None:
    if getattr(effects, "_dark_gift_effects_registered", False):
        return
    register_dark_gift_effects(effects)
    _register_global_dark_gift_hooks(effects)
    effects._dark_gift_effects_registered = True


def _make_golden_in_place(minion: dict) -> None:
    minion["isGolden"] = True
    minion["golden"] = True
    if minion.get("attackGold") is not None:
        minion["attack"] = int(minion["attackGold"])
    if minion.get("healthGold") is not None:
        minion["health"] = int(minion["healthGold"])
    if minion.get("textGold") is not None:
        minion["text"] = minion["textGold"]
    minion["_dark_gift_no_triple_reward"] = True


def _history_value(effects, player_id: int, gift_id: int) -> tuple[int, int]:
    state = effects.get_player_state(player_id)
    if gift_id == BATTLE_SCARS_EARLY:
        return int(state.get("battlecries_triggered_game", 0) or 0), 2
    if gift_id == BATTLE_SCARS_LATE:
        return int(state.get("battlecries_triggered_game", 0) or 0), 3
    if gift_id == DEATHS_EMBRACE_EARLY:
        return int(state.get("deathrattles_triggered_game", 0) or 0), 1
    if gift_id == DEATHS_EMBRACE_LATE:
        return int(state.get("deathrattles_triggered_game", 0) or 0), 2
    if gift_id == SPELL_SIPHON_EARLY:
        return int(state.get("tavern_spells_cast_game", 0) or 0), 2
    if gift_id == SPELL_SIPHON_LATE:
        return int(state.get("tavern_spells_cast_game", 0) or 0), 3
    return 0, 0


def attach_dark_gift(
    effects,
    player_id: int,
    minion: dict,
    gift: dict,
    *,
    acquired_turn: int,
) -> dict:
    """Attach one Gift and apply effects that happen immediately on acquisition."""

    _ensure_registered(effects)
    gift_id = int(gift["id"])
    attached = _attachment(gift, acquired_turn)

    if gift_id == HARPYS_TALONS:
        effects.grant_keyword(minion, "Divine Shield")
        effects.grant_keyword(minion, "Windfury")
    elif gift_id == FORTITUDE:
        effects.apply_buff(minion, attack=5, health=5)
    elif gift_id == FURTIVENESS:
        effects.grant_keyword(minion, "Stealth")
    elif gift_id == GILDING:
        _make_golden_in_place(minion)
    elif gift_id == AMALGAMATION:
        minion["minionType"] = "All"
        minion["minionTypes"] = ["All"]
    elif gift_id == INCUBATION:
        effects.apply_buff(minion, attack=4, health=4)
        attached["_incubation_due_turn"] = int(acquired_turn) + 2
        attached["_incubation_doubled"] = False
    elif gift_id == OFFENSIVE_SACRIFICE:
        effects.apply_buff(minion, attack=10)
    elif gift_id == DEFENSIVE_SACRIFICE:
        effects.apply_buff(minion, health=10)
    elif gift_id == TOXICITY:
        effects.grant_keyword(minion, "Venomous")
    elif gift_id == PERSISTING_HORROR:
        effects.grant_keyword(minion, "Reborn")
        minion["_dark_gift_persisting_horror"] = True
    elif gift_id == TITANIC_STRENGTH:
        effects.apply_buff(minion, attack=1000)
    elif gift_id == INVULNERABILITY:
        # CombatEngine already interprets Immune on BG minions as
        # "Immune while attacking".
        effects.grant_keyword(minion, "Immune")
    elif gift_id == TORETHS_BLESSING:
        attached["_shield_hits_remaining"] = 3
    elif gift_id == TARECGOSAS_BLESSING:
        minion["_dark_gift_tarecgosa_persistence"] = True
    elif gift_id == SUNKEN_PERSISTENCE:
        minion["_dark_gift_spellcraft_permanent"] = True

    count, amount = _history_value(effects, player_id, gift_id)
    if count and amount:
        effects.apply_buff(minion, attack=count * amount, health=count * amount)

    if gift_id == STEADY_GROWTH:
        # Final 36.2.2 values by offering/acquisition turn.
        attached["_steady_growth_stats"] = {
            3: (2, 2),
            4: (2, 3),
            5: (3, 4),
        }.get(int(acquired_turn), (3, 4))

    minion.setdefault("_attachments", []).append(attached)
    minion.setdefault("_dark_gift_ids", []).append(gift_id)
    minion.setdefault("_dark_gift_names", []).append(attached.get("name"))
    return attached


def after_dark_gift_acquired(effects, player_id: int, minion: dict, gift: dict) -> None:
    """Compatibility helper; Double Vision is resolved by CARD_ADDED_TO_HAND."""
    return None


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _same_player(ctx) -> bool:
    return ctx.event.get("player_id") == ctx.source_player_id


def _real_types(system, card: dict) -> list[str]:
    values = list(card.get("minionTypes") or [])
    if not values and card.get("minionType"):
        values = [card["minionType"]]
    return [str(value) for value in values if str(value) != "All"]


def _eligible_generated_minions(system, minion_type: str) -> list[dict]:
    result = []
    for card in getattr(system.game.pool, "card_definitions", ()):
        if card.get("cardType") != "minion" or card.get("pool") is not True:
            continue
        if card.get("isDuosOnly", False):
            continue
        if "tavern" not in (card.get("categories") or ()):
            continue
        if system.is_minion_type(card, minion_type):
            result.append(card)
    return result


def _tavern_spell_definitions(system) -> list[dict]:
    return [
        card
        for card in getattr(system.game.pool, "card_definitions", ())
        if card.get("cardType") == "spell"
        and card.get("pool") is True
        and not card.get("isDuosOnly", False)
        and "tavern" in (card.get("categories") or ())
    ]


def _force_magnetize(system, source: dict, target: dict) -> None:
    """Apply Polarization's explicit Magnetize instruction to any random Mech."""

    target["attack"] = int(target.get("attack", 0) or 0) + int(source.get("attack", 0) or 0)
    target["health"] = int(target.get("health", 0) or 0) + int(source.get("health", 0) or 0)
    for keyword in source.get("keywords", ()):
        if str(keyword).casefold() == "magnetic":
            continue
        if not system.has_keyword(target, str(keyword)):
            target.setdefault("keywords", []).append(keyword)
    target.setdefault("_attachments", []).append(deepcopy(source))
    target["_magnetization_count"] = int(target.get("_magnetization_count", 0) or 0) + 1


def _most_common_type(ctx) -> str | None:
    system = getattr(ctx.game, "dark_gifts", None)
    if system is not None:
        return system._most_common_type(ctx.source_player_id)
    return None


def _find_attachment(card: dict, gift_id: int) -> dict | None:
    for attachment in card.get("_attachments", ()):
        if isinstance(attachment, dict) and attachment.get("id") == gift_id:
            return attachment
    return None


def _persistent_board_card(ctx):
    index = ctx.source.get("_persistent_board_index")
    if index is None or ctx.source_player_id is None:
        return None
    player = ctx.game.get_player(ctx.source_player_id)
    if not 0 <= int(index) < len(player.board):
        return None
    card = player.board[int(index)]
    if not isinstance(card, dict):
        return None
    if card.get("id") != ctx.source.get("id"):
        return None
    return card


def _track_combat_max_health(ctx, key: str) -> None:
    if ctx.event.event_type == GameEvent.COMBAT_START:
        ctx.effect_state[key] = max(1, int(ctx.source.get("health", 1) or 1))
        ctx.effect_state[f"{key}_damage"] = 0
        return
    if ctx.event.event_type != GameEvent.MINION_DAMAGED:
        return
    if ctx.event.get("minion") is not ctx.source:
        return
    damage_key = f"{key}_damage"
    damage = int(ctx.effect_state.get(damage_key, 0) or 0) + int(ctx.event.get("amount", 0) or 0)
    ctx.effect_state[damage_key] = damage
    reconstructed = int(ctx.source.get("health", 0) or 0) + damage
    ctx.effect_state[key] = max(int(ctx.effect_state.get(key, 0) or 0), reconstructed)


# ---------------------------------------------------------------------------
# Trigger handlers
# ---------------------------------------------------------------------------


def _sharpened_sword(ctx):
    if _same_player(ctx):
        ctx.buff(ctx.source, attack=3)


def _toughened_shield(ctx):
    if _same_player(ctx):
        ctx.buff(ctx.source, health=3)


def _dexterity_early(ctx):
    if _same_player(ctx):
        ctx.buff(ctx.source, attack=2, health=2)


def _dexterity_late(ctx):
    if _same_player(ctx):
        ctx.buff(ctx.source, attack=4, health=4)


def _steady_growth(ctx):
    attack, health = ctx.effect_state.get("_steady_growth_stats", (3, 4))
    ctx.buff(ctx.source, attack=attack, health=health)


def _incubation(ctx):
    if ctx.effect_state.get("_incubation_doubled"):
        return
    due = int(ctx.effect_state.get("_incubation_due_turn", 10**9))
    if int(getattr(ctx.game, "round_number", 0) or 0) < due:
        return
    ctx.buff(
        ctx.source,
        attack=int(ctx.source.get("attack", 0) or 0),
        health=int(ctx.source.get("health", 0) or 0),
    )
    ctx.effect_state["_incubation_doubled"] = True


def _double_vision(ctx):
    if ctx.event.get("card") is not ctx.source:
        return
    if ctx.effect_state.get("_double_vision_resolved"):
        return
    ctx.effect_state["_double_vision_resolved"] = True
    ctx.system.add_generated_to_hand(ctx.source_player_id, int(ctx.source["id"]))


def _fresh_perspective(ctx):
    ctx.system.grant_free_refreshes(ctx.source_player_id, 2)


def _consanguinity(ctx):
    if not _same_player(ctx):
        return
    for _ in range(2):
        if ctx.system.add_generated_to_hand(ctx.source_player_id, BLOOD_GEM) is None:
            break


def _replication(ctx):
    count = int(ctx.effect_state.get("_replication_turns", 0) or 0) + 1
    if count < 2:
        ctx.effect_state["_replication_turns"] = count
        return
    ctx.effect_state["_replication_turns"] = 0
    ctx.system.add_generated_to_hand(ctx.source_player_id, int(ctx.source["id"]))


def _affinity(ctx):
    count = int(ctx.effect_state.get("_affinity_turns", 0) or 0) + 1
    if count < 2:
        ctx.effect_state["_affinity_turns"] = count
        return
    ctx.effect_state["_affinity_turns"] = 0

    types = _real_types(ctx.system, ctx.source)
    if not types:
        return
    chosen_type = ctx.effect_state.get("_affinity_type")
    if chosen_type not in types:
        chosen_type = ctx.random_choice(types)
        ctx.effect_state["_affinity_type"] = chosen_type

    chosen = ctx.random_choice(_eligible_generated_minions(ctx.system, chosen_type))
    if chosen is not None:
        ctx.system.add_generated_to_hand(ctx.source_player_id, chosen)


def _time_turning(ctx):
    ctx.system.trigger_card_family(
        ctx.source,
        TriggerFamily.END_OF_TURN,
        player_id=ctx.source_player_id,
        zone=EffectZone.BOARD,
        position=ctx.source_position,
    )


def _echoing_voice(ctx):
    ctx.system.trigger_card_family(
        ctx.source,
        TriggerFamily.BATTLECRY,
        player_id=ctx.source_player_id,
        zone=EffectZone.BOARD,
        position=ctx.source_position,
    )


def _jaws_of_death(ctx):
    ctx.system.trigger_card_family(
        ctx.source,
        TriggerFamily.DEATHRATTLE,
        player_id=ctx.source_player_id,
        zone=EffectZone.COMBAT,
        side=ctx.source_side,
        position=ctx.source_position,
    )


def _polarization(ctx):
    chosen = ctx.random_choice(_eligible_generated_minions(ctx.system, "Mech"))
    if chosen is None:
        return
    magnetic = ctx.system.create_card(int(chosen["id"]), generated=True)
    _force_magnetize(ctx.system, magnetic, ctx.source)


def _mystic_essence(ctx):
    chosen = ctx.random_choice(_tavern_spell_definitions(ctx.system))
    if chosen is not None:
        ctx.system.add_generated_to_hand(ctx.source_player_id, chosen)


def _demonology(ctx):
    if not _same_player(ctx):
        return
    state = ctx.player_state()
    state["dark_gift_fodder_refreshes"] = int(state.get("dark_gift_fodder_refreshes", 0) or 0) + 3


def _history_growth(ctx, family: TriggerFamily, amount: int):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    if ctx.event.get("family") != family:
        return
    ctx.buff(ctx.source, attack=amount, health=amount)


def _battle_scars_early(ctx):
    _history_growth(ctx, TriggerFamily.BATTLECRY, 2)


def _battle_scars_late(ctx):
    _history_growth(ctx, TriggerFamily.BATTLECRY, 3)


def _deaths_embrace_early(ctx):
    _history_growth(ctx, TriggerFamily.DEATHRATTLE, 1)


def _deaths_embrace_late(ctx):
    _history_growth(ctx, TriggerFamily.DEATHRATTLE, 2)


def _spell_siphon(ctx, amount: int):
    if not _same_player(ctx):
        return
    spell = ctx.event.get("spell") or ctx.event.get("card")
    if not isinstance(spell, dict) or "tavern" not in (spell.get("categories") or ()):
        return
    ctx.buff(ctx.source, attack=amount, health=amount)


def _spell_siphon_early(ctx):
    _spell_siphon(ctx, 2)


def _spell_siphon_late(ctx):
    _spell_siphon(ctx, 3)


def _transcendence(ctx):
    ctx.buff(ctx.source, attack=2 * int(ctx.source.get("attack", 0) or 0), health=2 * int(ctx.source.get("health", 0) or 0))


def _resistance(ctx):
    ctx.buff(ctx.source, health=int(ctx.source.get("health", 0) or 0))


def _hostility(ctx):
    ctx.buff(ctx.source, attack=int(ctx.source.get("attack", 0) or 0))


def _admiration(ctx):
    side = ctx.source_side
    if side is None or ctx.source not in side.board:
        return
    index = side.board.index(ctx.source)
    if index <= 0:
        return
    ctx.buff(ctx.source, attack=int(side.board[index - 1].get("attack", 0) or 0))


def _charisma(ctx):
    if not _same_player(ctx):
        return
    minion_type = _most_common_type(ctx)
    if minion_type is None:
        return
    chosen = ctx.random_choice(_eligible_generated_minions(ctx.system, minion_type))
    if chosen is not None:
        ctx.system.add_generated_to_hand(ctx.source_player_id, chosen)


def _offensive_sacrifice(ctx):
    side = ctx.source_side
    if side is None:
        return
    target = ctx.random_choice([card for card in side.board if isinstance(card, dict)])
    if target is not None:
        ctx.buff(target, attack=max(0, int(ctx.source.get("attack", 0) or 0)))


def _defensive_track(ctx):
    _track_combat_max_health(ctx, "_defensive_max_health")


def _defensive_sacrifice(ctx):
    side = ctx.source_side
    if side is None:
        return
    target = ctx.random_choice([card for card in side.board if isinstance(card, dict)])
    if target is not None:
        ctx.buff(target, health=max(0, int(ctx.effect_state.get("_defensive_max_health", 0) or 0)))


def _golemancy_track(ctx):
    _track_combat_max_health(ctx, "_golemancy_max_health")


def _golemancy(ctx):
    attack = max(0, int(ctx.source.get("attack", 0) or 0))
    health = max(1, int(ctx.effect_state.get("_golemancy_max_health", 1) or 1))
    ctx.summon(
        {
            "id": -132835,
            "name": "Dark Gift Golem",
            "cardType": "minion",
            "attack": attack,
            "health": health,
            "tier": 1,
            "keywords": [],
            "minionTypes": [],
            "_generated": True,
        }
    )


def _toreth_shield(ctx):
    if ctx.event.get("minion") is not ctx.source:
        return
    remaining = int(ctx.effect_state.get("_shield_hits_remaining", 3) or 0)
    if remaining <= 0:
        return
    remaining -= 1
    ctx.effect_state["_shield_hits_remaining"] = remaining
    if remaining > 0:
        ctx.source["_combat_divine_shield"] = True


def _persisting_track(ctx):
    _track_combat_max_health(ctx, "_persisting_full_health")


def _persisting_reborn(ctx):
    if ctx.event.get("minion") is not ctx.source:
        return
    full_health = max(1, int(ctx.effect_state.get("_persisting_full_health", 1) or 1))
    ctx.source["health"] = full_health


def _tarecgosa_start(ctx):
    ctx.effect_state["_tarec_start_attack"] = int(ctx.source.get("attack", 0) or 0)
    ctx.effect_state["_tarec_start_health"] = int(ctx.source.get("health", 0) or 0)
    ctx.effect_state["_tarec_start_keywords"] = tuple(str(value) for value in ctx.source.get("keywords", ()))
    ctx.effect_state["_tarec_damage"] = 0
    ctx.effect_state["_tarec_max_health"] = int(ctx.source.get("health", 0) or 0)
    ctx.effect_state["_tarec_persisted"] = False


def _tarecgosa_damage(ctx):
    if ctx.event.get("minion") is not ctx.source:
        return
    damage = int(ctx.effect_state.get("_tarec_damage", 0) or 0) + int(ctx.event.get("amount", 0) or 0)
    ctx.effect_state["_tarec_damage"] = damage
    reconstructed = int(ctx.source.get("health", 0) or 0) + damage
    ctx.effect_state["_tarec_max_health"] = max(int(ctx.effect_state.get("_tarec_max_health", 0) or 0), reconstructed)


def _persist_tarecgosa(ctx):
    if ctx.effect_state.get("_tarec_persisted"):
        return
    original = _persistent_board_card(ctx)
    if original is None:
        return

    start_attack = int(ctx.effect_state.get("_tarec_start_attack", ctx.source.get("attack", 0)) or 0)
    start_health = int(ctx.effect_state.get("_tarec_start_health", 1) or 1)
    final_attack = int(ctx.source.get("attack", 0) or 0)
    damage = int(ctx.effect_state.get("_tarec_damage", 0) or 0)
    final_max_health = max(
        int(ctx.effect_state.get("_tarec_max_health", 0) or 0),
        int(ctx.source.get("health", 0) or 0) + damage,
    )

    gained_attack = max(0, final_attack - start_attack)
    gained_health = max(0, final_max_health - start_health)
    if gained_attack or gained_health:
        ctx.system.apply_buff(original, attack=2 * gained_attack, health=2 * gained_health)

    start_keywords = {value.casefold() for value in ctx.effect_state.get("_tarec_start_keywords", ())}
    for keyword in ctx.source.get("keywords", ()):
        if str(keyword).casefold() not in start_keywords:
            ctx.system.grant_keyword(original, str(keyword))

    ctx.effect_state["_tarec_persisted"] = True


# ---------------------------------------------------------------------------
# Global post-processing hooks for mechanics that span an event resolution
# ---------------------------------------------------------------------------


def _sunken_source_for_spell(effects, event):
    player_id = event.get("player_id")
    spell = event.get("spell") or event.get("card")
    if player_id is None or not isinstance(spell, dict):
        return None
    source_id = spell.get("_spellcraft_source_id")
    if source_id is None or not spell.get("_spellcraft_temporary", False):
        return None
    player = effects.game.get_player(player_id)
    for card in player.board:
        if (
            isinstance(card, dict)
            and card.get("id") == source_id
            and card.get("_dark_gift_spellcraft_permanent", False)
        ):
            return card
    return None


def _sunken_spell_pre(effects, event):
    if _sunken_source_for_spell(effects, event) is None:
        return
    target = event.get("target")
    if not isinstance(target, dict):
        return
    event.context["_sunken_target"] = target
    event.context["_sunken_stat_len"] = len(target.get("_temporary_stat_modifiers", ()))
    event.context["_sunken_keyword_counts"] = {
        str(keyword): len(info.get("expiries", ()))
        for keyword, info in target.get("_temporary_keywords", {}).items()
    }


def _sunken_spell_post(effects, event):
    target = event.context.get("_sunken_target")
    if not isinstance(target, dict):
        return

    keep = int(event.context.get("_sunken_stat_len", 0) or 0)
    modifiers = list(target.get("_temporary_stat_modifiers", ()))
    if len(modifiers) > keep:
        # Stats are already applied. Removing only the expiry records converts
        # newly applied Spellcraft stats into permanent stats.
        target["_temporary_stat_modifiers"] = modifiers[:keep]

    old_counts = event.context.get("_sunken_keyword_counts", {})
    temporary = target.get("_temporary_keywords", {})
    for keyword, info in list(temporary.items()):
        old_count = int(old_counts.get(str(keyword), 0) or 0)
        expiries = list(info.get("expiries", ()))
        if len(expiries) <= old_count:
            continue
        info["expiries"] = expiries[:old_count]
        permanent = target.setdefault("_permanent_keyword_grants", [])
        if keyword not in permanent:
            permanent.append(keyword)
        if not info["expiries"]:
            temporary.pop(keyword, None)


def _demonology_refresh_post(effects, event):
    player_id = event.get("player_id")
    if player_id is None:
        return
    state = effects.get_player_state(player_id)
    remaining = int(state.get("dark_gift_fodder_refreshes", 0) or 0)
    if remaining <= 0:
        return

    try:
        fodder = effects.create_card(DEMON_FODDER, generated=True)
    except KeyError:
        return

    player = effects.game.get_player(player_id)
    player.tavern.slots.append(fodder)
    state["dark_gift_fodder_refreshes"] = remaining - 1
    effects.events.emit(
        GameEvent.TAVERN_CARD_APPEARED,
        player_id=player_id,
        card=fodder,
        tavern_slot=len(player.tavern.slots) - 1,
        dark_gift="Demonology",
    )


def _register_global_dark_gift_hooks(effects) -> None:
    effects.events.register(GameEvent.SPELL_CAST, lambda event: _sunken_spell_pre(effects, event), order=-1000)
    effects.events.register(GameEvent.SPELL_CAST, lambda event: _sunken_spell_post(effects, event), order=1000)
    effects.events.register(GameEvent.TAVERN_REFRESHED, lambda event: _demonology_refresh_post(effects, event), order=1000)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def register_dark_gift_effects(effects) -> None:
    """Register all event-driven Season 14 Dark Gift identities."""

    board = (EffectZone.BOARD,)
    hand = (EffectZone.HAND,)
    board_hand = (EffectZone.BOARD, EffectZone.HAND)
    board_combat = (EffectZone.BOARD, EffectZone.COMBAT)
    combat = (EffectZone.COMBAT,)

    effects.register_effect(SHARPENED_SWORD, GameEvent.CARD_PLAYED, _sharpened_sword, zones=board, name="Dark Gift: Sharpened Sword")
    effects.register_effect(TOUGHENED_SHIELD, GameEvent.CARD_PLAYED, _toughened_shield, zones=board, name="Dark Gift: Toughened Shield")
    effects.register_effect(DEXTERITY_EARLY, GameEvent.CARD_PLAYED, _dexterity_early, zones=board, name="Dark Gift: Dexterity +2/+2")
    effects.register_effect(DEXTERITY_LATE, GameEvent.CARD_PLAYED, _dexterity_late, zones=board, name="Dark Gift: Dexterity +4/+4")
    effects.register_effect(DOUBLE_VISION, GameEvent.CARD_ADDED_TO_HAND, _double_vision, zones=hand, name="Dark Gift: Double Vision")

    effects.register_end_of_turn(STEADY_GROWTH, _steady_growth, name="Dark Gift: Steady Growth")
    effects.register_effect(INCUBATION, GameEvent.TURN_START, _incubation, zones=board_hand, name="Dark Gift: Incubation")
    effects.register_deathrattle(FRESH_PERSPECTIVE, _fresh_perspective, name="Dark Gift: Fresh Perspective")
    effects.register_rally(CONSANGUINITY, _consanguinity, name="Dark Gift: Consanguinity")
    effects.register_end_of_turn(REPLICATION, _replication, name="Dark Gift: Replication")
    effects.register_end_of_turn(AFFINITY, _affinity, name="Dark Gift: Affinity")
    effects.register_start_of_turn(TIME_TURNING, _time_turning, name="Dark Gift: Time Turning")
    effects.register_end_of_turn(ECHOING_VOICE, _echoing_voice, name="Dark Gift: Echoing Voice")
    effects.register_start_of_combat(JAWS_OF_DEATH, _jaws_of_death, name="Dark Gift: Jaws of Death")
    effects.register_end_of_turn(POLARIZATION, _polarization, name="Dark Gift: Polarization")
    effects.register_deathrattle(MYSTIC_ESSENCE, _mystic_essence, name="Dark Gift: Mystic Essence")
    effects.register_rally(DEMONOLOGY, _demonology, name="Dark Gift: Demonology")

    effects.register_effect(BATTLE_SCARS_EARLY, GameEvent.TRIGGER_RESOLVED, _battle_scars_early, zones=board_combat, name="Dark Gift: Battle Scars early")
    effects.register_effect(BATTLE_SCARS_LATE, GameEvent.TRIGGER_RESOLVED, _battle_scars_late, zones=board_combat, name="Dark Gift: Battle Scars late")
    effects.register_effect(DEATHS_EMBRACE_EARLY, GameEvent.TRIGGER_RESOLVED, _deaths_embrace_early, zones=board_combat, name="Dark Gift: Death's Embrace early")
    effects.register_effect(DEATHS_EMBRACE_LATE, GameEvent.TRIGGER_RESOLVED, _deaths_embrace_late, zones=board_combat, name="Dark Gift: Death's Embrace late")
    effects.register_effect(SPELL_SIPHON_EARLY, GameEvent.SPELL_CAST, _spell_siphon_early, zones=board, name="Dark Gift: Spell Siphon early")
    effects.register_effect(SPELL_SIPHON_LATE, GameEvent.SPELL_CAST, _spell_siphon_late, zones=board, name="Dark Gift: Spell Siphon late")

    effects.register_start_of_combat(TRANSCENDENCE, _transcendence, name="Dark Gift: Transcendence")
    effects.register_start_of_combat(RESISTANCE, _resistance, name="Dark Gift: Resistance")
    effects.register_start_of_combat(HOSTILITY, _hostility, name="Dark Gift: Hostility")
    effects.register_start_of_combat(ADMIRATION, _admiration, name="Dark Gift: Admiration")
    effects.register_rally(CHARISMA, _charisma, name="Dark Gift: Charisma")
    effects.register_deathrattle(OFFENSIVE_SACRIFICE, _offensive_sacrifice, name="Dark Gift: Offensive Sacrifice")
    effects.register_deathrattle(DEFENSIVE_SACRIFICE, _defensive_sacrifice, name="Dark Gift: Defensive Sacrifice")
    effects.register_deathrattle(GOLEMANCY, _golemancy, name="Dark Gift: Golemancy")

    # Max-health trackers for effects whose Deathrattles need pre-damage Health.
    effects.register_effect(DEFENSIVE_SACRIFICE, GameEvent.COMBAT_START, _defensive_track, zones=combat, name="Dark Gift: Defensive max Health start")
    effects.register_effect(DEFENSIVE_SACRIFICE, GameEvent.MINION_DAMAGED, _defensive_track, zones=combat, name="Dark Gift: Defensive max Health damage")
    effects.register_effect(GOLEMANCY, GameEvent.COMBAT_START, _golemancy_track, zones=combat, name="Dark Gift: Golemancy max Health start")
    effects.register_effect(GOLEMANCY, GameEvent.MINION_DAMAGED, _golemancy_track, zones=combat, name="Dark Gift: Golemancy max Health damage")

    # Toreth's Blessing: the ordinary shield breaks three times total.
    effects.register_effect(TORETHS_BLESSING, GameEvent.DIVINE_SHIELD_LOST, _toreth_shield, zones=combat, name="Dark Gift: Toreth's Blessing")

    # Persisting Horror: normal Reborn plumbing creates the minion, then the
    # Gift restores its tracked full Health. Other copied bonus keywords are
    # already preserved by the combat-copy/Reborn path.
    effects.register_effect(PERSISTING_HORROR, GameEvent.COMBAT_START, _persisting_track, zones=combat, name="Dark Gift: Persisting Horror start")
    effects.register_effect(PERSISTING_HORROR, GameEvent.MINION_DAMAGED, _persisting_track, zones=combat, name="Dark Gift: Persisting Horror damage")
    effects.register_effect(PERSISTING_HORROR, GameEvent.REBORN, _persisting_reborn, zones=combat, name="Dark Gift: Persisting Horror Reborn")

    # Tarecgosa's Blessing persists doubled positive combat stat gains and any
    # newly gained keywords whether the minion survives or dies.
    effects.register_effect(TARECGOSAS_BLESSING, GameEvent.COMBAT_START, _tarecgosa_start, zones=combat, name="Dark Gift: Tarecgosa start")
    effects.register_effect(TARECGOSAS_BLESSING, GameEvent.MINION_DAMAGED, _tarecgosa_damage, zones=combat, name="Dark Gift: Tarecgosa damage")
    effects.register_effect(TARECGOSAS_BLESSING, GameEvent.MINION_DIED, _persist_tarecgosa, zones=(EffectZone.EVENT_SOURCE,), name="Dark Gift: Tarecgosa death persist")
    effects.register_effect(TARECGOSAS_BLESSING, GameEvent.COMBAT_END, _persist_tarecgosa, zones=combat, name="Dark Gift: Tarecgosa survive persist")
