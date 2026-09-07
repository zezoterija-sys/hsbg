"""Focused real-engine triple formation, enchantment and reward regressions."""

from copy import deepcopy
import random

import pytest

from game.bob import Bob
from game.events import GameEvent
from game.triples import TRIPLE_REWARD
from agents.observation import AgentMemory, ObservationBuilder
from agents.simulation_environment import DeterminizedBattlegroundsEnvironment


@pytest.fixture
def game():
    bob = Bob(seed=24680)
    bob.initialize_game()
    for player in bob.players:
        bob.choose_hero(player.player_id, player.hero_choices[0])
    return bob


def copies(game):
    # Use a real offered card so finite-pool returns are meaningful in this lobby.
    base = game.get_player(0).tavern.slots[0]
    return [game.effects.create_card(base['id'], generated=False) for _ in range(3)]


def form(game, cards):
    p = game.get_player(0)
    p.board[0:2] = cards[:2]
    p.hand.append(cards[2])
    game.events.emit(GameEvent.CARD_ADDED_TO_HAND, player_id=0, card=cards[2])
    return p.hand[-1]


def test_three_copies_across_zones_merge_with_all_buff_deltas(game):
    cards = copies(game)
    base = deepcopy(cards[0])
    game.effects.apply_buff(cards[0], attack=3, health=1)
    game.effects.apply_buff(cards[1], health=4)
    result = form(game, cards)
    assert result['attack'] == base['attackGold'] + 3
    assert result['health'] == base['healthGold'] + 5
    assert result['isGolden']
    assert game.get_player(0).board[:2] == [None, None]
    assert len(game.get_player(0).hand) == 1
    assert result['id'] != TRIPLE_REWARD


@pytest.mark.parametrize('deltas,expected', [([-9, 0, 0], 0), ([-2, 7, 0], 5)])
def test_debuffs_offset_buffs_but_cannot_reduce_initial_golden_base(game, deltas, expected):
    cards = copies(game)
    base = cards[0]['attackGold']
    for c, d in zip(cards, deltas):
        game.effects.apply_buff(c, attack=d)
    result = form(game, cards)
    assert result['attack'] == base + expected


def test_aura_bonus_is_not_baked_into_triple_and_attachments_are_preserved(game):
    cards = copies(game)
    base = cards[0]['attackGold']
    cards[0]['attack'] += 10
    cards[0]['_aura_attack_bonus'] = 10
    cards[1]['_attachments'] = [{'id': -42, 'attack': 3, 'health': 4, 'isGolden': False}]
    game.effects.apply_buff(cards[1], attack=3, health=4)
    game.effects.grant_keyword(cards[1], 'Taunt')
    result = form(game, cards)
    assert result['attack'] == base + 3
    assert 'Taunt' in result['keywords']
    assert result['_attachments'] == cards[1]['_attachments']
    assert result['_attachments'][0] is not cards[1]['_attachments'][0]
    assert not result['_attachments'][0]['isGolden']


def test_temporary_enchantments_keep_their_expiry(game):
    cards = copies(game)
    game.effects.apply_buff(cards[0], attack=5, until_next_turn=True)
    # Avoid testing a native keyword accidentally chosen by the seeded lobby.
    for c in cards:
        c['keywords'] = []
    game.effects.grant_keyword(cards[0], 'Immune', until_next_turn=True)
    result = form(game, cards)
    initial = result['attack']
    game.effects._expire_temporary_modifiers(result, game.round_number + 1)
    assert result['attack'] == initial - 5
    assert 'Immune' not in result['keywords']


def test_permanent_keyword_on_another_copy_survives_temporary_expiry(game):
    cards = copies(game)
    game.effects.grant_keyword(cards[0], 'Divine Shield', until_next_turn=True)
    game.effects.grant_keyword(cards[1], 'Divine Shield')
    result = form(game, cards)
    game.effects._expire_temporary_modifiers(result, game.round_number + 1)
    assert 'Divine Shield' in result['keywords']


