"""First ordinary batch: real engine effects, lifecycle, and AI continuations."""

from copy import deepcopy
import random

import pytest

from agents.observation import AgentMemory, ObservationBuilder
from agents.simulation_environment import DeterminizedBattlegroundsEnvironment
from game.actions import ActionType
from game.bob import Bob
from game.effects import EffectZone
from game.events import GameEvent
from game.hero_power_effects import (
    ALEXSTRASZA_QUEEN_OF_DRAGONS,
    CTHUN_SATURDAY_CTHUNS,
    DEATHWING_ALL_WILL_BURN,
    DOCTOR_HOLLIDAE_BLESSING_OF_THE_NINE_FROGS,
    EDWIN_SHARPEN_BLADES,
    KING_MUKLA_BANANARAMA,
    LADY_VASHJ_RELICS_OF_THE_DEEP,
    CAPTAIN_EUDORA_BURIED_TREASURE,
    LICH_BAZHIAL_GRAVEYARD_SHIFT,
    MALYGOS_ARCANE_ALTERATION,
    MILLIFICENT_TINKER,
    PYRAMAD_BRICK_BY_BRICK,
    ALAKIR_SWATTING_INSECTS,
    QUEEN_WAGTOGGLE_WAX_WARBAND,
    ROCK_MASTER_VOONE_UPBEAT_HARMONY,
    RAT_KING_A_TALE_OF_KINGS,
    SHUDDERWOCK_SNICKER_SNACK,
    XYRELLA_SEE_THE_LIGHT,
    RAGNAROS_SULFURAS,
    SKYCAPN_KRAGG_PIGGY_BANK,
    SNAKE_EYES_LUCKY_ROLL,
    register_audited_hero_power_effects,
)
from game.hero_powers import HeroPowerMode
from game.heroes import HEROES

BLACKTHORN, LICH_KING, PATCHWERK = 71458, 58024, 59397
BLOOD_GEM = 70136


def setup_game(hero):
    game = Bob(seed=123)
    game.create_players()
    game.round_number = 5
    game.phase = "recruit"
    game.priority_order = list(range(8))
    player = game.get_player(0)
    player.set_hero(hero)
    player.gold = 10
    player.set_ap(20)
    game.update_all_action_spaces()
    return game, player


def power_actions(game):
    game.update_action_space(0)
    return [a for a in game.get_player_action_space(0) if a.action_type == ActionType.HERO_POWER]


def test_printed_ordinary_power_contracts():
    expected = {
        BLACKTHORN: (71459, 1, "Get 2 <b>Blood Gems</b>. <i>(Twice per turn.)</i>"),
        LICH_KING: (58040, 0, "Give a minion <b>Reborn</b> until next turn."),
        PATCHWERK: (59399, 0, "Start the game with 30 extra Health."),
    }
    for hero, (power_id, cost, text) in expected.items():
        power = HEROES[hero]["power"]
        assert (power["id"], power["cost"], power["text"]) == (power_id, cost, text)


def test_blackthorn_cost_twice_per_turn_generated_gems_and_new_game_reset():
    game, player = setup_game(BLACKTHORN)
    pool_before = deepcopy(game.pool.available_cards)
    for _ in range(2):
        assert len(power_actions(game)) == 1
        game.use_hero_power(0)
    assert player.gold == 8
    assert [c["id"] for c in player.hand] == [BLOOD_GEM] * 4
    assert all(c["_generated"] for c in player.hand)
    assert game.get_player(1).hand == []
    assert game.pool.available_cards == pool_before
    assert not power_actions(game)
    with pytest.raises(ValueError):
        game.use_hero_power(0)
    game.round_number += 1
    game.use_hero_power(0)
    assert player.gold == 7
    assert game.hero_powers.uses_this_turn(0) == 1
    game.initialize_game()
    assert game.hero_powers.uses_this_game(0) == 0
    assert game.hero_powers.uses_this_turn(0) == 0
    assert game.hero_powers.get_rule(71459).max_uses_per_turn == 2


@pytest.mark.parametrize("hand_size,added", [(8, 2), (9, 1), (10, 0)])
def test_blackthorn_hand_capacity(hand_size, added):
    game, player = setup_game(BLACKTHORN)
    player.hand = [game.effects.create_card(BLOOD_GEM) for _ in range(hand_size)]
    game.use_hero_power(0)
    assert len(player.hand) == hand_size + added
    assert player.gold == 9
    assert game.hero_powers.uses_this_turn(0) == 1


