"""Search copies must own every stateful global effect callback."""

from copy import deepcopy
import random
from types import SimpleNamespace

import pytest

from agents.simulation_environment import DeterminizedBattlegroundsEnvironment
from game.bob import Bob
from game.dark_gift_effects import DEMONOLOGY, attach_dark_gift
from game.events import GameEvent


def test_spell_events_in_sibling_copies_do_not_mutate_the_template():
    source = Bob(seed=7)
    source.create_players()
    first, second = deepcopy(source), deepcopy(source)
    for game, count in ((first, 2), (second, 1)):
        for _ in range(count):
            game.events.emit(GameEvent.SPELL_CAST, player_id=0,
                             spell={"id": 104436, "categories": ["tavern"]})
    assert source.effects.get_player_state(0).get("spells_cast_game", 0) == 0
    assert first.effects.get_player_state(0)["spells_cast_game"] == 2
    assert second.effects.get_player_state(0)["spells_cast_game"] == 1
    assert first.effects.game is first
    assert first.effects.random is first.random is first.pool.random


def test_lazily_registered_dark_gift_hooks_follow_the_copied_game():
    source = Bob(seed=9)
    source.create_players()
    host = source.effects.create_card(120031)
    attach_dark_gift(source.effects, 0, host,
                     source.pool.card_definitions_by_id[DEMONOLOGY], acquired_turn=5)
    source.get_player(0).board[0] = host
    source.effects.get_player_state(0)["dark_gift_fodder_refreshes"] = 3
    copied = deepcopy(source)
    before = len(source.get_player(0).tavern.slots)
    copied.events.emit(GameEvent.TAVERN_REFRESHED, player_id=0)
    assert len(source.get_player(0).tavern.slots) == before
    assert len(copied.get_player(0).tavern.slots) == before + 1
    assert source.effects.get_player_state(0)["dark_gift_fodder_refreshes"] == 3
    assert copied.effects.get_player_state(0)["dark_gift_fodder_refreshes"] == 2


def test_copied_scheduler_queries_its_own_pending_choices():
    source = Bob(seed=12)
    source.create_players()
    copied = deepcopy(source)
    copied.effects.start_choice(0, copied.dark_gifts.RESOLVER_KEY, [1])
    assert copied.scheduler.has_pending_choice(0)
    assert not source.scheduler.has_pending_choice(0)


def test_seeded_bob_repeats_initial_lobby_and_first_shops():
    first = Bob(seed=424242)
    second = Bob(seed=424242)
    for game in (first, second):
        game.initialize_game()
    assert first.active_minion_types == second.active_minion_types
    assert first.priority_order == second.priority_order
    assert [p.hero_choices for p in first.players] == [p.hero_choices for p in second.players]
    for game in (first, second):
        for player in game.players:
            game.choose_hero(player.player_id, player.hero_choices[0])
    assert [p.tavern.slots for p in first.players] == [p.tavern.slots for p in second.players]
    assert [p.tavern.spell for p in first.players] == [p.tavern.spell for p in second.players]
    assert first.pool.available_cards == second.pool.available_cards
    assert first.random.getstate() == second.random.getstate()


def test_determinized_world_rng_is_repeatable_diverse_and_copy_isolated():
    source = Bob(seed=9)
    source.create_players()
    before = source.random.getstate()
    first, second, different = (deepcopy(source) for _ in range(3))
    for game, seed in ((first, 777), (second, 777), (different, 778)):
        DeterminizedBattlegroundsEnvironment._seed_world_rngs(game, random.Random(seed))
        assert game.random is game.pool.random is game.effects.random
        assert game.random is game.combat.random is game.combat.engine.random
    assert first.random.getstate() == second.random.getstate()
    assert first.random.getstate() != different.random.getstate()
    first.random.random()
    assert first.random.getstate() != second.random.getstate()
    assert source.random.getstate() == before


@pytest.mark.parametrize("shared", [True, False])
def test_each_distinct_world_rng_is_seeded_once(shared):
    generators = [random.Random(i) for i in range(5)]
    if shared:
        generators = [generators[0]] * 5
    game_rng, pool_rng, effects_rng, combat_rng, engine_rng = generators
    game = SimpleNamespace(
        random=game_rng,
        pool=SimpleNamespace(random=pool_rng),
        effects=SimpleNamespace(random=effects_rng),
        combat=SimpleNamespace(random=combat_rng, engine=SimpleNamespace(random=engine_rng)),
    )
    search_rng = random.Random(777)
    expected = random.Random(777)
    global_before = random.getstate()
    DeterminizedBattlegroundsEnvironment._seed_world_rngs(game, search_rng)
    distinct = [game_rng] if shared else generators
    for generator in distinct:
        assert generator.getstate() == random.Random(expected.getrandbits(64)).getstate()
    assert search_rng.getstate() == expected.getstate()
    assert random.getstate() == global_before


def test_world_rng_seeding_tolerates_missing_optional_components():
    game = SimpleNamespace(random=random.Random(0))
    DeterminizedBattlegroundsEnvironment._seed_world_rngs(game, random.Random(777))
    expected = random.Random(random.Random(777).getrandbits(64))
    assert game.random.getstate() == expected.getstate()
