from copy import deepcopy

from game.heroes import HEROES
from game.rulesets import CURRENT_RULESET


def test_current_ruleset_identity():
    assert CURRENT_RULESET.ruleset_id == "36.4.2-solos"
    assert CURRENT_RULESET.released == "2026-09-03"


def test_card_hotfix_is_applied_without_mutating_raw_input():
    raw = {
        "id": 59955,
        "name": "Goldrinn, the Great Wolf",
        "cardType": "minion",
        "tier": 6,
        "attack": 8,
        "health": 8,
        "pool": True,
        "categories": ["tavern"],
    }
    snapshot = deepcopy(raw)

    current = CURRENT_RULESET.normalize_card(raw)

    assert raw == snapshot
    assert current["tier"] == 5
    assert current["attack"] == 7
    assert current["health"] == 7
    assert current["attackGold"] == 14
    assert current["healthGold"] == 14
    assert "+7/+7" in current["text"]


def test_removed_live_pool_entry_is_disabled():
    sanctify = CURRENT_RULESET.normalize_card(
        {
            "name": "Sanctify",
            "cardType": "spell",
            "pool": True,
        }
    )
    assert sanctify["pool"] is False


def test_current_hero_armor_overlay_is_applied_to_runtime_heroes():
    by_name = {hero["name"]: hero for hero in HEROES.values()}

    assert by_name["Alexstrasza"]["armor"] == 8
    assert by_name["Reno Jackson"]["armor"] == 12
    assert by_name["Maiev Shadowsong"]["armor"] == 18


def test_missing_generated_hero_powers_are_repaired():
    by_name = {hero["name"]: hero for hero in HEROES.values()}

    rakanishu = by_name["Rakanishu"]["power"]
    tavish = by_name["Tavish Stormpike"]["power"]

    assert rakanishu["name"] == "Tavern Lighting"
    assert rakanishu["id"] == 122960
    assert "every 3 turns" in rakanishu["text"]
    assert tavish["name"] == "Lock and Load"
    assert tavish["id"] == 123150
    assert "Remove a minion in the Tavern" in tavish["text"]


def test_trinket_hotfixes_do_not_cross_lesser_greater_versions():
    lesser = {"name": "Inductive Gyroblade", "cardType": "trinket",
              "trinketTier": "lesser", "text": "Get a 4/4 Magnetic Satellite."}
    greater = {**lesser, "trinketTier": "greater"}
    assert CURRENT_RULESET.normalize_card(lesser) == lesser
    assert "12/12" in CURRENT_RULESET.normalize_card(greater)["text"]
    for tier in ("lesser", "greater"):
        raw = {"name": "Jailer Sticker", "cardType": "trinket", "trinketTier": tier, "manaCost": 4}
        assert CURRENT_RULESET.normalize_card(raw)["manaCost"] == 3


def test_lesser_pool_removal_does_not_remove_greater_namesake():
    base = {"name": "Blessing Portrait", "cardType": "trinket", "pool": True}
    assert not CURRENT_RULESET.normalize_card({**base, "trinketTier": "lesser"})["pool"]
    assert CURRENT_RULESET.normalize_card({**base, "trinketTier": "greater"})["pool"]
