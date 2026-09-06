"""Battlegrounds Gold/economy primitives.

This module keeps distinct mechanics distinct:

- normal start-of-turn Gold progression,
- immediate Gold gains during recruitment,
- permanent increases to a player's maximum Gold,
- deferred Gold gains/losses that resolve next turn,
- alternate purchase resources such as Hasty Excavation costing Health.

The separation matters because current Gold can exceed the player's normal
start-of-turn maximum, while max Gold changes future turn-start resources.
"""

from __future__ import annotations

from types import MethodType

from .events import GameEvent


STARTING_GOLD = 3
DEFAULT_MAX_GOLD = 10
GOLD_INCREASE_PER_TURN = 1
HASTY_EXCAVATION = 104559

# Run before the legacy card_effects pending-Gold listener (-500) so old
# content that already writes ``pending_gold_next_turn`` is upgraded to the
# correct uncapped gain semantics without paying twice.
DEFERRED_GOLD_TURN_START_ORDER = -600


def normal_turn_gold(round_number: int, max_gold: int = DEFAULT_MAX_GOLD) -> int:
    """Return the normal recruit-start Gold for a round/player maximum."""

    round_number = max(1, int(round_number))
    max_gold = max(0, int(max_gold))
    progression = STARTING_GOLD + (round_number - 1) * GOLD_INCREASE_PER_TURN
    return min(progression, max_gold)


def gain_gold(player, amount: int) -> int:
    """Gain Gold immediately without applying the turn-start maximum."""

    amount = max(0, int(amount or 0))
    player.gold = int(getattr(player, "gold", 0) or 0) + amount
    return amount


def lose_gold(player, amount: int) -> int:
    """Lose up to ``amount`` current Gold without going below zero."""

    amount = max(0, int(amount or 0))
    before = int(getattr(player, "gold", 0) or 0)
    lost = min(before, amount)
    player.gold = before - lost
    return lost


def increase_max_gold(player, amount: int) -> int:
    """Permanently increase the player's start-of-turn maximum Gold."""

    amount = max(0, int(amount or 0))
    current = int(getattr(player, "max_gold", DEFAULT_MAX_GOLD))
    player.max_gold = current + amount
    return player.max_gold


def queue_gold_next_turn(effects, player_id: int, amount: int) -> int:
    """Queue an uncapped Gold gain for the player's next TURN_START."""

    amount = max(0, int(amount or 0))
    state = effects.get_player_state(player_id)
    state["pending_gold_next_turn"] = int(
        state.get("pending_gold_next_turn", 0) or 0
    ) + amount
    return state["pending_gold_next_turn"]


def queue_gold_loss_next_turn(effects, player_id: int, amount: int) -> int:
    """Queue a Gold loss for the player's next TURN_START."""

    amount = max(0, int(amount or 0))
    state = effects.get_player_state(player_id)
    state["pending_gold_loss_next_turn"] = int(
        state.get("pending_gold_loss_next_turn", 0) or 0
    ) + amount
    return state["pending_gold_loss_next_turn"]


def tavern_spell_purchase_resource(spell) -> str:
    """Return the resource used to buy one Tavern spell."""

    if isinstance(spell, dict) and spell.get("id") == HASTY_EXCAVATION:
        return "health"
    return "gold"


def can_pay_tavern_spell(player, spell) -> bool:
    """Return whether ``player`` can pay the printed Tavern-spell cost."""

    if not isinstance(spell, dict):
        return False
    cost = max(0, int(spell.get("manaCost", 0) or 0))
    if tavern_spell_purchase_resource(spell) == "health":
        # Health-paid shop purchases cannot reduce the hero to 0.
        return int(getattr(player, "health", 0) or 0) > cost
    return int(getattr(player, "gold", 0) or 0) >= cost


def pay_tavern_spell_cost(effects, player_id, spell):
    """Pay one Tavern spell's purchase cost and return ``(resource, amount)``."""

    player = effects.game.get_player(player_id)
    cost = max(0, int(spell.get("manaCost", 0) or 0))
    resource = tavern_spell_purchase_resource(spell)

    if resource == "gold":
        effects.spend_gold(
            player_id,
            cost,
            reason="buy_spell",
            source=spell,
        )
        return resource, cost

    if int(getattr(player, "health", 0) or 0) <= cost:
        raise ValueError("Not enough Health to buy this Tavern spell.")

    # A Health cost is hero damage for current Battlegrounds interactions such
    # as Soul Rewinder. It bypasses Armor because the card explicitly costs
    # Health rather than dealing generic damage.
    player.health = int(player.health) - cost
    effects.events.emit(
        GameEvent.PLAYER_DAMAGED,
        player_id=player_id,
        amount=cost,
        armor_damage=0,
        health_damage=cost,
        self_damage=True,
        purchase_health_cost=True,
        source_card=spell,
    )
    return resource, cost


