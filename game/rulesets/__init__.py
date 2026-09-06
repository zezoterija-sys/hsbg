"""Versioned live Battlegrounds ruleset overlays.

The raw hsbg.cards dump remains untouched provenance data. Runtime game systems
normalize it through CURRENT_RULESET so hotfixes and explicit pool removals are
reproducible even when the checked-in dump lags the live client by a few days.
"""

from .patch_36_4_2 import CURRENT_RULESET, BattlegroundsRuleset

__all__ = ["BattlegroundsRuleset", "CURRENT_RULESET"]
