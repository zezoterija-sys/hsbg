"""Core Hearthstone Battlegrounds simulator package."""

from .actions import Action, ActionType
from .bob import Bob
from .heroes import HEROES
from .player import Player
from .pool import CardPool
from .rulesets import CURRENT_RULESET

# ``heroes.py`` is a generated historical snapshot. Apply the selected live
# Solos overlay once at package import so every active consumer sees the same
# armor and repaired hero-power definitions.
CURRENT_RULESET.apply_hero_overrides(HEROES)

__all__ = [
    "Action",
    "ActionType",
    "Bob",
    "Player",
    "CardPool",
    "HEROES",
    "CURRENT_RULESET",
]