def test_blackthorn_cannot_pay_and_generated_gem_is_castable():
    game, player = setup_game(BLACKTHORN)
    player.gold = 0
    assert not power_actions(game)
    with pytest.raises(ValueError):
        game.use_hero_power(0)
    assert not player.hand
    player.gold = 1
    game.use_hero_power(0)
    player.board[0] = game.effects.create_card(120031)
    before = (player.board[0]["attack"], player.board[0]["health"])
    target = game.effects.resolve_target_ref(0, EffectZone.BOARD, 0)
    game.cast_spell(0, 0, target_ref=target)
    assert (player.board[0]["attack"], player.board[0]["health"]) == (before[0] + 1, before[1] + 1)


def test_blackthorn_partial_uses_survive_search_and_encode_for_neural_ai():
    from agents.observation_encoder import CardVocabulary, ObservationEncoder

    game, player = setup_game(BLACKTHORN)
    game.use_hero_power(0)
    game.update_all_action_spaces()
    observation = ObservationBuilder(AgentMemory(0)).build(game)
    encoder = ObservationEncoder(CardVocabulary.from_cards_file())
    encoded = encoder.encode(observation)
    assert encoded.scalar_features[encoder.scalar_index("self_hero_power_uses_turn")] == pytest.approx(.1)
    assert encoded.scalar_features[encoder.scalar_index("self_hero_power_uses_game")] == pytest.approx(.01)
    world = DeterminizedBattlegroundsEnvironment().sample_determinization(
        observation, 0, random.Random(123)
    ).game
    assert len(power_actions(world)) == 1
    world.use_hero_power(0)
    assert not power_actions(world)
    assert len(world.get_player(0).hand) == 4
    assert len(player.hand) == 2
    assert game.hero_powers.uses_this_turn(0) == 1


def test_ordinary_power_resolves_on_final_interaction_budget():
    game, player = setup_game(BLACKTHORN)
    game.scheduler.begin_phase(range(8))
    for seat in game.players:
        seat.bind_recruit_scheduler(game.scheduler)
    player.ap = 1
    game.execute_action(0, power_actions(game)[0])
    assert player.ap == 0
    assert player.gold == 9
    assert len(player.hand) == 2
    assert not power_actions(game)


@pytest.mark.parametrize("native_reborn", [False, True])
def test_lich_king_keyword_expiry_preserves_native_reborn(native_reborn):
    game, player = setup_game(LICH_KING)
    minion = game.effects.create_card(120031)
    minion["keywords"] = ["Reborn"] if native_reborn else []
    player.board[0] = minion
    assert len(power_actions(game)) == 1
    target = game.effects.resolve_target_ref(0, EffectZone.BOARD, 0)
    game.use_hero_power(0, target_ref=target)
    assert player.gold == 10
    assert game.effects.has_keyword(minion, "Reborn")
    assert not power_actions(game)
    side = game.combat.engine.create_side(0, 1, [minion])
    assert game.effects.has_keyword(side.board[0], "Reborn")
    assert side.board[0] is not minion
    game.round_number += 1
    game.events.emit(GameEvent.TURN_START, player_id=0)
    assert game.effects.has_keyword(minion, "Reborn") == native_reborn
    assert len(power_actions(game)) == 1


def test_lich_king_invalid_targets_do_not_consume_use():
    game, player = setup_game(LICH_KING)
    assert not power_actions(game)
    with pytest.raises(ValueError):
        game.use_hero_power(0)
    game.get_player(1).board[0] = game.effects.create_card(120031)
    enemy = game.effects.resolve_target_ref(1, EffectZone.BOARD, 0)
    with pytest.raises(ValueError):
        game.use_hero_power(0, target_ref=enemy)
    player.board[0] = game.effects.create_card(120031)
    stale = game.effects.resolve_target_ref(0, EffectZone.BOARD, 0)
    player.board[0] = game.effects.create_card(120031)
    with pytest.raises(ValueError, match="stale"):
        game.use_hero_power(0, target_ref=stale)
    assert game.hero_powers.uses_this_turn(0) == 0


def test_patchwerk_health_is_applied_once_and_registration_is_idempotent():
    game, player = setup_game(PATCHWERK)
    assert player.health == 60
    assert game.hero_powers.rule_for_player(0).mode == HeroPowerMode.PASSIVE
    for _ in range(3):
        register_audited_hero_power_effects(game)
        game.events.emit(GameEvent.TURN_START, player_id=0)
    assert player.health == 60
    assert not power_actions(game)
    with pytest.raises(ValueError):
        game.use_hero_power(0)


