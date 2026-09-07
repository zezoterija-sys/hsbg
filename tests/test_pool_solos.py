import json
import random

from game.pool import CardPool


def _card(card_id, name, *, solos_only=False, duos_only=False):
    return {
        "id": card_id,
        "name": name,
        "cardType": "minion",
        "tier": 1,
        "pool": True,
        "categories": ["tavern"],
        "isSolosOnly": solos_only,
        "isDuosOnly": duos_only,
    }


def _write_cards(tmp_path):
    path = tmp_path / "cards.json"
    path.write_text(
        json.dumps(
            [
                _card(1, "Normal"),
                _card(2, "Solos", solos_only=True),
                _card(3, "Duos", duos_only=True),
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_solos_only_cards_are_included_and_duos_only_are_excluded(tmp_path):
    pool = CardPool(_write_cards(tmp_path), rng=random.Random(7))

    names = {card["name"] for card in pool.available_cards}

    assert "Normal" in names
    assert "Solos" in names
    assert "Duos" not in names


def test_injected_rng_makes_pool_draws_reproducible(tmp_path):
    path = _write_cards(tmp_path)

    first = CardPool(path, rng=random.Random(99))
    second = CardPool(path, rng=random.Random(99))

    first_draws = [first.get_random_minion(tier=1)["id"] for _ in range(10)]
    second_draws = [second.get_random_minion(tier=1)["id"] for _ in range(10)]

    assert first_draws == second_draws
