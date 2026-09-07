from copy import deepcopy
import random

import pytest

from agents.observation import AgentMemory, ObservationBuilder
from agents.observation_encoder import CardVocabulary, ObservationEncoder
from agents.simulation_environment import DeterminizedBattlegroundsEnvironment
from game.actions import ActionType
from game.economy import HASTY_EXCAVATION, tavern_spell_purchase_cost
from game.events import GameEvent
from tests.test_hero_power_correction_batch import setup


def offer(game, player, cost=2):
    card = game.effects.create_card(104436)
    card['manaCost'] = cost
    player.tavern.spell = card
    return card


def test_every_third_purchase_free_across_turns_without_mutating_printed_cost():
    game, player = setup(105431)
    for index in range(6):
        card = offer(game, player)
        expected = 0 if index % 3 == 2 else 2
        before = player.gold
        assert tavern_spell_purchase_cost(player, card) == expected
        assert tavern_spell_purchase_cost(player, card) == expected
        game.buy_spell(0)
        assert player.gold == before - expected
        assert card['manaCost'] == 2
        game.events.emit(GameEvent.TURN_END, player_id=0)
        game.events.emit(GameEvent.TURN_START, player_id=0)
    assert player.get_hero_power()['spell_purchase_progress'] == 0


def test_failed_purchases_and_other_players_do_not_advance_progress():
    game, player = setup(105431)
    offer(game, player)
    player.gold = 0
    with pytest.raises(ValueError):
        game.buy_spell(0)
    game.events.emit(GameEvent.SPELL_BOUGHT, player_id=1, card=player.tavern.spell)
    game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=player.tavern.spell)
    assert player.get_hero_power().get('spell_purchase_progress', 0) == 0
    player.gold = 10
    for _ in range(2):
        offer(game, player, cost=0)
        game.buy_spell(0)
    offer(game, player)
    player.hand = [game.effects.create_card(70136) for _ in range(10)]
    with pytest.raises(ValueError):
        game.buy_spell(0)
    assert player.get_hero_power()['spell_purchase_progress'] == 2


def test_free_purchase_legality_and_search_state_isolation():
    game, player = setup(105431)
    for _ in range(2):
        offer(game, player)
        game.buy_spell(0)
    card = offer(game, player)
    player.gold = 0
    game.update_action_space(0)
    actions = game.get_player_action_space(0)
    assert any(a.action_type == ActionType.BUY_SPELL for a in actions)
    assert not any(a.action_type == ActionType.HERO_POWER for a in actions)
    observation = ObservationBuilder(AgentMemory(0)).build(game)
    copied = DeterminizedBattlegroundsEnvironment().sample_determinization(
        observation, 0, random.Random(25)).game
    copied.buy_spell(0)
    assert copied.get_player(0).get_hero_power()['spell_purchase_progress'] == 0
    assert player.get_hero_power()['spell_purchase_progress'] == 2
    assert player.tavern.spell is card
    cloned = deepcopy(game)
    cloned.buy_spell(0)
    assert player.tavern.spell is card


def test_neural_scalars_distinguish_discount_progress():
    game, player = setup(105431)
    builder = ObservationBuilder(AgentMemory(0))
    encoder = ObservationEncoder(CardVocabulary([]))
    before = encoder._encode_scalars(builder.build(game))
    player.get_hero_power()['spell_purchase_progress'] = 2
    after = encoder._encode_scalars(builder.build(game))
    assert before != after


def test_zero_cost_health_purchase_does_not_emit_damage():
    game, player = setup(105431)
    for _ in range(2):
        offer(game, player)
        game.buy_spell(0)
    player.tavern.spell = game.effects.create_card(HASTY_EXCAVATION)
    player.health = 1
    player.gold = 0
    damage = []
    game.events.register(GameEvent.PLAYER_DAMAGED, damage.append)
    game.buy_spell(0)
    assert player.health == 1 and player.gold == 0
    assert damage == []
    assert player.get_hero_power()['spell_purchase_progress'] == 0
