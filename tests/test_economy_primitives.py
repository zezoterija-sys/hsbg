"""Conformance tests for Battlegrounds Gold/max-Gold mechanics."""

from pathlib import Path

from game.actions import ActionType
from game.bob import Bob
from game.combat import CombatResult
from game.economy import normal_turn_gold
from game.economy_effects import register_economy_effects
from game.events import GameEvent
from game.hero_power_effects import register_audited_hero_power_effects


CARDS_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "cards.json"

CAREFUL_INVESTMENT = 103779
STRIKE_OIL = 104029
TAVERN_COIN = 104436
OVERCONFIDENCE = 105267
PRIVATE_INVESTIGATOR = 132318
GALLYWIX = 57891
CENARIUS = 116920


def _game(*, round_number=8):
    game = Bob(cards_file=str(CARDS_FILE), seed=5501)
    game.create_players()
    game.phase = "recruit"
    game.round_number = round_number
    game.priority_order = list(range(8))
    register_economy_effects(game)
    return game


def _cast_generated_spell(game, player_id, card_id):
    player = game.get_player(player_id)
    player.hand.append(game.effects.create_card(card_id))
    game.cast_spell(player_id, len(player.hand) - 1)


def test_normal_turn_gold_uses_mutable_player_maximum():
    assert normal_turn_gold(1, 10) == 3
    assert normal_turn_gold(8, 10) == 10
    assert normal_turn_gold(9, 10) == 10
    assert normal_turn_gold(9, 11) == 11
    assert normal_turn_gold(10, 12) == 12


def test_immediate_gold_gain_can_exceed_max_gold():
    game = _game()
    player = game.get_player(0)
    player.max_gold = 10
    player.gold = 10

    game.effects.add_gold(0, 3)

    assert player.gold == 13
    assert player.max_gold == 10


def test_tavern_coin_gains_gold_without_changing_max_gold():
    game = _game()
    player = game.get_player(0)
    player.gold = 10
    player.max_gold = 10

    _cast_generated_spell(game, 0, TAVERN_COIN)

    assert player.gold == 11
    assert player.max_gold == 10


def test_careful_investment_queues_two_gold_for_next_turn_only():
    game = _game(round_number=8)
    player = game.get_player(0)
    player.gold = 7
    player.max_gold = 10

    _cast_generated_spell(game, 0, CAREFUL_INVESTMENT)

    state = game.effects.get_player_state(0)
    assert player.gold == 7
    assert player.max_gold == 10
    assert state["pending_gold_next_turn"] == 2

    # A normal new-turn reset happens before the queued gain resolves.
    player.set_gold(10)
    game.events.emit(GameEvent.TURN_START, player_id=0, round_number=9)
    assert player.gold == 12
    assert player.max_gold == 10


def test_strike_oil_increases_max_gold_but_not_current_gold():
    game = _game(round_number=8)
    player = game.get_player(0)
    player.gold = 7
    player.max_gold = 10

    _cast_generated_spell(game, 0, STRIKE_OIL)

    assert player.gold == 7
    assert player.max_gold == 11
    assert game.recruitment.calculate_gold(player) == 10

    game.round_number = 9
    assert game.recruitment.calculate_gold(player) == 11


def test_legacy_pending_gold_next_turn_resolves_uncapped_before_old_listener():
    game = _game(round_number=8)
    player = game.get_player(0)
    player.gold = 10
    player.max_gold = 10
    state = game.effects.get_player_state(0)
    state["pending_gold_next_turn"] = 2

    game.events.emit(GameEvent.TURN_START, player_id=0, round_number=8)

    assert player.gold == 12
    assert "pending_gold_next_turn" not in state


def test_private_investigator_current_patch_queues_two_gold_next_turn():
    game = _game(round_number=8)
    player = game.get_player(0)
    player.gold = 5
    player.board[0] = game.effects.create_card(PRIVATE_INVESTIGATOR)

    game.effects.resolve_activate(0, 0)

    state = game.effects.get_player_state(0)
    assert player.gold == 4
    assert state["pending_gold_next_turn"] == 2

    # Simulate the next recruit reset first, then TURN_START payout.
    player.set_gold(10)
    game.events.emit(GameEvent.TURN_START, player_id=0, round_number=9)
    assert player.gold == 12


