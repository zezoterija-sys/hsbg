import random

import pytest

from agents.observation import AgentMemory, ObservationBuilder
from agents.simulation_environment import DeterminizedBattlegroundsEnvironment
from game.actions import ActionType
from game.bob import Bob
from game.events import GameEvent
from game.card_effects import WRATH_WEAVER


def game():
    bob = Bob(seed=24680)
    bob.initialize_game()
    for player in bob.players:
        bob.choose_hero(player.player_id, player.hero_choices[0])
    return bob


def test_recruit_death_gets_placement_and_becomes_available_as_ghost():
    bob = game()
    eliminated_events = []
    bob.events.register(GameEvent.PLAYER_ELIMINATED, eliminated_events.append)
    player = bob.get_player(0)
    player.take_damage(player.health + player.armor)
    bob.recruitment.check_complete()
    assert player.placement == 8
    assert player.waiting
    pairings = bob.combat.create_pairings()
    ghosts = [p for p in pairings if p.player_b_is_ghost]
    assert len(ghosts) == 1
    assert ghosts[0].player_b_id == 0
    bob.recruitment.check_complete()
    assert len(eliminated_events) == 1


@pytest.mark.parametrize('gold', [0, 3])
def test_purchase_reserves_hand_space_before_gold_spent_effect(gold):
    bob = game()
    player = bob.get_player(0)
    # Use nine distinct synthetic minions so this hand-capacity regression does
    # not accidentally exercise the independent three-copy TripleSystem.
    player.hand = [
        {
            'id': -1000 - index,
            'name': f'Synthetic Hand Minion {index}',
            'cardType': 'minion',
            'attack': 1,
            'health': 1,
            'tier': 1,
            'keywords': [],
        }
        for index in range(9)
    ]
    player.gold = gold
    bought = player.tavern.slots[0]
    bob.events.register(GameEvent.GOLD_SPENT,
                        lambda event: bob.effects.add_generated_to_hand(0, 120031))
    if gold == 0:
        with pytest.raises(ValueError):
            bob.buy_minion(0, 0)
        assert len(player.hand) == 9
        assert player.tavern.slots[0] is bought
    else:
        bob.buy_minion(0, 0)
        assert len(player.hand) == 10
        assert player.hand[-1] is bought


def test_search_can_advance_real_scheduler_through_combat():
    bob = game()
    observation = ObservationBuilder(AgentMemory(0)).build(bob)
    env = DeterminizedBattlegroundsEnvironment()
    rng = random.Random(123)
    state = env.sample_determinization(observation, 0, rng)
    action = next(a for a in env.legal_actions(state, 0)
                  if a.action_type == ActionType.END_TURN)
    env.step(state, 0, action, rng)
    assert state.game.round_number > observation.round_number
    assert env.legal_actions(state, 0)
    assert bob.round_number == observation.round_number


def test_repeated_self_damage_after_lethal_does_not_crash():
    bob = game()
    player = bob.get_player(0)
    player.health, player.armor = 1, 0
    player.board[0] = bob.effects.create_card(WRATH_WEAVER, golden=True)
    bob.events.emit(GameEvent.CARD_PLAYED, player_id=0,
                    card={'id': -1, 'cardType': 'minion', 'minionType': 'Demon'})
    assert player.eliminated
    bob.recruitment.check_complete()
    assert player.placement == 8


def test_turn_end_discover_blocks_combat_even_after_budget_exhaustion():
    bob = game()
    bob.effects.register_choice_resolver('test_end_turn', lambda *args: None)
    def discover(event):
        if event.get('player_id') == 0:
            bob.effects.start_choice(0, 'test_end_turn', [1, 2])
    bob.events.register(GameEvent.TURN_END, discover)
    for player in bob.players:
        bob.scheduler.set_remaining_budget(player.player_id, 0)
    before = bob.round_number
    assert not bob.recruitment.check_complete()
    assert bob.phase == 'recruit'
    assert bob.round_number == before
    assert bob.recruitment.eligible_player_ids() == (0,)
    bob.update_all_action_spaces()
    bob.execute_action(0, bob.get_player_action_space(0)[0])
    assert bob.round_number == before + 1


def test_solos_hero_offers_exclude_duos_and_patchwerk_accepts_missing_armor():
    bob = game()
    from game.heroes import HEROES
    duos_ids = {card_id for card_id in HEROES
                if bob.pool.card_definitions_by_id[card_id].get('isDuosOnly')}
    assert duos_ids
    assert not duos_ids.intersection(bob._solos_hero_ids())
    patchwerk = next(i for i, d in HEROES.items() if d.get('name') == 'Patchwerk')
    assert HEROES[patchwerk]['armor'] is None
    from game.player import Player
    player = Player(0)
    player.set_hero(patchwerk)
    assert player.armor == 0
    assert player.health == 60
