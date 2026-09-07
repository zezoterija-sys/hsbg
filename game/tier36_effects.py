"""
Tier 3-6 Battlegrounds minion effects.

Generated from the project's cards.json content and executed by explicit card-ID
registrations.  No card text is parsed at runtime.

This module intentionally keeps advanced content out of the generic EffectSystem.
"""

from copy import deepcopy
from functools import partial
import re

from .effects import EffectZone, TriggerFamily
from .events import GameEvent


# =============================================================
# TIER 3 IDS
# =============================================================

ACCORD_O_TRON = 98576
AMBER_GUARDIAN = 95006
ANNOY_O_MODULE = 96812
AZSHARAN_CUTLASSIER = 123325
BLUE_WHELP = 122674
BREAKOUT_MASTERMIND = 132314
BRIARBACK_DRUMMER = 126669
CADAVER_CARETAKER = 113158
CAGEY_CONJURER = 132316
DEADLY_SPORE = 65031
DEEP_SEA_ANGLER = 80742
DEFLECT_O_BOT = 61930
DEVOUT_HELLCALLER = 122586
DIREMUCK_FORAGER = 108922
DISGUISED_GRAVEROBBER = 104610
DUSTBONE_DEVASTATOR = 122229
FRUIT_VENDOR = 132917
GEM_RAT = 116434
HANDLESS_FORSAKEN = 95265
HIRED_MOUNT = 132951
LOCKED_UP_MUTINEER = 132758
MALCHEZAAR_PRINCE_OF_DANCE = 99199
MAMA_MRRGLTON = 131145
METEORITE_CRASHER = 117406
MUMMIFIER = 108992
PAPA_MRRGLTON = 131147
PRIVATE_INVESTIGATOR = 132318
PROSTHETIC_HAND = 112364
RESCUE_BOT = 132895
ROARING_RECRUITER = 109806
SAND_SWIRLER = 119949
SLY_INFILTRATOR = 132630
SLY_RAPTOR = 101584
SPRIGHTLY_SCARAB = 108909
TASTY_LOBSTER = 132796
TIMECAP_N_HOOKTAIL = 103676
TRAPPED_CLAPPER = 132897
TREASURE_PARROT = 132987
TRENCH_FIGHTER = 126671
WAVELING = 126169
WAVERIDER = 80745
WILDFIRE_ELEMENTAL = 64189
WOLF_PUP = 132806

# =============================================================
# TIER 4 IDS
# =============================================================

ABYSSAL_BRUISER = 130658
AIR_BALLER = 133455
ASHEN_CORRUPTOR = 121687
AUTO_ASSEMBLER = 120025
BANANA_SLAMMA = 98824
BIGWIG_BANDIT = 122179
BLADE_COLLECTOR = 99035
BONKER = 70173
BOOM_IN_A_BOX = 133703
BRAMBLE_TUNNELER = 132632
BREAM_COUNTER = 98509
BRONZE_TIMEWALKER = 132955
CAGE_GNAWER = 133041
CAPTAIN_COOKIE = 133075
CLUNKER_JUNKER = 113766
DEAD_BELLRINGER = 132322
DEEPWATER_CHIEFTAIN = 131216
DRONE_DUPLICATOR = 132312
EN_DJINN_BLAZER = 126175
ENCHANTED_SENTINEL = 130796
FEARLESS_FOODIE = 113154
FLAMING_ENFORCER = 126924
FRIENDLY_GEIST = 120219
GEARFIN = 133283
GLAMBOT = 132893
GLOWING_CINDER = 119951
GUNPOWDER_COURIER = 98889
HEADHUNTER_GRYPHON = 132800
HEROIC_UNDERDOG = 126966
HUMON_GOZZ = 121640
IMP_LUSIONIST = 132899
IMPOSING_PERCUSSIONIST = 99232
KELP_KEEPER = 132883
LIVING_PRISON = 133453
LOVESICK_BALLADIST = 99011
MARITIME_EXTORTIONIST = 132764
MAW_CASTER = 121508
MOTLEY_PHALANX = 106487
PERSISTENT_POET = 108463
PLAGUERUNNER = 126451
RAZORFEN_FLAPPER = 126667
REFRESHING_ANOMALY = 64042
RIMESCALE_PRIESTESS = 122221
RUNIC_ARCANIST = 132985
SEAFLOOR_RECRUITER = 126916
SIN_DOREI_STRAIGHT_SHOT = 95286
SKY_HATCH_RUNAWAY = 132957
SNARE_TRAPPER = 132634
SNARKY_SHARK = 132804
SOULKEEPING_JAILER = 132306
TAVERN_TEMPEST = 64077
THORNED_TRAILBLAZER = 116190
TORTOLLAN_BLUE_SHELL = 92406
TWILIGHT_TIDEHUNTER = 132989
ZESTY_SHAKER = 99054

# =============================================================
# TIER 5 IDS
# =============================================================

AIR_REVENANT = 126173
BARRIER_BANSHEE = 133081
BILE_SPITTER = 122219
BRANN_BRONZEBEARD = 96786
CATACLYSMIC_HARBINGER = 130884
CHARGING_CZARINA = 110321
COSTUME_ENTHUSIAST = 126641
COUSIN_ERRGL = 131149
DANCING_BARNSTORMER = 99523
DARKCREST_STRATEGIST = 115555
DEFT_DESERTER = 133705
DEVILISH_DISTRACTOR = 132901
DRACONIC_WARDEN = 126860
DRAKKARI_ENCHANTER = 101314
DRUSTFALLEN_BUTCHER = 120104
DUAL_WIELD_CORSAIR = 115708
ENTERPRISING_ESCAPEE = 132762
FELBOAR = 110664
FELFIRE_CONJURER = 120299
FIRESCALE_HOARDER = 120213
GLOWSCALE = 80746
HOARDING_HYENA = 133039
INSATIABLE_UR_ZUL = 72060
KALECGOS_ARCANE_ASPECT = 60630
KANGOR_S_APPRENTICE = 59935
LEEROY_THE_RECKLESS = 90425
LURKING_LEVIATHAN = 130711
NIGHTMARE_PAR_TEA_GUEST = 120754
NOMI_KITCHEN_NIGHTMARE = 63626
PRIMALFIN_LOOKOUT = 60028
PROUD_PRIVATEER = 122520
RAZORFEN_VINEWEAVER = 122562
RODEO_PERFORMER = 104466
SANGUINE_REFINER = 122566
SCRAP_SCRAPER = 98592
SEWER_LORD = 130996
SHAMANIC_TIDECALLER = 133026
SHIPWRECKED_RASCAL = 122177
SHOWY_CYCLIST = 115565
SPARK_SNAPPER = 132676
TICHONDRIUS = 99228
TITUS_RIVENDARE = 97408
TRANQUIL_MEDITATIVE = 119942
TURQUOISE_SKITTERER = 119255
VIGILANT_BRISTLEMANE = 132320
VOID_PUP_TRAINER = 130078

# =============================================================
# TIER 6 IDS
# =============================================================

BALINDA_STONEHEARTH = 130298
CHORAL_MRRRGLR = 98948
CRIMSON_VINDICATOR = 132953
DEATHLY_STRIKER = 115610
DEATHSTRIDER = 132808
ELEMENTAL_OF_SURPRISE = 101280
EREDAR_ESCAPIST = 133028
ETERNAL_SUMMONER = 95263
FALLING_SKY_GOLEM = 130798
FAUNA_WHISPERER = 120905
FIRE_FORGED_EVOKER = 120301
FORSAKEN_WEAVER = 126733
GATEKEEPER_AMALGAM = 133329
GENTLE_DJINNI = 64062
GOLDRINN_THE_GREAT_WOLF = 59955
GROUNDBREAKER = 114816
HOOKTUSK_MASTER_MARAUDER = 132925
IGNITION_SPECIALIST = 105852
MAGICFIN_MYCOLOGIST = 122277
MOAT_CUSTODIAN = 132981
PRIMITIVE_PAINTER = 122281
RAVAGING_SCORPID = 132949
SANGUINE_CHAMPION = 80755
SILENT_DELIVERER = 132923
SKY_ADMIRAL_ROGERS = 122516
SNAZZY_PHANTOM = 133083
TORRENTIAL_RUINER = 133707
TURBO_HOGRIDER = 116195
TWISTED_WRATHGUARD = 130662
TYRAEL = 133438
UNBOUND_TEMPEST = 132983
UNLEASHED_MANA_SURGE = 120674
UTILITY_DRONE = 98588
VETERAN_BRIGAND = 132929
WARPWING = 92413

TIER36_CARD_IDS = {
    3: {
        ACCORD_O_TRON, AMBER_GUARDIAN, ANNOY_O_MODULE, AZSHARAN_CUTLASSIER,
        BLUE_WHELP, BREAKOUT_MASTERMIND, BRIARBACK_DRUMMER, CADAVER_CARETAKER,
        CAGEY_CONJURER, DEADLY_SPORE, DEEP_SEA_ANGLER, DEFLECT_O_BOT,
        DEVOUT_HELLCALLER, DIREMUCK_FORAGER, DISGUISED_GRAVEROBBER,
        DUSTBONE_DEVASTATOR, FRUIT_VENDOR, GEM_RAT, HANDLESS_FORSAKEN,
        HIRED_MOUNT, LOCKED_UP_MUTINEER, MALCHEZAAR_PRINCE_OF_DANCE,
        MAMA_MRRGLTON, METEORITE_CRASHER, MUMMIFIER, PAPA_MRRGLTON,
        PRIVATE_INVESTIGATOR, PROSTHETIC_HAND, RESCUE_BOT, ROARING_RECRUITER,
        SAND_SWIRLER, SLY_INFILTRATOR, SLY_RAPTOR, SPRIGHTLY_SCARAB,
        TASTY_LOBSTER, TIMECAP_N_HOOKTAIL, TRAPPED_CLAPPER, TREASURE_PARROT,
        TRENCH_FIGHTER, WAVELING, WAVERIDER, WILDFIRE_ELEMENTAL, WOLF_PUP,
    },
    4: {
        ABYSSAL_BRUISER, AIR_BALLER, ASHEN_CORRUPTOR, AUTO_ASSEMBLER,
        BANANA_SLAMMA, BIGWIG_BANDIT, BLADE_COLLECTOR, BONKER, BOOM_IN_A_BOX,
        BRAMBLE_TUNNELER, BREAM_COUNTER, BRONZE_TIMEWALKER, CAGE_GNAWER,
        CAPTAIN_COOKIE, CLUNKER_JUNKER, DEAD_BELLRINGER, DEEPWATER_CHIEFTAIN,
        DRONE_DUPLICATOR, EN_DJINN_BLAZER, ENCHANTED_SENTINEL, FEARLESS_FOODIE,
        FLAMING_ENFORCER, FRIENDLY_GEIST, GEARFIN, GLAMBOT, GLOWING_CINDER,
        GUNPOWDER_COURIER, HEADHUNTER_GRYPHON, HEROIC_UNDERDOG, HUMON_GOZZ,
        IMP_LUSIONIST, IMPOSING_PERCUSSIONIST, KELP_KEEPER, LIVING_PRISON,
        LOVESICK_BALLADIST, MARITIME_EXTORTIONIST, MAW_CASTER, MOTLEY_PHALANX,
        PERSISTENT_POET, PLAGUERUNNER, RAZORFEN_FLAPPER, REFRESHING_ANOMALY,
        RIMESCALE_PRIESTESS, RUNIC_ARCANIST, SEAFLOOR_RECRUITER,
        SIN_DOREI_STRAIGHT_SHOT, SKY_HATCH_RUNAWAY, SNARE_TRAPPER,
        SNARKY_SHARK, SOULKEEPING_JAILER, TAVERN_TEMPEST, THORNED_TRAILBLAZER,
        TORTOLLAN_BLUE_SHELL, TWILIGHT_TIDEHUNTER, ZESTY_SHAKER,
    },
    5: {
        AIR_REVENANT, BARRIER_BANSHEE, BILE_SPITTER, BRANN_BRONZEBEARD,
        CATACLYSMIC_HARBINGER, CHARGING_CZARINA, COSTUME_ENTHUSIAST,
        COUSIN_ERRGL, DANCING_BARNSTORMER, DARKCREST_STRATEGIST, DEFT_DESERTER,
        DEVILISH_DISTRACTOR, DRACONIC_WARDEN, DRAKKARI_ENCHANTER,
        DRUSTFALLEN_BUTCHER, DUAL_WIELD_CORSAIR, ENTERPRISING_ESCAPEE, FELBOAR,
        FELFIRE_CONJURER, FIRESCALE_HOARDER, GLOWSCALE, HOARDING_HYENA,
        INSATIABLE_UR_ZUL, KALECGOS_ARCANE_ASPECT, KANGOR_S_APPRENTICE,
        LEEROY_THE_RECKLESS, LURKING_LEVIATHAN, NIGHTMARE_PAR_TEA_GUEST,
        NOMI_KITCHEN_NIGHTMARE, PRIMALFIN_LOOKOUT, PROUD_PRIVATEER,
        RAZORFEN_VINEWEAVER, RODEO_PERFORMER, SANGUINE_REFINER, SCRAP_SCRAPER,
        SEWER_LORD, SHAMANIC_TIDECALLER, SHIPWRECKED_RASCAL, SHOWY_CYCLIST,
        SPARK_SNAPPER, TICHONDRIUS, TITUS_RIVENDARE, TRANQUIL_MEDITATIVE,
        TURQUOISE_SKITTERER, VIGILANT_BRISTLEMANE, VOID_PUP_TRAINER,
    },
    6: {
        BALINDA_STONEHEARTH, CHORAL_MRRRGLR, CRIMSON_VINDICATOR,
        DEATHLY_STRIKER, DEATHSTRIDER, ELEMENTAL_OF_SURPRISE, EREDAR_ESCAPIST,
        ETERNAL_SUMMONER, FALLING_SKY_GOLEM, FAUNA_WHISPERER, FIRE_FORGED_EVOKER,
        FORSAKEN_WEAVER, GATEKEEPER_AMALGAM, GENTLE_DJINNI,
        GOLDRINN_THE_GREAT_WOLF, GROUNDBREAKER, HOOKTUSK_MASTER_MARAUDER,
        IGNITION_SPECIALIST, MAGICFIN_MYCOLOGIST, MOAT_CUSTODIAN,
        PRIMITIVE_PAINTER, RAVAGING_SCORPID, SANGUINE_CHAMPION,
        SILENT_DELIVERER, SKY_ADMIRAL_ROGERS, SNAZZY_PHANTOM,
        TORRENTIAL_RUINER, TURBO_HOGRIDER, TWISTED_WRATHGUARD, TYRAEL,
        UNBOUND_TEMPEST, UNLEASHED_MANA_SURGE, UTILITY_DRONE, VETERAN_BRIGAND,
        WARPWING,
    },
}

# Generated cards used by Tier 3-6 content.
BLOOD_GEM = 70136
BLOOD_GEM_BARRAGE = 126676
ANGLERS_LURE = 83988
TAVERN_DISH_BANANA = 105752
HELPING_HAND = 100153
LOCKBOX = 132766
REPAIR_JOB = 133711
GOLDEN_TOUCH = 104448
GEM_CONFISCATION = 110642
UNDERSEA_MOUNT = 84374
ANCESTRAL_AUTOMATON = 108432
CHEFS_CHOICE = 105664
DEEPWATER_CLAN = 131218
METHODICAL_MADNESS = 132903
SHINY_RING = 109230
RIME_OR_REASON = 122259
EVOLVING_STRATEGY = 116478
GLOWING_CROWN = 84362
BUTCHERING = 110412
MISPLACED_TEA_SET = 105271
MEDITATION = 121479
EASTERLY_WINDS = 126909
MIGHTY_DRAGONBREATH = 132995
NATURAL_BLESSING = 104472
ETERNAL_KNIGHT = 95261
FISHBAIT = 132802
DEMON_FODDER = 130084
TASTY_LOBSTER_ID = TASTY_LOBSTER
MAMA_MRRGLTON_ID = MAMA_MRRGLTON
PAPA_MRRGLTON_ID = PAPA_MRRGLTON

BOUNTY_IDS = (122182, 122183, 122184, 122185, 122186)
CHROMADRAKE_CHILD_IDS = (126713, 126711, 126717, 126715, 126718)

# Some child definitions are omitted from the supplied card dump.  These
# fallbacks keep the simulator executable without inventing hidden text.
FALLBACK_DEFINITIONS = {
    99629: {
        "id": 99629, "name": "Skeleton", "cardType": "minion",
        "attack": 1, "health": 1, "tier": 1, "minionType": "Undead",
        "minionTypes": ["Undead"], "keywords": [], "_generated": True,
    },
}
for _cid in CHROMADRAKE_CHILD_IDS:
    FALLBACK_DEFINITIONS[_cid] = {
        "id": _cid, "name": "Chromadrake", "cardType": "minion",
        "attack": 1, "health": 1, "tier": 1, "minionType": "Dragon",
        "minionTypes": ["Dragon"], "keywords": [], "_generated": True,
        "_missing_definition": True,
    }


# =============================================================
# GENERIC HELPERS
# =============================================================


def _amount(ctx, normal, golden):
    return golden if ctx.is_golden else normal


def _state(ctx):
    return ctx.system.get_player_state(ctx.source_player_id)


def _player(ctx):
    return ctx.system.game.get_player(ctx.source_player_id)


def _is_type(system, card, minion_type):
    return isinstance(card, dict) and system.is_minion_type(card, minion_type)


