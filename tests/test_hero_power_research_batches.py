"""Real-engine regressions for research-driven Hero Power corrections."""
from copy import deepcopy
import random

import pytest

from game.effects import EffectZone
from game.events import GameEvent
from tests.test_hero_power_correction_batch import setup
from agents.observation import AgentMemory, ObservationBuilder
from agents.simulation_environment import DeterminizedBattlegroundsEnvironment


def discover_game(hero):
    game, player = setup(hero)
    player.tavern_tier = 4
    game.active_minion_types = ('Beast', 'Demon', 'Dragon', 'Elemental', 'Mech')
    game.pool.active_minion_types = game.active_minion_types
    kind = 'Dragon' if hero == 61488 else 'Mech'
    definitions = [card for card in game.pool.card_definitions
                   if card.get('cardType') == 'minion' and card.get('pool') is True
                   and 'tavern' in card.get('categories', [])
                   and not card.get('isDuosOnly', False)
                   and game.pool.is_pool_card(card)
                   and game.effects.is_minion_type(card, kind)
                   and (kind != 'Mech' or game.effects.has_keyword(card, 'Magnetic'))]
    assert len(definitions) >= 3
    game.pool.available_cards = [game.effects.create_card(card['id'], generated=False)
                                 for card in definitions[:3]]
    return game, player


@pytest.mark.parametrize('hero', [61488, 57946])
@pytest.mark.parametrize('resolution', ['select', 'full', 'eliminate'])
def test_hero_discover_reservations_are_conserved(hero, resolution):
    game, player = discover_game(hero)
    before = len(game.pool.available_cards)
    game.use_hero_power(0)
    choice = game.effects.get_pending_choice(0)
    assert len(choice.options) == 3
    assert len(game.pool.available_cards) == before - 3
    chosen = choice.options[0]
    if resolution == 'eliminate':
        player.eliminated = True
        game.events.emit(GameEvent.PLAYER_ELIMINATED, player_id=0)
    else:
        if resolution == 'full':
            player.hand = [game.effects.create_card(70136) for _ in range(10)]
        game.effects.resolve_choice(0, 0)
    assert game.effects.get_pending_choice(0) is None
    assert len(game.pool.available_cards) == before - (resolution == 'select')
    if resolution == 'select':
        assert player.hand[-1] is chosen
        assert not chosen.get('_generated', False)


def test_hero_discover_no_candidates_rejected_before_payment():
    game, player = discover_game(61488)
    game.pool.available_cards.clear()
    with pytest.raises(ValueError):
        game.use_hero_power(0)
    assert player.gold == 10 and game.hero_powers.uses_this_turn(0) == 0


def test_hero_discover_scarce_pool_reserves_one_copy_per_identity():
    game, player = discover_game(61488)
    original = game.pool.available_cards[0]
    duplicate = deepcopy(original)
    game.pool.available_cards = [original, duplicate]
    game.use_hero_power(0)
    choice = game.effects.get_pending_choice(0)
    assert len(choice.options) == 1
    assert len(game.pool.available_cards) == 1
    with pytest.raises(ValueError):
        game.effects.discover_pool_minions(0, lambda card: True)
    assert len(game.pool.available_cards) == 1
    copied = deepcopy(game)
    copied.effects.resolve_choice(0, 0)
    assert len(copied.get_player(0).hand) == 1
    assert player.hand == []
    assert game.effects.get_pending_choice(0) is choice
    player.eliminated = True
    game.events.emit(GameEvent.PLAYER_ELIMINATED, player_id=0)
    game.events.emit(GameEvent.PLAYER_ELIMINATED, player_id=0)
    assert len(game.pool.available_cards) == 2


def test_hero_discover_pending_search_keeps_reservation_alias_and_isolation():
    game, player = discover_game(61488)
    game.use_hero_power(0)
    observation = ObservationBuilder(AgentMemory(0)).build(game)
    copied = DeterminizedBattlegroundsEnvironment().sample_determinization(
        observation, 0, random.Random(22)).game
    choice = copied.effects.get_pending_choice(0)
    assert choice.options[0] is choice.metadata['reserved_offers'][0]
    before = len(copied.pool.available_cards)
    copied.effects.resolve_choice(0, 0)
    assert len(copied.pool.available_cards) == before + 2
    assert player.hand == [] and game.effects.get_pending_choice(0) is not None