def _resolve_deferred_gold(effects, event) -> None:
    player_id = event.get("player_id")
    if player_id is None or effects.game is None:
        return

    state = effects.get_player_state(player_id)
    gain = max(0, int(state.pop("pending_gold_next_turn", 0) or 0))
    loss = max(0, int(state.pop("pending_gold_loss_next_turn", 0) or 0))
    player = effects.game.get_player(player_id)

    if gain:
        gain_gold(player, gain)
    if loss:
        lose_gold(player, loss)


def _effect_gain_gold(self, player_id, amount):
    return gain_gold(self.game.get_player(player_id), amount)


def _effect_increase_max_gold(self, player_id, amount):
    return increase_max_gold(self.game.get_player(player_id), amount)


def _effect_queue_gold_next_turn(self, player_id, amount):
    return queue_gold_next_turn(self, player_id, amount)


def _effect_queue_gold_loss_next_turn(self, player_id, amount):
    return queue_gold_loss_next_turn(self, player_id, amount)


def _effect_can_pay_tavern_spell(self, player_id, spell):
    return can_pay_tavern_spell(self.game.get_player(player_id), spell)


def _effect_pay_tavern_spell_cost(self, player_id, spell):
    return pay_tavern_spell_cost(self, player_id, spell)


def install_economy_primitives(effects) -> None:
    """Install the canonical economy API on one EffectSystem instance."""

    if getattr(effects, "_economy_primitives_installed", False):
        return

    effects.add_gold = MethodType(_effect_gain_gold, effects)
    effects.add_max_gold = MethodType(_effect_increase_max_gold, effects)
    effects.increase_max_gold = MethodType(_effect_increase_max_gold, effects)
    effects.queue_gold_next_turn = MethodType(_effect_queue_gold_next_turn, effects)
    effects.queue_gold_loss_next_turn = MethodType(
        _effect_queue_gold_loss_next_turn,
        effects,
    )
    effects.can_pay_tavern_spell = MethodType(_effect_can_pay_tavern_spell, effects)
    effects.pay_tavern_spell_cost = MethodType(_effect_pay_tavern_spell_cost, effects)

    effects.events.register(
        GameEvent.TURN_START,
        lambda event: _resolve_deferred_gold(effects, event),
        order=DEFERRED_GOLD_TURN_START_ORDER,
    )
    effects._economy_primitives_installed = True


def _guarded_buy_spell(self, player_id):
    """Bob.buy_spell wrapper supporting Health-paid Tavern spells."""

    player = self.get_player(player_id)
    tavern = player.tavern
    spell = getattr(tavern, "spell", None)

    if not isinstance(spell, dict):
        raise ValueError("No Tavern spell is available.")
    if spell.get("cardType") != "spell":
        raise ValueError("Tavern spell slot does not contain a spell.")
    if len(player.hand) >= player.MAX_HAND_SIZE:
        raise ValueError("Hand is full.")

    # Ordinary Gold-paid spells continue through Bob's canonical implementation.
    if tavern_spell_purchase_resource(spell) == "gold":
        return type(self).buy_spell(self, player_id)

    if not can_pay_tavern_spell(player, spell):
        raise ValueError("Not enough Health to buy this Tavern spell.")

    player.hand.append(spell)
    tavern.spell = None
    resource, cost = self.effects.pay_tavern_spell_cost(player_id, spell)

    self.events.emit(
        GameEvent.SPELL_BOUGHT,
        source=self,
        player=player,
        player_id=player_id,
        spell=spell,
        card=spell,
        gold_cost=0,
        health_cost=cost,
        purchase_resource=resource,
    )


def install_tavern_spell_purchase_guard(game) -> None:
    """Install alternate-resource Tavern-spell buying on one Bob-like game."""

    if getattr(game, "_economy_buy_spell_guard_installed", False):
        return
    if not callable(getattr(game, "buy_spell", None)):
        return

    game.buy_spell = MethodType(_guarded_buy_spell, game)
    game._economy_buy_spell_guard_installed = True