def _has_keyword(system, card, keyword):
    return isinstance(card, dict) and system.has_keyword(card, keyword)


def _friendly_cards(player):
    return [card for card in player.board if isinstance(card, dict)]


def _friendly_of_type(system, player, minion_type):
    return [card for card in player.board if _is_type(system, card, minion_type)]


def _definitions(system, *, card_type="minion", tier=None, minion_type=None, predicate=None):
    result = []
    for card in getattr(system.game.pool, "card_definitions", []):
        if card.get("cardType") != card_type:
            continue
        if card.get("pool") is not True:
            continue
        if "tavern" not in (card.get("categories") or []):
            continue
        if card.get("isDuosOnly", False):
            continue
        if tier is not None and card.get("tier") != tier:
            continue
        if minion_type is not None and not system.is_minion_type(card, minion_type):
            continue
        if predicate is not None and not predicate(card):
            continue
        result.append(card)
    return result


def _definition(system, card_id):
    try:
        return system._definition_by_id(card_id)
    except KeyError:
        return FALLBACK_DEFINITIONS.get(card_id)


def _fresh_card(system, card_id, *, golden=False):
    try:
        return system.create_card(card_id, golden=golden, generated=True)
    except KeyError:
        card = deepcopy(FALLBACK_DEFINITIONS[card_id])
        card["isGolden"] = bool(golden)
        if golden:
            card["attack"] = int(card.get("attack", 0) or 0) * 2
            card["health"] = int(card.get("health", 0) or 0) * 2
        return card


def _add_to_hand(system, player_id, card_or_id, *, golden=False):
    if isinstance(card_or_id, int) and _definition(system, card_or_id) is None:
        player = system.game.get_player(player_id)
        if len(player.hand) >= getattr(player, "MAX_HAND_SIZE", 10):
            return None
        card = _fresh_card(system, card_or_id, golden=golden)
        player.hand.append(card)
        system.events.emit(GameEvent.CARD_GENERATED, player_id=player_id, card=card)
        system.events.emit(GameEvent.CARD_ADDED_TO_HAND, player_id=player_id, card=card)
        return card
    return system.add_generated_to_hand(player_id, card_or_id, golden=golden)


def _add_many(ctx, card_id, count, *, golden=False):
    result = []
    for _ in range(max(0, int(count))):
        card = _add_to_hand(ctx.system, ctx.source_player_id, card_id, golden=golden)
        if card is None:
            break
        result.append(card)
    return result


def _add_random(ctx, definitions, count=1, *, golden=False):
    definitions = list(definitions)
    result = []
    if not definitions:
        return result
    for _ in range(max(0, int(count))):
        definition = ctx.random_choice(definitions)
        card = _add_to_hand(
            ctx.system,
            ctx.source_player_id,
            definition.get("id"),
            golden=golden,
        )
        if card is None:
            break
        result.append(card)
    return result


def _random_type(ctx, minion_type, count=1, *, tier=None, golden=False):
    return _add_random(
        ctx,
        _definitions(ctx.system, minion_type=minion_type, tier=tier),
        count,
        golden=golden,
    )


def _random_tavern_spells(ctx, count=1, predicate=None):
    return _add_random(
        ctx,
        _definitions(ctx.system, card_type="spell", predicate=predicate),
        count,
    )


def _random_bounties(ctx, count=1):
    ids = [card_id for card_id in BOUNTY_IDS if _definition(ctx.system, card_id)]
    if not ids:
        return []
    result = []
    for _ in range(max(0, int(count))):
        card_id = ctx.random_choice(ids)
        card = _add_to_hand(ctx.system, ctx.source_player_id, card_id)
        if card is None:
            break
        result.append(card)
    return result


def _combat_side(ctx):
    if ctx.source_side is not None:
        return ctx.source_side
    for key in (
        "side", "side_a", "side_b", "attacking_side", "source_side",
        "defending_side", "target_side",
    ):
        side = ctx.event.get(key)
        if side is not None and getattr(side, "player_id", None) == ctx.source_player_id:
            return side
    return None


def _summon(ctx, card_or_id, count=1, *, golden=False, position=None):
    side = _combat_side(ctx)
    if side is None:
        return []
    if isinstance(card_or_id, int) and _definition(ctx.system, card_or_id) is None:
        engine = ctx.event.get("engine")
        result = []
        for offset in range(max(0, int(count))):
            card = _fresh_card(ctx.system, card_or_id, golden=golden)
            runtime = engine.summon(
                side,
                card,
                position=(None if position is None else position + offset),
            )
            if runtime is None:
                break
            result.append(runtime)
        return result
    return ctx.summon(card_or_id, count=count, golden=golden, position=position)


def _blood_gem_values(system, player_id):
    state = system.get_player_state(player_id)
    return (
        1 + int(state.get("blood_gem_attack_bonus", 0) or 0),
        1 + int(state.get("blood_gem_health_bonus", 0) or 0),
    )


def _blood_gem(ctx, target, count=1, *, permanent=True):
    attack, health = _blood_gem_values(ctx.system, ctx.source_player_id)
    ctx.buff(
        target,
        attack=attack * int(count),
        health=health * int(count),
        until_next_turn=not permanent,
    )


def _remove_keyword(card, keyword):
    wanted = str(keyword).casefold()
    card["keywords"] = [
        value for value in card.get("keywords", [])
        if str(value).casefold() != wanted
    ]
    for key in ("_permanent_keyword_grants",):
        if key in card:
            card[key] = [
                value for value in card.get(key, [])
                if str(value).casefold() != wanted
            ]
    if wanted == "reborn":
        card["_combat_reborn_available"] = False
    if wanted == "divine shield":
        card["_combat_divine_shield"] = False


def _consume_tavern(ctx, *, target=None, double=False, highest_health=False):
    player = _player(ctx)
    tavern = getattr(player, "tavern", None)
    if tavern is None:
        return None
    candidates = [
        (index, card)
        for index, card in enumerate(tavern.slots)
        if isinstance(card, dict) and card.get("cardType") == "minion"
    ]
    if not candidates:
        return None
    if highest_health:
        index, food = max(candidates, key=lambda item: int(item[1].get("health", 0) or 0))
    else:
        index, food = ctx.random_choice(candidates)
    tavern.slots[index] = None
    target = target if isinstance(target, dict) else ctx.source
    multiplier = 2 if double else 1
    ctx.buff(
        target,
        attack=int(food.get("attack", 0) or 0) * multiplier,
        health=int(food.get("health", 0) or 0) * multiplier,
    )
    for keyword in food.get("keywords", []):
        if str(keyword).casefold() in {
            "taunt", "divine shield", "reborn", "venomous", "windfury", "stealth",
        }:
            ctx.grant_keyword(target, keyword)
    return food


def _permanent_combat_buff(ctx, target, attack=0, health=0):
    ctx.buff(target, attack=attack, health=health)
    index = target.get("_persistent_board_index") if isinstance(target, dict) else None
    if index is None:
        return
    player = ctx.system.game.get_player(ctx.source_player_id)
    if 0 <= index < len(player.board) and isinstance(player.board[index], dict):
        ctx.system.apply_buff(player.board[index], attack=attack, health=health)


def _tavern_spell(spell):
    return isinstance(spell, dict) and (
        "tavern" in (spell.get("categories") or [])
        or str(spell.get("spellSchool", "")).casefold() == "tavern"
    )


def _card_has_choose_one(card):
    return isinstance(card, dict) and "choose one" in re.sub(r"<[^>]+>", "", str(card.get("text", ""))).casefold()


def _same_player(ctx, event_player_id):
    return event_player_id == ctx.source_player_id


def _target_ref_board_provider(*, types=None, exclude_source=False):
    types = tuple(types or ())

    def provider(context):
        player = context.game.get_player(context.player_id)
        result = []
        for index, card in enumerate(player.board):
            if not isinstance(card, dict):
                continue
            if exclude_source and card is context.source_card:
                continue
            if types and not any(context.game.effects.is_minion_type(card, value) for value in types):
                continue
            result.append(index)
        return result

    return provider


def _cast_registered_spell(ctx, spell_id, *, target=None, count=1):
    spell = _fresh_card(ctx.system, spell_id)
    for _ in range(max(0, int(count))):
        ctx.system.trigger_card_family(
            spell,
            TriggerFamily.SPELL,
            player_id=ctx.source_player_id,
            zone=EffectZone.EVENT_SOURCE,
            target=target,
        )


def _current_source_card_for_state(ctx):
    return ctx.effect_state if isinstance(ctx.effect_state, dict) else ctx.source


# =============================================================
# GLOBAL RUNTIME TRACKING / PASSIVES
# =============================================================


def _global_turn_start(effects, event):
    player_id = event.get("player_id")
    if player_id is None:
        return
    state = effects.get_player_state(player_id)
    player = effects.game.get_player(player_id)

    # Malchezaar refresh charges are recalculated from live copies.
    charges = 0
    for card in player.board:
        if isinstance(card, dict) and card.get("id") == MALCHEZAAR_PRINCE_OF_DANCE:
            charges += 4 if effects.is_golden(card) else 2
    state["health_refreshes_remaining"] = charges

    # Thorned Trailblazer: one/two Choose One cards combine both effects.
    combine = 0
    for card in player.board:
        if isinstance(card, dict) and card.get("id") == THORNED_TRAILBLAZER:
            combine += 2 if effects.is_golden(card) else 1
    state["choose_one_both_remaining"] = combine

    # Per-turn counters.
    state["zesty_shaker_used"] = 0
    state["magicfin_uses"] = 0

    # Lockboxes count down in hand.
    for card in list(player.hand):
        if not isinstance(card, dict) or card.get("id") != LOCKBOX:
            continue
        remaining = int(card.get("_lockbox_turns_remaining", 5) or 0) - 1
        card["_lockbox_turns_remaining"] = remaining
        if remaining > 0:
            continue
        player.hand.remove(card)
        candidates = _definitions(
            effects,
            predicate=lambda c: bool(c.get("minionType") or c.get("minionTypes")),
        )
        if candidates:
            chosen = effects.random.choice(candidates)
            effects.add_generated_to_hand(player_id, chosen.get("id"), golden=True)


def _global_spell_cast(effects, event):
    player_id = event.get("player_id")
    spell = event.get("spell") or event.get("card")
    if player_id is None or not isinstance(spell, dict):
        return
    state = effects.get_player_state(player_id)
    state["spells_cast_game"] = int(state.get("spells_cast_game", 0) or 0) + 1
    if _tavern_spell(spell):
        state["tavern_spells_cast_game"] = int(state.get("tavern_spells_cast_game", 0) or 0) + 1
        state["last_tavern_spell"] = deepcopy(spell)

    # Generic extra-stat rider for targeted Tavern spells.
    target = event.get("target")
    if _tavern_spell(spell) and isinstance(target, dict):
        attack = int(state.get("tavern_spell_attack_bonus", 0) or 0)
        health = int(state.get("tavern_spell_health_bonus", 0) or 0)
        if attack or health:
            effects.apply_buff(target, attack=attack, health=health)


def _global_card_played(effects, event):
    player_id = event.get("player_id")
    card = event.get("card")
    if player_id is None or not isinstance(card, dict):
        return
    state = effects.get_player_state(player_id)
    if effects.is_golden(card):
        state["golden_minions_played"] = int(state.get("golden_minions_played", 0) or 0) + 1
        # Wherever-scalers already owned by the player update immediately.
        player = effects.game.get_player(player_id)
        for existing in list(player.board) + list(player.hand) + list(getattr(player.tavern, "slots", [])):
            if isinstance(existing, dict) and existing.get("id") == MARITIME_EXTORTIONIST:
                _apply_global_card_modifiers(effects, player_id, existing)
    if card.get("id") in {MAMA_MRRGLTON, PAPA_MRRGLTON, COUSIN_ERRGL}:
        state["mrrgltons_played"] = int(state.get("mrrgltons_played", 0) or 0) + 1


def _global_trigger_resolved(effects, event):
    player_id = event.get("player_id")
    if player_id is None:
        return
    state = effects.get_player_state(player_id)
    family = event.get("family")
    if family == TriggerFamily.DEATHRATTLE:
        state["deathrattles_triggered_game"] = int(state.get("deathrattles_triggered_game", 0) or 0) + 1
        player = effects.game.get_player(player_id)
        for existing in list(player.board) + list(player.hand) + list(getattr(player.tavern, "slots", [])):
            if isinstance(existing, dict) and existing.get("id") == FALLING_SKY_GOLEM:
                _apply_global_card_modifiers(effects, player_id, existing)
    elif family == TriggerFamily.BATTLECRY:
        state["battlecries_triggered_game"] = int(state.get("battlecries_triggered_game", 0) or 0) + 1
    elif family == TriggerFamily.RALLY:
        state["rallies_triggered_game"] = int(state.get("rallies_triggered_game", 0) or 0) + 1


def _apply_global_card_modifiers(effects, player_id, card):
    if not isinstance(card, dict):
        return
    state = effects.get_player_state(player_id)

    # Wherever-they-are Undead bonus.
    if effects.is_minion_type(card, "Undead"):
        attack = int(state.get("undead_global_attack", 0) or 0)
        if attack and not card.get("_undead_global_applied"):
            effects.apply_buff(card, attack=attack)
            card["_undead_global_applied"] = attack

    # Future Ballers / Lobsters / Beetles.
    if card.get("id") == AIR_BALLER:
        attack = int(state.get("air_baller_future_attack", 0) or 0)
        health = int(state.get("air_baller_future_health", 0) or 0)
        already_a = int(card.get("_air_baller_applied_a", 0) or 0)
        already_h = int(card.get("_air_baller_applied_h", 0) or 0)
        effects.apply_buff(card, attack=attack - already_a, health=health - already_h)
        card["_air_baller_applied_a"] = attack
        card["_air_baller_applied_h"] = health

    if card.get("id") == TASTY_LOBSTER:
        attack = int(state.get("tasty_lobster_future_attack", 0) or 0)
        health = int(state.get("tasty_lobster_future_health", 0) or 0)
        already_a = int(card.get("_tasty_lobster_applied_a", 0) or 0)
        already_h = int(card.get("_tasty_lobster_applied_h", 0) or 0)
        effects.apply_buff(card, attack=attack - already_a, health=health - already_h)
        card["_tasty_lobster_applied_a"] = attack
        card["_tasty_lobster_applied_h"] = health

    if card.get("id") == 110402:
        attack = int(state.get("beetle_global_attack", 0) or 0)
        health = int(state.get("beetle_global_health", 0) or 0)
        already_a = int(card.get("_beetle_global_applied_a", 0) or 0)
        already_h = int(card.get("_beetle_global_applied_h", 0) or 0)
        effects.apply_buff(card, attack=attack - already_a, health=health - already_h)
        card["_beetle_global_applied_a"] = attack
        card["_beetle_global_applied_h"] = health

    # Dynamic "wherever" scalers.
    if card.get("id") == MARITIME_EXTORTIONIST:
        count = int(state.get("golden_minions_played", 0) or 0)
        per = 14 if effects.is_golden(card) else 7
        wanted = count * per
        applied = int(card.get("_maritime_applied", 0) or 0)
        effects.apply_buff(card, attack=wanted - applied, health=wanted - applied)
        card["_maritime_applied"] = wanted

    if card.get("id") == FALLING_SKY_GOLEM:
        count = int(state.get("deathrattles_triggered_game", 0) or 0)
        per_a, per_h = ((8, 4) if effects.is_golden(card) else (4, 2))
        wanted_a, wanted_h = count * per_a, count * per_h
        applied_a = int(card.get("_sky_golem_applied_a", 0) or 0)
        applied_h = int(card.get("_sky_golem_applied_h", 0) or 0)
        effects.apply_buff(card, attack=wanted_a - applied_a, health=wanted_h - applied_h)
        card["_sky_golem_applied_a"] = wanted_a
        card["_sky_golem_applied_h"] = wanted_h


def _global_card_entered(effects, event):
    player_id = event.get("player_id")
    card = event.get("card") or event.get("minion")
    if player_id is None:
        return
    _apply_global_card_modifiers(effects, player_id, card)


