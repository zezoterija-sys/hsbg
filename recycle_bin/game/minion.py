"""
Minion definitions and mechanics for Hearthstone Battlegrounds
"""
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional


class MinionType(Enum):
    """Minion types in Battlegrounds"""
    MURLOC = "murloc"
    BEAST = "beast"
    MECH = "mech"
    DEMON = "demon"
    ELEMENTAL = "elemental"
    DRAGON = "dragon"
    PIRATE = "pirate"
    UNDEAD = "undead"
    QUILBOAR = "quilboar"
    NEUTRAL = "neutral"


class Rarity(Enum):
    """Minion rarity tiers"""
    ONE = 1
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6


@dataclass
class Minion:
    """Represents a minion in the game"""
    name: str
    minion_type: MinionType
    attack: int
    health: int
    rarity: Rarity
    cost: int
    taunt: bool = False
    divine_shield: bool = False
    windfury: bool = False
    poisonous: bool = False
    deathrattle: bool = False
    id: Optional[int] = None
    
    def take_damage(self, damage: int) -> bool:
        """
        Minion takes damage. Returns True if minion dies.
        Divine shield absorbs one hit regardless of damage.
        """
        if self.divine_shield:
            self.divine_shield = False
            return False
        
        self.health -= damage
        return self.health <= 0
    
    def attack_damage(self) -> int:
        """Get attack damage (including windfury multiplier)"""
        multiplier = 2 if self.windfury else 1
        return self.attack * multiplier
    
    def copy(self):
        """Create a copy of this minion"""
        new_minion = Minion(
            name=self.name,
            minion_type=self.minion_type,
            attack=self.attack,
            health=self.health,
            rarity=self.rarity,
            cost=self.cost,
            taunt=self.taunt,
            divine_shield=self.divine_shield,
            windfury=self.windfury,
            poisonous=self.poisonous,
            deathrattle=self.deathrattle,
        )
        return new_minion
    
    def __repr__(self) -> str:
        return f"{self.name} ({self.attack}/{self.health})"


# Starter minions pool (Tier 1)
TIER_1_MINIONS = [
    Minion("Murozond Mummy", MinionType.UNDEAD, 1, 1, Rarity.ONE, 1),
    Minion("Wrath Weaver", MinionType.DEMON, 1, 1, Rarity.ONE, 1),
    Minion("Alleycat", MinionType.BEAST, 1, 1, Rarity.ONE, 1),
    Minion("Scam Advisor", MinionType.PIRATE, 1, 2, Rarity.ONE, 1),
    Minion("Murloc Tidecaller", MinionType.MURLOC, 1, 2, Rarity.ONE, 1),
    Minion("Rockpool Hunter", MinionType.MURLOC, 2, 1, Rarity.ONE, 1),
]

TIER_2_MINIONS = [
    Minion("Hated Nemesis", MinionType.DEMON, 2, 2, Rarity.TWO, 2),
    Minion("Bronze Warden", MinionType.DRAGON, 2, 1, Rarity.TWO, 2),
    Minion("Kaboom Bot", MinionType.MECH, 2, 2, Rarity.TWO, 2),
    Minion("Harvest Golem", MinionType.MECH, 2, 3, Rarity.TWO, 2),
    Minion("Murloc Scout", MinionType.MURLOC, 1, 1, Rarity.TWO, 2),
]

TIER_3_MINIONS = [
    Minion("Khadgar", MinionType.NEUTRAL, 2, 2, Rarity.THREE, 3),
    Minion("Brann Bronzebeard", MinionType.NEUTRAL, 2, 2, Rarity.THREE, 3),
    Minion("Rat Pack", MinionType.BEAST, 2, 2, Rarity.THREE, 3),
]

TIER_4_MINIONS = [
    Minion("Tarecgosa", MinionType.DRAGON, 8, 8, Rarity.FOUR, 4),
    Minion("Kalecgos", MinionType.DRAGON, 2, 8, Rarity.FOUR, 4),
]

TIER_5_MINIONS = [
    Minion("Tarecgosa", MinionType.DRAGON, 8, 8, Rarity.FIVE, 5),
]

TIER_6_MINIONS = [
    Minion("Lil Rag", MinionType.ELEMENTAL, 3, 2, Rarity.SIX, 6),
]

# Minion pool by tier
MINION_POOLS = {
    Rarity.ONE: TIER_1_MINIONS,
    Rarity.TWO: TIER_2_MINIONS,
    Rarity.THREE: TIER_3_MINIONS,
    Rarity.FOUR: TIER_4_MINIONS,
    Rarity.FIVE: TIER_5_MINIONS,
    Rarity.SIX: TIER_6_MINIONS,
}
