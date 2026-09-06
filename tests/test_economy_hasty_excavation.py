"""Conformance tests for Hasty Excavation's Health-paid Tavern purchase."""

from pathlib import Path

import pytest

from game.actions import ActionType
from game.bob import Bob
from game.economy import HASTY_EXCAVATION
from game.economy_effects import register_economy_effects


CARDS_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "cards.json"
SOUL_REWINDER = 100949


def _game(*, health=30, armor=0, gold=0):
    game = Bob(cards_file=str(CARDS_FILE), seed=5510)
    game.create_players()
    game.phase = "recruit"
    game.round_number = 5
    game.priority_order = list(range(8))
    player = game.get_player(0)
    player.health = health
    player.armor = armor
    player.gold = gold
    player.set_ap(20)
    register_economy_effects(game)
    player.tavern.spell = game.effects.create_card(HASTY_EXCAVATION, generated=False)
    return game, player


def _has_buy_spell_action(game):
    game.update_action_space(0)
    return any(
        action.action_type == ActionType.BUY_SPELL
        for action in game.get_player_action_space(0)
    )


def test_hasty_excavation_is_buyable_with_health_even_without_gold():
    game, player = _game(health=4, armor=7, gold=0)

    assert _has_buy_spell_action(game) is True
    game.buy_spell(0)

    assert player.gold == 0
    assert player.health == 1
    assert player.armor == 7
    assert player.tavern.spell is None
    assert len(player.hand) == 1
    assert player.hand[0]["id"] == HASTY_EXCAVATION


def test_hasty_excavation_cannot_be_bought_if_health_cost_would_be_lethal():
    game, player = _game(health=3, gold=20)

    assert _has_buy_spell_action(game) is False
    with pytest.raises(ValueError, match="Health"):
        game.buy_spell(0)

    assert player.health == 3
    assert player.gold == 20
    assert player.tavern.spell["id"] == HASTY_EXCAVATION


def test_casting_hasty_excavation_gains_current_gold_not_max_gold():
    game, player = _game(health=10, gold=0)
    player.max_gold = 10

    game.buy_spell(0)
    assert player.health == 7
    assert player.gold == 0

    game.cast_spell(0, 0)

    assert player.gold == 1
    assert player.max_gold == 10
    assert player.hand == []


def test_hasty_health_payment_emits_damage_that_soul_rewinder_can_rewind():
    game, player = _game(health=10, armor=5, gold=0)
    player.board[0] = game.effects.create_card(SOUL_REWINDER)
    rewinder_health_before = player.board[0]["health"]

    game.buy_spell(0)

    # The purchase costs Health, not Armor, and the current Soul Rewinder
    # handler rewinds that hero damage while receiving its own +2 Health buff.
    assert player.health == 10
    assert player.armor == 5
    assert player.board[0]["health"] == rewinder_health_before + 2


def test_reconstructed_recruit_world_installs_economy_rules_from_action_generation():
    """Search/template Bobs must not need Recruitment.start() for economy rules."""

    game = Bob(cards_file=str(CARDS_FILE), seed=5511)
    game.create_players()
    game.phase = "recruit"
    game.round_number = 5
    game.priority_order = list(range(8))

    player = game.get_player(0)
    player.health = 6
    player.armor = 4
    player.gold = 0
    player.set_ap(20)
    player.tavern.spell = game.effects.create_card(HASTY_EXCAVATION, generated=False)

    # No explicit register_economy_effects(game) call: ActionSpace is the first
    # normal entry point in a reconstructed search world and must install the
    # same idempotent economy rules used by the real Recruitment phase.
    assert not callable(getattr(game.effects, "can_pay_tavern_spell", None))
    assert _has_buy_spell_action(game) is True
    assert callable(getattr(game.effects, "can_pay_tavern_spell", None))

    game.buy_spell(0)
    assert player.gold == 0
    assert player.health == 3
    assert player.armor == 4
    assert player.hand[0]["id"] == HASTY_EXCAVATION