def test_ordinary_registration_does_not_duplicate_rewards():
    game, player = setup_game(BLACKTHORN)
    for _ in range(3):
        register_audited_hero_power_effects(game)
    game.use_hero_power(0)
    assert len(player.hand) == 2
    assert game.hero_powers.uses_this_turn(0) == 1


def test_runtime_hero_power_identity_can_be_replaced_and_reset():
    game, player = setup_game(PATCHWERK)
    original = deepcopy(player.get_hero_power())
    replacement = {
        "id": 999001,
        "name": "Temporary Test Power",
        "cost": 2,
        "text": "A temporary test power.",
    }
    player.set_hero_power(replacement)
    assert player.get_hero_power()["id"] == 999001
    assert player.hero_power_cost == 2
    player.reset_hero_power()
    assert player.get_hero_power() == original
    assert player.hero_power_cost == original["cost"]


def test_alexstrasza_unlocks_at_tier_four_and_starts_discover():
    game, player = setup_game(61488)
    player.tavern_tier = 3
    assert not power_actions(game)
    player.tavern_tier = 4
    assert game.hero_powers.get_rule(ALEXSTRASZA_QUEEN_OF_DRAGONS) is not None
    assert len(power_actions(game)) == 1
    game.use_hero_power(0)
    choice = game.effects.get_pending_choice(0)
    assert choice is not None
    assert choice.kind == "discover"
    assert len(choice.options) == 3
    assert all(game.effects.is_minion_type(card, "Dragon") for card in choice.options)


def test_doctor_hollidae_gets_a_tavern_spell():
    game, player = setup_game(105434)
    game.use_hero_power(0)
    assert len(player.hand) == 1
    assert player.hand[0]["cardType"] == "spell"
    assert "tavern" in {str(x).casefold() for x in player.hand[0].get("categories", [])}


def test_skycapn_kragg_is_once_per_game_and_scales_by_round():
    game, player = setup_game(62268)
    game.round_number = 1
    game.use_hero_power(0)
    assert player.gold == 12
    assert not power_actions(game)
    with pytest.raises(ValueError):
        game.use_hero_power(0)


def test_cthun_scales_end_of_turn_buffs():
    game, player = setup_game(58535)
    game.round_number = 2
    minion = game.effects.create_card(120031)
    player.board[0] = minion
    register_audited_hero_power_effects(game)
    game.use_hero_power(0)
    game.events.emit(GameEvent.TURN_END, player_id=0, round_number=2)
    assert (minion["attack"], minion["health"]) == (4, 4)
    assert game.hero_powers.get_rule(CTHUN_SATURDAY_CTHUNS) is not None


def test_edwin_improves_after_every_four_card_purchases():
    game, player = setup_game(57633)
    minion = game.effects.create_card(120031)
    player.board[0] = minion
    target = game.effects.resolve_target_ref(0, EffectZone.BOARD, 0)
    for _ in range(4):
        game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card={"cardType": "minion"})
    game.use_hero_power(0, target_ref=target)
    assert (minion["attack"], minion["health"]) == (5, 5)
    assert game.hero_powers.get_rule(EDWIN_SHARPEN_BLADES) is not None


def test_snake_eyes_rolls_gold_and_enforces_cooldown():
    game, player = setup_game(105314)
    game.round_number = 1
    game.use_hero_power(0)
    roll = game.effects.get_player_state(0)["hero_snake_eyes_last_roll"]
    assert 1 <= roll <= 6
    assert player.gold == 10 - 1 + roll
    assert not power_actions(game)
    game.round_number += roll
    assert not power_actions(game)
    game.round_number += 1
    assert len(power_actions(game)) == 1
    assert game.hero_powers.get_rule(SNAKE_EYES_LUCKY_ROLL) is not None


def test_ragnaros_replaces_buy_insect_with_sulfuras():
    game, player = setup_game(57892)
    assert player.get_hero_power()["id"] == 64424
    for _ in range(11):
        game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card={"cardType": "minion"})
    assert player.get_hero_power()["id"] == 64424
    game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card={"cardType": "minion"})
    assert player.get_hero_power()["id"] == RAGNAROS_SULFURAS
    assert game.hero_powers.rule_for_player(0).power_id == RAGNAROS_SULFURAS
    minion = game.effects.create_card(120031)
    player.board[0] = minion
    game.events.emit(GameEvent.TURN_END, player_id=0)
    # A single minion occupies both ends and receives both +8/+8 buffs.
    assert (minion["attack"], minion["health"]) == (18, 18)