def test_bazhial_spell_only_shop_transfer_damage_and_action_roundtrip():
    game, player = setup(58044)
    spell = game.effects.create_card(70136, generated=False)
    player.tavern.slots[:] = [None] * len(player.tavern.slots)
    player.tavern.spell = spell
    player.armor = 1
    health = player.health
    damage = []
    game.events.register(GameEvent.PLAYER_DAMAGED, damage.append)
    game.update_action_space(0)
    actions = [a for a in game.get_player_action_space(0)
               if a.action_type.value == 'hero_power']
    assert len(actions) == 1
    assert actions[0].effect_target_idx == player.tavern.spell_target_index
    game.resolve_action(0, actions[0])
    assert player.hand[-1] is spell
    assert player.tavern.spell is None
    assert player.gold == 8
    assert player.armor == 0 and player.health == health - 1
    assert len(damage) == 1 and damage[0].get('self_damage') is True


@pytest.mark.parametrize('invalid', ['stale', 'full', 'opponent'])
def test_bazhial_spell_rejection_preserves_state(invalid):
    game, player = setup(58044)
    player.tavern.spell = game.effects.create_card(70136)
    owner = player
    if invalid == 'opponent':
        owner = game.get_player(1)
        owner.tavern.spell = game.effects.create_card(70136)
    ref = game.effects.resolve_target_ref(owner.player_id, EffectZone.TAVERN,
                                          owner.tavern.spell_target_index)
    if invalid == 'stale':
        player.tavern.spell = game.effects.create_card(70136)
    if invalid == 'full':
        player.hand = [game.effects.create_card(70136) for _ in range(10)]
    before = (player.gold, player.health, player.armor, deepcopy(player.hand))
    with pytest.raises(ValueError):
        game.use_hero_power(0, target_ref=ref)
    assert (player.gold, player.health, player.armor, player.hand) == before
    assert game.hero_powers.uses_this_turn(0) == 0


def test_bazhial_spell_ref_in_copy_resolves_to_copy_not_original():
    game, player = setup(58044)
    player.tavern.spell = game.effects.create_card(70136)
    copied = deepcopy(game)
    ref = copied.effects.resolve_target_ref(0, EffectZone.TAVERN,
                                            copied.get_player(0).tavern.spell_target_index)
    copied.use_hero_power(0, target_ref=ref)
    assert player.tavern.spell is not None and player.hand == []
    assert copied.get_player(0).hand[0] is not player.tavern.spell


def test_vashj_spellcraft_expires_only_at_owner_turn_end():
    game, player = setup(85125)
    game.events.emit(GameEvent.TURN_START, player_id=1)
    assert player.hand == []
    game.events.emit(GameEvent.TURN_START, player_id=0)
    assert len(player.hand) == 1
    assert player.hand[0]['_spellcraft_temporary'] is True
    game.events.emit(GameEvent.TURN_END, player_id=1)
    assert len(player.hand) == 1
    copied = deepcopy(game)
    copied.events.emit(GameEvent.TURN_END, player_id=0)
    assert copied.get_player(0).hand == [] and len(player.hand) == 1
    game.events.emit(GameEvent.TURN_END, player_id=0)
    assert player.hand == []


def test_vashj_full_hand_does_not_overflow():
    game, player = setup(85125)
    player.hand = [game.effects.create_card(70136) for _ in range(10)]
    original = list(player.hand)
    game.events.emit(GameEvent.TURN_START, player_id=0)
    assert all(a is b for a, b in zip(player.hand, original))
    assert len(player.hand) == 10


@pytest.mark.parametrize('ghost', [False, True])
def test_deathwing_permanence_maps_each_owner_and_skips_ghost_original(ghost):
    game, player = setup(60369)
    opponent = game.get_player(1)
    player.board[2] = game.effects.create_card(120031)
    opponent.board[4] = game.effects.create_card(120031)
    snapshots = game.combat._snapshot_alive_boards()
    own = game.combat.engine.create_side(0, 1, snapshots[0])
    enemy = game.combat.engine.create_side(1, 1, snapshots[1], is_ghost=ghost)
    game.events.emit(GameEvent.COMBAT_START, side_a=own, side_b=enemy)
    assert own.board[0]['attack'] == enemy.board[0]['attack'] == 4
    assert player.board[2]['attack'] == 4
    assert opponent.board[4]['attack'] == (2 if ghost else 4)
    # Death during combat cannot erase an already-applied permanent gain.
    own.board.clear()
    enemy.board.clear()
    assert player.board[2]['attack'] == 4


def test_deathwing_permanence_in_copied_game_does_not_mutate_source():
    game, player = setup(60369)
    player.board[0] = game.effects.create_card(120031)
    copied = deepcopy(game)
    snapshots = copied.combat._snapshot_alive_boards()
    own = copied.combat.engine.create_side(0, 1, snapshots[0])
    enemy = copied.combat.engine.create_side(1, 1, [])
    copied.events.emit(GameEvent.COMBAT_START, side_a=own, side_b=enemy)
    assert copied.get_player(0).board[0]['attack'] == 4
    assert player.board[0]['attack'] == 2