def _global_tavern_refresh(effects, event):
    player_id = event.get("player_id")
    if player_id is None:
        return
    player = effects.game.get_player(player_id)
    state = effects.get_player_state(player_id)
    cards = [card for card in player.tavern.slots if isinstance(card, dict)]

    # Permanent Tavern Elemental buffs.
    elem_a = int(state.get("tavern_elemental_attack", 0) or 0)
    elem_h = int(state.get("tavern_elemental_health", 0) or 0)
    tier3_a = int(state.get("tavern_tier3_attack", 0) or 0)
    tier3_h = int(state.get("tavern_tier3_health", 0) or 0)
    all_a = int(state.get("tavern_all_attack", 0) or 0)
    all_h = int(state.get("tavern_all_health", 0) or 0)
    for card in cards:
        if all_a or all_h:
            effects.apply_buff(card, attack=all_a, health=all_h)
        if effects.is_minion_type(card, "Elemental") and (elem_a or elem_h):
            effects.apply_buff(card, attack=elem_a, health=elem_h)
        if int(card.get("tier", 0) or 0) <= 3 and (tier3_a or tier3_h):
            effects.apply_buff(card, attack=tier3_a, health=tier3_h)

    # Refresh-triggered persistent effects.
    random_buffs = list(state.get("refresh_random_buffs", []))
    for attack, health in random_buffs:
        candidates = [card for card in player.tavern.slots if isinstance(card, dict)]
        if candidates:
            effects.apply_buff(effects.random.choice(candidates), attack=attack, health=health)

    # Blood Gem Barrage applies Blood-Gem-sized stats to all minions on refresh.
    barrage = int(state.get("blood_gem_barrage_refreshes", 0) or 0)
    if barrage:
        gem_a, gem_h = (
            1 + int(state.get("blood_gem_attack_bonus", 0) or 0),
            1 + int(state.get("blood_gem_health_bonus", 0) or 0),
        )
        for card in cards:
            effects.apply_buff(card, attack=gem_a * barrage, health=gem_h * barrage)

    # Twisted Wrathguard queues Fodders for exactly the next Refresh.
    pending_fodder = int(state.pop("fodder_pending_count", 0) or 0)
    if pending_fodder > 0:
        for _ in range(pending_fodder):
            fodder = _fresh_card(effects, DEMON_FODDER)
            empty = next((i for i, card in enumerate(player.tavern.slots) if card is None), None)
            if empty is not None:
                player.tavern.slots[empty] = fodder
            elif player.tavern.slots:
                player.tavern.slots[-1] = fodder

            demons = [card for card in player.board if _is_type(effects, card, "Demon")]
            if demons:
                target = effects.random.choice(demons)
                multiplier = 2 if effects.is_golden(fodder) else 1
                effects.apply_buff(
                    target,
                    attack=int(fodder.get("attack", 0) or 0) * multiplier,
                    health=int(fodder.get("health", 0) or 0) * multiplier,
                )
                # Fodder immediately feeds itself. Tavern is responsible for
                # the ordinary slot refill on its next normal fill operation.
                try:
                    index = player.tavern.slots.index(fodder)
                    player.tavern.slots[index] = None
                    pool = effects.game.pool
                    replacement = None
                    getter = getattr(pool, "get_random_card", None)
                    if callable(getter):
                        replacement = getter(
                            card_type="minion",
                            max_tier=int(getattr(player, "tavern_tier", 1) or 1),
                        )
                    if replacement is not None:
                        player.tavern.slots[index] = replacement
                        effects.events.emit(
                            GameEvent.TAVERN_CARD_APPEARED,
                            player_id=player_id,
                            card=replacement,
                            tavern_slot=index,
                        )
                except ValueError:
                    pass


def _global_minion_died(effects, event):
    player_id = event.get("player_id")
    minion = event.get("minion")
    if player_id is None or not isinstance(minion, dict):
        return
    state = effects.get_player_state(player_id)
    if minion.get("id") == ETERNAL_KNIGHT:
        state["eternal_knights_died"] = int(state.get("eternal_knights_died", 0) or 0) + 1


def _global_minion_summoned(effects, event):
    player_id = event.get("player_id")
    minion = event.get("minion")
    if player_id is None or not isinstance(minion, dict):
        return
    state = effects.get_player_state(player_id)
    _apply_global_card_modifiers(effects, player_id, minion)

    if minion.get("id") == ETERNAL_KNIGHT:
        count = int(state.get("eternal_knights_died", 0) or 0)
        effects.apply_buff(minion, attack=4 * count, health=2 * count)

    if minion.get("id") == ANCESTRAL_AUTOMATON:
        previous = int(state.get("automata_summoned", 0) or 0)
        if previous:
            effects.apply_buff(minion, attack=3 * previous, health=2 * previous)
        state["automata_summoned"] = previous + 1


def _global_magnetized(effects, event):
    target = event.get("minion") or event.get("target")
    magnetic = event.get("card")
    if not isinstance(target, dict):
        return
    target["_magnetization_count"] = int(target.get("_magnetization_count", 0) or 0) + 1

    multiplier = int(target.pop("_next_magnetization_multiplier", 1) or 1)
    if multiplier > 1 and isinstance(magnetic, dict):
        for _ in range(multiplier - 1):
            effects.magnetize(deepcopy(magnetic), target)
            target["_magnetization_count"] += 1


def _register_global_runtime(effects):
    effects.events.register(GameEvent.TURN_START, partial(_global_turn_start, effects), order=-450)
    effects.events.register(GameEvent.SPELL_CAST, partial(_global_spell_cast, effects), order=-450)
    effects.events.register(GameEvent.CARD_PLAYED, partial(_global_card_played, effects), order=-450)
    effects.events.register(GameEvent.TRIGGER_RESOLVED, partial(_global_trigger_resolved, effects), order=-450)
    effects.events.register(GameEvent.CARD_ADDED_TO_HAND, partial(_global_card_entered, effects), order=500)
    effects.events.register(GameEvent.CARD_BOUGHT, partial(_global_card_entered, effects), order=500)
    effects.events.register(GameEvent.TAVERN_CARD_APPEARED, partial(_global_card_entered, effects), order=500)
    effects.events.register(GameEvent.TAVERN_REFRESHED, partial(_global_tavern_refresh, effects), order=500)
    effects.events.register(GameEvent.MINION_DIED, partial(_global_minion_died, effects), order=-450)
    effects.events.register(GameEvent.MINION_SUMMONED, partial(_global_minion_summoned, effects), order=-450)
    effects.events.register(GameEvent.MAGNETIZED, partial(_global_magnetized, effects), order=-450)

# =============================================================
# TIER 3
# =============================================================


def _register_tier3(effects):
    effects.register_start_of_turn(ACCORD_O_TRON, lambda c: c.system.add_gold(c.source_player_id, _amount(c, 1, 2)), name="Accord-o-Tron")
    effects.register_start_of_combat(AMBER_GUARDIAN, _amber_guardian, name="Amber Guardian")
    effects.register_battlecry(AZSHARAN_CUTLASSIER, _azsharan_cutlassier, name="Azsharan Cutlassier")
    effects.register_rally(BLUE_WHELP, _blue_whelp, name="Blue Whelp")
    effects.register_activate(BREAKOUT_MASTERMIND, 2, _breakout_mastermind, name="Breakout Mastermind")
    effects.register_battlecry(BRIARBACK_DRUMMER, lambda c: _add_many(c, BLOOD_GEM_BARRAGE, _amount(c, 1, 2)), name="Briarback Drummer")
    effects.register_deathrattle(CADAVER_CARETAKER, _cadaver_caretaker, name="Cadaver Caretaker")
    effects.register_activate(CAGEY_CONJURER, 1, _cagey_conjurer, name="Cagey Conjurer")
    effects.register_spellcraft(DEEP_SEA_ANGLER, ANGLERS_LURE)
    effects.register_effect(DEFLECT_O_BOT, GameEvent.MINION_SUMMONED, _deflect_o_bot, zones=(EffectZone.COMBAT,), name="Deflect-o-Bot")
    effects.register_effect(DEVOUT_HELLCALLER, GameEvent.MINION_DAMAGED, _devout_hellcaller, zones=(EffectZone.COMBAT,), name="Devout Hellcaller")
    effects.register_start_of_combat(DIREMUCK_FORAGER, _diremuck_forager, name="Diremuck Forager")
    effects.register_target_rule(DISGUISED_GRAVEROBBER, _target_ref_board_provider(types=("Undead",), exclude_source=True))
    effects.register_battlecry(DISGUISED_GRAVEROBBER, _disguised_graverobber, name="Disguised Graverobber")
    effects.register_rally(DUSTBONE_DEVASTATOR, _dustbone_devastator, name="Dustbone Devastator")
    effects.register_activate(FRUIT_VENDOR, 1, lambda c: _add_many(c, TAVERN_DISH_BANANA, _amount(c, 2, 4)), name="Fruit Vendor")
    effects.register_end_of_turn(GEM_RAT, lambda c: _add_many(c, 116596, _amount(c, 1, 2)), name="Gem Rat")
    effects.register_deathrattle(HANDLESS_FORSAKEN, lambda c: _summon(c, HELPING_HAND, _amount(c, 1, 2), position=c.event.get("death_position")), name="Handless Forsaken")
    effects.register_activate(HIRED_MOUNT, 2, _hired_mount, name="Hired Mount")
    effects.register_deathrattle(LOCKED_UP_MUTINEER, _locked_up_mutineer, name="Locked-up Mutineer")
    effects.register_battlecry(MAMA_MRRGLTON, _mama_mrrglton, name="Mama Mrrglton")
    effects.register_effect(METEORITE_CRASHER, GameEvent.CARD_SOLD, _meteorite_crasher, zones=(EffectZone.BOARD,), name="Meteorite Crasher")
    effects.register_deathrattle(MUMMIFIER, _mummifier, name="Mummifier")
    effects.register_battlecry(PAPA_MRRGLTON, _papa_mrrglton, name="Papa Mrrglton")
    effects.register_activate(PRIVATE_INVESTIGATOR, 1, _private_investigator, name="Private Investigator")
    effects.register_deathrattle(RESCUE_BOT, lambda c: _add_many(c, REPAIR_JOB, _amount(c, 1, 2)), name="Rescue Bot")
    effects.register_effect(ROARING_RECRUITER, GameEvent.ATTACK, _roaring_recruiter, zones=(EffectZone.COMBAT,), name="Roaring Recruiter")
    effects.register_battlecry(SAND_SWIRLER, _sand_swirler, name="Sand Swirler")
    effects.register_effect(SLY_INFILTRATOR, GameEvent.CARD_PLAYED, _sly_infiltrator, zones=(EffectZone.EVENT_SOURCE,), name="Sly Infiltrator")
    effects.register_deathrattle(SLY_RAPTOR, _sly_raptor, name="Sly Raptor")
    effects.register_target_rule(SPRIGHTLY_SCARAB, _target_ref_board_provider(types=("Beast",), exclude_source=False))
    effects.register_effect(SPRIGHTLY_SCARAB, GameEvent.CARD_PLAYED, _sprightly_scarab, zones=(EffectZone.EVENT_SOURCE,), name="Sprightly Scarab")
    effects.register_deathrattle(TASTY_LOBSTER, _tasty_lobster, name="Tasty Lobster")
    effects.register_effect(TIMECAP_N_HOOKTAIL, GameEvent.SPELL_CAST, _timecapn_hooktail, zones=(EffectZone.BOARD,), name="Timecap'n Hooktail")
    effects.register_deathrattle(TRAPPED_CLAPPER, _trapped_clapper, name="Trapped Clapper")
    effects.register_effect(TREASURE_PARROT, GameEvent.MINION_DAMAGED, _treasure_parrot, zones=(EffectZone.COMBAT,), name="Treasure Parrot")
    effects.register_end_of_turn(TRENCH_FIGHTER, lambda c: _add_many(c, GEM_CONFISCATION, _amount(c, 1, 2)), name="Trench Fighter")
    effects.register_deathrattle(WAVELING, _waveling, name="Waveling")
    effects.register_spellcraft(WAVERIDER, UNDERSEA_MOUNT)
    effects.register_effect(WILDFIRE_ELEMENTAL, GameEvent.AFTER_ATTACK, _wildfire_elemental, zones=(EffectZone.EVENT_SOURCE,), name="Wildfire Elemental")
    effects.register_rally(WOLF_PUP, _wolf_pup, name="Wolf Pup")


def _amber_guardian(ctx):
    side = _combat_side(ctx)
    if side is None:
        return
    dragons = [card for card in side.board if card is not ctx.source and _is_type(ctx.system, card, "Dragon")]
    count = min(len(dragons), _amount(ctx, 1, 2))
    for target in ctx.rng.sample(dragons, count) if count else []:
        ctx.buff(target, attack=2, health=2)
        ctx.grant_keyword(target, "Divine Shield")
        target["_combat_divine_shield"] = True


def _azsharan_cutlassier(ctx):
    state = _state(ctx)
    state["tavern_spell_attack_bonus"] = int(state.get("tavern_spell_attack_bonus", 0) or 0) + _amount(ctx, 1, 2)


def _blue_whelp(ctx):
    state = _state(ctx)
    state["tavern_spell_health_bonus"] = int(state.get("tavern_spell_health_bonus", 0) or 0) + _amount(ctx, 1, 2)


def _breakout_mastermind(ctx):
    _random_type(ctx, "Murloc", _amount(ctx, 1, 2))


def _cadaver_caretaker(ctx):
    _summon(ctx, 99629, _amount(ctx, 3, 6), position=ctx.event.get("death_position"))


def _cagey_conjurer(ctx):
    spells = _definitions(ctx.system, card_type="spell")
    if not spells:
        return
    for _ in range(_amount(ctx, 2, 4)):
        definition = ctx.random_choice(spells)
        spell = _fresh_card(ctx.system, definition.get("id"))
        target = ctx.source if ctx.system.has_target_rule(spell.get("id")) else None
        ctx.system.trigger_card_family(
            spell,
            TriggerFamily.SPELL,
            player_id=ctx.source_player_id,
            target=target,
        )


