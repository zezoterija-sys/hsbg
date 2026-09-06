"""Search copies must own every stateful global effect callback."""

from copy import deepcopy

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
