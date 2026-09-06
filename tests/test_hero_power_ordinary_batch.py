"""First ordinary batch: real engine effects, lifecycle, and AI continuations."""

from copy import deepcopy
import random

import pytest

from agents.observation import AgentMemory, ObservationBuilder
from agents.observation_encoder import CardVocabulary, ObservationEncoder
from agents.simulation_environment import DeterminizedBattlegroundsEnvironment
from game.actions import ActionType
from game.bob import Bob
from game.effects import EffectZone
from game.events import GameEvent
from game.hero_power_effects import register_audited_hero_power_effects
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
