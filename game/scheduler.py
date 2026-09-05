"""Recruit-phase simulation scheduling.

This module owns the artificial interaction/time budget used to stop AI agents
from acting infinitely quickly during a recruit phase. The budget is simulator
infrastructure, not a Hearthstone Battlegrounds resource.

Normal player interactions advance a per-seat logical clock. Seats at the
lowest logical time are eligible to submit the next simultaneous batch.
Mandatory zero-cost choices are continuations of an already-paid interaction
and therefore remain resolvable after the interaction budget reaches zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from .actions import Action, ActionType


@dataclass
class RecruitSeatState:
    """Private scheduling state for one player seat."""

    remaining_budget: int
    logical_time: int = 0
    finished: bool = False
    finish_reason: str | None = None


class RecruitScheduler:
    """Coordinate fair, deterministic recruit-phase interaction batches."""

    DEFAULT_INTERACTION_BUDGET = 100

    def __init__(self, interaction_budget: int = DEFAULT_INTERACTION_BUDGET):
        interaction_budget = int(interaction_budget)
        if interaction_budget < 0:
            raise ValueError("interaction_budget cannot be negative.")

        self.interaction_budget = interaction_budget
        self._states: dict[int, RecruitSeatState] = {}
        self._pending_choice_provider: Callable[[int], bool] | None = None

    # ------------------------------------------------------------------
    # Phase lifecycle
    # ------------------------------------------------------------------

    def begin_phase(self, player_ids: Iterable[int]) -> None:
        """Create fresh scheduling state for every living recruit seat."""

        self._states = {
            int(player_id): RecruitSeatState(
                remaining_budget=self.interaction_budget,
            )
            for player_id in player_ids
        }

    def clear(self) -> None:
        self._states.clear()

    def set_pending_choice_provider(
        self,
        provider: Callable[[int], bool] | None,
    ) -> None:
        """Bind a read-only mandatory-continuation query from the effect system."""

        self._pending_choice_provider = provider

    def has_pending_choice(self, player_id: int) -> bool:
        if self._pending_choice_provider is None:
            return False
        return bool(self._pending_choice_provider(int(player_id)))

    def has_player(self, player_id: int) -> bool:
        return int(player_id) in self._states

    def state_for(self, player_id: int) -> RecruitSeatState:
        try:
            return self._states[int(player_id)]
        except KeyError as exc:
            raise ValueError(
                f"Player {player_id} has no active recruit scheduling state."
            ) from exc

    # ------------------------------------------------------------------
    # Compatibility/read access
    # ------------------------------------------------------------------

    def remaining_budget(self, player_id: int) -> int:
        return self.state_for(player_id).remaining_budget

    def logical_time(self, player_id: int) -> int:
        return self.state_for(player_id).logical_time

    def is_finished(self, player_id: int) -> bool:
        return self.state_for(player_id).finished

    def is_waiting_compat(self, player_id: int) -> bool:
        """Old ``Player.waiting`` view without stranding mandatory choices."""

        state = self.state_for(player_id)
        if not state.finished:
            return False
        return not self.has_pending_choice(player_id)

    def set_remaining_budget(self, player_id: int, amount: int) -> None:
        """Compatibility hook for old AP-oriented tests/tools."""

        amount = int(amount)
        if amount < 0:
            raise ValueError("Interaction budget cannot be negative.")

        state = self.state_for(player_id)
        state.remaining_budget = amount
        if amount == 0 and not state.finished:
            state.finished = True
            state.finish_reason = "budget_exhausted"
        elif amount > 0 and state.finish_reason == "budget_exhausted":
            state.finished = False
            state.finish_reason = None

    # ------------------------------------------------------------------
    # Eligibility
    # ------------------------------------------------------------------

    def eligible_player_ids(
        self,
        player_ids: Iterable[int] | None = None,
        *,
        pending_choice_player_ids: Iterable[int] = (),
    ) -> tuple[int, ...]:
        """Return seats allowed to make the next decision.

        Pending mandatory choices take precedence because they are continuations
        of interactions that already resolved. Otherwise only unfinished seats
        at the minimum logical time are eligible. This gives a clean notion of
        simultaneous recruit actions without exposing scheduler state to agents.
        """

        allowed = (
            {int(player_id) for player_id in player_ids}
            if player_ids is not None
            else set(self._states)
        )

        pending = tuple(
            player_id
            for player_id in sorted({int(pid) for pid in pending_choice_player_ids})
            if player_id in allowed and player_id in self._states
        )
        if pending:
            return pending

        active = [
            player_id
            for player_id in allowed
            if player_id in self._states
            and not self._states[player_id].finished
        ]
        if not active:
            return ()

        minimum_time = min(self._states[player_id].logical_time for player_id in active)
        return tuple(
            player_id
            for player_id in sorted(active)
            if self._states[player_id].logical_time == minimum_time
        )

    def can_submit(
        self,
        player_id: int,
        action: Action,
        *,
        pending_choice: bool = False,
    ) -> bool:
        """Return whether scheduler state permits this action submission."""

        state = self.state_for(player_id)

        if action.action_type == ActionType.CHOOSE_OPTION:
            return bool(pending_choice)

        if state.finished:
            return False

        if action.action_type == ActionType.END_TURN:
            return True

        return state.remaining_budget >= int(action.interaction_cost)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def finish_player(self, player_id: int, reason: str = "end_turn") -> None:
        state = self.state_for(player_id)
        state.finished = True
        state.finish_reason = str(reason)

    def reopen_player(self, player_id: int) -> None:
        """Compatibility helper; normal recruit flow should not reopen a seat."""

        state = self.state_for(player_id)
        if state.remaining_budget <= 0:
            raise ValueError("Cannot reopen a player with no interaction budget.")
        state.finished = False
        state.finish_reason = None

    def commit_action(self, player_id: int, action: Action) -> None:
        """Commit scheduler cost after an action was accepted for a batch."""

        state = self.state_for(player_id)

        if action.action_type == ActionType.END_TURN:
            self.finish_player(player_id, "end_turn")
            return

        cost = int(action.interaction_cost)
        if cost < 0:
            raise ValueError("Interaction cost cannot be negative.")
        if cost == 0:
            return
        if state.finished:
            raise ValueError(f"Player {player_id} is already finished.")
        if state.remaining_budget < cost:
            raise ValueError(
                f"Player {player_id} has {state.remaining_budget} interaction budget, "
                f"needs {cost} for {action}."
            )

        state.remaining_budget -= cost
        state.logical_time += cost

        if state.remaining_budget == 0:
            state.finished = True
            state.finish_reason = "budget_exhausted"

    def consume_budget(self, player_id: int, amount: int = 1) -> None:
        """Compatibility bridge for legacy ``Player.spend_ap`` callers."""

        amount = int(amount)
        if amount < 0:
            raise ValueError("Cannot consume negative interaction budget.")
        if amount == 0:
            return

        state = self.state_for(player_id)
        if state.remaining_budget < amount:
            raise ValueError("Not enough interaction budget.")
        if state.finished:
            raise ValueError(f"Player {player_id} is already finished.")

        state.remaining_budget -= amount
        state.logical_time += amount
        if state.remaining_budget == 0:
            state.finished = True
            state.finish_reason = "budget_exhausted"

    # ------------------------------------------------------------------
    # Batch ordering / validation
    # ------------------------------------------------------------------

    @staticmethod
    def _priority_index(priority_order: Sequence[int]) -> dict[int, int]:
        return {
            int(player_id): index
            for index, player_id in enumerate(priority_order)
        }

    def order_batch(
        self,
        submissions: Sequence[tuple[int, Action]],
        priority_order: Sequence[int],
    ) -> list[tuple[int, Action]]:
        """Order an already-simultaneous batch by private deterministic priority."""

        priority = self._priority_index(priority_order)
        seen: set[int] = set()

        for player_id, _action in submissions:
            player_id = int(player_id)
            if player_id in seen:
                raise ValueError(
                    f"Player {player_id} submitted multiple actions in one batch."
                )
            if player_id not in priority:
                raise ValueError(
                    f"Player {player_id} is missing from the current priority order."
                )
            seen.add(player_id)

        return sorted(
            submissions,
            key=lambda submission: priority[int(submission[0])],
        )
