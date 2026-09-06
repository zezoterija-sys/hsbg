"""Public lobby types survive the AI boundary and search reconstruction."""

from dataclasses import asdict, replace
import random

import torch

from agents.observation import AgentMemory, ObservationBuilder
from agents.observation_encoder import CardVocabulary, ObservationEncoder
from agents.simulation_environment import DeterminizedBattlegroundsEnvironment
from game.bob import Bob
from game.lobby import is_minion_available_for_lobby


def _observation():
    game = Bob(seed=41)
    game.initialize_game()
    for player_id in tuple(game.priority_order):
        game.choose_hero(player_id, game.get_player(player_id).hero_choices[0])
    return game, ObservationBuilder(AgentMemory(0)).build(game)


def test_observation_exposes_lobby_types_but_not_priority_or_hidden_pool():
    game, observation = _observation()
    assert observation.active_minion_types == game.active_minion_types
    assert len(observation.active_minion_types) == 5
    fields = asdict(observation)
    assert "priority_order" not in fields
    assert "available_cards" not in fields["pool"]
    builder = ObservationBuilder(AgentMemory(0))
    game.priority_order.reverse()
    assert builder.build(game) == observation


def test_lobby_mask_has_fixed_schema_and_distinguishes_public_lobbies():
    game, observation = _observation()
    encoder = ObservationEncoder(CardVocabulary.from_cards_file())
    first = encoder.encode(observation)
    # Schema v4 includes the public lobby mask plus visible Dark Gift/keyword
    # card features. Do not silently reinterpret a v4 model as the older v3.
    assert encoder.SCHEMA_VERSION == 4
    for tribe in encoder.LOBBY_MINION_TYPES:
        index = encoder.scalar_index(f"lobby_type_{tribe.lower()}")
        assert first.scalar_features[index] == float(tribe in game.active_minion_types)
    alternate = tuple(t for t in encoder.LOBBY_MINION_TYPES if t not in game.active_minion_types)
    second = encoder.encode(replace(observation, active_minion_types=alternate))
    assert not torch.equal(first.scalar_features, second.scalar_features)
    assert torch.equal(first.card_ids, second.card_ids)


def test_determinizations_retain_real_lobby_types_and_pool_filtering():
    game, observation = _observation()
    environment = DeterminizedBattlegroundsEnvironment()
    for seed in (11, 12):
        state = environment.sample_determinization(observation, 0, random.Random(seed))
        assert state.game.active_minion_types == game.active_minion_types
        assert state.game.pool.active_minion_types == game.active_minion_types
        assert all(is_minion_available_for_lobby(card, game.active_minion_types)
                   for card in state.game.pool.available_cards if card.get("cardType") == "minion")
