"""Live Battlegrounds Solos ruleset for Hearthstone Patch 36.4.2.

Source of truth for balance values in this file is Blizzard's 36.4.2 patch
notes (September 3, 2026). The checked-in raw card dump remains unmodified;
these overrides are applied to independent runtime copies.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping


CARD_OVERRIDES: dict[str, dict[str, Any]] = {
    # Minions -----------------------------------------------------------
    "Tasty Lobster": {
        "attack": 2,
        "health": 1,
        "text": "Deathrattle: Give a random friendly Beast +2/+1. Improve your future Tasty Lobsters.",
    },
    "Hoarding Hyena": {"tier": 4, "attack": 4, "health": 6},
    "Goldrinn, the Great Wolf": {
        "tier": 5,
        "attack": 7,
        "health": 7,
        "text": "Deathrattle: Your Beasts have +7/+7 until next turn.",
    },
    "Lurking Leviathan": {
        "attack": 3,
        "health": 9,
        "text": "Whenever you summon a Beast, give it +3 Attack and improve this permanently.",
    },
    "Eredar Escapist": {
        "attack": 6,
        "health": 8,
        "text": "After your hero takes 4 damage, get a copy of Corrupted Cupcakes. (4 left!)",
    },
    "Soul Rewinder": {
        "attack": 4,
        "health": 2,
        "text": "After your hero takes damage, rewind it and give this +2 Health.",
    },
    "Ashen Corruptor": {
        "attack": 6,
        "health": 6,
        "text": "After your hero takes damage, rewind it and give minions in the Tavern +2/+2 this turn.",
    },
    "Tichondrius": {
        "attack": 4,
        "health": 4,
        "text": "After your hero takes damage, give your Demons +4/+4.",
    },
    "Malchezaar, Prince of Dance": {"attack": 4, "health": 3},
    "Devout Hellcaller": {
        "attack": 4,
        "health": 4,
        "text": "After another friendly Demon deals damage, gain +2/+2 permanently.",
    },
    "Bronze Timewalker": {"attack": 4, "health": 5},
    "Fire-forged Evoker": {
        "attack": 8,
        "health": 6,
        "text": "Start of Combat: Give your Dragons +2/+2. Improves permanently after you cast a Tavern spell.",
    },
    "Unleashed Mana Surge": {
        "attack": 6,
        "health": 9,
        "text": "After you play an Elemental, give your Elementals +2/+3.",
    },
    "Utility Drone": {
        "attack": 4,
        "health": 5,
        "text": "At the end of your turn, give your minions +4/+5 for each Magnetization they have.",
    },
    "Sanguine Champion": {
        "attack": 9,
        "health": 4,
        "text": "Battlecry and Deathrattle: Your Blood Gems give an extra +2/+1 this game.",
    },
    "Sanguine Refiner": {
        "attack": 3,
        "health": 8,
        "text": "Rally: Your Blood Gems give an extra +1/+2 this game.",
    },
    "Prodigious Tusker": {"attack": 2, "health": 5},
    "Fearless Foodie": {"tier": 3},
    "Jailbird Juggernaut": {
        "text": "Rally: Summon a Golem with this minion's stats to attack the target first.",
    },
    "Private Investigator": {
        "attack": 5,
        "health": 6,
        "text": "Activate (1): Gain 2 Gold next turn.",
    },
    "Cagey Conjurer": {"tier": 4},
    "Forsaken Weaver": {
        "attack": 3,
        "health": 8,
        "text": "After you cast a Tavern spell, your Undead have +3 Attack this game (wherever they are).",
    },
    "Drustfallen Butcher": {
        "attack": 2,
        "health": 7,
        "text": "Avenge (3): Get a Butchering.",
    },
    "Tyrael": {
        "text": "Activate (1): Set another minion's stats to 50/50.",
    },
    # Tavern spells -----------------------------------------------------
    "Mighty Dragonbreath": {
        "text": "Give your minions +3/+2. Repeat for your Dragons. Repeat for your minions with Divine Shield.",
    },
    "Natural Blessing": {
        "manaCost": 2,
        "text": "Choose a minion. Give all minions that share a type with it +2/+1.",
    },
    "Sanctify": {"pool": False},
}


LESSER_TRINKET_OVERRIDES: dict[str, dict[str, Any]] = {
    "Blessing Portrait": {"pool": False},
    "Copper Coil": {"pool": False},
    "Cowrie Necklace": {"pool": False},
    "Deathwhisper Sticker": {"pool": False},
    "Warcry Totem": {"manaCost": 3},
    "Splinter of Aurum": {"manaCost": 3},
    "Demonic Bloodletter": {"manaCost": 3},
    "Ominous Stone": {"manaCost": 2},
    "Herding Horn": {"manaCost": 2},
    "Wand of Divination": {"manaCost": 1},
    "Floating Candle Set": {"manaCost": 4},
    "Sellemental Portrait": {"manaCost": 6},
    "War Drum": {"manaCost": 3},
    "Chromatic Tear": {"manaCost": 3},
    "Bleeding Heart": {"manaCost": 2},
    "Kaleidoscope": {"manaCost": 0},
    "Jailer Sticker": {"manaCost": 3},
    "Glowing Gauntlet": {"manaCost": 0},
    "Ophidian Staff": {"manaCost": 3},
    "Spell-powered Wrench": {"manaCost": 0},
    "Minion Bait": {"manaCost": 0},
    "Pilgrimp Sticker": {"manaCost": 1},
    "Scraper Sticker": {"manaCost": 2},
    "Lucky Tabby": {"manaCost": 0},
    "Putricide Sticker": {"manaCost": 1},
    "Fish Portrait": {"manaCost": 1},
    "Emergency Gearblade": {"manaCost": 0},
    "Comfy Coffin": {"manaCost": 1},
    "Holy Mallet": {"manaCost": 0},
    "Dragon Skull": {"manaCost": 2},
    "Automaton Portrait": {"manaCost": 0},
    "Archaic Scroll": {
        "text": "After you cast 8 spells, get a random Naga. (8 left!)",
    },
    "Bubble Crown": {
        "text": "Once you cast 14 spells, your Tavern spells give an extra +4/+4. (14 left!)",
    },
    "Gold Mallet": {
        "text": "At the end of your turn, give your minions +1/+1. (Improved by Golden minions you've played this game!)",
    },
    "Rune of Transmutation": {
        "text": "After you cast 18 spells, replace this with a random Greater Naga Trinket. (18 left!)",
    },
    "Stormcoil Sticker": {
        "manaCost": 1,
        "text": "After 6 friendly minions die, get a random Mech. (6 left!)",
    },
    "Lionfish Portrait": {
        "text": "Get a Lurking Lionfish. Whenever a friendly Beast attacks, give it +4/+2.",
    },
    "Nomi Sticker": {
        "text": "After you play an Elemental, give Elementals in the Tavern +3/+2 this game.",
    },
}


GREATER_TRINKET_OVERRIDES: dict[str, dict[str, Any]] = {
    "Coral Spear": {"pool": False},
    "Dramaloc Sticker": {"manaCost": 6},
    "Myrmidon Sticker": {"manaCost": 3},
    "Groundbreaker Portrait": {"manaCost": 6},
    "Multilayered Shield": {"manaCost": 4},
    "Honeycomb Ring": {"manaCost": 4},
    "Bassgill Portrait": {"manaCost": 2},
    "Ghastly Sticker": {"manaCost": 4},
    "Recycling Sticker": {"manaCost": 5},
    "Escapee Portrait": {"manaCost": 7},
    "Pocket Cyclone": {"manaCost": 0},
    "Pagle's Fishing Rod": {"manaCost": 3},
    "Privateer Portrait": {"manaCost": 4},
    "Fancy Spellbook": {"manaCost": 0},
    "Dalaran Cheese Wheel": {"manaCost": 0},
    "Fridge Magnet": {"manaCost": 1},
    "Lightfeather Sticker": {"manaCost": 0},
    "Insurrectionist's Blade": {"manaCost": 2},
    "Booty Bay Brew": {"manaCost": 0},
    "Wolfhead Flail": {"manaCost": 4},
    "Jailer Sticker": {"manaCost": 3},
    "Herald Sticker": {"manaCost": 2},
    "Ironforge Anvil": {"manaCost": 1},
    "Quilligraphy Set": {"manaCost": 1},
    "Reinforced Shield": {"manaCost": 1},
    "Lava Lamp": {
        "text": "After you sell 7 minions, get a random Elemental. (7 left!)",
    },
    "Nazjatar Postcard": {
        "manaCost": 2,
        "text": "After you play 2 Naga, get a random Spellcraft spell. (2 left!)",
    },
    "Baller Portrait": {
        "manaCost": 5,
        "text": "Get a Temperature Shift. After you play 11 Elementals, repeat this. (11 left!)",
    },
    "All-Purpose Kibble": {
        "manaCost": 2,
        "text": "Whenever a friendly Beast attacks, give it +3 Attack and permanently improve this.",
    },
    "Inductive Gyroblade": {
        "text": "At the end of your turn, get a 12/12 Magnetic Satellite. (Improved by each Tavern spell you've cast this turn!)",
    },
    "Miniature Ship": {
        "text": "After you cast a Tavern spell, give your Pirates +3/+3.",
    },
    "Trusty Crowbar": {
        "text": "Whenever you get a Pirate, give your left-most minion +16/+16.",
    },
    "Thaumaturgist Portrait": {
        "text": "Get 2 Thaumaturgists. Your Thaumaturgists' Spellcrafts are permanent.",
    },
}


HERO_ARMOR_OVERRIDES: dict[str, int] = {
    "Reno Jackson": 12,
    "Inge, the Iron Hymn": 10,
    "Cariel Roame": 10,
    "Alexstrasza": 8,
    "Zerek, Master Cloner": 12,
    "Vanndar Stormpike": 10,
    "Forest Lord Cenarius": 13,
    "Sneed": 15,
    "Time Twister Chromie": 14,
    "Dancin' Deryl": 18,
    "Heistbaron Togwaggle": 16,
    "The Rat King": 14,
    "Patches the Pirate": 19,
    "Silas Darkmoon": 16,
    "E.T.C., Band Manager": 16,
    "Loh, the Living Legend": 19,
    "Tras'tath, Soul Parasite": 15,
    "Cap'n Hoggarr": 14,
    "Scabbs Cutterbutter": 18,
    "Xyrella": 14,
    "Snake Eyes": 8,
    "Y'Shaarj": 20,
    "Kurtrus Ashfallen": 16,
    "Infinite Toki": 15,
    "Kael'thas Sunstrider": 18,
    "Sindragosa": 10,
    "Maiev Shadowsong": 18,
}


HERO_POWER_OVERRIDES: dict[str, dict[str, Any]] = {
    # These two definitions were unresolved in the generated heroes.py file.
    "Rakanishu": {
        "name": "Tavern Lighting",
        "cost": 0,
        "text": "Your Tavern spells give an extra +1/+1. At the start of every 3 turns, improve this. (3 turns left!)",
    },
    "Tavish Stormpike": {
        "name": "Lock and Load",
        "cost": 0,
        "text": "Remove a minion in the Tavern. When you have space next combat, fire it at a random enemy minion.",
    },
}


@dataclass(frozen=True)
class BattlegroundsRuleset:
    version: str
    mode: str
    released: str
    card_overrides: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    hero_armor_overrides: Mapping[str, int] = field(default_factory=dict)
    hero_power_overrides: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    lesser_trinket_overrides: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    greater_trinket_overrides: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    @property
    def ruleset_id(self) -> str:
        return f"{self.version}-{self.mode}"

    def normalize_card(self, card: Mapping[str, Any]) -> dict[str, Any]:
        """Return an independent card definition normalized to this patch."""

        normalized = deepcopy(dict(card))
        mapping = self.card_overrides
        if normalized.get("cardType") == "trinket":
            mapping = {
                "lesser": self.lesser_trinket_overrides,
                "greater": self.greater_trinket_overrides,
            }.get(normalized.get("trinketTier"), {})
        override = mapping.get(str(normalized.get("name", "")))
        if override:
            normalized.update(deepcopy(dict(override)))
            if normalized.get("cardType") == "minion":
                # These patch stat changes apply to the standard golden
                # counterpart too. Never keep stale raw golden base stats.
                for stat in ("attack", "health"):
                    if stat in override and stat + "Gold" not in override:
                        normalized[stat + "Gold"] = 2 * int(override[stat])
        return normalized

    def normalize_cards(self, cards) -> list[dict[str, Any]]:
        return [self.normalize_card(card) for card in cards]

    def apply_hero_overrides(self, heroes: dict[int, dict[str, Any]]) -> None:
        """Apply current Solos armor/power hotfixes to generated hero data."""

        for hero in heroes.values():
            name = str(hero.get("name", ""))

            if name in self.hero_armor_overrides:
                hero["armor"] = int(self.hero_armor_overrides[name])

            power_override = self.hero_power_overrides.get(name)
            if power_override:
                current = dict(hero.get("power") or {})
                current.update(deepcopy(dict(power_override)))
                hero["power"] = current


CURRENT_RULESET = BattlegroundsRuleset(
    version="36.4.2",
    mode="solos",
    released="2026-09-03",
    card_overrides=CARD_OVERRIDES,
    hero_armor_overrides=HERO_ARMOR_OVERRIDES,
    hero_power_overrides=HERO_POWER_OVERRIDES,
    lesser_trinket_overrides=LESSER_TRINKET_OVERRIDES,
    greater_trinket_overrides=GREATER_TRINKET_OVERRIDES,
)
