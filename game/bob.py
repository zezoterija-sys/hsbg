"""
Main game controller.

Bob coordinates the game systems.

Detailed player, tavern, recruitment, action,
combat, and event logic belongs to their respective systems.
"""

from .actions import ActionType
from .combat import Combat
from .events import EventDispatcher, GameEvent
from .heroes import HEROES
from .player import Player
from .pool import CardPool
from .recruitment import Recruitment
from .effects import EffectSystem
from .card_effects import register_card_effects


class Bob:
    """Main game controller."""

    PLAYER_COUNT = 8

    HERO_SELECTION_AP = 1

    TAVERN_UPGRADE_COSTS = {
        2: 5,
        3: 6,
        4: 7,
        5: 10,
        6: 10,
    }

    def __init__(self, cards_file="data/raw/cards.json"):

        self.players = []

        self.round_number = 0
        self.phase = None

        self.priority_order = []

        self.hero_pool = list(
            HEROES.keys()
        )

        self.game_over = False

        # Result of the most recently completed combat phase.
        self.last_combat_result = None

        # =====================================================
        # SHARED SYSTEMS
        # =====================================================

        self.events = EventDispatcher()
        # General executable card / hero / spell effect system.
        # It listens to the same event dispatcher used by the
        # rest of the game.
        self.effects = EffectSystem(
            game=self,
            events=self.events,
        )

        register_card_effects(
                    self.effects
                )

        self.pool = CardPool(
            cards_file=cards_file
        )

        self.recruitment = Recruitment(
            self
        )

        self.combat = Combat(
            self,
            events=self.events,
        )

    # =========================================================
    # GAME INITIALIZATION
    # =========================================================

    def initialize_game(self):
        """Initialize a new game and begin hero selection."""

        self.round_number = 0
        self.phase = "hero_selection"
        self.game_over = False

        self.last_combat_result = None

        self.events.clear_history()

        # Clear per-game effect runtime state while preserving
        # all registered card/effect handlers.
        self.effects.reset_runtime_state_for_new_game()

        # Reset shared card pool.
        self.pool = CardPool(
            cards_file=str(
                self.pool.cards_file
            )
        )

        # Reset combat controller, including ghost history.
        self.combat = Combat(
            self,
            events=self.events,
        )

        # Reset hero pool.
        self.hero_pool = list(
            HEROES.keys()
        )

        self.create_players()

        self.generate_priority_order()

        self.events.emit(
            GameEvent.GAME_START,
            source=self,
            player_count=self.PLAYER_COUNT,
        )

        self.events.emit(
            GameEvent.HERO_SELECTION_START,
            source=self,
            priority_order=(
                self.priority_order.copy()
            ),
        )

        self.prepare_hero_selection()

    def create_players(self):
        """Create the eight Player objects."""

        self.players = [
            Player(player_id)
            for player_id
            in range(self.PLAYER_COUNT)
        ]

    # =========================================================
    # PLAYERS
    # =========================================================

    def get_player(self, player_id):
        """Retrieve a player by ID."""

        if (
            player_id < 0
            or player_id >= len(self.players)
        ):
            raise ValueError(
                "Invalid player ID."
            )

        return self.players[
            player_id
        ]

    def is_player_active(
        self,
        player_id,
    ):
        """Return whether a player is still alive."""

        player = self.get_player(
            player_id
        )

        return not player.eliminated

    def get_alive_players(self):
        """Return all non-eliminated players."""

        return [
            player
            for player in self.players
            if not player.eliminated
        ]

    # =========================================================
    # PRIORITY
    # =========================================================

    def generate_priority_order(self):
        """Generate a random player priority order."""

        import random

        self.priority_order = list(
            range(self.PLAYER_COUNT)
        )

        random.shuffle(
            self.priority_order
        )

    def get_priority_position(
        self,
        player_id,
    ):
        """
        Return a player's current priority position.

        Lower number means higher priority.
        """

        self.get_player(
            player_id
        )

        try:
            return self.priority_order.index(
                player_id
            )

        except ValueError:
            raise ValueError(
                f"Player {player_id} is missing "
                f"from priority order."
            )

    # =========================================================
    # HERO SELECTION
    # =========================================================

    def prepare_hero_selection(self):
        """
        Give every player four unique hero choices.

        Distribution follows player priority.
        """

        import random

        available_heroes = list(
            self.hero_pool
        )

        for player_id in (
            self.priority_order
        ):

            player = self.get_player(
                player_id
            )

            # Hero selection receives exactly 1 AP.
            player.set_ap(
                self.HERO_SELECTION_AP
            )

            if len(available_heroes) < 4:
                raise ValueError(
                    "Not enough heroes available "
                    "for hero selection."
                )

            choices = random.sample(
                available_heroes,
                4,
            )

            player.hero_choices = (
                choices
            )

            for hero_id in choices:
                available_heroes.remove(
                    hero_id
                )

    def choose_hero(
        self,
        player_id,
        hero_id,
    ):
        """Choose one offered hero."""

        player = self.get_player(
            player_id
        )

        if self.phase != "hero_selection":
            raise ValueError(
                "It is not hero selection."
            )

        if player.hero is not None:
            raise ValueError(
                "Player already selected a hero."
            )

        if (
            hero_id
            not in player.hero_choices
        ):
            raise ValueError(
                "That hero was not offered "
                "to this player."
            )

        player.set_hero(
            hero_id
        )

        # Hero selection consumes its one AP.
        player.spend_ap(
            self.HERO_SELECTION_AP
        )

        if hero_id in self.hero_pool:
            self.hero_pool.remove(
                hero_id
            )

        # Return unselected heroes.
        for other_hero in (
            player.hero_choices
        ):

            if (
                other_hero != hero_id
                and other_hero
                not in self.hero_pool
            ):
                self.hero_pool.append(
                    other_hero
                )

        player.hero_choices = []

        self.events.emit(
            GameEvent.HERO_SELECTED,
            source=self,
            player=player,
            player_id=player_id,
            hero_id=hero_id,
        )

        self.check_hero_selection_complete()

    def check_hero_selection_complete(
        self,
    ):
        """Start recruitment once all players selected."""

        for player in self.players:

            if player.hero is None:
                return

        self.start_recruit_phase()

    # =========================================================
    # RECRUITMENT / COMBAT LOOP
    # =========================================================

    def start_recruit_phase(self):
        """Start the next recruit phase."""

        if self.game_over:
            return

        before_taverns = {
            player.player_id: list(player.tavern.slots)
            for player in self.players
            if hasattr(player, "tavern")
        }

        self.recruitment.start()

        # Recruitment owns the automatic start-of-turn Tavern refill.
        # Emit appearance events here for cards that were newly placed
        # during that refill without re-emitting persisted frozen cards.
        for player in self.players:
            if not hasattr(player, "tavern"):
                continue
            self._emit_tavern_card_appearances(
                player.player_id,
                before_taverns.get(player.player_id, []),
            )

    def end_recruit_phase(self):
        """Move from recruitment into combat."""

        if self.game_over:
            return

        return self.combat_phase()

    def combat_phase(self):
        """
        Resolve a complete combat phase.

        If more than one player survives, automatically
        start the next recruit phase.
        """

        self.phase = "combat"

        result = (
            self.combat.run_round()
        )

        self.last_combat_result = (
            result
        )

        if result.game_over:

            self.game_over = True
            self.phase = "game_over"

            return result

        # Continue the game.
        self.start_recruit_phase()

        return result

    # =========================================================
    # ACTION SPACE
    # =========================================================

    def update_action_space(
        self,
        player_id,
    ):
        player = self.get_player(
            player_id
        )

        player.action_space.generate_for_player(
            player=player,
            game_state=self,
        )

    def update_all_action_spaces(self):
        """Regenerate action spaces for every player."""

        for player in self.players:

            self.update_action_space(
                player.player_id
            )

    def get_player_action_space(
        self,
        player_id,
    ):
        player = self.get_player(
            player_id
        )

        return (
            player.action_space
            .get_legal_actions()
        )

    # =========================================================
    # ACTION EXECUTION
    # =========================================================

    def _validate_action(
        self,
        player_id,
        action,
    ):
        """Validate an action against current legal actions."""

        player = self.get_player(
            player_id
        )

        if player.eliminated:
            raise ValueError(
                "Eliminated player cannot act."
            )

        if (
            not player.action_space
            .is_legal_action(action)
        ):
            raise ValueError(
                f"Illegal action for player "
                f"{player_id}: {action}"
            )

    def _execute_validated_action(
        self,
        player_id,
        action,
    ):
        """
        Execute an action already validated against the
        appropriate pre-action state.

        AP is committed before action resolution so triggered
        effects cannot invalidate the action's already-approved
        AP payment.
        """

        player = self.get_player(
            player_id
        )

        if (
            action.action_type
            == ActionType.END_TURN
        ):
            player.end_turn()

        else:
            ap_cost = int(
                action.ap_cost
            )

            if ap_cost < 0:
                raise ValueError(
                    "Action AP cost cannot be negative."
                )

            if player.ap < ap_cost:
                raise ValueError(
                    f"Not enough AP for player {player_id}: "
                    f"have {player.ap}, need {ap_cost}, "
                    f"action={action}"
                )

            # Commit the interaction cost before resolving the
            # action and any triggered effects.
            if ap_cost:
                player.spend_ap(
                    ap_cost
                )

            self.resolve_action(
                player_id,
                action,
            )

        self.events.emit(
            GameEvent.ACTION_RESOLVED,
            source=self,
            player=player,
            player_id=player_id,
            action=action,
        )

    def execute_action(
        self,
        player_id,
        action,
    ):
        """
        Execute one normal action immediately.

        Normal actions resolve in call order.
        """

        self._validate_action(
            player_id,
            action,
        )

        self._execute_validated_action(
            player_id,
            action,
        )

        self.update_all_action_spaces()

        self.recruitment.check_complete()

    def execute_colliding_actions(
        self,
        submissions,
    ):
        """
        Resolve actions known to have occurred simultaneously.

        Normal action call order is ignored only for this
        explicit collision case.

        All actions are validated against the pre-collision
        state, then resolved according to player priority.
        """

        if not submissions:
            return []

        seen_players = set()

        # Validate against pre-collision state.
        for player_id, action in submissions:

            if player_id in seen_players:
                raise ValueError(
                    f"Player {player_id} submitted "
                    f"multiple actions in one collision."
                )

            seen_players.add(
                player_id
            )

            self._validate_action(
                player_id,
                action,
            )

        ordered_submissions = sorted(
            submissions,
            key=lambda submission: (
                self.get_priority_position(
                    submission[0]
                )
            ),
        )

        for (
            player_id,
            action,
        ) in ordered_submissions:

            self._execute_validated_action(
                player_id,
                action,
            )

        self.update_all_action_spaces()

        self.recruitment.check_complete()

        return ordered_submissions

    # =========================================================
    # ACTION ROUTING
    # =========================================================

    def _target_ref_from_action(
        self,
        player_id,
        action,
    ):
        """Resolve an Action's optional effect target."""

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

    def resolve_action(
        self,
        player_id,
        action,
    ):
        action_type = (
            action.action_type
        )

        target_ref = self._target_ref_from_action(
            player_id,
            action,
        )

        if (
            action_type
            == ActionType.BUY_MINION
        ):

            self.buy_minion(
                player_id,
                action.target_idx,
            )

        elif (
            action_type
            == ActionType.BUY_SPELL
        ):

            self.buy_spell(
                player_id
            )

        elif (
            action_type
            == ActionType.SELL_MINION
        ):

            self.sell_minion(
                player_id,
                action.target_idx,
            )

        elif (
            action_type
            == ActionType.PLAY_MINION
        ):

            self.play_minion(
                player_id,
                action.target_idx,
                action.position_idx,
                target_ref=target_ref,
            )

        elif (
            action_type
            == ActionType.CAST_SPELL
        ):

            self.cast_spell(
                player_id,
                action.target_idx,
                target_ref=target_ref,
            )

        elif (
            action_type
            == ActionType.HERO_POWER
        ):

            self.use_hero_power(
                player_id,
                target_ref=target_ref,
            )

        elif (
            action_type
            == ActionType.ACTIVATE
        ):

            self.effects.resolve_activate(
                player_id,
                action.target_idx,
                target_ref=target_ref,
            )

        elif (
            action_type
            == ActionType.CHOOSE_OPTION
        ):

            self.effects.resolve_choice(
                player_id,
                action.option_idx,
            )

        elif (
            action_type
            == ActionType.REFRESH
        ):

            self.refresh(
                player_id
            )

        elif (
            action_type
            == ActionType.FREEZE
        ):

            self.freeze(
                player_id
            )

        elif (
            action_type
            == ActionType.UNFREEZE
        ):

            self.unfreeze(
                player_id
            )

        elif (
            action_type
            == ActionType.UPGRADE_TAVERN
        ):

            self.upgrade_tavern(
                player_id
            )

        elif (
            action_type
            == ActionType.REPOSITION
        ):

            self.reposition(
                player_id,
                action.target_idx,
                action.position_idx,
            )

        else:
            raise ValueError(
                f"Unsupported action: "
                f"{action_type}"
            )

    # =========================================================
    # BUY / SELL
    # =========================================================

    def buy_minion(
        self,
        player_id,
        tavern_slot,
    ):
        """Buy one Tavern minion."""

        player = self.get_player(
            player_id
        )

        tavern = player.tavern

        if tavern_slot is None:
            raise ValueError(
                "Tavern slot is required."
            )

        if (
            tavern_slot < 0
            or tavern_slot
            >= len(tavern.slots)
        ):
            raise ValueError(
                "Invalid Tavern slot."
            )

        minion = (
            tavern.slots[
                tavern_slot
            ]
        )

        if minion is None:
            raise ValueError(
                "Tavern slot is empty."
            )

        if (
            minion.get("cardType")
            != "minion"
        ):
            raise ValueError(
                "Tavern slot does not "
                "contain a minion."
            )

        if (
            len(player.hand)
            >= player.MAX_HAND_SIZE
        ):
            raise ValueError(
                "Hand is full."
            )

        self.effects.spend_gold(
            player_id,
            3,
            reason="buy_minion",
            source=minion,
        )

        player.hand.append(
            minion
        )

        tavern.slots[
            tavern_slot
        ] = None

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

    def buy_spell(
        self,
        player_id,
    ):
        """Buy the Tavern spell currently offered to a player."""

        player = self.get_player(
            player_id
        )
        tavern = player.tavern
        spell = getattr(
            tavern,
            "spell",
            None,
        )

        if not isinstance(spell, dict):
            raise ValueError(
                "No Tavern spell is available."
            )

        if spell.get("cardType") != "spell":
            raise ValueError(
                "Tavern spell slot does not contain a spell."
            )

        if (
            len(player.hand)
            >= player.MAX_HAND_SIZE
        ):
            raise ValueError(
                "Hand is full."
            )

        cost = int(
            spell.get("manaCost", 0)
            or 0
        )

        self.effects.spend_gold(
            player_id,
            cost,
            reason="buy_spell",
            source=spell,
        )

        player.hand.append(
            spell
        )
        tavern.spell = None

        self.events.emit(
            GameEvent.SPELL_BOUGHT,
            source=self,
            player=player,
            player_id=player_id,
            spell=spell,
            card=spell,
            gold_cost=cost,
        )

    def sell_minion(
        self,
        player_id,
        board_slot,
    ):
        """Sell one board minion."""

        player = self.get_player(
            player_id
        )

        if board_slot is None:
            raise ValueError(
                "Board slot is required."
            )

        if (
            board_slot < 0
            or board_slot
            >= len(player.board)
        ):
            raise ValueError(
                "Invalid board slot."
            )

        minion = (
            player.board[
                board_slot
            ]
        )

        if minion is None:
            raise ValueError(
                "Board slot is empty."
            )

        sell_value = (
            self.effects.get_sell_value(
                player_id,
                minion,
            )
        )

        self.effects.add_gold(
            player_id,
            sell_value,
        )

        # Normal pool cards return to the shared pool.
        # Generated/non-pool cards disappear.
        if self.pool.is_pool_card(
            minion
        ):
            self.pool.return_card(
                minion
            )

        player.board[
            board_slot
        ] = None

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

    def _emit_tavern_card_appearances(
        self,
        player_id,
        before_slots=None,
    ):
        """Emit appearance events for newly placed Tavern minions."""

        player = self.get_player(
            player_id
        )
        before_slots = list(
            before_slots or []
        )

        for tavern_slot, card in enumerate(
            player.tavern.slots
        ):
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

    def refresh(
        self,
        player_id,
    ):
        """Refresh the player's Tavern."""

        player = self.get_player(
            player_id
        )

        before_slots = list(
            player.tavern.slots
        )

        self.effects.pay_refresh_cost(
            player_id
        )

        player.tavern.refresh(
            self.pool
        )

        self._emit_tavern_card_appearances(
            player_id,
            before_slots,
        )

        self.events.emit(
            GameEvent.TAVERN_REFRESHED,
            source=self,
            player=player,
            player_id=player_id,
        )

    def freeze(
        self,
        player_id,
    ):
        """Freeze the player's Tavern."""

        player = self.get_player(
            player_id
        )

        player.tavern.freeze()

        self.events.emit(
            GameEvent.TAVERN_FROZEN,
            source=self,
            player=player,
            player_id=player_id,
        )

    def unfreeze(
        self,
        player_id,
    ):
        """Unfreeze the player's Tavern."""

        player = self.get_player(
            player_id
        )

        player.tavern.unfreeze()

        self.events.emit(
            GameEvent.TAVERN_UNFROZEN,
            source=self,
            player=player,
            player_id=player_id,
        )

    def upgrade_tavern(
        self,
        player_id,
    ):
        """Upgrade the player's Tavern."""

        player = self.get_player(
            player_id
        )

        old_tier = (
            player.tavern_tier
        )

        next_tier = (
            old_tier + 1
        )

        if (
            next_tier
            not in self.TAVERN_UPGRADE_COSTS
        ):
            raise ValueError(
                "Tavern is already "
                "at maximum tier."
            )

        cost = (
            self.TAVERN_UPGRADE_COSTS[
                next_tier
            ]
        )

        self.effects.spend_gold(
            player_id,
            cost,
            reason="upgrade_tavern",
        )

        player.upgrade_tavern(
            next_tier
        )

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
        """Play a minion from hand onto the board or Magnetize it."""

        player = self.get_player(
            player_id
        )

        if hand_idx is None:
            raise ValueError(
                "Hand position is required."
            )

        if position_idx is None:
            raise ValueError(
                "Board position is required."
            )

        if (
            hand_idx < 0
            or hand_idx
            >= len(player.hand)
        ):
            raise ValueError(
                "Invalid hand position."
            )

        card = (
            player.hand[
                hand_idx
            ]
        )

        if card is None:
            raise ValueError(
                "Hand position is empty."
            )

        if (
            card.get("cardType")
            != "minion"
        ):
            raise ValueError(
                "Only minions can be "
                "played onto the board."
            )

        if (
            position_idx < 0
            or position_idx
            >= len(player.board)
        ):
            raise ValueError(
                "Invalid board position."
            )

        destination = player.board[
            position_idx
        ]

        # Replacement actions.py can legally route Magnetic minions to an
        # occupied compatible destination, including when the board is full.
        if destination is not None:
            if not self.effects.can_magnetize(
                card,
                destination,
            ):
                raise ValueError(
                    "Board position is occupied."
                )

            played = player.hand.pop(
                hand_idx
            )
            self.effects.magnetize(
                played,
                destination,
            )

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
                target=(
                    target_ref.card
                    if target_ref is not None
                    else None
                ),
                target_ref=target_ref,
                magnetic_target=destination,
            )
            return

        played = player.hand.pop(
            hand_idx
        )

        player.board[
            position_idx
        ] = played

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
            target=(
                target_ref.card
                if target_ref is not None
                else None
            ),
            target_ref=target_ref,
        )

    def cast_spell(
        self,
        player_id,
        hand_idx,
        *,
        target_ref=None,
    ):
        """Cast one spell from hand."""

        player = self.get_player(
            player_id
        )

        if hand_idx is None:
            raise ValueError(
                "Hand position is required."
            )

        if (
            hand_idx < 0
            or hand_idx >= len(player.hand)
        ):
            raise ValueError(
                "Invalid hand position."
            )

        spell = player.hand[
            hand_idx
        ]

        if not isinstance(spell, dict) or spell.get("cardType") != "spell":
            raise ValueError(
                "Hand position does not contain a spell."
            )

        spell = player.hand.pop(
            hand_idx
        )

        self.events.emit(
            GameEvent.SPELL_CAST,
            source=self,
            player=player,
            player_id=player_id,
            spell=spell,
            card=spell,
            target=(
                target_ref.card
                if target_ref is not None
                else None
            ),
            target_ref=target_ref,
        )

    # =========================================================
    # HERO POWER
    # =========================================================

    def use_hero_power(
        self,
        player_id,
        *,
        target_ref=None,
    ):
        """Use the player's hero power."""

        player = self.get_player(
            player_id
        )

        cost = (
            player.hero_power_cost
        )
        hero_power = (
            player.get_hero_power()
        )

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
            target=(
                target_ref.card
                if target_ref is not None
                else None
            ),
            target_ref=target_ref,
        )

    # =========================================================
    # REPOSITION
    # =========================================================

    def reposition(
        self,
        player_id,
        from_idx,
        to_idx,
    ):
        """Swap two occupied board positions."""

        player = self.get_player(
            player_id
        )

        if (
            from_idx is None
            or to_idx is None
        ):
            raise ValueError(
                "Reposition requires source "
                "and destination."
            )

        if (
            from_idx < 0
            or from_idx >= len(player.board)
        ):
            raise ValueError(
                "Invalid source position."
            )

        if (
            to_idx < 0
            or to_idx >= len(player.board)
        ):
            raise ValueError(
                "Invalid destination position."
            )

        if from_idx == to_idx:
            raise ValueError(
                "Source and destination "
                "must be different."
            )

        if (
            player.board[
                from_idx
            ]
            is None
        ):
            raise ValueError(
                "Source position is empty."
            )

        if (
            player.board[
                to_idx
            ]
            is None
        ):
            raise ValueError(
                "Destination position is empty."
            )

        (
            player.board[from_idx],
            player.board[to_idx],
        ) = (
            player.board[to_idx],
            player.board[from_idx],
        )

    # =========================================================
    # STATE
    # =========================================================

    def get_state(self):
        """Return core global game state."""

        return {
            "round": self.round_number,
            "phase": self.phase,
            "priority_order": (
                self.priority_order.copy()
            ),
            "game_over": self.game_over,
            "alive_player_ids": [
                player.player_id
                for player
                in self.get_alive_players()
            ],
            "players": self.players,
        }