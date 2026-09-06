"""Conformance tests for the currently audited Hero Power content.

These tests lock both the printed live definitions and the runtime behavior that
matters to game play: legal-action lifecycle, ownership, real Bob economy paths,
counters across turns, and once-per-game handling.
"""

from pathlib import Path

import pytest

from game.actions import ActionType
from game.bob import Bob
from game.effects import EffectZone, TargetRef
from game.events import GameEvent
from game.hero_power_effects import register_audited_hero_power_effects
from game.heroes import HEROES


CARDS_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "cards.json"

GEORGE = 57929
FLURGL = 60372
NOZDORMU = 61489
KAELTHAS = 61912
DINOTAMER_BRANN = 60214
OMU = 63604
HOGGARR = 101130

BRANN_BRONZEBEARD = 96786
TAVERN_COIN = 104436

EXPECTED_AUDITED_POWERS = {
    GEORGE: (
        57562,
        "Boon of Light",
        1,
        "Give a minion <b>Divine Shield</b>.",
    ),
    FLURGL: (
        60448,
        "Gone Fishing",
        0,
        "After you sell 5 minions, get a random Murloc. <i>(5 left!)</i>",
    ),
    NOZDORMU: (
        61491,
        "Clairvoyance",
        0,
        "At the start of your turn, gain a free <b>Refresh</b>.",
    ),
    KAELTHAS: (
        61917,
        "Verdant Spheres",
        0,
        "After you buy 3 minions, get a Tavern Coin.",
    ),
    DINOTAMER_BRANN: (
        60218,
        "Battle Brand",
        0,
        "After you buy 4 <b>Battlecry</b> minions, get a Brann Bronzebeard. <i>(Once per game.)</i>",
    ),
    OMU: (
        63605,
        "Everbloom",
        0,
        "After you upgrade the Tavern, gain 2 Gold.",
    ),
    HOGGARR: (
        101132,
        "I'm the Cap'n Now",
        0,
        "After you buy a Pirate, gain 1 Gold.",
    ),
}


def _game(hero_id, *, round_number=5, gold=10):
    game = Bob(cards_file=str(CARDS_FILE), seed=4401)
    game.create_players()
    game.phase = "recruit"
    game.round_number = round_number
    game.priority_order = list(range(8))
    player = game.get_player(0)
    player.set_hero(hero_id)
    player.set_gold(gold)
    player.set_ap(20)
    hero_powers = register_audited_hero_power_effects(game)
    return game, player, hero_powers


def _hero_power_actions(game, player_id=0):
    game.update_action_space(player_id)
    return [
        action
        for action in game.get_player_action_space(player_id)
        if action.action_type == ActionType.HERO_POWER
    ]


def _definition_minion(game, *, minion_type=None, keyword=None):
    return next(
        card
        for card in game.pool.card_definitions
        if card.get("cardType") == "minion"
        and (minion_type is None or game.effects.is_minion_type(card, minion_type))
        and (keyword is None or game.effects.has_keyword(card, keyword))
    )


def test_audited_live_hero_power_definitions_are_locked():
    for hero_id, (power_id, name, cost, text) in EXPECTED_AUDITED_POWERS.items():
        power = HEROES[hero_id]["power"]
        assert power["id"] == power_id
        assert power["name"] == name
        assert int(power["cost"]) == cost
        assert power["text"] == text


def test_george_is_targeted_costs_one_and_is_legal_only_once_per_turn():
    game, player, hero_powers = _game(GEORGE, round_number=5, gold=2)
    player.board[2] = game.effects.create_card(120031)
    player.board[4] = game.effects.create_card(120031)
    game.get_player(1).board[0] = game.effects.create_card(120031)

    actions = _hero_power_actions(game)
    assert len(actions) == 2
    assert {(a.effect_target_player_id, a.effect_target_zone, a.effect_target_idx)
            for a in actions} == {
                (0, EffectZone.BOARD.value, 2),
                (0, EffectZone.BOARD.value, 4),
            }

    target_ref = TargetRef(0, EffectZone.BOARD, 2, player.board[2])
    game.use_hero_power(0, target_ref=target_ref)

    assert player.gold == 1
    assert game.effects.has_keyword(player.board[2], "Divine Shield")
    assert hero_powers.uses_this_turn(0) == 1
    assert hero_powers.can_use(0) is False
    assert _hero_power_actions(game) == []

    # The default active-power use limit is per recruit turn, not per game.
    game.round_number = 6
    assert hero_powers.uses_this_turn(0) == 0
    assert hero_powers.can_use(0) is True
    assert len(_hero_power_actions(game)) == 2


def test_george_requires_gold_and_a_friendly_board_target():
    game, player, hero_powers = _game(GEORGE, gold=0)
    player.board[0] = game.effects.create_card(120031)
    assert hero_powers.can_use(0) is False
    assert _hero_power_actions(game) == []

    player.gold = 1
    player.board = [None] * len(player.board)
    assert hero_powers.can_use(0) is True
    # Lifecycle is usable, but no legal target means no actionable Hero Power.
    assert _hero_power_actions(game) == []


def test_passive_and_automatic_audited_powers_are_never_clickable():
    for hero_id in (FLURGL, NOZDORMU, KAELTHAS, DINOTAMER_BRANN, OMU, HOGGARR):
        game, _, hero_powers = _game(hero_id)
        assert hero_powers.can_use(0) is False
        assert _hero_power_actions(game) == []