def test_king_mukla_distributes_bananas_at_turn_start():
    game, player = setup_game(59814)
    opponent = game.get_player(1)
    game.events.emit(GameEvent.TURN_START, player_id=0)
    assert [card["id"] for card in player.hand] == [122906, 122906]
    assert [card["id"] for card in opponent.hand] == [122906]
    assert game.hero_powers.get_rule(0) is None
    assert game.hero_powers.get_rule(KING_MUKLA_BANANARAMA) is not None


def test_malygos_replaces_a_tavern_minion_with_same_tier():
    game, player = setup_game(61490)
    player.tavern.slots[0] = game.pool.get_random_minion(tier=1)
    original = next(card for card in player.tavern.slots if isinstance(card, dict))
    slot = player.tavern.slots.index(original)
    player.gold = 10
    target = game.effects.resolve_target_ref(0, EffectZone.TAVERN, slot)
    pool_before = len(game.pool.available_cards)
    game.use_hero_power(0, target_ref=target)
    replacement = player.tavern.slots[slot]
    assert replacement is not None
    assert replacement["tier"] == original["tier"]
    assert replacement is not original
    assert len(game.pool.available_cards) == pool_before
    assert game.hero_powers.uses_this_turn(0) == 1


def test_millificent_unlocks_at_tier_four_and_discovers_magnetic_mechs():
    game, player = setup_game(57946)
    game.active_minion_types = ("Beast", "Demon", "Dragon", "Elemental", "Mech")
    game.pool.active_minion_types = game.active_minion_types
    player.tavern_tier = 3
    assert not power_actions(game)
    player.tavern_tier = 4
    assert game.hero_powers.get_rule(MILLIFICENT_TINKER) is not None
    game.use_hero_power(0)
    choice = game.effects.get_pending_choice(0)
    assert choice is not None
    assert len(choice.options) == 3
    assert all(
        game.effects.is_minion_type(card, "Mech")
        and game.effects.has_keyword(card, "Magnetic")
        for card in choice.options
    )


def test_pyramad_steals_a_tavern_minion_and_doubles_health():
    game, player = setup_game(59831)
    player.tavern.slots[0] = game.pool.get_random_minion(tier=1)
    original = player.tavern.slots[0]
    health_before = original["health"]
    game.use_hero_power(0)
    assert player.tavern.slots[0] is None
    assert len(player.hand) == 1
    assert player.hand[0]["id"] == original["id"]
    assert player.hand[0] is original
    assert player.hand[0]["health"] == health_before * 2
    assert game.hero_powers.get_rule(PYRAMAD_BRICK_BY_BRICK) is not None


def test_lich_bazhial_steals_a_tavern_card_and_takes_damage():
    game, player = setup_game(58044)
    player.tavern.slots[0] = game.pool.get_random_minion(tier=1)
    target = game.effects.resolve_target_ref(0, EffectZone.TAVERN, 0)
    durability_before = player.health + player.armor
    game.use_hero_power(0, target_ref=target)
    assert player.tavern.slots[0] is None
    assert len(player.hand) == 1
    assert player.health + player.armor == durability_before - 2
    assert game.hero_powers.get_rule(LICH_BAZHIAL_GRAVEYARD_SHIFT) is not None


def test_xyrella_sets_stolen_tavern_minion_to_two_two():
    game, player = setup_game(70956)
    player.tavern.slots[0] = game.pool.get_random_minion(tier=1)
    target = game.effects.resolve_target_ref(0, EffectZone.TAVERN, 0)
    game.use_hero_power(0, target_ref=target)
    assert player.tavern.slots[0] is None
    assert [(card["attack"], card["health"]) for card in player.hand] == [(2, 2)]
    assert game.hero_powers.get_rule(XYRELLA_SEE_THE_LIGHT) is not None


def test_deathwing_draft_is_not_registered_until_permanence_is_supported():
    game, player = setup_game(60369)
    own = game.effects.create_card(120031)
    enemy = game.effects.create_card(120031)
    side_a = game.combat.engine.create_side(0, 1, [own])
    side_b = game.combat.engine.create_side(1, 1, [enemy])
    game.events.emit(GameEvent.COMBAT_START, side_a=side_a, side_b=side_b)
    assert side_a.board[0]["attack"] == 2
    assert side_b.board[0]["attack"] == 2
    assert game.hero_powers.get_rule(DEATHWING_ALL_WILL_BURN) is None


