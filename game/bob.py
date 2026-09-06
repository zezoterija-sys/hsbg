"""Main Hearthstone Battlegrounds game controller.

Bob coordinates game-rule systems. Artificial recruit timing/budget state lives
in RecruitScheduler and is deliberately kept separate from Hearthstone state.
"""

import random

from .actions import ActionType
from .card_effects import register_card_effects
from .combat import Combat
from .dark_gifts import DarkGiftSystem
from .effects import EffectSystem, EffectZone, TargetContext
from .events import EventDispatcher, GameEvent
from .hero_powers import HeroPowerSystem
from .heroes import HEROES
from .lobby import roll_active_minion_types
from .player import Player
from .pool import CardPool
from .recruitment import Recruitment
from .triples import TripleSystem
from .rulesets.patch_36_4_2_effects import register_36_4_2_effect_overrides


class Bob:
    """Main game controller."""

    PLAYER_COUNT = 8

    TAVERN_UPGRADE_COSTS = {
        2: 5,
        3: 6,
        4: 7,
        5: 10,
        6: 10,
    }

    def __init__(self, cards_file="data/raw/cards.json", seed=None):
        self.seed = seed
        self.random = random.Random(seed)

        self.players = []
        self.round_number = 0
        self.phase = None

        # Public live-lobby rule state: five active minion types are rolled for
        # each normal Solos game before hero selection.
        self.active_minion_types = roll_active_minion_types(self.random)

        # Private deterministic resolution order. This is simulator scheduling
        # state, not information that should be exposed to an AI observation.
        self.priority_order = []

        self.hero_pool = []
        self.game_over = False
        self.last_combat_result = None

        self.events = EventDispatcher()
        self.effects = EffectSystem(
            game=self,
            events=self.events,
            rng=self.random,
        )
        register_card_effects(self.effects)
        register_36_4_2_effect_overrides(self.effects)

        self.pool = CardPool(
            cards_file=cards_file,
            rng=self.random,
            active_minion_types=self.active_minion_types,
        )
        self.hero_pool = self._solos_hero_ids()

        self.triples = TripleSystem(self)

        # Season 14 global Dark Discovery lifecycle. Individual Gift behavior
        # remains ordinary attachment-driven EffectSystem logic.
        self.dark_gifts = DarkGiftSystem(self)

        # Recruitment creates and exposes self.scheduler.
        self.recruitment = Recruitment(self)
        self.scheduler = self.recruitment.scheduler
        self.combat = Combat(self)

    # =========================================================
    # PLAYER / GAME INITIALIZATION
    # =========================================================

    def create_players(self):
        self.players = [
            Player(player_id)
            for player_id in range(self.PLAYER_COUNT)
        ]
        return self.players

    def get_player(self, player_id):
        return self.players[player_id]

    def get_alive_players(self):
        return [player for player in self.players if not player.eliminated]

    def initialize_game(self):
        self.create_players()
        self.round_number = 0
        self.phase = "hero_selection"
        self.game_over = False
        self.last_combat_result = None
        self.priority_order = []

        self.effects.reset_runtime_state_for_new_game()
        self.events.emit(
            GameEvent.GAME_START,
            source=self,
            player_count=self.PLAYER_COUNT,
        )

        self._prepare_hero_selection()
        return self.get_state()

    # =========================================================
    # HERO SELECTION
    # =========================================================

    def _solos_hero_ids(self):
        return [
            hero_id
            for hero_id, hero in HEROES.items()
            if not hero.get("isDuosOnly", False)
        ]

    def _prepare_hero_selection(self):
        if len(self.players) != self.PLAYER_COUNT:
            raise ValueError("Bob requires exactly 8 players before hero selection.")

        self.phase = "hero_selection"
        self.generate_priority_order()

        available = self._solos_hero_ids()
        self.random.shuffle(available)
        needed = self.PLAYER_COUNT * 4
        if len(available) < needed:
            raise RuntimeError("Not enough unique heroes for four choices per player.")

        cursor = 0
        for player_id in self.priority_order:
            player = self.get_player(player_id)
            player.hero_choices = available[cursor : cursor + 4]
            cursor += 4

        self.hero_pool = [
            hero_id
            for hero_id in self._solos_hero_ids()
            if hero_id not in {
                choice
                for player in self.players
                for choice in player.hero_choices
            }
        ]

        self.events.emit(
            GameEvent.HERO_SELECTION_START,
            source=self,
            priority_order=self.priority_order.copy(),
        )

    def choose_hero(self, player_id, hero_id):
        if self.phase != "hero_selection":
            raise ValueError("Heroes can only be chosen during hero selection.")

        player = self.get_player(player_id)
        if player.hero is not None:
            raise ValueError("Player already selected a hero.")
        if hero_id not in player.hero_choices:
            raise ValueError("Hero was not offered to this player.")

        unchosen = [choice for choice in player.hero_choices if choice != hero_id]
        player.set_hero(hero_id)
        player.hero_choices = []
        self.hero_pool.extend(unchosen)

        self.events.emit(
            GameEvent.HERO_SELECTED,
            source=self,
            player=player,
            player_id=player_id,
            hero_id=hero_id,
        )

        if all(player.hero is not None for player in self.players):
            self.recruitment.start()

    # =========================================================
    # PRIORITY / ACTION SPACES
    # =========================================================

    def generate_priority_order(self):
        self.priority_order = [
            player.player_id
            for player in self.players
            if not player.eliminated
        ]
        self.random.shuffle(self.priority_order)
        self.combat.set_priority_order(self.priority_order)
        return self.priority_order

    def update_action_space(self, player_id):
        player = self.get_player(player_id)
        player.action_space.update(player, self)
        return player.action_space.get_actions()

    def update_all_action_spaces(self):
        for player in self.players:
            self.update_action_space(player.player_id)

    def get_player_action_space(self, player_id):
        return self.get_player(player_id).action_space.get_actions()

    # =========================================================
    # ACTION EXECUTION / BATCH RESOLUTION
    # =========================================================

    @staticmethod
    def _action_target_ref(action):
        if action.effect_target_zone is None:
            return None
        try:
            zone = EffectZone(action.effect_target_zone)
        except ValueError as exc:
            raise ValueError(f"Unknown effect target zone: {action.effect_target_zone}") from exc
        return TargetRef(
            player_id=action.effect_target_player_id,
            zone=zone,
            index=action.effect_target_idx,
            card=None,
        )

    def _resolve_action_target_ref(self, action):
        if action.effect_target_zone is None:
            return None
        try:
            zone = EffectZone(action.effect_target_zone)
        except ValueError as exc:
            raise ValueError(f"Unknown effect target zone: {action.effect_target_zone}") from exc
        return self.effects.resolve_target_ref(
            action.effect_target_player_id,
            zone,
            action.effect_target_idx,
        )

    def _validate_action(self, player_id, action):
        player = self.get_player(player_id)
        if not isinstance(action, Action):
            raise ValueError("Action must be an Action instance.")
        if action not in player.action_space.get_actions():
            raise ValueError(f"Action is not currently legal for player {player_id}: {action}")

    def execute_action(self, player_id, action):
        return self.resolve_action_batch([(player_id, action)])[0]

    def resolve_action_batch(self, submissions):
        submissions = list(submissions)
        if not submissions:
            return []

        player_ids = [player_id for player_id, _ in submissions]
        if len(player_ids) != len(set(player_ids)):
            raise ValueError("A player may submit at most one action per batch.")

        eligible = set(self.recruitment.eligible_player_ids())
        if set(player_ids) != eligible:
            raise ValueError(
                "Batch submissions must match exactly the scheduler-eligible players."
            )

        # Validate every action against the same pre-action state before any
        # shared-state mutation occurs.
        for player_id, action in submissions:
            self._validate_action(player_id, action)

        by_player = dict(submissions)
        results = []
        for player_id in self.priority_order:
            action = by_player.get(player_id)
            if action is None:
                continue

            results.append(self._execute_validated_action(player_id, action))
            if self.game_over:
                break

        return results

    # Backward-compatible alias used by older tests/tools.
    resolve_collision_batch = resolve_action_batch

    def _execute_validated_action(self, player_id, action):
        player = self.get_player(player_id)

        if action.action_type == ActionType.CHOOSE_OPTION:
            self.effects.resolve_choice(player_id, action.option_idx)
            self.scheduler.note_continuation(player_id)

        elif action.action_type == ActionType.END_TURN:
            self.recruitment.player_end_turn(player_id)

        elif action.action_type == ActionType.REFRESH:
            self.refresh(player_id)
            self.scheduler.commit_interaction(player_id)

        elif action.action_type == ActionType.BUY_MINION:
            self.buy_minion(player_id, action.target_idx)
            self.scheduler.commit_interaction(player_id)

        elif action.action_type == ActionType.BUY_SPELL:
            self.buy_spell(player_id)
            self.scheduler.commit_interaction(player_id)

        elif action.action_type == ActionType.SELL_MINION:
            self.sell_minion(player_id, action.target_idx)
            self.scheduler.commit_interaction(player_id)

        elif action.action_type == ActionType.PLAY_MINION:
            self.play_minion(
                player_id,
                action.target_idx,
                action.position_idx,
                target_ref=self._resolve_action_target_ref(action),
            )
            self.scheduler.commit_interaction(player_id)

        elif action.action_type == ActionType.CAST_SPELL:
            self.cast_spell(
                player_id,
                action.target_idx,
                target_ref=self._resolve_action_target_ref(action),
            )
            self.scheduler.commit_interaction(player_id)

        elif action.action_type == ActionType.ACTIVATE:
            self.effects.resolve_activate(
                player_id,
                action.target_idx,
                target_ref=self._resolve_action_target_ref(action),
            )
            self.scheduler.commit_interaction(player_id)

        elif action.action_type == ActionType.HERO_POWER:
            self.use_hero_power(
                player_id,
                target_ref=self._resolve_action_target_ref(action),
            )
            self.scheduler.commit_interaction(player_id)

        elif action.action_type == ActionType.DARK_GIFT:
            self.dark_gifts.open_offer(player_id)
            self.scheduler.commit_interaction(player_id)

        elif action.action_type == ActionType.FREEZE:
            self.freeze(player_id)
            self.scheduler.commit_interaction(player_id)

        elif action.action_type == ActionType.UNFREEZE:
            self.unfreeze(player_id)
            self.scheduler.commit_interaction(player_id)

        elif action.action_type == ActionType.UPGRADE_TAVERN:
            self.upgrade_tavern(player_id)
            self.scheduler.commit_interaction(player_id)

        elif action.action_type == ActionType.REPOSITION:
            self.reposition(player_id, action.target_idx, action.position_idx)
            self.scheduler.commit_interaction(player_id)

        else:
            raise ValueError(f"Unsupported action type: {action.action_type}")

        self.events.emit(
            GameEvent.ACTION_RESOLVED,
            source=self,
            player=player,
            player_id=player_id,
            action=action,
        )

        if self.phase == "recruit":
            self.update_all_action_spaces()
            self.recruitment.check_complete()

        return action

    # =========================================================
    # BUY / SELL
    # =========================================================

    def buy_minion(self, player_id, tavern_slot):
        player = self.get_player(player_id)
        tavern = player.tavern

        if tavern_slot is None:
            raise ValueError("Tavern slot is required.")
        if tavern_slot < 0 or tavern_slot >= len(tavern.slots):
            raise ValueError("Invalid Tavern slot.")

        minion = tavern.slots[tavern_slot]
        if minion is None:
            raise ValueError("Tavern slot is empty.")
        if minion.get("cardType") != "minion":
            raise ValueError("Tavern slot does not contain a minion.")
        if len(player.hand) >= player.MAX_HAND_SIZE:
            raise ValueError("Hand is full.")

        if player.gold < 3:
            raise ValueError("Not enough Gold.")
        # Reserve the purchased card's hand slot before Gold-spent effects can
        # generate cards into that same slot (e.g. Sky Admiral Rogers).
        player.hand.append(minion)
        tavern.slots[tavern_slot] = None
        self.effects.spend_gold(
            player_id,
            3,
            reason="buy_minion",
            source=minion,
        )

        self.events.emit(
            GameEvent.CARD_BOUGHT,
            source=self,
            player=player,
            player_id=player_id,
            card=minion,
            minion=minion,
            tavern_slot=tavern_slot,
            gold_cost=3,
        )

    def buy_spell(self, player_id):
        player = self.get_player(player_id)
        tavern = player.tavern
        spell = getattr(tavern, "spell", None)

        if not isinstance(spell, dict):
            raise ValueError("No Tavern spell is available.")
        if spell.get("cardType") != "spell":
            raise ValueError("Tavern spell slot does not contain a spell.")
        if len(player.hand) >= player.MAX_HAND_SIZE:
            raise ValueError("Hand is full.")

        cost = int(spell.get("manaCost", 0) or 0)
        if player.gold < cost:
            raise ValueError("Not enough Gold.")
        player.hand.append(spell)
        tavern.spell = None
        self.effects.spend_gold(
            player_id,
            cost,
            reason="buy_spell",
            source=spell,
        )

        self.events.emit(
            GameEvent.SPELL_BOUGHT,
            source=self,
            player=player,
            player_id=player_id,
            spell=spell,
            card=spell,
            gold_cost=cost,
        )

    def sell_minion(self, player_id, board_slot):
        player = self.get_player(player_id)

        if board_slot is None:
            raise ValueError("Board slot is required.")
        if board_slot < 0 or board_slot >= len(player.board):
            raise ValueError("Invalid board slot.")

        minion = player.board[board_slot]
        if minion is None:
            raise ValueError("Board slot is empty.")

        sell_value = self.effects.get_sell_value(player_id, minion)
        self.effects.add_gold(player_id, sell_value)

        if self.pool.is_pool_card(minion):
            self.pool.return_card(minion)

        player.board[board_slot] = None

        self.events.emit(
            GameEvent.CARD_SOLD,
            source=self,
            player=player,
            player_id=player_id,
            card=minion,
            minion=minion,
            board_slot=board_slot,
            sell_value=sell_value,
            gold_gained=sell_value,
        )

    # =========================================================
    # TAVERN
    # =========================================================

    def _emit_tavern_card_appearances(self, player_id, before_slots=None):
        player = self.get_player(player_id)
        before_slots = list(before_slots or [])

        for tavern_slot, card in enumerate(player.tavern.slots):
            if card is None:
                continue

            old_card = (
                before_slots[tavern_slot]
                if tavern_slot < len(before_slots)
                else None
            )
            if card is old_card:
                continue

            self.events.emit(
                GameEvent.TAVERN_CARD_APPEARED,
                source=self,
                player=player,
                player_id=player_id,
                card=card,
                tavern_slot=tavern_slot,
            )

    def refresh(self, player_id):
        player = self.get_player(player_id)
        before_slots = list(player.tavern.slots)

        self.effects.pay_refresh_cost(player_id)
        player.tavern.refresh(self.pool)
        self._emit_tavern_card_appearances(player_id, before_slots)

        self.events.emit(
            GameEvent.TAVERN_REFRESHED,
            source=self,
            player=player,
            player_id=player_id,
        )

    def freeze(self, player_id):
        player = self.get_player(player_id)
        player.tavern.freeze()
        self.events.emit(
            GameEvent.TAVERN_FROZEN,
            source=self,
            player=player,
            player_id=player_id,
        )

    def unfreeze(self, player_id):
        player = self.get_player(player_id)
        player.tavern.unfreeze()
        self.events.emit(
            GameEvent.TAVERN_UNFROZEN,
            source=self,
            player=player,
            player_id=player_id,
        )

    def upgrade_tavern(self, player_id):
        player = self.get_player(player_id)
        old_tier = player.tavern_tier
        next_tier = old_tier + 1

        if next_tier not in self.TAVERN_UPGRADE_COSTS:
            raise ValueError("Tavern is already at maximum tier.")

        cost = self.TAVERN_UPGRADE_COSTS[next_tier]
        self.effects.spend_gold(
            player_id,
            cost,
            reason="upgrade_tavern",
        )
        player.upgrade_tavern(next_tier)

        self.events.emit(
            GameEvent.TAVERN_UPGRADED,
            source=self,
            player=player,
            player_id=player_id,
            old_tier=old_tier,
            new_tier=next_tier,
            gold_cost=cost,
        )

    # =========================================================
    # MINION PLAY / SPELL CAST
    # =========================================================

    def play_minion(
        self,
        player_id,
        hand_idx,
        position_idx,
        *,
        target_ref=None,
    ):
        player = self.get_player(player_id)

        if hand_idx is None:
            raise ValueError("Hand position is required.")
        if position_idx is None:
            raise ValueError("Board position is required.")
        if hand_idx < 0 or hand_idx >= len(player.hand):
            raise ValueError("Invalid hand position.")

        card = player.hand[hand_idx]
        if card is None:
            raise ValueError("Hand position is empty.")
        if card.get("cardType") != "minion":
            raise ValueError("Only minions can be played onto the board.")
        if position_idx < 0 or position_idx >= len(player.board):
            raise ValueError("Invalid board position.")

        destination = player.board[position_idx]

        if destination is not None:
            if not self.effects.can_magnetize(card, destination):
                raise ValueError("Board position is occupied.")

            played = player.hand.pop(hand_idx)
            self.effects.magnetize(played, destination)

            self.events.emit(
                GameEvent.CARD_PLAYED,
                source=self,
                player=player,
                player_id=player_id,
                card=played,
                minion=played,
                hand_index=hand_idx,
                position=position_idx,
                board_position=position_idx,
                target=(target_ref.card if target_ref is not None else None),
                target_ref=target_ref,
                magnetic_target=destination,
            )
            return

        played = player.hand.pop(hand_idx)
        player.board[position_idx] = played

        self.events.emit(
            GameEvent.CARD_PLAYED,
            source=self,
            player=player,
            player_id=player_id,
            card=played,
            minion=played,
            hand_index=hand_idx,
            position=position_idx,
            board_position=position_idx,
            target=(target_ref.card if target_ref is not None else None),
            target_ref=target_ref,
        )

    def cast_spell(self, player_id, hand_idx, *, target_ref=None):
        player = self.get_player(player_id)

        if hand_idx is None:
            raise ValueError("Hand position is required.")
        if hand_idx < 0 or hand_idx >= len(player.hand):
            raise ValueError("Invalid hand position.")

        spell = player.hand[hand_idx]
        if not isinstance(spell, dict) or spell.get("cardType") != "spell":
            raise ValueError("Hand position does not contain a spell.")

        spell = player.hand.pop(hand_idx)

        self.events.emit(
            GameEvent.SPELL_CAST,
            source=self,
            player=player,
            player_id=player_id,
            spell=spell,
            card=spell,
            target=(target_ref.card if target_ref is not None else None),
            target_ref=target_ref,
        )
        # Casting a card from hand is also a card-play interaction. Generated
        # casts elsewhere emit SPELL_CAST only and must not count as plays.
        self.events.emit(
            GameEvent.CARD_PLAYED,
            source=self,
            player=player,
            player_id=player_id,
            card=spell,
            hand_index=hand_idx,
            target=(target_ref.card if target_ref is not None else None),
            target_ref=target_ref,
        )

    # =========================================================
    # HERO POWER
    # =========================================================

    def use_hero_power(self, player_id, *, target_ref=None):
        player = self.get_player(player_id)
        hero_power = player.get_hero_power()
        if not isinstance(hero_power, dict):
            raise ValueError("Player has no Hero Power.")

        hero_powers = HeroPowerSystem.for_game(self)
        hero_powers.validate_use(player_id)

        power_id = hero_power.get("id")
        has_target_rule = self.effects.has_target_rule(power_id)
        if has_target_rule:
            context = TargetContext(
                game=self,
                player_id=player_id,
                source_card=hero_power,
                source_zone=EffectZone.HERO_POWER,
                action_kind="hero_power",
            )
            legal_refs = self.effects.get_valid_target_refs(power_id, context)
            legal_keys = {
                (ref.player_id, ref.zone, ref.index)
                for ref in legal_refs
            }
            if target_ref is None or (
                target_ref.player_id,
                target_ref.zone,
                target_ref.index,
            ) not in legal_keys:
                raise ValueError("Invalid Hero Power target.")
            # Resolve the currently-live target from game state so callers
            # cannot smuggle an arbitrary card object behind a legal index.
            target_ref = self.effects.resolve_target_ref(
                target_ref.player_id,
                target_ref.zone,
                target_ref.index,
            )
        elif target_ref is not None:
            raise ValueError("This Hero Power does not take a target.")

        cost = int(player.hero_power_cost or 0)
        self.effects.spend_gold(
            player_id,
            cost,
            reason="hero_power",
            source=hero_power,
        )

        self.events.emit(
            GameEvent.HERO_POWER_USED,
            source=self,
            player=player,
            player_id=player_id,
            hero_power=hero_power,
            gold_cost=cost,
            target=(target_ref.card if target_ref is not None else None),
            target_ref=target_ref,
        )

    # =========================================================
    # REPOSITION
    # =========================================================

    def reposition(self, player_id, from_idx, to_idx):
        player = self.get_player(player_id)

        if from_idx is None or to_idx is None:
            raise ValueError("Reposition requires source and destination.")
        if from_idx < 0 or from_idx >= len(player.board):
            raise ValueError("Invalid source position.")
        if to_idx < 0 or to_idx >= len(player.board):
            raise ValueError("Invalid destination position.")
        if from_idx == to_idx:
            raise ValueError("Source and destination must be different.")
        if player.board[from_idx] is None:
            raise ValueError("Source position is empty.")
        if player.board[to_idx] is None:
            raise ValueError("Destination position is empty.")

        player.board[from_idx], player.board[to_idx] = (
            player.board[to_idx],
            player.board[from_idx],
        )

    # =========================================================
    # STATE
    # =========================================================

    def get_state(self, *, include_private=False):
        """Return public global game state plus optional scheduler internals."""

        state = {
            "round": self.round_number,
            "phase": self.phase,
            "game_over": self.game_over,
            "active_minion_types": self.active_minion_types,
            "alive_player_ids": [
                player.player_id for player in self.get_alive_players()
            ],
            "players": self.players,
        }

        if include_private:
            state["priority_order"] = self.priority_order.copy()
            if self.phase == "recruit":
                state["scheduler"] = {
                    player.player_id: {
                        "remaining_budget": self.scheduler.remaining_budget(player.player_id),
                        "logical_time": self.scheduler.logical_time(player.player_id),
                        "finished": self.scheduler.is_finished(player.player_id),
                    }
                    for player in self.get_alive_players()
                    if self.scheduler.has_player(player.player_id)
                }

        return state
