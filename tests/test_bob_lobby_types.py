from pathlib import Path

from game.bob import Bob
from game.lobby import LOBBY_MINION_TYPE_COUNT, card_minion_types


CARDS_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "cards.json"


def test_seeded_bob_rolls_same_five_public_minion_types():
    first = Bob(cards_file=str(CARDS_FILE), seed=24680)
    second = Bob(cards_file=str(CARDS_FILE), seed=24680)

    first.initialize_game()
    second.initialize_game()

    assert first.active_minion_types == second.active_minion_types
    assert len(first.active_minion_types) == LOBBY_MINION_TYPE_COUNT
    assert first.pool.active_minion_types == first.active_minion_types
    assert first.get_state()["active_minion_types"] == first.active_minion_types


def test_real_bob_pool_contains_no_banned_single_or_dual_type_minions():
    game = Bob(cards_file=str(CARDS_FILE), seed=777)
    game.initialize_game()

    active = set(game.active_minion_types)

    for card in game.pool.available_cards:
        if card.get("cardType") != "minion":
            continue

        printed = set(card_minion_types(card))
        if not printed or "All" in printed:
            continue

        assert printed & active, (
            f"{card.get('name')} with types {sorted(printed)} appeared in "
            f"lobby {sorted(active)}"
        )
