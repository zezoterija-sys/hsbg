"""Regression coverage for the live Season 14 Dark Gift effect layer."""

from pathlib import Path

from game.bob import Bob
from game.dark_gift_effects import (
    ALL_DARK_GIFT_IDS,
    DEXTERITY_EARLY,
    FORTITUDE,
    GILDING,
    HARPYS_TALONS,
    INCUBATION,
    SHARPENED_SWORD,
    STEADY_GROWTH,
    TOXICITY,
    attach_dark_gift,
)
from game.dark_gifts import DARK_GIFT_TURN_WINDOWS
from game.events import GameEvent


CARDS_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "cards.json"


def _game():
    game = Bob(cards_file=str(CARDS_FILE), seed=777)
    game.create_players()
    game.phase = "recruit"
    game.round_number = 3
    return game


def _host(**updates):
    card = {
        "id": 900001,
        "name": "Gift Test Minion",
        "cardType": "minion",
        "attack": 10,
        "health": 10,
        "attackGold": 20,
        "healthGold": 20,
        "text": "",
        "textGold": "Golden text",
        "tier": 3,
        "minionType": "Murloc",
        "minionTypes": ["Murloc"],
        "keywords": [],
    }
    card.update(updates)
    return card


def _gift(game, gift_id):
    definition = game.pool.card_definitions_by_id[gift_id]
    return dict(definition)


def test_all_43_live_dark_gift_identities_are_accounted_for():
    game = _game()
    raw_ids = {
        int(card["id"])
        for card in game.pool.card_definitions
        if card.get("cardType") == "spell"
        and "darkgift" in (card.get("categories") or ())
        and card.get("pool") is True
    }

    assert len(ALL_DARK_GIFT_IDS) == 43
    assert raw_ids == ALL_DARK_GIFT_IDS
    assert set(DARK_GIFT_TURN_WINDOWS) == ALL_DARK_GIFT_IDS


def test_immediate_stat_and_keyword_gifts_apply_to_the_physical_minion():
    game = _game()

    fortitude = _host()
    attach_dark_gift(game.effects, 0, fortitude, _gift(game, FORTITUDE), acquired_turn=3)
    assert (fortitude["attack"], fortitude["health"]) == (15, 15)

    talons = _host()
    attach_dark_gift(game.effects, 0, talons, _gift(game, HARPYS_TALONS), acquired_turn=3)
    assert game.effects.has_keyword(talons, "Divine Shield")
    assert game.effects.has_keyword(talons, "Windfury")

    toxicity = _host()
    attach_dark_gift(game.effects, 0, toxicity, _gift(game, TOXICITY), acquired_turn=9)
    assert game.effects.has_keyword(toxicity, "Venomous")


def test_gilding_uses_the_minions_real_golden_definition_values():
    game = _game()
    host = _host()

    attach_dark_gift(game.effects, 0, host, _gift(game, GILDING), acquired_turn=4)

    assert host["isGolden"] is True
    assert host["attack"] == 20
    assert host["health"] == 20
    assert host["text"] == "Golden text"
    assert host["_dark_gift_no_triple_reward"] is True


def test_card_play_scalers_are_attachment_effects_not_special_bob_rules():
    game = _game()
    player = game.get_player(0)

    sword = _host()
    attach_dark_gift(game.effects, 0, sword, _gift(game, SHARPENED_SWORD), acquired_turn=3)
    player.board[0] = sword

    game.events.emit(GameEvent.CARD_PLAYED, player_id=0, card={"id": 1})
    assert sword["attack"] == 13
    assert sword["health"] == 10

    dexterity = _host(id=900002)
    attach_dark_gift(game.effects, 0, dexterity, _gift(game, DEXTERITY_EARLY), acquired_turn=7)
    player.board[1] = dexterity

    game.events.emit(GameEvent.CARD_PLAYED, player_id=0, card={"id": 2})
    assert dexterity["attack"] == 12
    assert dexterity["health"] == 12


def test_steady_growth_uses_final_36_2_2_turn_values():
    game = _game()
    player = game.get_player(0)

    expected = {
        3: (2, 2),
        4: (2, 3),
        5: (3, 4),
    }
    for index, (turn, amount) in enumerate(expected.items()):
        host = _host(id=900010 + index)
        attach_dark_gift(game.effects, 0, host, _gift(game, STEADY_GROWTH), acquired_turn=turn)
        player.board[index] = host
        before = (host["attack"], host["health"])
        game.events.emit(GameEvent.TURN_END, player_id=0, round_number=turn)
        assert host["attack"] - before[0] == amount[0]
        assert host["health"] - before[1] == amount[1]
        player.board[index] = None


def test_incubation_doubles_at_start_of_the_second_later_turn():
    game = _game()
    player = game.get_player(0)
    host = _host()
    attach_dark_gift(game.effects, 0, host, _gift(game, INCUBATION), acquired_turn=6)
    player.board[0] = host

    assert (host["attack"], host["health"]) == (14, 14)

    game.round_number = 7
    game.events.emit(GameEvent.TURN_START, player_id=0, round_number=7)
    assert (host["attack"], host["health"]) == (14, 14)

    game.round_number = 8
    game.events.emit(GameEvent.TURN_START, player_id=0, round_number=8)
    assert (host["attack"], host["health"]) == (28, 28)

    game.events.emit(GameEvent.TURN_START, player_id=0, round_number=8)
    assert (host["attack"], host["health"]) == (28, 28)
