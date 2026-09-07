import random

from game.lobby import (
    LOBBY_MINION_TYPE_COUNT,
    SEASON_14_MINION_TYPES,
    is_minion_available_for_lobby,
    roll_active_minion_types,
)
from game.pool import CardPool


def test_season14_has_ten_eligible_minion_types_and_rolls_five():
    assert len(SEASON_14_MINION_TYPES) == 10
    assert LOBBY_MINION_TYPE_COUNT == 5

    first = roll_active_minion_types(random.Random(1234))
    second = roll_active_minion_types(random.Random(1234))

    assert first == second
    assert len(first) == 5
    assert len(set(first)) == 5
    assert set(first) <= set(SEASON_14_MINION_TYPES)


def test_neutral_and_all_minions_are_available_in_every_lobby():
    active = {"Beast", "Demon", "Dragon", "Elemental", "Mech"}

    assert is_minion_available_for_lobby({"minionTypes": []}, active)
    assert is_minion_available_for_lobby({"minionTypes": ["All"]}, active)


def test_single_type_minion_requires_its_type():
    active = {"Beast", "Demon", "Dragon", "Elemental", "Mech"}

    assert is_minion_available_for_lobby({"minionTypes": ["Beast"]}, active)
    assert not is_minion_available_for_lobby({"minionTypes": ["Murloc"]}, active)


def test_dual_type_minion_is_available_when_either_type_is_active():
    assert is_minion_available_for_lobby(
        {"minionTypes": ["Demon", "Pirate"]},
        {"Pirate", "Murloc", "Naga", "Quilboar", "Undead"},
    )
    assert not is_minion_available_for_lobby(
        {"minionTypes": ["Demon", "Pirate"]},
        {"Beast", "Dragon", "Elemental", "Mech", "Murloc"},
    )


def test_current_solos_physical_minion_copy_counts():
    assert CardPool.MINION_COPY_COUNTS == {
        1: 15,
        2: 15,
        3: 13,
        4: 11,
        5: 9,
        6: 7,
    }


def test_current_tavern_spell_copy_counts():
    assert CardPool.TAVERN_SPELL_COPY_COUNTS == {
        1: 5,
        2: 7,
        3: 9,
        4: 11,
        5: 9,
        6: 7,
    }
