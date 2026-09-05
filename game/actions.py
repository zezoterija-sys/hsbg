"""Action definitions and legal-action generation."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from .effects import EffectZone, TargetContext


class ActionType(Enum):
    REFRESH = "refresh"
    BUY_MINION = "buy_minion"
    BUY_SPELL = "buy_spell"
    SELL_MINION = "sell_minion"
    PLAY_MINION = "play_minion"
    CAST_SPELL = "cast_spell"
    HERO_POWER = "hero_power"
    ACTIVATE = "activate"
    FREEZE = "freeze"
    UNFREEZE = "unfreeze"
    UPGRADE_TAVERN = "upgrade_tavern"
    REPOSITION = "reposition"
    CHOOSE_OPTION = "choose_option"
    END_TURN = "end_turn"


@dataclass(frozen=True)
class Action:
    """
    One concrete player decision.

    Existing meanings are preserved:
      target_idx   = source/shop/hand/board index
      position_idx = board destination/target index

    option_idx is used only for an already-open Discover/Choose One choice.
    """

    action_type: ActionType
    target_idx: Optional[int] = None
    position_idx: Optional[int] = None
    option_idx: Optional[int] = None
    effect_target_player_id: Optional[int] = None
    effect_target_zone: Optional[str] = None
    effect_target_idx: Optional[int] = None

    @property
    def ap_cost(self) -> int:
        # Choice resolution is part of the action that opened the choice; it
        # must remain resolvable even if that action spent the player's last AP.
        if self.action_type in (ActionType.END_TURN, ActionType.CHOOSE_OPTION):
            return 0
        return 1

    def __repr__(self) -> str:
        parts = [self.action_type.value]
        if self.target_idx is not None:
            parts.append(f"target={self.target_idx}")
        if self.position_idx is not None:
            parts.append(f"position={self.position_idx}")
        if self.option_idx is not None:
            parts.append(f"option={self.option_idx}")
        if self.effect_target_idx is not None:
            zone = self.effect_target_zone or "board"
            pid = (
                f"p{self.effect_target_player_id}:"
                if self.effect_target_player_id is not None
                else ""
            )
            parts.append(f"effect_target={pid}{zone}[{self.effect_target_idx}]")
        if len(parts) == 1:
            return parts[0]
        return f"{parts[0]}({', '.join(parts[1:])})"


class ActionSpace:
    """Generate legal recruit-phase actions without executing them."""

    MAX_BOARD_SIZE = 7
    MAX_HAND_SIZE = 10

    def __init__(self):
        self.available_actions: list[Action] = []

    def reset(self):
        self.available_actions.clear()

    def add_action(self, action: Action):
        if action not in self.available_actions:
            self.available_actions.append(action)

    def add_actions(self, actions: list[Action]):
        for action in actions:
            self.add_action(action)

    def get_legal_actions(self) -> list[Action]:
        return self.available_actions.copy()

    def is_legal_action(self, action: Action) -> bool:
        return action in self.available_actions

    @staticmethod
    def _target_kwargs(target_ref):
        return {
            "effect_target_player_id": target_ref.player_id,
            "effect_target_zone": target_ref.zone.value,
            "effect_target_idx": target_ref.index,
        }

    @staticmethod
    def _hero_power(player):
        getter = getattr(player, "get_hero_power", None)
        if callable(getter):
            return getter()
        hero = getattr(player, "hero", None)
        if isinstance(hero, dict):
            return hero.get("power")
        return None

    def generate_for_player(self, player: Any, game_state: Any):
        self.reset()

        if getattr(game_state, "phase", None) != "recruit":
            return

        effects = getattr(
            game_state,
            "effects",
            None,
        )

        # Mandatory choices must remain resolvable even when the
        # action that opened them spent the player's final AP.
        if effects is not None:
            pending = effects.get_pending_choice(
                player.player_id
            )

            if pending is not None:
                for option_idx in range(
                    len(pending.options)
                ):
                    self.add_action(
                        Action(
                            ActionType.CHOOSE_OPTION,
                            option_idx=option_idx,
                        )
                    )
                return

        if getattr(player, "waiting", False):
            return

        self.add_action(Action(ActionType.END_TURN))

        ap = getattr(player, "ap", 0)
        if ap <= 0:
            return

        gold = getattr(player, "gold", 0)
        hand = getattr(player, "hand", [])
        board = getattr(player, "board", [])
        tavern = getattr(player, "tavern", None)

        # -----------------------------------------------------
        # REFRESH
        # -----------------------------------------------------
        can_refresh = gold >= 1
        if effects is not None:
            state = effects.get_player_state(player.player_id)
            can_refresh = can_refresh or (
                int(state.get("free_refreshes", 0) or 0) > 0
                or int(state.get("health_refreshes_remaining", 0) or 0) > 0
            )
        if can_refresh:
            self.add_action(Action(ActionType.REFRESH))

        # -----------------------------------------------------
        # BUY MINION / TAVERN SPELL
        # -----------------------------------------------------
        hand_has_space = len(hand) < self.MAX_HAND_SIZE

        if gold >= 3 and tavern is not None and hand_has_space:
            for idx, minion in enumerate(tavern.slots):
                if minion is not None:
                    self.add_action(
                        Action(ActionType.BUY_MINION, target_idx=idx)
                    )

        if tavern is not None and hand_has_space:
            spell = getattr(tavern, "spell", None)
            if isinstance(spell, dict):
                spell_cost = int(spell.get("manaCost", 0) or 0)
                if gold >= spell_cost:
                    self.add_action(Action(ActionType.BUY_SPELL))

        # -----------------------------------------------------
        # SELL
        # -----------------------------------------------------
        for idx, minion in enumerate(board):
            if minion is not None:
                self.add_action(Action(ActionType.SELL_MINION, target_idx=idx))

        # -----------------------------------------------------
        # PLAY MINION / MAGNETIZE
        # -----------------------------------------------------
        empty_positions = [idx for idx, minion in enumerate(board) if minion is None]

        for hand_idx, card in enumerate(hand):
            if not isinstance(card, dict) or card.get("cardType") != "minion":
                continue

            # Normal play into an empty slot. Targeted Battlecries encode
            # their effect target separately from the board destination.
            if effects is not None and effects.has_target_rule(card.get("id")):
                context = TargetContext(
                    game=game_state,
                    player_id=player.player_id,
                    source_card=card,
                    source_zone=EffectZone.HAND,
                    action_kind="play_minion",
                )
                target_refs = effects.get_valid_target_refs(card.get("id"), context)
                for board_idx in empty_positions:
                    for target_ref in target_refs:
                        self.add_action(
                            Action(
                                ActionType.PLAY_MINION,
                                target_idx=hand_idx,
                                position_idx=board_idx,
                                **self._target_kwargs(target_ref),
                            )
                        )
            else:
                for board_idx in empty_positions:
                    self.add_action(
                        Action(
                            ActionType.PLAY_MINION,
                            target_idx=hand_idx,
                            position_idx=board_idx,
                        )
                    )

            # Magnetic may be played directly onto an occupied Mech even when
            # the board is full.
            if effects is not None and effects.is_magnetic(card):
                for board_idx, target in enumerate(board):
                    if effects.can_magnetize(card, target):
                        self.add_action(
                            Action(
                                ActionType.PLAY_MINION,
                                target_idx=hand_idx,
                                position_idx=board_idx,
                            )
                        )

        # -----------------------------------------------------
        # CAST SPELL
        # -----------------------------------------------------
        for hand_idx, card in enumerate(hand):
            if not isinstance(card, dict) or card.get("cardType") != "spell":
                continue

            if effects is not None and effects.has_target_rule(card.get("id")):
                context = TargetContext(
                    game=game_state,
                    player_id=player.player_id,
                    source_card=card,
                    source_zone=EffectZone.HAND,
                    action_kind="cast_spell",
                )
                for target_ref in effects.get_valid_target_refs(card.get("id"), context):
                    self.add_action(
                        Action(
                            ActionType.CAST_SPELL,
                            target_idx=hand_idx,
                            **self._target_kwargs(target_ref),
                        )
                    )
            else:
                self.add_action(
                    Action(ActionType.CAST_SPELL, target_idx=hand_idx)
                )

        # -----------------------------------------------------
        # ACTIVATE
        # -----------------------------------------------------
        if effects is not None:
            for board_idx, card in enumerate(board):
                if not isinstance(card, dict):
                    continue
                ability = effects.get_activate_ability(card)
                if ability is None or not effects.can_activate(player.player_id, board_idx):
                    continue

                targets = effects.get_activate_target_refs(player.player_id, board_idx)
                if ability.target_provider is None:
                    self.add_action(
                        Action(ActionType.ACTIVATE, target_idx=board_idx)
                    )
                else:
                    for target_ref in targets:
                        self.add_action(
                            Action(
                                ActionType.ACTIVATE,
                                target_idx=board_idx,
                                **self._target_kwargs(target_ref),
                            )
                        )

        # -----------------------------------------------------
        # HERO POWER
        # -----------------------------------------------------
        hero_power_cost = getattr(player, "hero_power_cost", 0)
        if gold >= hero_power_cost:
            power = self._hero_power(player)
            if (
                effects is not None
                and isinstance(power, dict)
                and effects.has_target_rule(power.get("id"))
            ):
                context = TargetContext(
                    game=game_state,
                    player_id=player.player_id,
                    source_card=power,
                    source_zone=EffectZone.HERO_POWER,
                    action_kind="hero_power",
                )
                targets = effects.get_valid_target_refs(power.get("id"), context)
                for target_ref in targets:
                    self.add_action(
                        Action(
                            ActionType.HERO_POWER,
                            **self._target_kwargs(target_ref),
                        )
                    )
            else:
                self.add_action(Action(ActionType.HERO_POWER))

        # -----------------------------------------------------
        # FREEZE / UNFREEZE
        # -----------------------------------------------------
        if tavern is not None:
            if tavern.frozen:
                self.add_action(Action(ActionType.UNFREEZE))
            else:
                self.add_action(Action(ActionType.FREEZE))

        # -----------------------------------------------------
        # UPGRADE
        # -----------------------------------------------------
        tavern_tier = getattr(player, "tavern_tier", 1)
        upgrade_costs = getattr(
            game_state,
            "TAVERN_UPGRADE_COSTS",
            {2: 5, 3: 6, 4: 7, 5: 10, 6: 10},
        )
        next_tier = tavern_tier + 1
        if next_tier in upgrade_costs and gold >= upgrade_costs[next_tier]:
            self.add_action(Action(ActionType.UPGRADE_TAVERN))

        # -----------------------------------------------------
        # REPOSITION: occupied <-> occupied, per project rule.
        # -----------------------------------------------------
        occupied = [idx for idx, minion in enumerate(board) if minion is not None]
        for from_idx in occupied:
            for to_idx in occupied:
                if from_idx != to_idx:
                    self.add_action(
                        Action(
                            ActionType.REPOSITION,
                            target_idx=from_idx,
                            position_idx=to_idx,
                        )
                    )

    def __len__(self) -> int:
        return len(self.available_actions)

    def __repr__(self) -> str:
        return f"ActionSpace({len(self.available_actions)} actions)"
