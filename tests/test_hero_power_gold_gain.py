"""Gold-gain edge cases for audited Hero Powers.

Battlegrounds permits shop-phase Gold gains above 10; 10 is the normal
start-of-turn ceiling, not a cap on Gold earned during recruitment.
"""

from pathlib import Path

from game.bob import Bob
from game.events import GameEvent
from game.hero_power_effects import register_audited_hero_power_effects


CARDS_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "cards.json"
OMU = 63604
HOGGARR = 101130


def _game(hero_id):
    game = Bob(cards_file=str(CARDS_FILE), seed=4403)
    game.create_players()
    game.phase = "recruit"
    game.round_number = 5
    player = game.get_player(0)
    player.set_hero(hero_id)
    player.gold = 10
    register_audited_hero_power_effects(game)
    return game, player


def test_omu_can_gain_gold_above_ten():
    game, player = _game(OMU)
    game.events.emit(
        GameEvent.TAVERN_UPGRADED,
        player_id=0,
        old_tier=4,
        new_tier=5,
        gold_cost=0,
    )
    assert player.gold == 12


def test_hoggarr_can_gain_gold_above_ten_after_a_pirate_purchase_event():
    game, player = _game(HOGGARR)
    pirate = next(
        card
        for card in game.pool.card_definitions
        if card.get("cardType") == "minion"
        and game.effects.is_minion_type(card, "Pirate")
    )
    game.events.emit(GameEvent.CARD_BOUGHT, player_id=0, card=pirate)
    assert player.gold == 11
