from copy import deepcopy
import random
import pytest
from game.bob import Bob
from game.effects import EffectZone
from game.events import GameEvent
from game.hero_power_effects import register_audited_hero_power_effects
from game.economy import HASTY_EXCAVATION
from agents.observation import AgentMemory, ObservationBuilder
from agents.simulation_environment import DeterminizedBattlegroundsEnvironment


def setup(hero):
    game = Bob(seed=123)
    game.create_players()
    game.phase = 'recruit'
    game.round_number = 2
    game.priority_order = list(range(8))
    player = game.get_player(0)
    player.set_hero(hero)
    player.gold = 10
    player.ap = 20
    register_audited_hero_power_effects(game)
    return game, player


def test_cthun_requires_payment_and_own_turn_end():
    game, player = setup(58535)
    card = game.effects.create_card(120031)
    player.board[0] = card
    before = card['attack']
    game.events.emit(GameEvent.TURN_END, player_id=0)
    assert card['attack'] == before
    game.use_hero_power(0)
    assert player.gold == 9
    game.events.emit(GameEvent.TURN_END, player_id=1)
    assert card['attack'] == before
    game.events.emit(GameEvent.TURN_END, player_id=0)
    assert card['attack'] == before + 2
    game.events.emit(GameEvent.TURN_END, player_id=0)
    assert card['attack'] == before + 2


@pytest.mark.parametrize('hero', [59831, 58044, 70956])
def test_theft_preserves_physical_copy_and_rejects_full_hand(hero):
    game, player = setup(hero)
    card = game.pool.get_random_minion(tier=1)
    player.tavern.slots[0] = card
    target = game.effects.resolve_target_ref(0, EffectZone.TAVERN, 0)
    kwargs = {} if hero == 59831 else {'target_ref': target}
    player.hand = [game.effects.create_card(70136) for _ in range(10)]
    with pytest.raises(ValueError):
        game.use_hero_power(0, **kwargs)
    assert player.gold == 10
    assert game.hero_powers.uses_this_turn(0) == 0
    player.hand.clear()
    game.use_hero_power(0, **kwargs)
    assert player.hand[0] is card
    assert not card.get('_generated', False)
    assert player.tavern.slots[0] is None


def test_voone_plain_copy_drops_buffs():
    game, player = setup(99033)
    original = game.effects.create_card(120031)
    base = original['attack']
    original['attack'] += 50
    original['_attachments'] = [{'id': 70136}]
    player.hand = [original]
    for _ in range(3):
        game.events.emit(GameEvent.TURN_END, player_id=0)
    assert player.hand[1]['attack'] == base
    assert not player.hand[1].get('_attachments')
    assert original['attack'] == base + 50


def test_ragnaros_replacement_survives_search():
    game, player = setup(57892)
    for _ in range(12):
        game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card={'cardType': 'minion'})
    observation = ObservationBuilder(AgentMemory(0)).build(game)
    world = DeterminizedBattlegroundsEnvironment().sample_determinization(
        observation, 0, random.Random(12)
    ).game
    assert world.get_player(0).get_hero_power()['id'] == 64426
    assert world.get_player(0).get_hero_power() is not player.get_hero_power()


def test_alakir_shield_blocks_damage_only_on_combat_copy():
    game, player = setup(64403)
    original = game.effects.create_card(120031)
    player.board[0] = original
    engine = game.combat.engine
    own = engine.create_side(0, 1, [original])
    enemy = engine.create_side(1, 1, [game.effects.create_card(120031)])
    game.events.emit(GameEvent.COMBAT_START, side_a=own, side_b=enemy)
    target = own.board[0]
    health = target['health']
    assert target['_combat_divine_shield']
    engine.deal_minion_damage(enemy.board[0], target, 1,
                       source_side=enemy, target_side=own)
    assert target['health'] == health
    assert not target['_combat_divine_shield']
    engine.deal_minion_damage(enemy.board[0], target, 1,
                       source_side=enemy, target_side=own)
    assert target['health'] == health - 1
    assert not game.effects.has_keyword(original, 'Divine Shield')


@pytest.mark.parametrize('hero,key,threshold', [
    (57633, 'hero_edwin_card_purchases', 4),
    (57892, 'hero_ragnaros_card_buys', 12),
])
@pytest.mark.parametrize('health_paid', [False, True])
def test_card_purchase_powers_count_real_spell_purchase_once(hero, key, threshold, health_paid):
    game, player = setup(hero)
    state = game.effects.get_player_state(0)
    state[key] = threshold - 1
    spell = (game.effects.create_card(HASTY_EXCAVATION, generated=False)
             if health_paid else {'id': -1, 'cardType': 'spell', 'manaCost': 1})
    player.tavern.spell = spell
    game.buy_spell(0)
    assert state[key] == threshold
    assert player.hand[-1] is spell
    assert player.tavern.spell is None
    if hero == 57892:
        assert player.get_hero_power()['id'] == 64426


@pytest.mark.parametrize('hero,key', [
    (57633, 'hero_edwin_card_purchases'),
    (57892, 'hero_ragnaros_card_buys'),
])
def test_card_purchase_counters_ignore_other_players_and_failed_purchases(hero, key):
    game, player = setup(hero)
    state = game.effects.get_player_state(0)
    other = game.get_player(1)
    other.gold = 10
    other.tavern.spell = {'id': -1, 'cardType': 'spell', 'manaCost': 1}
    game.buy_spell(1)
    assert state.get(key, 0) == 0
    player.gold = 0
    player.tavern.spell = {'id': -1, 'cardType': 'spell', 'manaCost': 1}
    with pytest.raises(ValueError):
        game.buy_spell(0)
    assert state.get(key, 0) == 0


def test_deathwing_does_not_buff_other_players_match():
    from game.heroes import HEROES
    hero = next(key for key, value in HEROES.items() if value['name'] == 'Deathwing')
    game, player = setup(hero)
    engine = game.combat.engine
    first = engine.create_side(1, 1, [game.effects.create_card(120031)])
    second = engine.create_side(2, 1, [game.effects.create_card(120031)])
    before = [side.board[0]['attack'] for side in (first, second)]
    game.events.emit(GameEvent.COMBAT_START, side_a=first, side_b=second)
    assert [side.board[0]['attack'] for side in (first, second)] == before
