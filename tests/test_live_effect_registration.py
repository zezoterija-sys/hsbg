from game.bob import Bob
from game.effects import TriggerFamily
from game.tier36_effects import MIGHTY_DRAGONBREATH, NATURAL_BLESSING


def _named_registration(game, card_id, name):
    matches = [
        effect
        for effect in game.effects._effects.get(card_id, ())
        if effect.name == name
    ]
    assert len(matches) == 1
    return matches[0]


def test_36_4_2_tavern_spell_overrides_remain_spell_family():
    game = Bob(seed=7)

    dragonbreath = _named_registration(
        game,
        MIGHTY_DRAGONBREATH,
        f"Tier 3-6 spell {MIGHTY_DRAGONBREATH}",
    )
    blessing = _named_registration(
        game,
        NATURAL_BLESSING,
        f"Tier 3-6 spell {NATURAL_BLESSING}",
    )

    assert dragonbreath.family is TriggerFamily.SPELL
    assert blessing.family is TriggerFamily.SPELL
