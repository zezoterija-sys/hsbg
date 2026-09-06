"""Generation/discover definitions use Solos availability, not Duos rules."""

from types import SimpleNamespace

import pytest

from game.card_effects import _normal_tavern_minion_definitions, _tavern_spell_definitions
from game.tier36_effects import _definitions


@pytest.mark.parametrize("kind,helper", [
    ("minion", _normal_tavern_minion_definitions),
    ("spell", _tavern_spell_definitions),
    ("minion", _definitions),
    ("spell", lambda system: _definitions(system, card_type="spell")),
])
def test_solos_helpers_include_solos_only_and_exclude_duos(kind, helper):
    definitions = [
        dict(id=1, isSolosOnly=True), dict(id=2),
        dict(id=3, isDuosOnly=True), dict(id=4, isSolosOnly=True, isDuosOnly=True),
    ]
    for card in definitions:
        card.update(cardType=kind, pool=True, categories=["tavern"], tier=3)
    system = SimpleNamespace(game=SimpleNamespace(pool=SimpleNamespace(card_definitions=definitions)))
    assert {card["id"] for card in helper(system)} == {1, 2}
