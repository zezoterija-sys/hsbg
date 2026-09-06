"""Main Hearthstone Battlegrounds game controller.

Bob coordinates game-rule systems. Artificial recruit timing/budget state lives
in RecruitScheduler and is deliberately kept separate from Hearthstone state.
"""

import random

from .actions import ActionType
from .card_effects import register_card_effects
from .combat import Combat
from .dark_gifts import DarkGiftSystem
from .effects import EffectSystem
from .events import EventDispatcher, GameEvent
from .heroes import HEROES
from .lobby import roll_active_minion_types
from .player import Player
from .pool import CardPool
from .recruitment import Recruitment
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

        # Season 14 global Dark Discovery lifecycle. Individual Gift behavior
        # remains ordinary attachment-driven EffectSystem logic.
        self.dark_gifts = DarkGiftSystem(self)

        # Recruitment creates and exposes self.scheduler.
        self.recruitment = Recruitment(self)

        self.combat = Combat(
            self,
            events=self.events,
            rng=self.random,
        )

    # =========================================================
    # GAME INITIALIZATION
    # =========================================================

    def initialize_game(self):
        """Initialize a new game and begin hero selection."""

        # Reinitializing a seeded Bob reproduces the same game stream.
        self.random.seed(self.seed)

        self.round_number = 0
        self.phase = "hero_selection"
        self.game_over = False
        self.last_combat_result = None

        self.events.clear_history()
        self.effects.reset_runtime_state_for_new_game()
        self.dark_gifts.reset()

        # Minion types are public game state and must be selected before hero
        # offers and before any Tavern cards are drawn.
        self.active_minion_types = roll_active_minion_types(self.random)

        self.pool = CardPool(
            cards_file=str(self.pool.cards_file),
            rng=self.random,
            active_minion_types=self.active_minion_types,
        )

        self.combat = Combat(
            self,
            events=self.events,
            rng=self.random,
        )

        self.scheduler.clear()
        self.hero_pool = self._solos_hero_ids()
        self.create_players()
        self.generate_priority_order()

        self.events.emit(
            GameEvent.GAME_START,
            source=self,
            player_count=self.PLAYER_COUNT,
            active_minion_types=self.active_minion_types,
        )
        self.events.emit(
            GameEvent.HERO_SELECTION_START,
            source=self,
            priority_order=self.priority_order.copy(),
            active_minion_types=self.active_minion_types,
        )

        self.prepare_hero_selection()

    def create_players(self):
        self.players = [Player(player_id) for player_id in range(self.PLAYER_COUNT)]

    # =========================================================
    # PLAYERS
    # =========================================================

    def get_player(self, player_id):
        if player_id < 0 or player_id >= len(self.players):
            raise ValueError("Invalid player ID.")
        return self.players[player_id]

    def is_player_active(self, player_id):
        return not self.get_player(player_id).eliminated

    def get_alive_players(self):
        return [player for player in self.players if not player.eliminated]

    # =========================================================
    # PRIVATE RESOLUTION PRIORITY
    # =========================================================

    def generate_priority_order(self):
        """Generate a seeded private resolution order."""

        self.priority_order = list(range(self.PLAYER_COUNT))
        self.random.shuffle(self.priority_order)

    def get_priority_position(self, player_id):
        self.get_player(player_id)
        try:
            return self.priority_order.index(player_id)
        except ValueError as exc:
            raise ValueError(
                f"Player {player_id} is missing from priority order."
            ) from exc

    # =========================================================
    # HERO SELECTION
    # =========================================================

    def prepare_hero_selection(self):
        """Give every player four unique hero choices in priority order."""

        available_heroes = list(self.hero_pool)

        for player_id in self.priority_order:
            player = self.get_player(player_id)

            if len(available_heroes) < 4:
                raise ValueError("Not enough heroes available for hero selection.")

            choices = self.random.sample(available_heroes, 4)
            player.hero_choices = choices

            for hero_id in choices:
                available_heroes.remove(hero_id)

    def _solos_hero_ids(self):
        return [
            hero_id for hero_id in HEROES
            if (definition := self.pool.card_definitions_by_id.get(hero_id))
            and definition.get("pool") is True
            and not definition.get("isDuosOnly", False)
        ]

    def choose_hero(self, player_id, hero_id):
        """Choose one offered hero. Hero selection is not recruit AP."""

        player = self.get_player(player_id)

        if self.phase != "hero_selection":
            raise ValueError("It is not hero selection.")
        if player.hero is not None:
            raise ValueError("Player already selected a hero.")
        if hero_id not in player.hero_choices:
            raise ValueError("That hero was not offered to this player.")

        player.set_hero(hero_id)

        if hero_id in self.hero_pool:
            self.hero_pool.remove(hero_id)

        for other_hero in player.hero_choices:
            if other_hero != hero_id and other_hero not in self.hero_pool:
                self.hero_pool.append(other_hero)

        player.hero_choices = []

        self.events.emit(
            GameEvent.HERO_SELECTED,
            source=self,
            player=player,
            player_id=player_id,
            hero_id=hero_id,
        )

        self.check_hero_selection_complete()

    def check_hero_selection_complete(self):
        if any(player.hero is None for player in self.players):
            return
        self.start_recruit_phase()

    # =========================================================
    # RECRUITMENT / COMBAT LOOP
    # =========================================================

    def start_recruit_phase(self):
        if self.game_over:
            return

        before_taverns = {
            player.player_id: list(player.tavern.slots)
            for player in self.players
            if hasattr(player, "tavern")
        }

        self.recruitment.start()

        for player in self.players:
            if not hasattr(player, "tavern"):
                continue
            self._emit_tavern_card_appearances(
                player.player_id,
                before_taverns.get(player.player_id, []),
            )

    def end_recruit_phase(self):
        if self.game_over:
            return
        return self.combat_phase()

    def combat_phase(self):
        self.phase = "combat"
        result = self.combat.run_round()
        self.last_combat_result = result

        if result.game_over:
            self.game_over = True
            self.phase = "game_over"
            return result

        self.start_recruit_phase()
        return result

    # =========================================================
    # ACTION SPACE
    # =========================================================

    def update_action_space(self, player_id):
        player = self.get_player(player_id)
        player.action_space.generate_for_player(
            player=player,
            game_state=self,
        )

    def update_all_action_spaces(self):
        for player in self.players:
            self.update_action_space(player.player_id)

    def get_player_action_space(self, player_id):
        return self.get_player(player_id).action_space.get_legal_actions()

    # =========================================================
    # ACTION EXECUTION
    # =========================================================

    def _has_pending_choice(self, player_id):
        return self.effects.get_pending_choice(player_id) is not None

    def _validate_action(self, player_id, action):
        """Validate an action against the shared pre-action state."""

        player = self.get_player(player_id)
        if player.eliminated:
            raise ValueError("Eliminated player cannot act.")

        if not player.action_space.is_legal_action(action):
            raise ValueError(f"Illegal action for player {player_id}: {action}")

        if self.phase == "recruit" and self.scheduler.has_player(player_id):
            eligible = set(self.recruitment.eligible_player_ids())
            if player_id not in eligible:
                raise ValueError(
                    f"Player {player_id} is not eligible at the current logical time."
                )

            if not self.scheduler.can_submit(
                player_id,
                action,
                pending_choice=self._has_pending_choice(player_id),
            ):
                raise ValueError(
                    f"Recruit scheduler rejected player {player_id}: {action}"
                )

    def _execute_validated_action(self, player_id, action):
        """Execute an action already validated against the pre-action state."""

        player = self.get_player(player_id)

        # Commit artificial interaction time before resolving triggered effects.
        # This preserves the previous useful invariant without making the budget
        # a Hearthstone Player resource.
        if self.phase == "recruit" and self.scheduler.has_player(player_id):
            self.scheduler.commit_action(player_id, action)
        elif action.action_type == ActionType.END_TURN:
            player.end_turn()
        elif action.interaction_cost:
            # Compatibility for isolated legacy tests without Recruitment.
            player.spend_ap(action.interaction_cost)

        if action.action_type != ActionType.END_TURN:
            self.resolve_action(player_id, action)

        self.events.emit(
            GameEvent.ACTION_RESOLVED,
            source=self,
            player=player,
            player_id=player_id,
            action=action,
        )

    def execute_action(self, player_id, action):
        """Execute one scheduler-eligible action immediately."""

        self._validate_action(player_id, action)
        self._execute_validated_action(player_id, action)
        self.update_all_action_spaces()
        self.recruitment.check_complete()

    def resolve_action_batch(self, submissions):
        """Resolve one logical-time batch from a shared pre-action state.

        Every submission is validated before any is executed. The private seeded
        phase priority is used only to make shared-state races deterministic.
        """

        if not submissions:
            return []

        seen_players = set()
        for player_id, action in submissions:
            if player_id in seen_players:
                raise ValueError(
                    f"Player {player_id} submitted multiple actions in one batch."
                )
            seen_players.add(player_id)
            self._validate_action(player_id, action)

        if self.phase == "recruit":
            ordered_submissions = self.scheduler.order_batch(
                submissions,
                self.priority_order,
            )
        else:
            ordered_submissions = sorted(
                submissions,
                key=lambda submission: self.get_priority_position(submission[0]),
            )

        for player_id, action in ordered_submissions:
            self._execute_validated_action(player_id, action)

        self.update_all_action_spaces()
        self.recruitment.check_complete()
        return ordered_submissions

    def execute_colliding_actions(self, submissions):
        """Deprecated compatibility alias for ``resolve_action_batch``."""

        return self.resolve_action_batch(submissions)

    # =========================================================
    # ACTION ROUTING
    # =========================================================

    def _target_ref_from_action(self, player_id, action):
        if action.effect_target_idx is None:
            return None

        target_player_id = (
            action.effect_target_player_id
            if action.effect_target_player_id is not None
            else player_id
        )
        target_zone = (
            action.effect_target_zone
            if action.effect_target_zone is not None
            else "board"
        )

        return self.effects.resolve_target_ref(
            target_player_id,
            target_zone,
            action.effect_target_idx,
        )

    def resolve_action(self, player_id, action):
        action_type = action.action_type
        target_ref = self._target_ref_from_action(player_id, action)

        if action_type == ActionType.BUY_MINION:
            self.buy_minion(player_id, action.target_idx)
        elif action_type == ActionType.BUY_SPELL:
            self.buy_spell(player_id)
        elif action_type == ActionType.SELL_MINION:
            self.sell_minion(player_id, action.target_idx)
        elif action_type == ActionType.PLAY_MINION:
            self.play_minion(
                player_id,
                action.target_idx,
                action.position_idx,
                target_ref=target_ref,
            )
        elif action_type == ActionType.CAST_SPELL:
            self.cast_spell(
                player_id,
                action.target_idx,
                target_ref=target_ref,
            )
        elif action_type == ActionType.HERO_POWER:
            self.use_hero_power(player_id, target_ref=target_ref)
        elif action_type == ActionType.ACTIVATE:
            self.effects.resolve_activate(
                player_id,
                action.target_idx,
                target_ref=target_ref,
            )
        elif action_type == ActionType.DARK_GIFT:
            self.dark_gifts.use(player_id)
        elif action_type == ActionType.CHOOSE_OPTION:
            self.effects.resolve_choice(player_id, action.option_idx)
        elif action_type == ActionType.REFRESH:
            self.refresh(player_id)
        elif action_type == ActionType.FREEZE:
            self.freeze(player_id)
        elif action_type == ActionType.UNFREEZE:
            self.unfreeze(player_id)
        elif action_type == ActionType.UPGRADE_TAVERN:
            self.upgrade_tavern(player_id)
        elif action_type == ActionType.REPOSITION:
            self.reposition(player_id, action.target_idx, action.position_idx)
        else:
            raise ValueError(f"Unsupported action: {action_type}")

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
        cost = player.hero_power_cost
        hero_power = player.get_hero_power()

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