def test_nozdormu_grants_exactly_one_free_refresh_and_real_refresh_consumes_it():
    game, player, hero_powers = _game(NOZDORMU, round_number=3, gold=0)
    assert hero_powers.can_use(0) is False

    state = game.effects.get_player_state(0)
    assert int(state.get("free_refreshes", 0) or 0) == 0
    game.events.emit(GameEvent.TURN_START, player_id=0, round_number=3)
    assert state["free_refreshes"] == 1

    game.refresh(0)
    assert player.gold == 0
    assert state["free_refreshes"] == 0

    with pytest.raises(ValueError):
        game.refresh(0)


def test_omu_real_upgrade_spends_cost_then_refunds_two_gold():
    game, player, hero_powers = _game(OMU, gold=10)
    assert hero_powers.can_use(0) is False
    assert player.tavern_tier == 1

    game.upgrade_tavern(0)

    assert player.tavern_tier == 2
    assert player.gold == 7  # 10 - 5 upgrade + 2 Everbloom


def test_hoggarr_real_pirate_purchase_refunds_one_gold_and_other_buys_do_not():
    game, player, hero_powers = _game(HOGGARR, gold=7)
    assert hero_powers.can_use(0) is False

    pirate = _definition_minion(game, minion_type="Pirate")
    non_pirate = next(
        card
        for card in game.pool.card_definitions
        if card.get("cardType") == "minion"
        and not game.effects.is_minion_type(card, "Pirate")
    )

    player.tavern.slots[0] = game.effects.create_card(non_pirate["id"], generated=False)
    game.buy_minion(0, 0)
    assert player.gold == 4

    player.tavern.slots[0] = game.effects.create_card(pirate["id"], generated=False)
    game.buy_minion(0, 0)
    assert player.gold == 2  # 4 - 3 + 1 from I'm the Cap'n Now


def test_hoggarr_only_reacts_to_its_own_players_purchase():
    game, player, _ = _game(HOGGARR, gold=4)
    pirate = _definition_minion(game, minion_type="Pirate")

    game.events.emit(GameEvent.CARD_BOUGHT, player_id=1, card=pirate)
    assert player.gold == 4

    game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=pirate)
    assert player.gold == 5


def test_flurgl_counter_persists_across_turns_and_repeats_every_five_sales():
    game, player, hero_powers = _game(FLURGL, gold=0)
    game.active_minion_types = (
        "Beast", "Dragon", "Mech", "Murloc", "Pirate"
    )
    assert hero_powers.can_use(0) is False

    sold_id = _definition_minion(game, minion_type="Beast")["id"]
    for _ in range(4):
        player.board[0] = game.effects.create_card(sold_id)
        game.sell_minion(0, 0)
    assert player.hand == []

    game.round_number += 1
    player.board[0] = game.effects.create_card(sold_id)
    game.sell_minion(0, 0)
    assert len(player.hand) == 1
    assert game.effects.is_minion_type(player.hand[0], "Murloc")

    for _ in range(5):
        player.board[0] = game.effects.create_card(sold_id)
        game.sell_minion(0, 0)
    assert len(player.hand) == 2
    assert all(game.effects.is_minion_type(card, "Murloc") for card in player.hand)


def test_kaelthas_counts_only_minion_buys_across_turns_and_repeats_every_three():
    game, player, hero_powers = _game(KAELTHAS, gold=10)
    assert hero_powers.can_use(0) is False

    minion_id = _definition_minion(game)["id"]
    for _ in range(2):
        player.tavern.slots[0] = game.effects.create_card(minion_id, generated=False)
        game.buy_minion(0, 0)
    assert not any(card.get("id") == TAVERN_COIN for card in player.hand)

    # Counter is not a once-per-turn counter.
    game.round_number += 1
    player.tavern.slots[0] = game.effects.create_card(minion_id, generated=False)
    game.buy_minion(0, 0)
    assert [card.get("id") for card in player.hand].count(TAVERN_COIN) == 1

    # A spell purchase event must not advance Verdant Spheres.
    state = game.effects.get_player_state(0)
    assert state["hero_kaelthas_minion_buys"] == 0
    game.events.emit(
        GameEvent.CARD_BOUGHT,
        player_id=0,
        card={"id": -99, "cardType": "spell", "keywords": []},
    )
    assert state["hero_kaelthas_minion_buys"] == 0


def test_dinotamer_brann_counts_battlecry_buys_across_turns_and_rewards_once_per_game():
    game, player, hero_powers = _game(DINOTAMER_BRANN)
    assert hero_powers.can_use(0) is False

    battlecry = {
        "id": -70,
        "cardType": "minion",
        "keywords": ["Battlecry"],
    }
    plain = {"id": -71, "cardType": "minion", "keywords": []}

    game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=plain)
    for _ in range(2):
        game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=battlecry)
    assert not any(card.get("id") == BRANN_BRONZEBEARD for card in player.hand)

    game.round_number += 1
    game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=battlecry)
    assert not any(card.get("id") == BRANN_BRONZEBEARD for card in player.hand)

    game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=battlecry)
    assert [card.get("id") for card in player.hand].count(BRANN_BRONZEBEARD) == 1

    for _ in range(8):
        game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=battlecry)
    assert [card.get("id") for card in player.hand].count(BRANN_BRONZEBEARD) == 1