def _deflect_o_bot(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    summoned = ctx.event.get("minion")
    if not _is_type(ctx.system, summoned, "Mech"):
        return
    ctx.buff(ctx.source, attack=_amount(ctx, 2, 4))
    ctx.grant_keyword(ctx.source, "Divine Shield")
    ctx.source["_combat_divine_shield"] = True


def _devout_hellcaller(ctx):
    source_minion = ctx.event.get("source_minion")
    source_side = ctx.event.get("source_side")
    if source_side is None or getattr(source_side, "player_id", None) != ctx.source_player_id:
        return
    if source_minion is ctx.source or not _is_type(ctx.system, source_minion, "Demon"):
        return
    a, h = ((2, 4) if ctx.is_golden else (1, 2))
    _permanent_combat_buff(ctx, ctx.source, a, h)


def _diremuck_forager(ctx):
    side = _combat_side(ctx)
    player = _player(ctx)
    if side is None:
        return
    murlocs = [deepcopy(card) for card in player.hand if _is_type(ctx.system, card, "Murloc")]
    murlocs.sort(key=lambda card: int(card.get("attack", 0) or 0), reverse=True)
    count = _amount(ctx, 1, 2)
    engine = ctx.event.get("engine")
    for card in murlocs[:count]:
        if len(side.board) >= 7:
            break
        engine.summon(side, card)


def _disguised_graverobber(ctx):
    target = ctx.event.get("target")
    player = _player(ctx)
    if not isinstance(target, dict) or target is ctx.source:
        return
    try:
        index = player.board.index(target)
    except ValueError:
        return
    player.board[index] = None
    for _ in range(_amount(ctx, 1, 2)):
        _add_to_hand(ctx.system, ctx.source_player_id, target.get("id"), golden=False)


def _dustbone_devastator(ctx):
    amount = _amount(ctx, 1, 2)
    state = _state(ctx)
    state["undead_global_attack"] = int(state.get("undead_global_attack", 0) or 0) + amount
    player = _player(ctx)
    for card in list(player.board) + list(player.hand):
        if _is_type(ctx.system, card, "Undead"):
            ctx.system.apply_buff(card, attack=amount)
            card["_undead_global_applied"] = int(card.get("_undead_global_applied", 0) or 0) + amount


def _hired_mount(ctx):
    for _ in range(_amount(ctx, 1, 2)):
        card_id = ctx.random_choice(CHROMADRAKE_CHILD_IDS)
        _add_to_hand(ctx.system, ctx.source_player_id, card_id)


def _locked_up_mutineer(ctx):
    player = _player(ctx)
    existing = next((card for card in player.hand if isinstance(card, dict) and card.get("id") == LOCKBOX), None)
    reduction = _amount(ctx, 1, 2)
    if existing is not None:
        existing["_lockbox_turns_remaining"] = max(0, int(existing.get("_lockbox_turns_remaining", 5) or 0) - reduction)
        return
    card = _add_to_hand(ctx.system, ctx.source_player_id, LOCKBOX)
    if card is not None:
        card["_lockbox_turns_remaining"] = 5


def _mrrglton_amount(ctx):
    prior = max(0, int(_state(ctx).get("mrrgltons_played", 1) or 1) - 1)
    return _amount(ctx, 3 + prior, 6 + 2 * prior)


def _mama_mrrglton(ctx):
    amount = _mrrglton_amount(ctx)
    for card in _friendly_of_type(ctx.system, _player(ctx), "Murloc"):
        if card is not ctx.source:
            ctx.buff(card, attack=amount)


def _papa_mrrglton(ctx):
    amount = _mrrglton_amount(ctx)
    for card in _friendly_of_type(ctx.system, _player(ctx), "Murloc"):
        if card is not ctx.source:
            ctx.buff(card, health=amount)


def _meteorite_crasher(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    sold = ctx.event.get("card") or ctx.event.get("minion")
    if _is_type(ctx.system, sold, "Elemental"):
        amount = _amount(ctx, 4, 8)
        ctx.buff(ctx.source, attack=amount, health=amount)


def _mummifier(ctx):
    side = _combat_side(ctx)
    if side is None:
        return
    targets = [card for card in side.board if card is not ctx.source and _is_type(ctx.system, card, "Undead") and not _has_keyword(ctx.system, card, "Reborn")]
    count = min(len(targets), _amount(ctx, 1, 2))
    for target in ctx.rng.sample(targets, count) if count else []:
        ctx.grant_keyword(target, "Reborn")
        target["_combat_reborn_available"] = True


def _private_investigator(ctx):
    state = _state(ctx)
    state["pending_gold_next_turn"] = int(state.get("pending_gold_next_turn", 0) or 0) + _amount(ctx, 3, 6)


def _roaring_recruiter(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    attacker = ctx.event.get("attacker")
    if attacker is ctx.source or not _is_type(ctx.system, attacker, "Dragon"):
        return
    a, h = ((6, 2) if ctx.is_golden else (3, 1))
    ctx.buff(attacker, attack=a, health=h)


def _sand_swirler(ctx):
    state = _state(ctx)
    state["elemental_effect_attack_bonus"] = int(state.get("elemental_effect_attack_bonus", 0) or 0) + _amount(ctx, 2, 4)


def _sly_infiltrator(ctx):
    if ctx.event.get("card") is not ctx.source:
        return False
    ctx.start_choice(
        "tier36_sly_infiltrator",
        ["refreshes", "blood_gems"],
        kind="choose_one",
        metadata={"golden": ctx.is_golden},
    )
    return True


def _sly_raptor(ctx):
    beasts = _definitions(ctx.system, minion_type="Beast")
    if not beasts:
        return
    card = _fresh_card(ctx.system, ctx.random_choice(beasts).get("id"))
    stats = _amount(ctx, 6, 12)
    card["attack"] = stats
    card["health"] = stats
    _summon(ctx, card, position=ctx.event.get("death_position"))


def _sprightly_scarab(ctx):
    if ctx.event.get("card") is not ctx.source:
        return False
    target = ctx.event.get("target")
    if not _is_type(ctx.system, target, "Beast"):
        return False
    ctx.start_choice(
        "tier36_sprightly_scarab",
        ["reborn", "windfury"],
        kind="choose_one",
        metadata={"target": target, "golden": ctx.is_golden},
    )
    return True


def _tasty_lobster(ctx):
    side = _combat_side(ctx)
    if side is not None:
        beasts = [card for card in side.board if _is_type(ctx.system, card, "Beast")]
        if beasts:
            target = ctx.random_choice(beasts)
            amount = _amount(ctx, 1, 2)
            ctx.buff(target, attack=amount, health=amount)
    amount = _amount(ctx, 1, 2)
    state = _state(ctx)
    state["tasty_lobster_future_attack"] = int(state.get("tasty_lobster_future_attack", 0) or 0) + amount
    state["tasty_lobster_future_health"] = int(state.get("tasty_lobster_future_health", 0) or 0) + amount


def _timecapn_hooktail(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    if not _tavern_spell(ctx.event.get("spell")):
        return
    amount = _amount(ctx, 1, 2)
    for card in _friendly_cards(_player(ctx)):
        ctx.buff(card, attack=amount)


def _trapped_clapper(ctx):
    state = _state(ctx)
    state["fodder_refreshes_remaining"] = max(int(state.get("fodder_refreshes_remaining", 0) or 0), 3)
    state["fodder_per_refresh"] = max(int(state.get("fodder_per_refresh", 0) or 0), _amount(ctx, 1, 2))


def _treasure_parrot(ctx):
    source_minion = ctx.event.get("source_minion")
    source_side = ctx.event.get("source_side")
    if source_minion is not ctx.source or source_side is None or getattr(source_side, "player_id", None) != ctx.source_player_id:
        return
    state_card = _current_source_card_for_state(ctx)
    if state_card.get("_treasure_parrot_completed"):
        return
    dealt = int(state_card.get("_treasure_parrot_damage", 0) or 0) + int(ctx.event.get("amount", 0) or 0)
    state_card["_treasure_parrot_damage"] = dealt
    if dealt >= 35:
        state_card["_treasure_parrot_completed"] = True
        _add_many(ctx, GOLDEN_TOUCH, _amount(ctx, 1, 2))


def _waveling(ctx):
    state = _state(ctx)
    count = _amount(ctx, 1, 2)
    state.setdefault("refresh_random_buffs", []).extend([(4, 4)] * count)


def _wildfire_elemental(ctx):
    if ctx.event.get("attacker") is not ctx.source or not ctx.event.get("target_died"):
        return
    excess = int(ctx.event.get("excess_damage", 0) or 0)
    if excess <= 0:
        return
    engine = ctx.event.get("engine")
    defending = ctx.event.get("defending_side")
    position = ctx.event.get("target_position_before")
    if engine is None or defending is None or position is None:
        return
    positions = [position - 1, position]
    targets = [defending.board[i] for i in positions if 0 <= i < len(defending.board)]
    if not ctx.is_golden and targets:
        targets = [ctx.random_choice(targets)]
    for target in targets:
        engine.deal_minion_damage(ctx.source, target, excess, source_side=ctx.event.get("attacking_side"), target_side=defending)


def _wolf_pup(ctx):
    side = _combat_side(ctx)
    if side is None:
        return
    a, h = ((8, 2) if ctx.is_golden else (4, 1))
    for card in side.board:
        if card is not ctx.source:
            ctx.buff(card, attack=a, health=h)

# =============================================================
# TIER 4
# =============================================================


def _register_tier4(effects):
    effects.register_effect(ABYSSAL_BRUISER, GameEvent.SPELL_CAST, _abyssal_bruiser, zones=(EffectZone.BOARD,), name="Abyssal Bruiser")
    effects.register_effect(ABYSSAL_BRUISER, GameEvent.CARD_PLAYED, _abyssal_bruiser_sync, zones=(EffectZone.EVENT_SOURCE,), name="Abyssal Bruiser sync")
    effects.register_effect(AIR_BALLER, GameEvent.CARD_SOLD, _air_baller, zones=(EffectZone.EVENT_SOURCE,), name="Air Baller")
    effects.register_effect(ASHEN_CORRUPTOR, GameEvent.PLAYER_DAMAGED, _ashen_corruptor, zones=(EffectZone.BOARD,), name="Ashen Corruptor")
    effects.register_deathrattle(AUTO_ASSEMBLER, _auto_assembler, name="Auto Assembler")
    effects.register_effect(BANANA_SLAMMA, GameEvent.MINION_SUMMONED, _banana_slamma, zones=(EffectZone.COMBAT,), name="Banana Slamma")
    effects.register_rally(BIGWIG_BANDIT, lambda c: _random_bounties(c, _amount(c, 1, 2)), name="Bigwig Bandit")
    effects.register_effect(BLADE_COLLECTOR, GameEvent.ATTACK, _blade_collector, zones=(EffectZone.EVENT_SOURCE,), name="Blade Collector")
    effects.register_rally(BONKER, _bonker, name="Bonker")
    effects.register_start_of_combat(BOOM_IN_A_BOX, _boom_in_a_box, name="Boom-in-a-Box")
    effects.register_rally(BRAMBLE_TUNNELER, _bramble_tunneler, name="Bramble Tunneler")
    effects.register_effect(BREAM_COUNTER, GameEvent.CARD_PLAYED, _bream_counter, zones=(EffectZone.HAND,), name="Bream Counter")
    effects.register_rally(BRONZE_TIMEWALKER, _bronze_timewalker, name="Bronze Timewalker")
    effects.register_effect(CAGE_GNAWER, GameEvent.ATTACK, _cage_gnawer, zones=(EffectZone.COMBAT,), name="Cage Gnawer")
    effects.register_deathrattle(CAPTAIN_COOKIE, lambda c: _add_many(c, CHEFS_CHOICE, _amount(c, 1, 2)), name="Captain Cookie")
    effects.register_target_rule(CLUNKER_JUNKER, _target_ref_board_provider(types=("Mech",)))
    effects.register_battlecry(CLUNKER_JUNKER, _clunker_junker, name="Clunker Junker")
    effects.register_activate(DEAD_BELLRINGER, 1, _dead_bellringer, target_provider=_target_ref_board_provider(types=("Undead",), exclude_source=True), name="Dead Bellringer")
    effects.register_battlecry(DEEPWATER_CHIEFTAIN, lambda c: _add_many(c, DEEPWATER_CLAN, _amount(c, 1, 2)), name="Deepwater Chieftain Battlecry")
    effects.register_deathrattle(DEEPWATER_CHIEFTAIN, lambda c: _add_many(c, DEEPWATER_CLAN, _amount(c, 1, 2)), name="Deepwater Chieftain Deathrattle")
    effects.register_activate(DRONE_DUPLICATOR, 1, _drone_duplicator, name="Drone Duplicator")
    effects.register_battlecry(EN_DJINN_BLAZER, _en_djinn_blazer, name="En-Djinn Blazer")
    effects.register_effect(ENCHANTED_SENTINEL, GameEvent.SPELL_CAST, _enchanted_sentinel, zones=(EffectZone.BOARD,), name="Enchanted Sentinel")
    effects.register_effect(FEARLESS_FOODIE, GameEvent.CARD_PLAYED, _fearless_foodie, zones=(EffectZone.EVENT_SOURCE,), name="Fearless Foodie")
    effects.register_end_of_turn(FLAMING_ENFORCER, _flaming_enforcer, name="Flaming Enforcer")
    effects.register_deathrattle(FRIENDLY_GEIST, _friendly_geist, name="Friendly Geist")
    effects.register_end_of_turn(GEARFIN, _gearfin, name="Gearfin")
    effects.register_effect(GLAMBOT, GameEvent.SPELL_CAST, _glambot, zones=(EffectZone.BOARD,), name="Glambot")
    effects.register_deathrattle(GLOWING_CINDER, _glowing_cinder, name="Glowing Cinder")
    effects.register_effect(GUNPOWDER_COURIER, GameEvent.GOLD_SPENT, _gunpowder_courier, zones=(EffectZone.BOARD,), name="Gunpowder Courier")
    effects.register_rally(HEADHUNTER_GRYPHON, lambda c: _random_type(c, "Beast", _amount(c, 1, 2)), name="Headhunter Gryphon")
    effects.register_rally(HEROIC_UNDERDOG, _heroic_underdog, name="Heroic Underdog")
    effects.register_effect(HUMON_GOZZ, GameEvent.SPELL_CAST, _humongozz, zones=(EffectZone.BOARD,), name="Humon'gozz")
    effects.register_deathrattle(IMP_LUSIONIST, lambda c: _add_many(c, METHODICAL_MADNESS, _amount(c, 1, 2)), name="Imp-lusionist")
    effects.register_battlecry(IMPOSING_PERCUSSIONIST, _imposing_percussionist, name="Imposing Percussionist")
    effects.register_activate(KELP_KEEPER, 1, _kelp_keeper, target_provider=_battlecry_targets, name="Kelp Keeper")
    effects.register_activate(LIVING_PRISON, 1, _living_prison_activate, name="Living Prison")
    effects.register_effect(LIVING_PRISON, GameEvent.CARD_BOUGHT, _living_prison_bought, zones=(EffectZone.BOARD,), name="Living Prison buy")
    effects.register_target_rule(LOVESICK_BALLADIST, _target_ref_board_provider(types=("Pirate",)))
    effects.register_battlecry(LOVESICK_BALLADIST, _lovesick_balladist, name="Lovesick Balladist")
    effects.register_effect(MARITIME_EXTORTIONIST, GameEvent.CARD_PLAYED, _maritime_extortionist_sync, zones=(EffectZone.BOARD, EffectZone.HAND), name="Maritime Extortionist")
    effects.register_target_rule(MAW_CASTER, _target_ref_board_provider(types=("Undead",), exclude_source=True))
    effects.register_battlecry(MAW_CASTER, _maw_caster, name="Maw Caster")
    effects.register_deathrattle(MOTLEY_PHALANX, _motley_phalanx, name="Motley Phalanx")
    effects.register_deathrattle(PLAGUERUNNER, _plaguerunner, name="Plaguerunner")
    effects.register_deathrattle(RAZORFEN_FLAPPER, lambda c: _add_many(c, BLOOD_GEM_BARRAGE, _amount(c, 1, 2)), name="Razorfen Flapper")
    effects.register_battlecry(REFRESHING_ANOMALY, lambda c: c.system.grant_free_refreshes(c.source_player_id, _amount(c, 2, 4)), name="Refreshing Anomaly")
    effects.register_spellcraft(RIMESCALE_PRIESTESS, RIME_OR_REASON)
    effects.register_start_of_combat(RUNIC_ARCANIST, lambda c: _cast_registered_spell(c, SHINY_RING, count=_amount(c, 2, 4)), name="Runic Arcanist")
    effects.register_rally(SEAFLOOR_RECRUITER, _seafloor_recruiter, name="Seafloor Recruiter")
    effects.register_rally(SIN_DOREI_STRAIGHT_SHOT, _sindorei_straight_shot, name="Sin'dorei Straight Shot")
    effects.register_activate(SKY_HATCH_RUNAWAY, 1, _sky_hatch_runaway, target_provider=_rally_targets, name="Sky-hatch Runaway")
    effects.register_effect(SNARE_TRAPPER, GameEvent.CARD_PLAYED, _snare_trapper, zones=(EffectZone.EVENT_SOURCE,), name="Snare Trapper")
    effects.register_effect(SNARKY_SHARK, GameEvent.CARD_SOLD, _snarky_shark, zones=(EffectZone.EVENT_SOURCE,), name="Snarky Shark")
    effects.register_activate(SOULKEEPING_JAILER, 2, _soulkeeping_jailer, name="Soulkeeping Jailer")
    effects.register_battlecry(TAVERN_TEMPEST, lambda c: _random_type(c, "Elemental", _amount(c, 1, 2)), name="Tavern Tempest")
    effects.register_effect(TWILIGHT_TIDEHUNTER, GameEvent.SPELL_CAST, _twilight_tidehunter, zones=(EffectZone.BOARD,), name="Twilight Tidehunter")
    effects.register_effect(ZESTY_SHAKER, GameEvent.SPELL_CAST, _zesty_shaker, zones=(EffectZone.BOARD,), name="Zesty Shaker")


def _abyssal_bruiser_sync(ctx):
    if ctx.event.get("card") is not ctx.source:
        return False
    count = int(_state(ctx).get("tavern_spells_cast_game", 0) or 0)
    a, h = ((4, 2) if ctx.is_golden else (2, 1))
    ctx.buff(ctx.source, attack=a * count, health=h * count)
    return True


def _abyssal_bruiser(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id or not _tavern_spell(ctx.event.get("spell")):
        return
    a, h = ((4, 2) if ctx.is_golden else (2, 1))
    ctx.buff(ctx.source, attack=a, health=h)


def _air_baller(ctx):
    if ctx.event.get("card") is not ctx.source:
        return
    a = h = _amount(ctx, 2, 4)
    player = _player(ctx)
    for card in _friendly_cards(player):
        ctx.buff(card, attack=a, health=h)
    state = _state(ctx)
    state["air_baller_future_attack"] = int(state.get("air_baller_future_attack", 0) or 0) + a
    state["air_baller_future_health"] = int(state.get("air_baller_future_health", 0) or 0) + h


def _ashen_corruptor(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    player = _player(ctx)
    player.health = int(getattr(player, "health", 0) or 0) + int(ctx.event.get("health_damage", 0) or 0)
    player.armor = int(getattr(player, "armor", 0) or 0) + int(ctx.event.get("armor_damage", 0) or 0)
    amount = _amount(ctx, 1, 2)
    for card in getattr(player.tavern, "slots", []):
        if isinstance(card, dict):
            ctx.buff(card, attack=amount, health=amount, until_next_turn=True)


def _auto_assembler(ctx):
    _summon(ctx, ANCESTRAL_AUTOMATON, 1, golden=ctx.is_golden, position=ctx.event.get("death_position"))


def _banana_slamma(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    summoned = ctx.event.get("minion")
    if not _is_type(ctx.system, summoned, "Beast"):
        return
    multiplier = 3 if ctx.is_golden else 2
    current = int(summoned.get("attack", 0) or 0)
    summoned["attack"] = current * multiplier


def _blade_collector(ctx):
    if ctx.event.get("attacker") is not ctx.source:
        return
    engine = ctx.event.get("engine")
    defending = ctx.event.get("defending_side")
    target = ctx.event.get("target")
    attacking = ctx.event.get("attacking_side")
    if engine is None or defending is None or target not in defending.board:
        return
    index = defending.board.index(target)
    damage = engine.get_attack(ctx.source)
    for pos in (index - 1, index + 1):
        if 0 <= pos < len(defending.board):
            engine.deal_minion_damage(ctx.source, defending.board[pos], damage, source_side=attacking, target_side=defending)


def _bonker(ctx):
    side = _combat_side(ctx)
    if side is None:
        return
    for card in side.board:
        if card is not ctx.source:
            _blood_gem(ctx, card, _amount(ctx, 1, 2))


def _boom_in_a_box(ctx):
    engine = ctx.event.get("engine")
    if engine is None:
        return
    sides = []
    for key in ("side_a", "side_b"):
        side = ctx.event.get(key)
        if side is not None and side not in sides:
            sides.append(side)
    for _ in range(_amount(ctx, 1, 2)):
        for side in sides:
            for target in list(side.board):
                if target is ctx.source:
                    continue
                engine.deal_minion_damage(ctx.source, target, 3, source_side=_combat_side(ctx), target_side=side)


def _bramble_tunneler(ctx):
    candidates = _definitions(ctx.system, predicate=_card_has_choose_one)
    _add_random(ctx, candidates, _amount(ctx, 1, 2))


def _bream_counter(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    played = ctx.event.get("card")
    if _is_type(ctx.system, played, "Murloc"):
        amount = _amount(ctx, 6, 12)
        ctx.buff(ctx.source, attack=amount, health=amount)


def _bronze_timewalker(ctx):
    for _ in range(_amount(ctx, 1, 2)):
        _add_to_hand(ctx.system, ctx.source_player_id, ctx.random_choice(CHROMADRAKE_CHILD_IDS))


def _cage_gnawer(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    attacker = ctx.event.get("attacker")
    if not _is_type(ctx.system, attacker, "Beast"):
        return
    side = _combat_side(ctx)
    a, h = ((4, 2) if ctx.is_golden else (2, 1))
    for card in side.board if side is not None else []:
        if _is_type(ctx.system, card, "Beast"):
            ctx.buff(card, attack=a, health=h)


def _battlecry_targets(context):
    effects = context.game.effects
    result = []
    for index, card in enumerate(context.game.get_player(context.player_id).board):
        if not isinstance(card, dict):
            continue
        if any(effect.family == TriggerFamily.BATTLECRY for effect in effects.get_effects_for_card(card.get("id"))):
            result.append(index)
    return result


def _rally_targets(context):
    effects = context.game.effects
    result = []
    for index, card in enumerate(context.game.get_player(context.player_id).board):
        if not isinstance(card, dict):
            continue
        if any(effect.family == TriggerFamily.RALLY for effect in effects.get_effects_for_card(card.get("id"))):
            result.append(index)
    return result


def _clunker_junker(ctx):
    target = ctx.event.get("target")
    if not _is_type(ctx.system, target, "Mech"):
        return
    candidates = _definitions(ctx.system, minion_type="Mech", predicate=lambda c: ctx.system.has_keyword(c, "Magnetic"))
    ctx.system.discover_cards(
        ctx.source_player_id,
        candidates,
        resolver_key="tier36_magnetize_discover",
        metadata={"target": target, "remaining": _amount(ctx, 1, 2)},
    )


def _dead_bellringer(ctx):
    target = ctx.event.get("target")
    if not _is_type(ctx.system, target, "Undead") or target is ctx.source:
        return
    ctx.grant_keyword(target, "Reborn")
    player = _player(ctx)
    try:
        player.board[player.board.index(target)] = None
    except ValueError:
        pass
    amount = _amount(ctx, 4, 8)
    ctx.buff(ctx.source, attack=amount, health=amount)


def _drone_duplicator(ctx):
    ctx.source["_next_magnetization_multiplier"] = 3 if ctx.is_golden else 2


def _en_djinn_blazer(ctx):
    _state(ctx).setdefault("refresh_random_buffs", []).extend([(10, 10)] * _amount(ctx, 1, 2))


def _enchanted_sentinel(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id or not _tavern_spell(ctx.event.get("spell")):
        return
    target = ctx.event.get("target")
    if isinstance(target, dict):
        amount = _amount(ctx, 1, 2)
        ctx.buff(target, attack=amount, health=amount)


def _fearless_foodie(ctx):
    if ctx.event.get("card") is not ctx.source:
        return False
    ctx.start_choice("tier36_fearless_foodie", ["improve", "gems"], kind="choose_one", metadata={"golden": ctx.is_golden})
    return True


def _flaming_enforcer(ctx):
    _consume_tavern(ctx, double=ctx.is_golden, highest_health=True)


def _friendly_geist(ctx):
    state = _state(ctx)
    state["tavern_spell_attack_bonus"] = int(state.get("tavern_spell_attack_bonus", 0) or 0) + _amount(ctx, 1, 2)


def _gearfin(ctx):
    _random_tavern_spells(ctx, _amount(ctx, 2, 4), predicate=lambda card: int(card.get("manaCost", 0) or 0) == 1)


def _satellite(stats):
    return {
        "id": 116244,
        "name": "Satellite",
        "cardType": "minion",
        "attack": stats,
        "health": stats,
        "minionType": "Mech",
        "minionTypes": ["Mech"],
        "keywords": ["Magnetic"],
        "_generated": True,
    }


def _glambot(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    target = ctx.event.get("target")
    if not _is_type(ctx.system, target, "Mech"):
        return
    for _ in range(_amount(ctx, 1, 2)):
        ctx.system.magnetize(_satellite(4), target)


def _glowing_cinder(ctx):
    state = _state(ctx)
    state["elemental_effect_health_bonus"] = int(state.get("elemental_effect_health_bonus", 0) or 0) + _amount(ctx, 2, 4)


def _counter_spend(ctx, threshold, key):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return 0
    source = _current_source_card_for_state(ctx)
    current = int(source.get(key, 0) or 0) + int(ctx.event.get("amount", 0) or 0)
    triggers, remainder = divmod(current, threshold)
    source[key] = remainder
    return triggers


def _gunpowder_courier(ctx):
    triggers = _counter_spend(ctx, 5, "_gunpowder_gold")
    if triggers <= 0:
        return
    amount = 2 * triggers * (2 if ctx.is_golden else 1)
    for card in _friendly_of_type(ctx.system, _player(ctx), "Pirate"):
        ctx.buff(card, attack=amount)


def _heroic_underdog(ctx):
    target = ctx.event.get("target")
    if isinstance(target, dict):
        ctx.buff(ctx.source, attack=int(target.get("attack", 0) or 0) * (2 if ctx.is_golden else 1))


def _humongozz(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id or not _tavern_spell(ctx.event.get("spell")):
        return
    target = ctx.event.get("target")
    if isinstance(target, dict):
        a, h = ((2, 4) if ctx.is_golden else (1, 2))
        ctx.buff(target, attack=a, health=h)


def _imposing_percussionist(ctx):
    candidates = _definitions(ctx.system, minion_type="Demon")
    ctx.system.discover_cards(
        ctx.source_player_id,
        candidates,
        resolver_key="tier36_demon_discover_damage",
        metadata={"remaining": _amount(ctx, 1, 2)},
    )


def _kelp_keeper(ctx):
    target = ctx.event.get("target")
    if not isinstance(target, dict):
        return
    for _ in range(_amount(ctx, 1, 2)):
        ctx.system.trigger_card_family(target, TriggerFamily.BATTLECRY, player_id=ctx.source_player_id, target=None, minion=target)


def _living_prison_activate(ctx):
    _current_source_card_for_state(ctx)["_living_prison_waiting"] = 2 if ctx.is_golden else 1


def _living_prison_bought(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    source = _current_source_card_for_state(ctx)
    multiplier = int(source.get("_living_prison_waiting", 0) or 0)
    bought = ctx.event.get("card")
    if multiplier <= 0 or not isinstance(bought, dict):
        return
    source["_living_prison_waiting"] = 0
    ctx.buff(ctx.source, attack=int(bought.get("attack", 0) or 0) * multiplier, health=int(bought.get("health", 0) or 0) * multiplier)


def _lovesick_balladist(ctx):
    target = ctx.event.get("target")
    if not _is_type(ctx.system, target, "Pirate"):
        return
    spent = int(_state(ctx).get("gold_spent_turn", 0) or 0)
    amount = 1 + spent
    if ctx.is_golden:
        amount *= 2
    ctx.buff(target, health=amount)


def _maritime_extortionist_sync(ctx):
    _apply_global_card_modifiers(ctx.system, ctx.source_player_id, ctx.source)


def _maw_caster(ctx):
    target = ctx.event.get("target")
    player = _player(ctx)
    if not _is_type(ctx.system, target, "Undead"):
        return
    try:
        player.board[player.board.index(target)] = None
    except ValueError:
        return
    candidates = _definitions(ctx.system, minion_type="Undead")
    ctx.system.discover_cards(
        ctx.source_player_id,
        candidates,
        resolver_key="tier36_multi_add_discover",
        metadata={"remaining": _amount(ctx, 1, 2)},
    )


def _motley_phalanx(ctx):
    side = _combat_side(ctx)
    if side is None:
        return
    amount = _amount(ctx, 3, 6)
    types = ["Beast", "Demon", "Dragon", "Elemental", "Mech", "Murloc", "Naga", "Pirate", "Quilboar", "Undead"]
    used = set()
    for minion_type in types:
        candidates = [card for card in side.board if id(card) not in used and _is_type(ctx.system, card, minion_type)]
        if not candidates:
            continue
        target = ctx.random_choice(candidates)
        used.add(id(target))
        _permanent_combat_buff(ctx, target, amount, amount)


def _plaguerunner(ctx):
    outside_combat = _combat_side(ctx) is None
    amount = _amount(ctx, 4 if outside_combat else 2, 8 if outside_combat else 4)
    state = _state(ctx)
    state["undead_global_attack"] = int(state.get("undead_global_attack", 0) or 0) + amount
    player = _player(ctx)
    for card in list(player.board) + list(player.hand):
        if _is_type(ctx.system, card, "Undead"):
            ctx.system.apply_buff(card, attack=amount)
            card["_undead_global_applied"] = int(card.get("_undead_global_applied", 0) or 0) + amount


def _seafloor_recruiter(ctx):
    side = _combat_side(ctx)
    if side is None or ctx.source not in side.board:
        return
    index = side.board.index(ctx.source)
    if index + 1 >= len(side.board):
        return
    target = side.board[index + 1]
    for _ in range(_amount(ctx, 1, 2)):
        _cast_registered_spell(ctx, CHEFS_CHOICE, target=target)


def _sindorei_straight_shot(ctx):
    target = ctx.event.get("target")
    if not isinstance(target, dict):
        return
    _remove_keyword(target, "Reborn")
    _remove_keyword(target, "Taunt")


def _sky_hatch_runaway(ctx):
    target = ctx.event.get("target")
    if not isinstance(target, dict):
        return
    for _ in range(_amount(ctx, 1, 2)):
        ctx.system.trigger_card_family(target, TriggerFamily.RALLY, player_id=ctx.source_player_id, attacker=target)


def _snare_trapper(ctx):
    if ctx.event.get("card") is not ctx.source:
        return False
    ctx.start_choice("tier36_snare_trapper", ["quilboar", "max_gold"], kind="choose_one", metadata={"golden": ctx.is_golden})
    return True


def _snarky_shark(ctx):
    if ctx.event.get("card") is not ctx.source:
        return
    player = _player(ctx)
    try:
        player.tavern.refresh(ctx.system.game.pool)
    except TypeError:
        player.tavern.refresh()
    fishbait = _fresh_card(ctx.system, FISHBAIT, golden=ctx.is_golden)
    if player.tavern.slots:
        player.tavern.slots[0] = fishbait
    beast = next((card for card in player.board if _is_type(ctx.system, card, "Beast")), None)
    if beast is not None and int(beast.get("attack", 0) or 0) > 0:
        bonus = 10 if ctx.is_golden else 5
        ctx.buff(beast, attack=bonus, health=bonus)


def _soulkeeping_jailer(ctx):
    player = _player(ctx)
    double = ctx.is_golden
    for demon in [card for card in player.board if _is_type(ctx.system, card, "Demon")]:
        _consume_tavern(ctx, target=demon, double=double)


def _twilight_tidehunter(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id or ctx.event.get("target") is not ctx.source:
        return
    hand = [card for card in _player(ctx).hand if isinstance(card, dict)]
    if hand:
        amount = _amount(ctx, 8, 16)
        ctx.buff(hand[0], attack=amount, health=amount)


def _zesty_shaker(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id or ctx.event.get("target") is not ctx.source:
        return
    spell = ctx.event.get("spell")
    if not isinstance(spell, dict) or not spell.get("_spellcraft_temporary", False):
        return
    source = _current_source_card_for_state(ctx)
    round_number = int(getattr(ctx.system.game, "round_number", 0) or 0)
    if source.get("_zesty_round") == round_number:
        return
    source["_zesty_round"] = round_number
    for _ in range(_amount(ctx, 1, 2)):
        _add_to_hand(ctx.system, ctx.source_player_id, deepcopy(spell))

# =============================================================
# TIER 5
# =============================================================


def _register_tier5(effects):
    effects.register_effect(AIR_REVENANT, GameEvent.GOLD_SPENT, _air_revenant, zones=(EffectZone.BOARD,), name="Air Revenant")
    effects.register_effect(BARRIER_BANSHEE, GameEvent.REBORN, _barrier_banshee, zones=(EffectZone.COMBAT,), name="Barrier Banshee")
    effects.register_rally(BILE_SPITTER, _bile_spitter, name="Bile Spitter")
    effects.register_trigger_multiplier(BRANN_BRONZEBEARD, (TriggerFamily.BATTLECRY,), extra_normal=1, extra_golden=2, zones=(EffectZone.BOARD,), name="Brann Bronzebeard")
    effects.register_end_of_turn(CATACLYSMIC_HARBINGER, _cataclysmic_harbinger, name="Cataclysmic Harbinger")
    effects.register_effect(CHARGING_CZARINA, GameEvent.SPELL_CAST, _charging_czarina, zones=(EffectZone.BOARD,), name="Charging Czarina")
    effects.register_start_of_combat(COSTUME_ENTHUSIAST, _costume_enthusiast, name="Costume Enthusiast")
    effects.register_end_of_turn(COUSIN_ERRGL, _cousin_errgl, name="Cousin Errgl")
    effects.register_battlecry(DANCING_BARNSTORMER, _dancing_barnstormer, name="Dancing Barnstormer Battlecry")
    effects.register_deathrattle(DANCING_BARNSTORMER, _dancing_barnstormer, name="Dancing Barnstormer Deathrattle")
    effects.register_spellcraft(DARKCREST_STRATEGIST, EVOLVING_STRATEGY)
    effects.register_start_of_turn(DARKCREST_STRATEGIST, _darkcrest_turn_start, name="Darkcrest Strategist improve")
    effects.register_activate(DEFT_DESERTER, 1, _deft_deserter, name="Deft Deserter")
    effects.register_effect(DEVILISH_DISTRACTOR, GameEvent.SPELL_CAST, _devilish_distractor, zones=(EffectZone.BOARD,), name="Devilish Distractor")
    effects.register_battlecry(DRACONIC_WARDEN, _draconic_warden, name="Draconic Warden Battlecry")
    effects.register_deathrattle(DRACONIC_WARDEN, _draconic_warden, name="Draconic Warden Deathrattle")
    effects.register_trigger_multiplier(DRAKKARI_ENCHANTER, (TriggerFamily.END_OF_TURN,), extra_normal=1, extra_golden=2, zones=(EffectZone.BOARD,), name="Drakkari Enchanter")
    effects.register_avenge(DRUSTFALLEN_BUTCHER, 4, lambda c: _add_many(c, BUTCHERING, _amount(c, 1, 2)), name="Drustfallen Butcher")
    effects.register_effect(DUAL_WIELD_CORSAIR, GameEvent.GOLD_SPENT, _dual_wield_corsair, zones=(EffectZone.BOARD,), name="Dual-Wield Corsair")
    effects.register_effect(ENTERPRISING_ESCAPEE, GameEvent.GOLD_SPENT, _enterprising_escapee, zones=(EffectZone.BOARD,), name="Enterprising Escapee")
    effects.register_effect(FELBOAR, GameEvent.TRIGGER_RESOLVED, _felboar, zones=(EffectZone.BOARD,), name="Felboar")
    effects.register_end_of_turn(FELFIRE_CONJURER, _felfire_conjurer, name="Felfire Conjurer")
    effects.register_battlecry(FIRESCALE_HOARDER, lambda c: _add_many(c, SHINY_RING, _amount(c, 1, 2)), name="Firescale Hoarder Battlecry")
    effects.register_deathrattle(FIRESCALE_HOARDER, lambda c: _add_many(c, SHINY_RING, _amount(c, 1, 2)), name="Firescale Hoarder Deathrattle")
    effects.register_spellcraft(GLOWSCALE, GLOWING_CROWN)
    effects.register_rally(HOARDING_HYENA, _hoarding_hyena, name="Hoarding Hyena")
    effects.register_effect(INSATIABLE_UR_ZUL, GameEvent.CARD_PLAYED, _insatiable_urzul, zones=(EffectZone.BOARD,), name="Insatiable Ur'zul")
    effects.register_effect(KALECGOS_ARCANE_ASPECT, GameEvent.TRIGGER_RESOLVED, _kalecgos, zones=(EffectZone.BOARD,), name="Kalecgos")
    effects.register_deathrattle(KANGOR_S_APPRENTICE, _kangors_apprentice, name="Kangor's Apprentice")
    effects.register_deathrattle(LEEROY_THE_RECKLESS, _leeroy, name="Leeroy the Reckless")
    effects.register_effect(LURKING_LEVIATHAN, GameEvent.MINION_SUMMONED, _lurking_leviathan, zones=(EffectZone.COMBAT,), name="Lurking Leviathan")
    effects.register_battlecry(NIGHTMARE_PAR_TEA_GUEST, lambda c: _add_many(c, MISPLACED_TEA_SET, _amount(c, 1, 2)), name="Nightmare Par-tea Guest Battlecry")
    effects.register_deathrattle(NIGHTMARE_PAR_TEA_GUEST, lambda c: _add_many(c, MISPLACED_TEA_SET, _amount(c, 1, 2)), name="Nightmare Par-tea Guest Deathrattle")
    effects.register_effect(NOMI_KITCHEN_NIGHTMARE, GameEvent.CARD_PLAYED, _nomi, zones=(EffectZone.BOARD,), name="Nomi")
    effects.register_battlecry(PRIMALFIN_LOOKOUT, _primalfin_lookout, name="Primalfin Lookout")
    effects.register_trigger_multiplier(PROUD_PRIVATEER, (TriggerFamily.SPELL,), extra_normal=1, extra_golden=2, zones=(EffectZone.BOARD,), condition=_bounty_multiplier_condition, name="Proud Privateer")
    effects.register_rally(RAZORFEN_VINEWEAVER, lambda c: _blood_gem(c, c.source, _amount(c, 3, 6)), name="Razorfen Vineweaver")
    effects.register_battlecry(RODEO_PERFORMER, _rodeo_performer, name="Rodeo Performer")
    effects.register_rally(SANGUINE_REFINER, _sanguine_refiner, name="Sanguine Refiner")
    effects.register_deathrattle(SCRAP_SCRAPER, _scrap_scraper, name="Scrap Scraper")
    effects.register_deathrattle(SEWER_LORD, _sewer_lord, name="Sewer Lord")
    effects.register_deathrattle(70790, _sewer_rat_deathrattle, name="Sewer Rat")
    effects.register_effect(SHAMANIC_TIDECALLER, GameEvent.SPELL_CAST, _shamanic_tidecaller, zones=(EffectZone.BOARD,), name="Shamanic Tidecaller")
    effects.register_battlecry(SHIPWRECKED_RASCAL, lambda c: _random_bounties(c, _amount(c, 1, 2)), name="Shipwrecked Rascal Battlecry")
    effects.register_deathrattle(SHIPWRECKED_RASCAL, lambda c: _random_bounties(c, _amount(c, 1, 2)), name="Shipwrecked Rascal Deathrattle")
    effects.register_deathrattle(SHOWY_CYCLIST, _showy_cyclist, name="Showy Cyclist")
    effects.register_effect(SPARK_SNAPPER, GameEvent.CARD_PLAYED, _spark_snapper, zones=(EffectZone.BOARD,), name="Spark Snapper")
    effects.register_effect(TICHONDRIUS, GameEvent.PLAYER_DAMAGED, _tichondrius, zones=(EffectZone.BOARD,), name="Tichondrius")
    effects.register_trigger_multiplier(TITUS_RIVENDARE, (TriggerFamily.DEATHRATTLE,), extra_normal=1, extra_golden=2, zones=(EffectZone.BOARD, EffectZone.COMBAT), name="Titus Rivendare")
    effects.register_spellcraft(TRANQUIL_MEDITATIVE, MEDITATION)
    effects.register_deathrattle(TURQUOISE_SKITTERER, _turquoise_skitterer, name="Turquoise Skitterer")
    effects.register_effect(VIGILANT_BRISTLEMANE, GameEvent.SPELL_CAST, _vigilant_bristlemane, zones=(EffectZone.BOARD,), name="Vigilant Bristlemane")
    effects.register_battlecry(VOID_PUP_TRAINER, _void_pup_trainer, name="Void Pup Trainer")


def _air_revenant(ctx):
    triggers = _counter_spend(ctx, 7, "_air_revenant_gold")
    for _ in range(triggers * _amount(ctx, 1, 2)):
        _cast_registered_spell(ctx, EASTERLY_WINDS)


def _barrier_banshee(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    amount = _amount(ctx, 7, 14)
    ctx.grant_keyword(ctx.source, "Divine Shield")
    ctx.source["_combat_divine_shield"] = True
    ctx.buff(ctx.source, attack=amount, health=amount)


def _bile_spitter(ctx):
    side = _combat_side(ctx)
    if side is None:
        return
    targets = [card for card in side.board if card is not ctx.source and _is_type(ctx.system, card, "Murloc")]
    count = min(len(targets), _amount(ctx, 1, 2))
    for target in ctx.rng.sample(targets, count) if count else []:
        ctx.grant_keyword(target, "Venomous")
        target["_combat_venomous_available"] = True


def _cataclysmic_harbinger(ctx):
    spell = _state(ctx).get("last_tavern_spell")
    if not isinstance(spell, dict):
        return
    for _ in range(_amount(ctx, 1, 2)):
        _add_to_hand(ctx.system, ctx.source_player_id, deepcopy(spell))


def _charging_czarina(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id or not _tavern_spell(ctx.event.get("spell")):
        return
    amount = _amount(ctx, 4, 8)
    for card in _friendly_cards(_player(ctx)):
        if _has_keyword(ctx.system, card, "Divine Shield"):
            ctx.buff(card, attack=amount)


def _costume_enthusiast(ctx):
    hand = [card for card in _player(ctx).hand if isinstance(card, dict)]
    if not hand:
        return
    highest = max(int(card.get("attack", 0) or 0) for card in hand)
    ctx.buff(ctx.source, attack=highest * (2 if ctx.is_golden else 1))


def _cousin_errgl(ctx):
    if ctx.is_golden:
        _add_to_hand(ctx.system, ctx.source_player_id, MAMA_MRRGLTON)
        _add_to_hand(ctx.system, ctx.source_player_id, PAPA_MRRGLTON)
    else:
        _add_to_hand(ctx.system, ctx.source_player_id, ctx.random_choice((MAMA_MRRGLTON, PAPA_MRRGLTON)))


def _dancing_barnstormer(ctx):
    amount = _amount(ctx, 8, 16)
    state = _state(ctx)
    state["tavern_elemental_attack"] = int(state.get("tavern_elemental_attack", 0) or 0) + amount
    state["tavern_elemental_health"] = int(state.get("tavern_elemental_health", 0) or 0) + amount
    player = _player(ctx)
    for card in player.tavern.slots:
        if _is_type(ctx.system, card, "Elemental"):
            ctx.system.apply_buff(card, attack=amount, health=amount)


def _darkcrest_turn_start(ctx):
    state = _state(ctx)
    state["darkcrest_strategy_tier"] = min(6, int(state.get("darkcrest_strategy_tier", 1) or 1) + 1)


def _deft_deserter(ctx):
    player = _player(ctx)
    amount = _amount(ctx, 8, 16)
    for card in player.tavern.slots:
        if not isinstance(card, dict):
            continue
        ctx.buff(card, attack=amount, health=amount)
        keyword = ctx.random_choice(("Taunt", "Divine Shield", "Windfury"))
        ctx.grant_keyword(card, keyword)


def _devilish_distractor(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id or ctx.event.get("target") is not ctx.source:
        return
    amount = _amount(ctx, 2, 4)
    state = _state(ctx)
    state["tavern_all_attack"] = int(state.get("tavern_all_attack", 0) or 0) + amount
    state["tavern_all_health"] = int(state.get("tavern_all_health", 0) or 0) + amount
    for card in _player(ctx).tavern.slots:
        if isinstance(card, dict):
            ctx.buff(card, attack=amount, health=amount)


def _draconic_warden(ctx):
    _bronze_timewalker(ctx)


def _dual_wield_corsair(ctx):
    triggers = _counter_spend(ctx, 5, "_dual_wield_gold")
    repetitions = triggers * (2 if ctx.is_golden else 1)
    player = _player(ctx)
    for _ in range(repetitions):
        pirates = _friendly_of_type(ctx.system, player, "Pirate")
        count = min(2, len(pirates))
        for target in ctx.rng.sample(pirates, count) if count else []:
            ctx.buff(target, attack=4, health=5)


def _enterprising_escapee(ctx):
    triggers = _counter_spend(ctx, 5, "_escapee_gold")
    for _ in range(triggers):
        _locked_up_mutineer(ctx)


def _felboar(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id or ctx.event.get("family") != TriggerFamily.SPELL:
        return
    source = _current_source_card_for_state(ctx)
    count = int(source.get("_felboar_spell_count", 0) or 0) + 1
    triggers, remainder = divmod(count, 3)
    source["_felboar_spell_count"] = remainder
    for _ in range(triggers):
        _consume_tavern(ctx, double=ctx.is_golden)


def _felfire_conjurer(ctx):
    state = _state(ctx)
    amount = _amount(ctx, 1, 2)
    state["tavern_spell_attack_bonus"] = int(state.get("tavern_spell_attack_bonus", 0) or 0) + amount
    state["tavern_spell_health_bonus"] = int(state.get("tavern_spell_health_bonus", 0) or 0) + amount


def _hoarding_hyena(ctx):
    _summon(ctx, TASTY_LOBSTER, 1, golden=ctx.is_golden)


def _insatiable_urzul(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    played = ctx.event.get("card")
    if _is_type(ctx.system, played, "Demon"):
        _consume_tavern(ctx, double=ctx.is_golden)


def _kalecgos(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id or ctx.event.get("family") != TriggerFamily.BATTLECRY:
        return
    amount = _amount(ctx, 2, 4)
    for card in _friendly_of_type(ctx.system, _player(ctx), "Dragon"):
        ctx.buff(card, attack=amount, health=amount)


def _kangors_apprentice(ctx):
    side = _combat_side(ctx)
    if side is None:
        return
    mechs = [card for card in side.dead_minions if _is_type(ctx.system, card, "Mech")]
    for card in mechs[:_amount(ctx, 2, 4)]:
        card_id = card.get("id")
        if _definition(ctx.system, card_id):
            _summon(ctx, card_id, 1, golden=False, position=ctx.event.get("death_position"))
        else:
            copy = deepcopy(card)
            copy["isGolden"] = False
            _summon(ctx, copy, position=ctx.event.get("death_position"))


def _leeroy(ctx):
    killer = ctx.event.get("killer")
    if isinstance(killer, dict):
        killer["health"] = 0


def _lurking_leviathan(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    summoned = ctx.event.get("minion")
    if summoned is ctx.source or not _is_type(ctx.system, summoned, "Beast"):
        return
    source = _current_source_card_for_state(ctx)
    improvement = int(source.get("_leviathan_improvement", 0) or 0)
    base = 4 if ctx.is_golden else 2
    step = 2 if ctx.is_golden else 1
    ctx.buff(summoned, attack=base + improvement)
    source["_leviathan_improvement"] = improvement + step
    index = ctx.source.get("_persistent_board_index")
    if index is not None:
        player = _player(ctx)
        if 0 <= index < len(player.board) and isinstance(player.board[index], dict):
            player.board[index]["_leviathan_improvement"] = source["_leviathan_improvement"]


def _nomi(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    played = ctx.event.get("card")
    if not _is_type(ctx.system, played, "Elemental"):
        return
    amount = _amount(ctx, 4, 8)
    state = _state(ctx)
    state["tavern_elemental_attack"] = int(state.get("tavern_elemental_attack", 0) or 0) + amount
    state["tavern_elemental_health"] = int(state.get("tavern_elemental_health", 0) or 0) + amount
    for card in _player(ctx).tavern.slots:
        if _is_type(ctx.system, card, "Elemental"):
            ctx.buff(card, attack=amount, health=amount)


def _primalfin_lookout(ctx):
    player = _player(ctx)
    others = [card for card in player.board if card is not ctx.source and _is_type(ctx.system, card, "Murloc")]
    if not others:
        return
    ctx.system.discover_cards(
        ctx.source_player_id,
        _definitions(ctx.system, minion_type="Murloc"),
        resolver_key="tier36_multi_add_discover",
        metadata={"remaining": _amount(ctx, 1, 2)},
    )


def _bounty_multiplier_condition(source, event, multiplier_source):
    spell = event.get("spell") or event.get("card")
    return isinstance(spell, dict) and spell.get("id") in BOUNTY_IDS


def _rodeo_performer(ctx):
    ctx.system.discover_cards(
        ctx.source_player_id,
        _definitions(ctx.system, card_type="spell"),
        resolver_key="tier36_multi_add_discover",
        metadata={"remaining": _amount(ctx, 1, 2)},
    )


def _sanguine_refiner(ctx):
    amount = _amount(ctx, 1, 2)
    state = _state(ctx)
    state["blood_gem_attack_bonus"] = int(state.get("blood_gem_attack_bonus", 0) or 0) + amount
    state["blood_gem_health_bonus"] = int(state.get("blood_gem_health_bonus", 0) or 0) + amount


def _scrap_scraper(ctx):
    candidates = _definitions(ctx.system, minion_type="Mech", predicate=lambda card: ctx.system.has_keyword(card, "Magnetic"))
    _add_random(ctx, candidates, _amount(ctx, 1, 2))


def _sewer_rat(golden=False):
    return {
        "id": 70790,
        "name": "Sewer Rat",
        "cardType": "minion",
        "attack": 4 if golden else 2,
        "health": 4 if golden else 2,
        "minionType": "Beast",
        "minionTypes": ["Beast"],
        "keywords": ["Deathrattle"],
        "isGolden": bool(golden),
        "_generated": True,
    }


def _sewer_lord(ctx):
    for _ in range(2):
        _summon(ctx, _sewer_rat(ctx.is_golden), position=ctx.event.get("death_position"))


def _sewer_rat_deathrattle(ctx):
    turtle = {
        "id": -70791,
        "name": "Sewer Turtle",
        "cardType": "minion",
        "attack": 4 if ctx.is_golden else 2,
        "health": 6 if ctx.is_golden else 3,
        "minionType": "Beast",
        "minionTypes": ["Beast"],
        "keywords": ["Taunt"],
        "_generated": True,
    }
    _summon(ctx, turtle, position=ctx.event.get("death_position"))


def _shamanic_tidecaller(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id or not _is_type(ctx.system, ctx.event.get("target"), "Murloc"):
        return
    amount = _amount(ctx, 3, 6)
    player = _player(ctx)
    for card in list(player.board) + list(player.hand):
        if _is_type(ctx.system, card, "Murloc"):
            ctx.buff(card, attack=amount, health=amount)


def _showy_cyclist(ctx):
    scale = 1 + int(_state(ctx).get("spells_cast_game", 0) or 0) // 3
    a, h = ((4 * scale, 2 * scale) if ctx.is_golden else (2 * scale, 1 * scale))
    side = _combat_side(ctx)
    cards = side.board if side is not None else _friendly_cards(_player(ctx))
    for card in cards:
        if _is_type(ctx.system, card, "Naga"):
            if side is not None:
                _permanent_combat_buff(ctx, card, a, h)
            else:
                ctx.buff(card, attack=a, health=h)


def _spark_snapper(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    played = ctx.event.get("card")
    if not _is_type(ctx.system, played, "Mech"):
        return
    source = _current_source_card_for_state(ctx)
    base = 4 if ctx.is_golden else 2
    improvement = int(source.get("_snapper_improvement", 0) or 0)
    stats = base + improvement
    ctx.system.magnetize(_satellite(stats), played)
    source["_snapper_improvement"] = improvement + base


def _tichondrius(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    amount = _amount(ctx, 3, 6)
    for card in _friendly_of_type(ctx.system, _player(ctx), "Demon"):
        ctx.buff(card, attack=amount, health=amount)


def _turquoise_skitterer(ctx):
    amount = _amount(ctx, 5, 10)
    state = _state(ctx)
    state["beetle_global_attack"] = int(state.get("beetle_global_attack", 0) or 0) + amount
    state["beetle_global_health"] = int(state.get("beetle_global_health", 0) or 0) + amount
    _summon(ctx, 110402, _amount(ctx, 1, 2), position=ctx.event.get("death_position"))


def _vigilant_bristlemane(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id or ctx.event.get("target") is not ctx.source:
        return
    player = _player(ctx)
    try:
        index = player.board.index(ctx.source)
    except ValueError:
        return
    for pos in (index - 1, index + 1):
        if 0 <= pos < len(player.board) and isinstance(player.board[pos], dict):
            _blood_gem(ctx, player.board[pos], _amount(ctx, 1, 2))


def _void_pup_trainer(ctx):
    amount = _amount(ctx, 3, 6)
    state = _state(ctx)
    state["tavern_tier3_attack"] = int(state.get("tavern_tier3_attack", 0) or 0) + amount
    state["tavern_tier3_health"] = int(state.get("tavern_tier3_health", 0) or 0) + amount
    for card in _player(ctx).tavern.slots:
        if isinstance(card, dict) and int(card.get("tier", 0) or 0) <= 3:
            ctx.buff(card, attack=amount, health=amount)

# =============================================================
# TIER 6
# =============================================================


def _friendly_spell_multiplier_condition(source, event, multiplier_source):
    target = event.get("target")
    if not isinstance(target, dict) or source.player_id is None:
        return False
    player = multiplier_source.system.game.get_player(source.player_id) if hasattr(multiplier_source, "system") else None
    # Fallback below is used by EffectSystem, whose multiplier_source is the
    # effect host card rather than a context object.
    if player is None:
        return True
    return target in getattr(player, "board", [])


def _balinda_condition(source, event, multiplier_source):
    target = event.get("target")
    if not isinstance(target, dict) or source.player_id is None:
        return False
    try:
        player = multiplier_source.game.get_player(source.player_id)
    except Exception:
        try:
            player = source.card.get("_effect_system").game.get_player(source.player_id)
        except Exception:
            return True
    return target in getattr(player, "board", [])


def _balinda_condition_simple(source, event, multiplier_source):
    # Spell actions in this simulator pass the physical target object.  Requiring
    # a target keeps untargeted Tavern spells from being multiplied; Bob/ActionSpace
    # already restricts normal targeted spells to friendly legal targets.
    return isinstance(event.get("target"), dict)


def _choral_mrrrglr(ctx):
    player = _player(ctx)
    attack = sum(int(card.get("attack", 0) or 0) for card in player.hand if isinstance(card, dict))
    health = sum(int(card.get("health", 0) or 0) for card in player.hand if isinstance(card, dict))
    multiplier = 2 if ctx.is_golden else 1
    ctx.buff(ctx.source, attack=attack * multiplier, health=health * multiplier)


def _crimson_vindicator(ctx):
    _cast_registered_spell(ctx, MIGHTY_DRAGONBREATH, count=_amount(ctx, 1, 2))


def _deathly_striker_avenge(ctx):
    count = _amount(ctx, 1, 2)
    generated = _random_type(ctx, "Undead", count)
    source = _current_source_card_for_state(ctx)
    ids = source.setdefault("_deathly_striker_summon_ids", [])
    ids.extend(card.get("id") for card in generated if isinstance(card, dict))


def _deathly_striker_deathrattle(ctx):
    source = _current_source_card_for_state(ctx)
    ids = list(source.get("_deathly_striker_summon_ids", []))
    if not ids:
        return
    player = _player(ctx)
    position = ctx.event.get("death_position")
    for card_id in ids:
        match = next(
            (
                card for card in player.hand
                if isinstance(card, dict) and card.get("id") == card_id
            ),
            None,
        )
        if match is None:
            continue
        _summon(ctx, deepcopy(match), position=position)
        if position is not None:
            position += 1


def _deathstrider(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    if ctx.event.get("family") != TriggerFamily.RALLY:
        return
    side = _combat_side(ctx)
    if side is None:
        return
    source_attacker = None
    original = ctx.event.get("original_event")
    if original is not None:
        source_attacker = original.get("attacker")
    if not isinstance(source_attacker, dict):
        return
    # Only friendly Rally attacks count.
    if source_attacker not in side.board:
        return
    for candidate in side.board:
        if not isinstance(candidate, dict):
            continue
        registrations = ctx.system.get_effects_for_card(candidate.get("id"))
        if not any(effect.family == TriggerFamily.DEATHRATTLE for effect in registrations):
            continue
        for _ in range(_amount(ctx, 1, 2)):
            ctx.system.trigger_card_family(
                candidate,
                TriggerFamily.DEATHRATTLE,
                player_id=ctx.source_player_id,
                zone=EffectZone.COMBAT,
                side=side,
                minion=candidate,
                death_position=side.board.index(candidate),
                engine=(original.get("engine") if original is not None else None),
            )
        break


def _eredar_escapist(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    damage = int(ctx.event.get("health_damage", ctx.event.get("amount", 0)) or 0)
    if damage <= 0:
        return
    source = _current_source_card_for_state(ctx)
    current = int(source.get("_eredar_damage", 0) or 0) + damage
    triggers, remainder = divmod(current, 3)
    source["_eredar_damage"] = remainder
    if triggers:
        _cast_registered_spell(
            ctx,
            SHINY_RING,
            count=triggers * _amount(ctx, 1, 2),
        )


def _eternal_summoner(ctx):
    _summon(
        ctx,
        ETERNAL_KNIGHT,
        1,
        golden=ctx.is_golden,
        position=ctx.event.get("death_position"),
    )


def _fauna_whisperer(ctx):
    player = _player(ctx)
    try:
        index = player.board.index(ctx.source)
    except ValueError:
        return
    targets = []
    for pos in (index - 1, index + 1):
        if 0 <= pos < len(player.board) and isinstance(player.board[pos], dict):
            targets.append(player.board[pos])
    for target in targets:
        _cast_registered_spell(
            ctx,
            NATURAL_BLESSING,
            target=target,
            count=_amount(ctx, 1, 2),
        )


def _fire_forged_spell(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    if not _tavern_spell(ctx.event.get("spell") or ctx.event.get("card")):
        return
    source = _current_source_card_for_state(ctx)
    source["_fire_forged_attack"] = int(source.get("_fire_forged_attack", 0) or 0) + _amount(ctx, 2, 4)
    source["_fire_forged_health"] = int(source.get("_fire_forged_health", 0) or 0) + _amount(ctx, 1, 2)


def _fire_forged_start(ctx):
    source = _current_source_card_for_state(ctx)
    attack = _amount(ctx, 2, 4) + int(source.get("_fire_forged_attack", 0) or 0)
    health = _amount(ctx, 1, 2) + int(source.get("_fire_forged_health", 0) or 0)
    side = _combat_side(ctx)
    if side is None:
        return
    for card in side.board:
        if _is_type(ctx.system, card, "Dragon"):
            ctx.buff(card, attack=attack, health=health)


def _forsaken_weaver(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    if not _tavern_spell(ctx.event.get("spell") or ctx.event.get("card")):
        return
    amount = _amount(ctx, 2, 4)
    state = _state(ctx)
    state["undead_global_attack"] = int(state.get("undead_global_attack", 0) or 0) + amount
    player = _player(ctx)
    for card in list(player.board) + list(player.hand) + list(getattr(player.tavern, "slots", [])):
        if _is_type(ctx.system, card, "Undead"):
            ctx.system.apply_buff(card, attack=amount)


def _gatekeeper_amalgam(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    if ctx.event.get("target") is not ctx.source:
        return
    _cast_registered_spell(ctx, MISPLACED_TEA_SET, count=_amount(ctx, 1, 2))


def _gentle_djinni(ctx):
    _random_type(ctx, "Elemental", _amount(ctx, 1, 2))


def _buff_persistent_until_next_turn(ctx, combat_target, attack, health):
    ctx.system.apply_buff(combat_target, attack=attack, health=health)
    index = combat_target.get("_persistent_board_index") if isinstance(combat_target, dict) else None
    if index is None:
        return
    player = _player(ctx)
    if 0 <= index < len(player.board) and isinstance(player.board[index], dict):
        ctx.system.apply_buff(
            player.board[index],
            attack=attack,
            health=health,
            until_next_turn=True,
        )


def _goldrinn(ctx):
    side = _combat_side(ctx)
    if side is None:
        return
    amount = _amount(ctx, 8, 16)
    for card in side.board:
        if _is_type(ctx.system, card, "Beast"):
            _buff_persistent_until_next_turn(ctx, card, amount, amount)


def _groundbreaker(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    played = ctx.event.get("card")
    if not _is_type(ctx.system, played, "Naga"):
        return
    spells = int(_state(ctx).get("spells_cast_game", 0) or 0)
    step = 1 + spells // 3
    amount = step * (2 if ctx.is_golden else 1)
    ctx.buff(ctx.source, attack=amount, health=amount)


def _hooktusk_master(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    choice = ctx.event.get("choice")
    if getattr(choice, "kind", None) != "discover":
        return
    improvement = int(_state(ctx).get("golden_minions_played", 0) or 0)
    amount = (1 + improvement) * (2 if ctx.is_golden else 1)
    for card in _friendly_of_type(ctx.system, _player(ctx), "Pirate"):
        if card is not ctx.source:
            ctx.buff(card, attack=amount, health=amount)


def _ignition_specialist(ctx):
    _random_tavern_spells(ctx, _amount(ctx, 2, 4))


def _magicfin_mycologist(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    spell = ctx.event.get("spell") or ctx.event.get("card")
    if not _tavern_spell(spell):
        return
    state = _state(ctx)
    used = int(state.get("magicfin_uses", 0) or 0)
    limit = 2 if ctx.is_golden else 1
    if used >= limit:
        return
    state["magicfin_uses"] = used + 1
    apprentice = _fresh_card(ctx.system, 122285)
    apprentice["attack"] = 1
    apprentice["health"] = 1
    apprentice["_taught_spell"] = deepcopy(spell)
    apprentice["_cannot_triple"] = True
    _add_to_hand(ctx.system, ctx.source_player_id, apprentice)


def _magicfin_apprentice(ctx):
    spell = _current_source_card_for_state(ctx).get("_taught_spell")
    if not isinstance(spell, dict):
        return
    target = ctx.event.get("target")
    # If the spell needs a target and the Apprentice was played without one,
    # select a deterministic-random friendly board target.
    if ctx.system.has_target_rule(spell.get("id")) and not isinstance(target, dict):
        player = _player(ctx)
        candidates = [card for card in player.board if isinstance(card, dict) and card is not ctx.source]
        if candidates:
            target = ctx.random_choice(candidates)
    ctx.system.trigger_card_family(
        deepcopy(spell),
        TriggerFamily.SPELL,
        player_id=ctx.source_player_id,
        zone=EffectZone.EVENT_SOURCE,
        target=target,
    )


def _moat_custodian(ctx):
    state = _state(ctx)
    amount = _amount(ctx, 2, 4)
    state["elemental_effect_attack_bonus"] = int(state.get("elemental_effect_attack_bonus", 0) or 0) + amount
    state["elemental_effect_health_bonus"] = int(state.get("elemental_effect_health_bonus", 0) or 0) + amount


def _primitive_painter(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    played = ctx.event.get("card")
    if not isinstance(played, dict) or int(played.get("tier", 99) or 99) > 3:
        return
    amount = _amount(ctx, 3, 6)
    for card in _friendly_of_type(ctx.system, _player(ctx), "Murloc"):
        ctx.buff(card, attack=amount, health=amount)


def _ravaging_scorpid_attack(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    attacker = ctx.event.get("attacker")
    side = _combat_side(ctx)
    if side is None or attacker not in side.board:
        return
    amount = _amount(ctx, 5, 10)
    state = _state(ctx)
    state["beetle_global_attack"] = int(state.get("beetle_global_attack", 0) or 0) + amount
    state["beetle_global_health"] = int(state.get("beetle_global_health", 0) or 0) + amount
    for card in side.board:
        if isinstance(card, dict) and card.get("id") == 110402:
            ctx.buff(card, attack=amount, health=amount)


def _ravaging_scorpid_deathrattle(ctx):
    _summon(ctx, 110402, _amount(ctx, 1, 2), position=ctx.event.get("death_position"))


def _sanguine_champion(ctx):
    amount = _amount(ctx, 1, 2)
    state = _state(ctx)
    state["blood_gem_attack_bonus"] = int(state.get("blood_gem_attack_bonus", 0) or 0) + amount
    state["blood_gem_health_bonus"] = int(state.get("blood_gem_health_bonus", 0) or 0) + amount


def _silent_deliverer(ctx):
    candidates = _definitions(ctx.system, tier=4)
    for card in _add_random(ctx, candidates, _amount(ctx, 1, 2), golden=True):
        card["_no_triple_reward"] = True


def _sky_admiral_rogers(ctx):
    triggers = _counter_spend(ctx, 9, "_rogers_gold")
    for _ in range(triggers):
        _random_bounties(ctx, _amount(ctx, 1, 2))


def _snazzy_phantom(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    reborn = ctx.event.get("minion")
    if not isinstance(reborn, dict):
        return
    side = _combat_side(ctx)
    if side is None:
        return
    undead = [card for card in side.board if _is_type(ctx.system, card, "Undead")]
    if not undead:
        return
    target = undead[-1]
    amount = int(reborn.get("attack", 0) or 0) * (2 if ctx.is_golden else 1)
    ctx.buff(target, attack=amount, health=amount)


def _torrential_ruiner(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    target = ctx.event.get("target")
    if not _is_type(ctx.system, target, "Naga"):
        return
    a, h = ((4, 6) if ctx.is_golden else (2, 3))
    for card in _friendly_cards(_player(ctx)):
        ctx.buff(card, attack=a, health=h)


def _turbo_hogrider(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    played = ctx.event.get("card")
    if not _card_has_choose_one(played):
        return
    count = _amount(ctx, 3, 6)
    for card in _friendly_of_type(ctx.system, _player(ctx), "Quilboar"):
        if card is not ctx.source:
            _blood_gem(ctx, card, count)


def _twisted_wrathguard(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    state = _state(ctx)
    state["fodder_pending_count"] = int(state.get("fodder_pending_count", 0) or 0) + _amount(ctx, 1, 2)


def _tyrael(ctx):
    target = ctx.event.get("target")
    if not isinstance(target, dict) or target is ctx.source:
        return
    value = 100 if ctx.is_golden else 50
    target["attack"] = value
    target["health"] = value


def _unbound_tempest(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    played = ctx.event.get("card")
    if not _is_type(ctx.system, played, "Elemental"):
        return
    source = _current_source_card_for_state(ctx)
    count = int(source.get("_unbound_elementals", 0) or 0) + 1
    triggers, remainder = divmod(count, 3)
    source["_unbound_elementals"] = remainder
    for _ in range(triggers):
        _consume_tavern(ctx, double=ctx.is_golden, highest_health=True)


def _unleashed_mana_surge(ctx):
    if ctx.event.get("player_id") != ctx.source_player_id:
        return
    if not _is_type(ctx.system, ctx.event.get("card"), "Elemental"):
        return
    amount = 8 if ctx.is_golden else 4
    for card in _friendly_of_type(ctx.system, _player(ctx), "Elemental"):
        ctx.buff(card, attack=amount, health=amount)


def _utility_drone(ctx):
    amount = 8 if ctx.is_golden else 4
    for card in _friendly_cards(_player(ctx)):
        count = int(card.get("_magnetization_count", 0) or 0)
        if count:
            ctx.buff(card, attack=amount * count, health=amount * count)


def _veteran_brigand(ctx):
    if ctx.event.get("card") is not ctx.source:
        return False
    ctx.start_choice(
        "tier36_veteran_brigand",
        ["gems", "barrage"],
        kind="choose_one",
        metadata={"golden": ctx.is_golden},
    )
    return True


def _register_tier6(effects):
    effects.register_trigger_multiplier(
        BALINDA_STONEHEARTH,
        (TriggerFamily.SPELL,),
        extra_normal=1,
        extra_golden=2,
        zones=(EffectZone.BOARD,),
        condition=_balinda_condition_simple,
        name="Balinda Stonehearth",
    )
    effects.register_start_of_combat(CHORAL_MRRRGLR, _choral_mrrrglr, name="Choral Mrrrglr")
    effects.register_rally(CRIMSON_VINDICATOR, _crimson_vindicator, name="Crimson Vindicator")
    effects.register_avenge(DEATHLY_STRIKER, 4, _deathly_striker_avenge, name="Deathly Striker Avenge")
    effects.register_deathrattle(DEATHLY_STRIKER, _deathly_striker_deathrattle, name="Deathly Striker Deathrattle")
    effects.register_effect(DEATHSTRIDER, GameEvent.TRIGGER_RESOLVED, _deathstrider, zones=(EffectZone.COMBAT,), name="Deathstrider")
    # Elemental of Surprise's special triple compatibility is engine/triple logic;
    # its Divine Shield is native keyword handling.
    effects.register_effect(EREDAR_ESCAPIST, GameEvent.PLAYER_DAMAGED, _eredar_escapist, zones=(EffectZone.BOARD,), name="Eredar Escapist")
    effects.register_deathrattle(ETERNAL_SUMMONER, _eternal_summoner, name="Eternal Summoner")
    # Falling Sky Golem is maintained by the global wherever-modifier tracker.
    effects.register_end_of_turn(FAUNA_WHISPERER, _fauna_whisperer, name="Fauna Whisperer")
    effects.register_effect(FIRE_FORGED_EVOKER, GameEvent.SPELL_CAST, _fire_forged_spell, zones=(EffectZone.BOARD,), name="Fire-forged Evoker improve")
    effects.register_start_of_combat(FIRE_FORGED_EVOKER, _fire_forged_start, name="Fire-forged Evoker")
    effects.register_effect(FORSAKEN_WEAVER, GameEvent.SPELL_CAST, _forsaken_weaver, zones=(EffectZone.BOARD,), name="Forsaken Weaver")
    effects.register_effect(GATEKEEPER_AMALGAM, GameEvent.SPELL_CAST, _gatekeeper_amalgam, zones=(EffectZone.BOARD,), name="Gatekeeper Amalgam")
    effects.register_battlecry(GENTLE_DJINNI, _gentle_djinni, name="Gentle Djinni Battlecry")
    effects.register_deathrattle(GENTLE_DJINNI, _gentle_djinni, name="Gentle Djinni Deathrattle")
    effects.register_deathrattle(GOLDRINN_THE_GREAT_WOLF, _goldrinn, name="Goldrinn")
    effects.register_effect(GROUNDBREAKER, GameEvent.CARD_PLAYED, _groundbreaker, zones=(EffectZone.BOARD,), name="Groundbreaker")
    effects.register_effect(HOOKTUSK_MASTER_MARAUDER, GameEvent.CHOICE_RESOLVED, _hooktusk_master, zones=(EffectZone.BOARD,), name="Hooktusk, Master Marauder")
    effects.register_end_of_turn(IGNITION_SPECIALIST, _ignition_specialist, name="Ignition Specialist")
    effects.register_effect(MAGICFIN_MYCOLOGIST, GameEvent.SPELL_BOUGHT, _magicfin_mycologist, zones=(EffectZone.BOARD,), name="Magicfin Mycologist")
    effects.register_battlecry(122285, _magicfin_apprentice, name="Magicfin Apprentice taught spell")
    effects.register_rally(MOAT_CUSTODIAN, _moat_custodian, name="Moat Custodian")
    effects.register_effect(PRIMITIVE_PAINTER, GameEvent.CARD_PLAYED, _primitive_painter, zones=(EffectZone.BOARD,), name="Primitive Painter")
    effects.register_effect(RAVAGING_SCORPID, GameEvent.ATTACK, _ravaging_scorpid_attack, zones=(EffectZone.COMBAT,), name="Ravaging Scorpid attack")
    effects.register_deathrattle(RAVAGING_SCORPID, _ravaging_scorpid_deathrattle, name="Ravaging Scorpid Deathrattle")
    effects.register_battlecry(SANGUINE_CHAMPION, _sanguine_champion, name="Sanguine Champion Battlecry")
    effects.register_deathrattle(SANGUINE_CHAMPION, _sanguine_champion, name="Sanguine Champion Deathrattle")
    effects.register_battlecry(SILENT_DELIVERER, _silent_deliverer, name="Silent Deliverer")
    effects.register_effect(SKY_ADMIRAL_ROGERS, GameEvent.GOLD_SPENT, _sky_admiral_rogers, zones=(EffectZone.BOARD,), name="Sky Admiral Rogers")
    effects.register_effect(SNAZZY_PHANTOM, GameEvent.REBORN, _snazzy_phantom, zones=(EffectZone.COMBAT,), name="Snazzy Phantom")
    effects.register_effect(TORRENTIAL_RUINER, GameEvent.SPELL_CAST, _torrential_ruiner, zones=(EffectZone.BOARD,), name="Torrential Ruiner")
    effects.register_effect(TURBO_HOGRIDER, GameEvent.CARD_PLAYED, _turbo_hogrider, zones=(EffectZone.BOARD,), name="Turbo Hogrider")
    effects.register_effect(TWISTED_WRATHGUARD, GameEvent.CARD_SOLD, _twisted_wrathguard, zones=(EffectZone.BOARD,), name="Twisted Wrathguard")
    effects.register_activate(
        TYRAEL,
        2,
        _tyrael,
        target_provider=_target_ref_board_provider(exclude_source=True),
        name="Tyrael",
    )
    effects.register_effect(UNBOUND_TEMPEST, GameEvent.CARD_PLAYED, _unbound_tempest, zones=(EffectZone.BOARD,), name="Unbound Tempest")
    effects.register_effect(UNLEASHED_MANA_SURGE, GameEvent.CARD_PLAYED, _unleashed_mana_surge, zones=(EffectZone.BOARD,), name="Unleashed Mana Surge")
    effects.register_end_of_turn(UTILITY_DRONE, _utility_drone, name="Utility Drone")
    effects.register_effect(VETERAN_BRIGAND, GameEvent.CARD_PLAYED, _veteran_brigand, zones=(EffectZone.EVENT_SOURCE,), family=TriggerFamily.BATTLECRY, name="Veteran Brigand")
    # Warpwing's Immune-while-attacking keyword is handled natively by CombatEngine.


# =============================================================
# CHOICE / DISCOVER RESOLVERS
# =============================================================


def _choice_add_card(system, player_id, option, metadata):
    remaining = max(1, int(metadata.get("remaining", 1) or 1))
    card_id = option.get("id") if isinstance(option, dict) else int(option)
    for _ in range(remaining):
        _add_to_hand(system, player_id, card_id)


def _choice_magnetize(system, player_id, option, metadata):
    target = metadata.get("target")
    if not isinstance(target, dict):
        return
    remaining = max(1, int(metadata.get("remaining", 1) or 1))
    card_id = option.get("id") if isinstance(option, dict) else int(option)
    for _ in range(remaining):
        magnetic = _fresh_card(system, card_id)
        system.magnetize(magnetic, target)


def _deal_hero_damage(system, player_id, amount, *, source=None):
    amount = max(0, int(amount or 0))
    if amount <= 0:
        return
    player = system.game.get_player(player_id)
    if getattr(player, "eliminated", False):
        return
    if hasattr(player, "take_damage"):
        armor_damage, health_damage = player.take_damage(amount)
    else:
        armor = int(getattr(player, "armor", 0) or 0)
        armor_damage = min(armor, amount)
        player.armor = armor - armor_damage
        health_damage = amount - armor_damage
        player.health = max(0, int(getattr(player, "health", 0) or 0) - health_damage)
    system.events.emit(
        GameEvent.PLAYER_DAMAGED,
        player_id=player_id,
        amount=amount,
        armor_damage=armor_damage,
        health_damage=health_damage,
        self_damage=True,
        source_card=source,
    )


def _choice_demon_damage(system, player_id, option, metadata):
    remaining = max(1, int(metadata.get("remaining", 1) or 1))
    card_id = option.get("id") if isinstance(option, dict) else int(option)
    definition = _definition(system, card_id) or (option if isinstance(option, dict) else {})
    for _ in range(remaining):
        _add_to_hand(system, player_id, card_id)
        _deal_hero_damage(system, player_id, int(definition.get("tier", 0) or 0))


def _choice_sly_infiltrator(system, player_id, option, metadata):
    golden = bool(metadata.get("golden", False))
    if option == "refreshes":
        system.grant_free_refreshes(player_id, 4 if golden else 2)
    elif option == "blood_gems":
        for _ in range(6 if golden else 3):
            _add_to_hand(system, player_id, BLOOD_GEM)


def _choice_sprightly_scarab(system, player_id, option, metadata):
    target = metadata.get("target")
    if not isinstance(target, dict):
        return
    golden = bool(metadata.get("golden", False))
    if option == "reborn":
        system.apply_buff(target, attack=2 if golden else 1, health=2 if golden else 1)
        system.grant_keyword(target, "Reborn")
    elif option == "windfury":
        system.apply_buff(target, attack=8 if golden else 4)
        system.grant_keyword(target, "Windfury")


def _choice_fearless_foodie(system, player_id, option, metadata):
    golden = bool(metadata.get("golden", False))
    state = system.get_player_state(player_id)
    if option == "improve":
        amount = 2 if golden else 1
        state["blood_gem_attack_bonus"] = int(state.get("blood_gem_attack_bonus", 0) or 0) + amount
        state["blood_gem_health_bonus"] = int(state.get("blood_gem_health_bonus", 0) or 0) + amount
    elif option == "gems":
        for _ in range(8 if golden else 4):
            _add_to_hand(system, player_id, BLOOD_GEM)


def _choice_snare_trapper(system, player_id, option, metadata):
    golden = bool(metadata.get("golden", False))
    if option == "quilboar":
        definitions = _definitions(system, minion_type="Quilboar")
        for _ in range(2 if golden else 1):
            if not definitions:
                break
            picked = system.random.choice(definitions)
            _add_to_hand(system, player_id, picked.get("id"))
    elif option == "max_gold":
        system.add_max_gold(player_id, 2 if golden else 1)


def _choice_veteran_brigand(system, player_id, option, metadata):
    golden = bool(metadata.get("golden", False))
    count = 6 if golden else 3
    player = system.game.get_player(player_id)
    if option == "gems":
        gem_a, gem_h = _blood_gem_values(system, player_id)
        for card in player.board:
            if isinstance(card, dict):
                system.apply_buff(card, attack=gem_a * count, health=gem_h * count)
                card["_blood_gems_received"] = int(card.get("_blood_gems_received", 0) or 0) + count
    elif option == "barrage":
        state = system.get_player_state(player_id)
        state["blood_gem_barrage_refreshes"] = int(state.get("blood_gem_barrage_refreshes", 0) or 0) + count


def _register_choice_resolvers(effects):
    effects.register_choice_resolver("tier36_multi_add_discover", _choice_add_card)
    effects.register_choice_resolver("tier36_magnetize_discover", _choice_magnetize)
    effects.register_choice_resolver("tier36_demon_discover_damage", _choice_demon_damage)
    effects.register_choice_resolver("tier36_sly_infiltrator", _choice_sly_infiltrator)
    effects.register_choice_resolver("tier36_sprightly_scarab", _choice_sprightly_scarab)
    effects.register_choice_resolver("tier36_fearless_foodie", _choice_fearless_foodie)
    effects.register_choice_resolver("tier36_snare_trapper", _choice_snare_trapper)
    effects.register_choice_resolver("tier36_veteran_brigand", _choice_veteran_brigand)


# =============================================================
# GENERATED / TAVERN SPELL EFFECTS USED BY TIER 3-6
# =============================================================


def _spell_target(ctx):
    return ctx.event.get("target")


def _spell_blood_gem_barrage(ctx):
    state = _state(ctx)
    state["blood_gem_barrage_refreshes"] = int(state.get("blood_gem_barrage_refreshes", 0) or 0) + 1


def _spell_anglers_lure(ctx):
    target = _spell_target(ctx)
    if not isinstance(target, dict):
        return
    a, h = ((4, 12) if ctx.is_golden else (2, 6))
    ctx.buff(target, attack=a, health=h, until_next_turn=True)
    ctx.grant_keyword(target, "Taunt", until_next_turn=True)


def _spell_tavern_dish_banana(ctx):
    target = _spell_target(ctx)
    if isinstance(target, dict):
        ctx.buff(target, attack=2, health=2)


def _spell_repair_job(ctx):
    target = _spell_target(ctx)
    if isinstance(target, dict):
        ctx.buff(target, attack=4, health=8)


def _spell_golden_touch(ctx):
    player = _player(ctx)
    candidates = [card for card in player.tavern.slots if isinstance(card, dict) and card.get("cardType") == "minion"]
    if not candidates:
        return
    card = ctx.random_choice(candidates)
    if ctx.system.is_golden(card):
        return
    card["isGolden"] = True
    if card.get("attackGold") is not None:
        card["attack"] = int(card.get("attackGold", card.get("attack", 0)) or 0)
    else:
        card["attack"] = int(card.get("attack", 0) or 0) * 2
    if card.get("healthGold") is not None:
        card["health"] = int(card.get("healthGold", card.get("health", 0)) or 0)
    else:
        card["health"] = int(card.get("health", 0) or 0) * 2


def _spell_gem_confiscation(ctx):
    target = _spell_target(ctx)
    if not isinstance(target, dict):
        return
    player = _player(ctx)
    try:
        index = player.board.index(target)
    except ValueError:
        return
    _blood_gem(ctx, target, 2)
    stolen = 0
    for pos in (index - 1, index + 1):
        if not (0 <= pos < len(player.board)):
            continue
        neighbor = player.board[pos]
        if not isinstance(neighbor, dict):
            continue
        gems = int(neighbor.pop("_blood_gems_received", 0) or 0)
        if gems <= 0:
            continue
        gem_a, gem_h = _blood_gem_values(ctx.system, ctx.source_player_id)
        ctx.system.apply_buff(neighbor, attack=-gem_a * gems, health=-gem_h * gems)
        stolen += gems
    if stolen:
        _blood_gem(ctx, target, stolen)


def _spell_undersea_mount(ctx):
    target = _spell_target(ctx)
    if not isinstance(target, dict):
        return
    amount = 4 if ctx.is_golden else 2
    ctx.buff(target, attack=amount, health=amount)
    if _is_type(ctx.system, target, "Naga"):
        ctx.grant_keyword(target, "Windfury", until_next_turn=True)


def _spell_chefs_choice(ctx):
    target = _spell_target(ctx)
    if not isinstance(target, dict):
        return
    all_types = [
        value for value in (target.get("minionTypes") or [target.get("minionType")])
        if value and str(value).casefold() != "all"
    ]
    if not all_types:
        return
    minion_type = ctx.random_choice(all_types)
    candidates = [
        card for card in _definitions(ctx.system, minion_type=minion_type)
        if card.get("id") != target.get("id")
    ]
    _add_random(ctx, candidates, 1)


def _spell_deepwater_clan(ctx):
    target = _spell_target(ctx)
    if isinstance(target, dict):
        ctx.buff(target, attack=2, health=2)
    for card in _friendly_of_type(ctx.system, _player(ctx), "Murloc"):
        ctx.buff(card, attack=2, health=2)


def _spell_methodical_madness(ctx):
    target = _spell_target(ctx)
    if not _is_type(ctx.system, target, "Demon"):
        return
    _consume_tavern(ctx, target=target)
    _consume_tavern(ctx, target=target)


def _spell_shiny_ring(ctx):
    for card in _friendly_cards(_player(ctx)):
        ctx.buff(card, attack=1, health=1)


def _spell_rime_or_reason(ctx):
    count = 2 if ctx.is_golden else 1
    candidates = _definitions(
        ctx.system,
        card_type="spell",
        predicate=lambda card: "give" in re.sub(r"<[^>]+>", "", str(card.get("text", ""))).casefold()
        and ("+" in str(card.get("text", ""))),
    )
    _add_random(ctx, candidates, count)


def _spell_evolving_strategy(ctx):
    _random_type(ctx, "Naga", 2 if ctx.is_golden else 1, tier=1)


def _spell_glowing_crown(ctx):
    target = _spell_target(ctx)
    if isinstance(target, dict):
        ctx.grant_keyword(target, "Divine Shield", until_next_turn=True)


def _spell_butchering(ctx):
    target = _spell_target(ctx)
    if not _is_type(ctx.system, target, "Undead"):
        return
    player = _player(ctx)
    try:
        player.board[player.board.index(target)] = None
    except ValueError:
        return
    state = _state(ctx)
    state["undead_global_attack"] = int(state.get("undead_global_attack", 0) or 0) + 5
    for card in list(player.board) + list(player.hand) + list(player.tavern.slots):
        if _is_type(ctx.system, card, "Undead"):
            ctx.system.apply_buff(card, attack=5)


def _spell_misplaced_tea_set(ctx):
    player = _player(ctx)
    types = ["Beast", "Demon", "Dragon", "Elemental", "Mech", "Murloc", "Naga", "Pirate", "Quilboar", "Undead"]
    for minion_type in types:
        candidates = [card for card in player.board if _is_type(ctx.system, card, minion_type)]
        if candidates:
            target = ctx.random_choice(candidates)
            ctx.buff(target, attack=4, health=4)


def _spell_meditation(ctx):
    amount = 2 if ctx.is_golden else 1
    state = _state(ctx)
    state["tavern_spell_attack_bonus"] = int(state.get("tavern_spell_attack_bonus", 0) or 0) + amount
    state["tavern_spell_health_bonus"] = int(state.get("tavern_spell_health_bonus", 0) or 0) + amount


def _spell_easterly_winds(ctx):
    _state(ctx).setdefault("refresh_random_buffs", []).append((8, 8))


def _spell_mighty_dragonbreath(ctx):
    player = _player(ctx)
    for card in _friendly_cards(player):
        ctx.buff(card, attack=2, health=1)
        if _is_type(ctx.system, card, "Dragon"):
            ctx.buff(card, attack=2, health=1)
        if _has_keyword(ctx.system, card, "Divine Shield"):
            ctx.buff(card, attack=2, health=1)


def _spell_natural_blessing(ctx):
    target = _spell_target(ctx)
    if not isinstance(target, dict):
        return
    target_types = [
        value for value in (target.get("minionTypes") or [target.get("minionType")])
        if value
    ]
    if not target_types:
        return
    for card in _friendly_cards(_player(ctx)):
        if any(_is_type(ctx.system, card, value) for value in target_types):
            ctx.buff(card, attack=3, health=3)


def _spell_healthy_bounty(ctx):
    cards = _friendly_cards(_player(ctx))
    for card in ctx.rng.sample(cards, min(4, len(cards))):
        ctx.buff(card, health=4)


def _spell_hostile_bounty(ctx):
    cards = _friendly_cards(_player(ctx))
    for card in ctx.rng.sample(cards, min(4, len(cards))):
        ctx.buff(card, attack=4)


def _spell_selfish_bounty(ctx):
    target = next((card for card in _player(ctx).board if isinstance(card, dict)), None)
    if target is not None:
        ctx.buff(target, attack=6, health=6)


def _spell_friendly_bounty(ctx):
    player = _player(ctx)
    counts = {}
    types = ["Beast", "Demon", "Dragon", "Elemental", "Mech", "Murloc", "Naga", "Pirate", "Quilboar", "Undead"]
    for minion_type in types:
        counts[minion_type] = sum(1 for card in player.board if _is_type(ctx.system, card, minion_type))
    best = max(counts.values(), default=0)
    if best <= 0:
        return
    tied = [key for key, value in counts.items() if value == best]
    _random_type(ctx, ctx.random_choice(tied), 1)


def _spell_wealthy_bounty(ctx):
    ctx.system.add_gold(ctx.source_player_id, 2)


def _register_generated_spells(effects):
    board_targets = (
        ANGLERS_LURE, TAVERN_DISH_BANANA, REPAIR_JOB, GEM_CONFISCATION,
        UNDERSEA_MOUNT, CHEFS_CHOICE, DEEPWATER_CLAN, GLOWING_CROWN,
        NATURAL_BLESSING,
    )
    for card_id in board_targets:
        effects.register_target_rule(card_id, _target_ref_board_provider())
    effects.register_target_rule(METHODICAL_MADNESS, _target_ref_board_provider(types=("Demon",)))
    effects.register_target_rule(BUTCHERING, _target_ref_board_provider(types=("Undead",)))

    spell_handlers = {
        BLOOD_GEM_BARRAGE: _spell_blood_gem_barrage,
        ANGLERS_LURE: _spell_anglers_lure,
        TAVERN_DISH_BANANA: _spell_tavern_dish_banana,
        REPAIR_JOB: _spell_repair_job,
        GOLDEN_TOUCH: _spell_golden_touch,
        GEM_CONFISCATION: _spell_gem_confiscation,
        UNDERSEA_MOUNT: _spell_undersea_mount,
        CHEFS_CHOICE: _spell_chefs_choice,
        DEEPWATER_CLAN: _spell_deepwater_clan,
        METHODICAL_MADNESS: _spell_methodical_madness,
        SHINY_RING: _spell_shiny_ring,
        RIME_OR_REASON: _spell_rime_or_reason,
        EVOLVING_STRATEGY: _spell_evolving_strategy,
        GLOWING_CROWN: _spell_glowing_crown,
        BUTCHERING: _spell_butchering,
        MISPLACED_TEA_SET: _spell_misplaced_tea_set,
        MEDITATION: _spell_meditation,
        EASTERLY_WINDS: _spell_easterly_winds,
        MIGHTY_DRAGONBREATH: _spell_mighty_dragonbreath,
        NATURAL_BLESSING: _spell_natural_blessing,
        122182: _spell_healthy_bounty,
        122183: _spell_hostile_bounty,
        122184: _spell_selfish_bounty,
        122185: _spell_friendly_bounty,
        122186: _spell_wealthy_bounty,
    }
    for card_id, handler in spell_handlers.items():
        effects.register_effect(
            card_id,
            GameEvent.SPELL_CAST,
            handler,
            zones=(EffectZone.EVENT_SOURCE,),
            family=TriggerFamily.SPELL,
            name=f"Tier 3-6 spell {card_id}",
        )


# =============================================================
# PUBLIC REGISTRATION ENTRY POINT
# =============================================================


def register_tier36_effects(effects):
    """Register all Tier 3-6 minion content and its generated spell support."""
    _register_choice_resolvers(effects)
    _register_generated_spells(effects)
    _register_global_runtime(effects)
    _register_tier3(effects)
    _register_tier4(effects)
    _register_tier5(effects)
    _register_tier6(effects)