def test_alakir_marks_leftmost_combat_minion():
    game, player = setup_game(64403)
    first = game.effects.create_card(120031)
    second = game.effects.create_card(120031)
    side_a = game.combat.engine.create_side(0, 1, [first, second])
    side_b = game.combat.engine.create_side(1, 1, [])
    game.events.emit(GameEvent.COMBAT_START, side_a=side_a, side_b=side_b)
    assert game.effects.has_keyword(side_a.board[0], "Windfury")
    assert game.effects.has_keyword(side_a.board[0], "Divine Shield")
    assert game.effects.has_keyword(side_a.board[0], "Taunt")
    assert not game.effects.has_keyword(side_a.board[1], "Taunt")
    assert game.hero_powers.get_rule(ALAKIR_SWATTING_INSECTS) is not None


def test_wagtoggle_draft_is_not_registered_until_progression_is_supported():
    game, player = setup_game(57924)
    beast = game.effects.create_card(120031)
    beast["minionTypes"] = ["Beast"]
    mech = game.effects.create_card(120031)
    mech["minionTypes"] = ["Mech"]
    side_a = game.combat.engine.create_side(0, 1, [beast, mech])
    side_b = game.combat.engine.create_side(1, 1, [])
    game.events.emit(GameEvent.COMBAT_START, side_a=side_a, side_b=side_b)
    assert (side_a.board[0]["attack"], side_a.board[0]["health"]) == (2, 2)
    assert (side_a.board[1]["attack"], side_a.board[1]["health"]) == (2, 2)
    assert game.hero_powers.get_rule(QUEEN_WAGTOGGLE_WAX_WARBAND) is None


def test_lady_vashj_generates_a_spellcraft_spell_at_turn_start():
    game, player = setup_game(85125)
    game.events.emit(GameEvent.TURN_START, player_id=0)
    assert len(player.hand) == 1
    assert player.hand[0]["cardType"] == "spell"
    assert "spellcraft" in {
        str(value).casefold() for value in player.hand[0].get("categories", [])
    }
    assert game.hero_powers.get_rule(LADY_VASHJ_RELICS_OF_THE_DEEP) is not None


def test_voone_copies_leftmost_hand_card_every_three_turns():
    game, player = setup_game(99033)
    original = game.effects.create_card(120031)
    player.hand = [original]
    for turn in range(1, 3):
        game.events.emit(GameEvent.TURN_END, player_id=0, round_number=turn)
        assert len(player.hand) == 1
    game.events.emit(GameEvent.TURN_END, player_id=0, round_number=3)
    assert len(player.hand) == 2
    assert player.hand[1]["id"] == original["id"]
    assert player.hand[1] is not original
    assert game.hero_powers.get_rule(ROCK_MASTER_VOONE_UPBEAT_HARMONY) is not None


def test_shudderwock_targets_a_friendly_battlecry_minion():
    game, player = setup_game(58027)
    game.round_number = 3
    battlecry = game.effects.create_card(122285)
    player.board[0] = battlecry
    target = game.effects.resolve_target_ref(0, EffectZone.BOARD, 0)
    game.use_hero_power(0, target_ref=target)
    assert game.hero_powers.uses_this_turn(0) == 1
    assert game.hero_powers.get_rule(SHUDDERWOCK_SNICKER_SNACK) is not None


def test_rat_king_discovers_from_rotating_minion_type():
    game, player = setup_game(57893)
    game.active_minion_types = (
        "Beast", "Demon", "Dragon", "Elemental", "Mech",
        "Murloc", "Naga", "Pirate", "Quilboar", "Undead",
    )
    game.pool.active_minion_types = game.active_minion_types
    game.round_number = 1
    game.use_hero_power(0)
    choice = game.effects.get_pending_choice(0)
    assert choice is not None
    assert len(choice.options) == 3
    assert all(game.effects.is_minion_type(card, "Beast") for card in choice.options)
    assert game.hero_powers.get_rule(RAT_KING_A_TALE_OF_KINGS) is not None


def test_captain_eudora_draft_is_unavailable():
    game, player = setup_game(62242)
    gold_before = player.gold
    with pytest.raises(ValueError):
        game.use_hero_power(0)
    assert player.hand == []
    assert player.gold == gold_before
    assert game.hero_powers.uses_this_game(0) == 0
    assert not power_actions(game)
    assert game.hero_powers.get_rule(CAPTAIN_EUDORA_BURIED_TREASURE) is None