def test_generated_acquisition_can_complete_triple_and_no_combat_tripling(game):
    p = game.get_player(0)
    cards = copies(game)
    p.hand = cards[:2]
    game.phase = 'combat'
    game.effects.add_generated_to_hand(0, cards[2])
    assert len(p.hand) == 3
    game.phase = 'recruit'
    game.events.emit(GameEvent.RECRUIT_START)
    assert len(p.hand) == 1
    assert p.hand[0]['isGolden']
    assert len(p.hand[0]['_pool_copies']) == 2


def test_golden_cards_do_not_combine_again_and_six_basics_make_two(game):
    p = game.get_player(0)
    card_id = copies(game)[0]['id']
    p.hand = [game.effects.create_card(card_id) for _ in range(6)]
    game.triples.resolve(0)
    assert len(p.hand) == 2
    p.hand.append(game.effects.create_card(card_id, golden=True))
    game.triples.resolve(0)
    assert len(p.hand) == 3


@pytest.mark.parametrize('tier,expected', [(1, 2), (4, 5), (5, 6), (6, 6)])
def test_reward_tier_is_locked_when_golden_played_and_discover_reserves_pool(game, tier, expected):
    p = game.get_player(0)
    golden = form(game, copies(game))
    p.tavern.tier = tier
    game.play_minion(0, p.hand.index(golden), 0)
    reward = next(c for c in p.hand if c['id'] == TRIPLE_REWARD)
    assert reward['_discover_tier'] == expected
    assert len([c for c in p.hand if c['id'] == TRIPLE_REWARD]) == 1
    p.tavern.tier = 6
    before = game.pool.available_count()
    game.cast_spell(0, p.hand.index(reward))
    choice = game.effects.get_pending_choice(0)
    assert len(choice.options) == 3
    assert len({c['id'] for c in choice.options}) == 3
    assert {c['tier'] for c in choice.options} == {expected}
    assert game.pool.available_count() == before - 3
    chosen = choice.options[0]
    game.effects.resolve_choice(0, 0)
    assert any(c is chosen for c in p.hand)
    assert game.pool.available_count() == before - 1


def test_sale_of_triple_returns_three_plain_copies(game):
    p = game.get_player(0)
    result = form(game, copies(game))
    p.hand.remove(result)
    p.board[0] = result
    before = game.pool.available_count()
    game.sell_minion(0, 0)
    assert game.pool.available_count() == before + 3
    assert all(not game.effects.is_golden(c) for c in game.pool.available_cards[-3:])


def test_suppressed_reward_is_respected(game):
    p = game.get_player(0)
    result = form(game, copies(game))
    result['_no_triple_reward'] = True
    game.play_minion(0, p.hand.index(result), 0)
    assert not any(c['id'] == TRIPLE_REWARD for c in p.hand)


def test_discover_copy_and_search_keep_reservations_and_resolvers_isolated(game):
    reward = game.triples.grant_reward(0)
    p = game.get_player(0)
    game.cast_spell(0, p.hand.index(reward))
    observation = ObservationBuilder(AgentMemory(0)).build(game)
    env = DeterminizedBattlegroundsEnvironment()
    state = env.sample_determinization(observation, 0, random.Random(3))
    world = state.game
    pending = world.effects.get_pending_choice(0)
    assert pending.options[0] is pending.metadata['reserved_offers'][0]
    before = world.pool.available_count()
    world.effects.resolve_choice(0, 0)
    assert world.pool.available_count() == before + 2
    assert game.effects.get_pending_choice(0) is not None
    assert not p.hand


def test_buying_third_copy_combines_without_extra_gold_or_action(game):
    p = game.get_player(0)
    bought = p.tavern.slots[0]
    p.board[0:2] = [game.effects.create_card(bought['id']) for _ in range(2)]
    p.gold = 3
    game.buy_minion(0, 0)
    assert p.gold == 0
    assert p.tavern.slots[0] is None
    assert len(p.hand) == 1 and p.hand[0]['isGolden']
