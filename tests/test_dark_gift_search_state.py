"""Search worlds restore own Dark Discovery state without pool duplication."""

from agents.observation import AgentMemory, ObservationBuilder
from agents.simulation_environment import DeterminizedBattlegroundsEnvironment
from game.actions import ActionType
from game.bob import Bob
from game.dark_gift_effects import SHARPENED_SWORD, attach_dark_gift
from game.events import GameEvent


def _game():
    game = Bob(seed=24680)
    game.initialize_game()
    for player in game.players:
        game.choose_hero(player.player_id, player.hero_choices[0])
    game.round_number = 3
    game.get_player(0).gold = 10
    game.update_all_action_spaces()
    return game


def _observe(game):
    return ObservationBuilder(AgentMemory(0)).build(game)


def test_dark_discovery_reconstruction_preserves_reservations_and_use_limits():
    source = _game()
    action = next(a for a in source.get_player_action_space(0) if a.action_type == ActionType.DARK_GIFT)
    source.execute_action(0, action)
    observation = _observe(source)
    view = observation.pending_choice
    real = source.effects.get_pending_choice(0)
    assert view.options[0].minion is view.metadata["reserved_offers"][0].minion
    assert view.options[0].minion is not real.options[0].minion
    simulation = DeterminizedBattlegroundsEnvironment()._build_public_template(observation)
    pending = simulation.effects.get_pending_choice(0)
    assert pending.options[0].minion is pending.metadata["reserved_offers"][0].minion
    before = simulation.pool.available_count()
    assert simulation.dark_gifts.uses(0) == 1
    simulation.effects.resolve_choice(0, 0)
    # Exactly the two unselected reserved minions return to the pool.
    assert simulation.pool.available_count() == before + 2
    assert not simulation.dark_gifts.can_use(0)
    assert source.effects.get_pending_choice(0) is real
    assert not source.get_player(0).hand


def test_restored_gifts_execute_and_exhausted_use_limit_survives_observation():
    source = _game()
    host = source.effects.create_card(120031)
    attach_dark_gift(source.effects, 0, host,
                     source.pool.card_definitions_by_id[SHARPENED_SWORD], acquired_turn=3)
    source.get_player(0).board[0] = host
    source.effects.get_player_state(0)["dark_gift_uses"] = 3
    simulation = DeterminizedBattlegroundsEnvironment()._build_public_template(_observe(source))
    initial = host["attack"]
    simulation.events.emit(GameEvent.CARD_PLAYED, player_id=0, card={"id": 1})
    assert simulation.get_player(0).board[0]["attack"] == initial + 3
    assert host["attack"] == initial
    assert not simulation.dark_gifts.can_use(0)
