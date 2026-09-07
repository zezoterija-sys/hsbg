"""Defense-in-depth validation for Bob's direct Hero Power API.

ActionSpace already exposes only legal Hero Power actions.  Bob.use_hero_power
also remains a useful low-level API for tests/search tooling, so direct calls
must not bypass active/passive mode, unlocks, per-turn/per-game limits, Gold,
or target legality.
"""

from __future__ import annotations

from types import MethodType

from .effects import EffectZone, TargetContext
from .hero_powers import HeroPowerSystem


def _target_key(target_ref):
    if target_ref is None:
        return None
    return (
        int(target_ref.player_id),
        target_ref.zone,
        target_ref.index,
    )


def _guarded_use_hero_power(self, player_id, *, target_ref=None):
    hero_powers = HeroPowerSystem.for_game(self)
    hero_powers.validate_use(player_id)

    player = self.get_player(player_id)
    power = player.get_hero_power()
    if not isinstance(power, dict) or not isinstance(power.get("id"), int):
        raise ValueError("Player has no valid Hero Power definition.")

    power_id = power["id"]
    effects = self.effects

    if effects.has_target_rule(power_id):
        context = TargetContext(
            game=self,
            player_id=player_id,
            source_card=power,
            source_zone=EffectZone.HERO_POWER,
            action_kind="hero_power",
        )
        legal_refs = effects.get_valid_target_refs(power_id, context)
        legal_by_key = {_target_key(ref): ref for ref in legal_refs}
        supplied_key = _target_key(target_ref)
        legal_ref = legal_by_key.get(supplied_key)

        if target_ref is None or legal_ref is None:
            raise ValueError("Hero Power requires a currently legal target.")

        # Reject stale TargetRefs whose indexed slot has since changed.
        if legal_ref.card is not target_ref.card:
            raise ValueError("Hero Power target is stale or no longer legal.")
    elif target_ref is not None:
        raise ValueError("This Hero Power does not take a target.")

    # The wrapper is installed on the Bob *instance*, leaving the class method
    # as the actual executor. This avoids recursive wrapping and deep-copies
    # cleanly because no closure captures a source Bob instance.
    return type(self).use_hero_power(
        self,
        player_id,
        target_ref=target_ref,
    )


def install_hero_power_use_guard(game) -> None:
    """Install direct-call validation on one Bob-like game instance."""

    if getattr(game, "_hero_power_use_guard_installed", False):
        return
    if not callable(getattr(game, "use_hero_power", None)):
        return

    game.use_hero_power = MethodType(_guarded_use_hero_power, game)
    game._hero_power_use_guard_installed = True
