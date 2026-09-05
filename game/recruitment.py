"""
Recruitment phase system.

Handles:
- Starting recruit phases
- Hearthstone recruit resources (Gold)
- Private simulator interaction scheduling
- Priority generation for deterministic shared-state resolution
- Tavern preparation order
- Turn-start / turn-end events
- Recruit-phase completion

Only living players participate in recruitment.
"""

from .events import GameEvent
from .scheduler import RecruitScheduler


class Recruitment:
    """Controls the recruit phase."""

    STARTING_GOLD = 3
    MAX_GOLD = 10
    GOLD_INCREASE_PER_ROUND = 1

    RECRUIT_INTERACTION_BUDGET = 100
    # Backward-compatible name for external tools/tests. This is not a game AP.
    RECRUIT_AP = RECRUIT_INTERACTION_BUDGET

    def __init__(self, bob):
        self.bob = bob
        self.scheduler = RecruitScheduler(
            interaction_budget=self.RECRUIT_INTERACTION_BUDGET
        )
        # Public engine handle for ActionSpace/AI controllers. The scheduler
        # remains simulator-control state and must not be exposed in observations.
        self.bob.scheduler = self.scheduler

    # =========================================================
    # START RECRUIT PHASE
    # =========================================================

    def start(self):
        """
        Start a new recruit phase.

        Order:
        1. Increase round
        2. Enter recruit phase
        3. Generate private deterministic player priority
        4. Reset living player resources + scheduler state
        5. Prepare living Taverns in priority order
        6. Emit RECRUIT_START
        7. Emit TURN_START for each living player
        8. Generate legal actions
        """

        if self.bob.game_over:
            return

        alive_players = self.get_alive_players()

        if len(alive_players) <= 1:
            raise RuntimeError(
                "Cannot start recruitment with fewer than two living players."
            )

        self.bob.round_number += 1
        self.bob.phase = "recruit"

        # New priority before anything that draws from the shared Tavern pool.
        self.generate_priority()
        self.prepare_players()
        self.refresh_taverns()

        self.bob.events.emit(
            GameEvent.RECRUIT_START,
            source=self,
            round_number=self.bob.round_number,
            priority_order=self.bob.priority_order.copy(),
            alive_player_ids=[
                player.player_id
                for player in alive_players
            ],
        )

        # Taverns/resources already exist. Start-of-turn effects resolve before
        # legal actions are generated, in the phase's private resolution order.
        for player_id in self.bob.priority_order:
            player = self.bob.get_player(player_id)

            if player.eliminated:
                continue

            self.bob.events.emit(
                GameEvent.TURN_START,
                source=self,
                player_id=player_id,
                round_number=self.bob.round_number,
            )

        self.bob.update_all_action_spaces()

    # =========================================================
    # ALIVE PLAYERS
    # =========================================================

    def get_alive_players(self):
        """Return players still participating in the game."""

        return [
            player
            for player in self.bob.players
            if not player.eliminated
        ]

    # =========================================================
    # PRIORITY
    # =========================================================

    def generate_priority(self):
        """Generate a new private random resolution order."""

        self.bob.generate_priority_order()

    # =========================================================
    # GOLD
    # =========================================================

    def calculate_gold(self):
        """Calculate base Gold for this recruit phase."""

        return min(
            self.STARTING_GOLD
            + (
                self.bob.round_number - 1
            )
            * self.GOLD_INCREASE_PER_ROUND,
            self.MAX_GOLD,
        )

    # =========================================================
    # PLAYER / SCHEDULER PREPARATION
    # =========================================================

    def prepare_players(self):
        """Reset recruit resources and private scheduling state."""

        gold = self.calculate_gold()
        alive_players = self.get_alive_players()

        self.scheduler.begin_phase(
            player.player_id for player in alive_players
        )

        # Bind every Player once so legacy ``ap``/``waiting`` reads become
        # compatibility views over scheduler state during live recruit phases.
        for player in self.bob.players:
            player.bind_recruit_scheduler(self.scheduler)

        for player in alive_players:
            player.reset_for_recruit_phase(
                gold=gold,
            )

    def pending_choice_player_ids(self):
        """Return living seats with mandatory zero-cost continuations."""

        effects = getattr(self.bob, "effects", None)
        if effects is None:
            return ()

        return tuple(
            player.player_id
            for player in self.get_alive_players()
            if effects.get_pending_choice(player.player_id) is not None
        )

    def eligible_player_ids(self):
        """Seats that should make the next recruit decisions simultaneously."""

        alive_ids = [player.player_id for player in self.get_alive_players()]
        return self.scheduler.eligible_player_ids(
            alive_ids,
            pending_choice_player_ids=self.pending_choice_player_ids(),
        )

    # =========================================================
    # TAVERN PREPARATION
    # =========================================================

    def refresh_taverns(self):
        """Prepare living Taverns in player-priority order."""

        for player_id in self.bob.priority_order:
            player = self.bob.get_player(
                player_id
            )

            if player.eliminated:
                continue

            tavern = player.tavern

            tavern.set_tier(
                player.tavern_tier
            )

            tavern.refresh_for_new_recruit_phase(
                self.bob.pool
            )

    # =========================================================
    # TURN-END EVENT
    # =========================================================

    def _emit_turn_end_once(self, player):
        """Emit TURN_END once for this player in this round."""

        if (
            getattr(
                player,
                "_turn_end_event_round",
                None,
            )
            == self.bob.round_number
        ):
            return

        player._turn_end_event_round = (
            self.bob.round_number
        )

        self.bob.events.emit(
            GameEvent.TURN_END,
            source=self,
            player_id=player.player_id,
            round_number=self.bob.round_number,
        )

    # =========================================================
    # END TURN
    # =========================================================

    def player_end_turn(self, player_id):
        """End recruitment for one player."""

        player = self.bob.get_player(
            player_id
        )

        if self.bob.phase != "recruit":
            raise ValueError(
                "Player can only end their turn during recruitment."
            )

        if player.eliminated:
            raise ValueError(
                "Eliminated player cannot end a recruit turn."
            )

        # A mandatory choice must be resolved before the player is allowed to
        # finish recruitment.
        effects = getattr(
            self.bob,
            "effects",
            None,
        )

        if (
            effects is not None
            and effects.get_pending_choice(
                player_id
            )
            is not None
        ):
            raise ValueError(
                "Player must resolve the pending choice "
                "before ending their turn."
            )

        self.scheduler.finish_player(player_id, "end_turn")

        self.bob.update_action_space(
            player_id
        )

        self.check_complete()

    # =========================================================
    # COMPLETION
    # =========================================================

    def check_complete(self):
        """
        Process seats that have finished recruitment and end the phase once
        every living scheduler seat is finished and all mandatory choices are
        resolved.
        """

        if self.bob.phase != "recruit":
            return False

        alive_players = (
            self.get_alive_players()
        )

        if not alive_players:
            return False

        pending_choice_players = set(
            self.pending_choice_player_ids()
        )

        # Do not emit TURN_END while a mandatory continuation is open, even if
        # the interaction budget was exhausted by the action that opened it.
        for player in alive_players:
            if (
                self.scheduler.is_finished(player.player_id)
                and player.player_id not in pending_choice_players
            ):
                self._emit_turn_end_once(
                    player
                )

        if pending_choice_players:
            return False

        if not all(
            self.scheduler.is_finished(player.player_id)
            for player in alive_players
        ):
            return False

        self.bob.events.emit(
            GameEvent.RECRUIT_END,
            source=self,
            round_number=self.bob.round_number,
            alive_player_ids=[
                player.player_id
                for player in alive_players
            ],
        )

        self.bob.end_recruit_phase()

        return True