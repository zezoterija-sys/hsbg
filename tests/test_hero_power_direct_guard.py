"""Defense-in-depth tests for direct Bob.use_hero_power calls."""

from pathlib import Path

import pytest

from game.bob import Bob
from game.effects import EffectZone
from game.hero_power_effects import register_audited_hero_power_effects


CARDS_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "cards.json"
GEORGE = 57929
GALLYWIX = 57891
CENARIUS = 116920


def _game(hero_id, *, gold=10, round_number=5):
    game = Bob(cards_file=str(CARDS_FILE), seed=5520)
    game.create_players()
    game.phase = "recruit"
    game.round_number = round_number
    game.priority_order = list(range(8))
    player = game.get_player(0)
    player.set_hero(hero_id)
    player.gold = gold
    player.set_ap(20)
    hero_powers = register_audited_hero_power_effects(game)
    return game, player, hero_powers


def _plain_minion(game):
    definition = next(
        card
        for card in game.pool.card_definitions
        if card.get("cardType") == "minion"
    )
    return game.effects.create_card(definition["id"])


def test_george_direct_api_cannot_bypass_once_per_turn_limit():
    game, player, hero_powers = _game(GEORGE, gold=3)
    player.board[0] = _plain_minion(game)
    target = game.effects.resolve_target_ref(0, EffectZone.BOARD, 0)

    game.use_hero_power(0, target_ref=target)

    assert player.gold == 2
    assert hero_powers.uses_this_turn(0) == 1
    assert game.effects.has_keyword(player.board[0], "Divine Shield")

    with pytest.raises(ValueError, match="not currently usable"):
        game.use_hero_power(0, target_ref=target)

    assert player.gold == 2
    assert hero_powers.uses_this_turn(0) == 1


def test_george_direct_api_rejects_enemy_target_before_spending_gold():
    game, player, hero_powers = _game(GEORGE, gold=3)
    game.get_player(1).board[0] = _plain_minion(game)
    enemy_target = game.effects.resolve_target_ref(1, EffectZone.BOARD, 0)

    with pytest.raises(ValueError, match="legal target"):
        game.use_hero_power(0, target_ref=enemy_target)

    assert player.gold == 3
    assert hero_powers.uses_this_turn(0) == 0


def test_cenarius_direct_api_increases_max_gold_only_once_per_turn():
    game, player, hero_powers = _game(CENARIUS, gold=7, round_number=8)
    assert player.max_gold == 10

    game.use_hero_power(0)

    assert player.gold == 4
    assert player.max_gold == 11
    assert hero_powers.uses_this_turn(0) == 1

    with pytest.raises(ValueError, match="not currently usable"):
        game.use_hero_power(0)

    assert player.gold == 4
    assert player.max_gold == 11

    game.round_number = 9
    game.use_hero_power(0)
    assert player.gold == 1
    assert player.max_gold == 12
    assert hero_powers.uses_this_turn(0) == 1


def test_passive_gallywix_cannot_be_invoked_through_direct_api():
    game, player, hero_powers = _game(GALLYWIX, gold=10)

    assert hero_powers.can_use(0) is False
    with pytest.raises(ValueError, match="not currently usable"):
        game.use_hero_power(0)

    assert player.gold == 10
    assert hero_powers.uses_this_game(0) == 0
