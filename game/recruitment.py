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
    RECRUIT_AP = RECRUIT_INTERACTION_BUDGET

    def __init__(self, bob):
        self.bob = bob
        self.scheduler = RecruitScheduler(
            interaction_budget=self.RECRUIT_INTERACTION_BUDGET
        )
        self.scheduler.set_pending_choice_provider(
            lambda player_id: (
                self.bob.effects.get_pending_choice(player_id) is not None
            )
        )
        self.bob.scheduler = self.scheduler

    def start(self):
        """Start a new recruit phase."""

        if self.bob.game_over:
            return

        alive_players = self.get_alive_players()
        if len(alive_players) <= 1:
            raise RuntimeError(
                "Cannot start recruitment with fewer than two living players."
            )

        self.bob.round_number += 1
        self.bob.phase = "recruit"

        self.generate_priority()
        self.prepare_players()
        self.refresh_taverns()

        self.bob.events.emit(
            GameEvent.RECRUIT_START,
            source=self,
            round_number=self.bob.round_number,
            priority_order=self.bob.priority_order.copy(),
            alive_player_ids=[player.player_id for player in alive_players],
        )

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

    def get_alive_players(self):
        return [player for player in self.bob.players if not player.eliminated]

    def generate_priority(self):
        self.bob.generate_priority_order()

    def calculate_gold(self):
        return min(
            self.STARTING_GOLD
            + (self.bob.round_number - 1) * self.GOLD_INCREASE_PER_ROUND,
            self.MAX_GOLD,
        )

    def prepare_players(self):
        """Reset recruit resources and private scheduling state."""

        gold = self.calculate_gold()
        alive_players = self.get_alive_players()

        self.scheduler.begin_phase(
            player.player_id for player in alive_players
        )

        for player in self.bob.players:
            player.bind_recruit_scheduler(self.scheduler)

        for player in alive_players:
            player.reset_for_recruit_phase(gold=gold)

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

    def refresh_taverns(self):
        """Prepare living Taverns in private player-priority order."""

        for player_id in self.bob.priority_order:
            player = self.bob.get_player(player_id)
            if player.eliminated:
                continue

            tavern = player.tavern
            tavern.set_tier(player.tavern_tier)
            tavern.refresh_for_new_recruit_phase(self.bob.pool)

    def _emit_turn_end_once(self, player):
        if getattr(player, "_turn_end_event_round", None) == self.bob.round_number:
            return

        player._turn_end_event_round = self.bob.round_number
        self.bob.events.emit(
            GameEvent.TURN_END,
            source=self,
            player_id=player.player_id,
            round_number=self.bob.round_number,
        )

    def player_end_turn(self, player_id):
        player = self.bob.get_player(player_id)

        if self.bob.phase != "recruit":
            raise ValueError(
                "Player can only end their turn during recruitment."
            )
        if player.eliminated:
            raise ValueError(
                "Eliminated player cannot end a recruit turn."
            )

        if self.bob.effects.get_pending_choice(player_id) is not None:
            raise ValueError(
                "Player must resolve the pending choice before ending their turn."
            )

        self.scheduler.finish_player(player_id, "end_turn")
        self.bob.update_action_space(player_id)
        self.check_complete()

    def check_complete(self):
        """End recruitment after every living seat is effectively finished."""

        if self.bob.phase != "recruit":
            return False

        alive_players = self.get_alive_players()
        if not alive_players:
            return False

        pending_choice_players = set(self.pending_choice_player_ids())

        for player in alive_players:
            if (
                self.scheduler.is_finished(player.player_id)
                and player.player_id not in pending_choice_players
            ):
                self._emit_turn_end_once(player)

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
            alive_player_ids=[player.player_id for player in alive_players],
        )

        self.bob.end_recruit_phase()
        return True