def test_overconfidence_win_queues_three_gold_for_next_turn():
    game = _game(round_number=8)
    player = game.get_player(0)
    _cast_generated_spell(game, 0, OVERCONFIDENCE)

    result = CombatResult(
        player_a_id=0,
        player_b_id=1,
        winner_id=0,
        loser_id=1,
        tie=False,
        damage_to_a=0,
        damage_to_b=5,
        surviving_a=[],
        surviving_b=[],
        attacks=1,
    )
    game.events.emit(GameEvent.COMBAT_END, result=result)

    state = game.effects.get_player_state(0)
    assert state["pending_gold_next_turn"] == 3

    player.set_gold(10)
    game.events.emit(GameEvent.TURN_START, player_id=0, round_number=9)
    assert player.gold == 13


def test_overconfidence_tie_queues_one_and_loss_queues_nothing():
    tie_game = _game()
    _cast_generated_spell(tie_game, 0, OVERCONFIDENCE)
    tie_result = CombatResult(
        player_a_id=0,
        player_b_id=1,
        winner_id=None,
        loser_id=None,
        tie=True,
        damage_to_a=0,
        damage_to_b=0,
        surviving_a=[],
        surviving_b=[],
        attacks=1,
    )
    tie_game.events.emit(GameEvent.COMBAT_END, result=tie_result)
    assert tie_game.effects.get_player_state(0)["pending_gold_next_turn"] == 1

    loss_game = _game()
    _cast_generated_spell(loss_game, 0, OVERCONFIDENCE)
    loss_result = CombatResult(
        player_a_id=0,
        player_b_id=1,
        winner_id=1,
        loser_id=0,
        tie=False,
        damage_to_a=5,
        damage_to_b=0,
        surviving_a=[],
        surviving_b=[],
        attacks=1,
    )
    loss_game.events.emit(GameEvent.COMBAT_END, result=loss_result)
    assert "pending_gold_next_turn" not in loss_game.effects.get_player_state(0)
    assert "overconfidence_pending" not in loss_game.effects.get_player_state(0)


def test_gallywix_is_passive_and_each_sale_banks_gold_for_next_turn():
    game = _game(round_number=8)
    player = game.get_player(0)
    player.set_hero(GALLYWIX)
    hero_powers = register_audited_hero_power_effects(game)

    assert hero_powers.can_use(0) is False
    game.update_action_space(0)
    assert not any(
        action.action_type == ActionType.HERO_POWER
        for action in game.get_player_action_space(0)
    )

    game.events.emit(GameEvent.CARD_SOLD, player_id=0, card={"cardType": "minion"})
    game.events.emit(GameEvent.CARD_SOLD, player_id=0, card={"cardType": "minion"})
    state = game.effects.get_player_state(0)
    assert state["pending_gold_next_turn"] == 2

    player.set_gold(10)
    game.events.emit(GameEvent.TURN_START, player_id=0, round_number=9)
    assert player.gold == 12


def test_cenarius_costs_three_increases_max_gold_once_per_turn():
    game = _game(round_number=8)
    player = game.get_player(0)
    player.set_hero(CENARIUS)
    player.gold = 6
    player.set_ap(20)
    hero_powers = register_audited_hero_power_effects(game)

    game.update_action_space(0)
    actions = [
        action
        for action in game.get_player_action_space(0)
        if action.action_type == ActionType.HERO_POWER
    ]
    assert len(actions) == 1

    game.use_hero_power(0)
    assert player.gold == 3
    assert player.max_gold == 11
    assert hero_powers.can_use(0) is False

    game.update_action_space(0)
    assert not any(
        action.action_type == ActionType.HERO_POWER
        for action in game.get_player_action_space(0)
    )

    game.round_number = 9
    assert hero_powers.can_use(0) is True
