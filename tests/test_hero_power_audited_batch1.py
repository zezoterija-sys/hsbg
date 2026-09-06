"""Conformance tests for the first audited Hero Power batches."""

from pathlib import Path

from game.actions import ActionType
from game.bob import Bob
from game.effects import EffectZone, TargetRef
from game.events import GameEvent
from game.hero_power_effects import register_audited_hero_power_effects


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


def test_george_is_active_targeted_once_per_turn_and_grants_divine_shield():
    game, player, hero_powers = _game(GEORGE)
    player.board[2] = game.effects.create_card(120031)

    game.update_action_space(0)
    actions = [
        action
        for action in game.get_player_action_space(0)
        if action.action_type == ActionType.HERO_POWER
    ]
    assert len(actions) == 1
    assert actions[0].effect_target_zone == EffectZone.BOARD.value
    assert actions[0].effect_target_idx == 2

    target_ref = TargetRef(0, EffectZone.BOARD, 2, player.board[2])
    gold_before = player.gold
    game.use_hero_power(0, target_ref=target_ref)

    assert player.gold == gold_before - 1
    assert game.effects.has_keyword(player.board[2], "Divine Shield")
    assert hero_powers.uses_this_turn(0) == 1
    assert hero_powers.can_use(0) is False


def test_nozdormu_is_automatic_not_clickable_and_grants_one_free_refresh_at_turn_start():
    game, _, hero_powers = _game(NOZDORMU, round_number=3)

    assert hero_powers.can_use(0) is False
    game.update_action_space(0)
    assert not any(
        action.action_type == ActionType.HERO_POWER
        for action in game.get_player_action_space(0)
    )

    state = game.effects.get_player_state(0)
    assert int(state.get("free_refreshes", 0) or 0) == 0
    game.events.emit(GameEvent.TURN_START, player_id=0, round_number=3)
    assert state["free_refreshes"] == 1


def test_omu_is_passive_and_gains_two_gold_after_tavern_upgrade():
    game, player, hero_powers = _game(OMU, gold=4)

    assert hero_powers.can_use(0) is False
    game.events.emit(
        GameEvent.TAVERN_UPGRADED,
        player_id=0,
        old_tier=1,
        new_tier=2,
        gold_cost=5,
    )
    assert player.gold == 6


def test_hoggarr_is_passive_and_refunds_one_gold_only_after_buying_a_pirate():
    game, player, hero_powers = _game(HOGGARR, gold=4)

    assert hero_powers.can_use(0) is False

    pirate = next(
        card
        for card in game.pool.card_definitions
        if card.get("cardType") == "minion"
        and game.effects.is_minion_type(card, "Pirate")
    )
    non_pirate = next(
        card
        for card in game.pool.card_definitions
        if card.get("cardType") == "minion"
        and not game.effects.is_minion_type(card, "Pirate")
    )

    game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=non_pirate)
    assert player.gold == 4

    game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=pirate)
    assert player.gold == 5


def test_flurgl_gets_one_random_lobby_murloc_after_every_five_sales():
    game, player, hero_powers = _game(FLURGL)
    game.active_minion_types = (
        "Beast", "Dragon", "Mech", "Murloc", "Pirate"
    )
    assert hero_powers.can_use(0) is False

    sold = {"id": -50, "cardType": "minion", "minionTypes": ["Beast"]}
    for _ in range(4):
        game.events.emit(GameEvent.CARD_SOLD, player_id=0, card=sold)
    assert player.hand == []

    game.events.emit(GameEvent.CARD_SOLD, player_id=0, card=sold)
    assert len(player.hand) == 1
    assert game.effects.is_minion_type(player.hand[0], "Murloc")

    for _ in range(5):
        game.events.emit(GameEvent.CARD_SOLD, player_id=0, card=sold)
    assert len(player.hand) == 2
    assert all(game.effects.is_minion_type(card, "Murloc") for card in player.hand)


def test_kaelthas_gets_a_tavern_coin_after_each_three_minion_purchases():
    game, player, hero_powers = _game(KAELTHAS)
    assert hero_powers.can_use(0) is False

    bought = {"id": -60, "cardType": "minion", "keywords": []}
    for _ in range(2):
        game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=bought)
    assert not any(card.get("id") == TAVERN_COIN for card in player.hand)

    game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=bought)
    assert [card.get("id") for card in player.hand] == [TAVERN_COIN]

    for _ in range(3):
        game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=bought)
    assert [card.get("id") for card in player.hand] == [TAVERN_COIN, TAVERN_COIN]


def test_dinotamer_brann_rewards_after_four_battlecry_buys_only_once_per_game():
    game, player, hero_powers = _game(DINOTAMER_BRANN)
    assert hero_powers.can_use(0) is False

    battlecry = {
        "id": -70,
        "cardType": "minion",
        "keywords": ["Battlecry"],
    }
    plain = {"id": -71, "cardType": "minion", "keywords": []}

    game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=plain)
    for _ in range(3):
        game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=battlecry)
    assert not any(card.get("id") == BRANN_BRONZEBEARD for card in player.hand)

    game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=battlecry)
    assert [card.get("id") for card in player.hand].count(BRANN_BRONZEBEARD) == 1

    for _ in range(8):
        game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=battlecry)
    assert [card.get("id") for card in player.hand].count(BRANN_BRONZEBEARD) == 1
