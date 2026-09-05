"""
Thinking budget for AI agents in Hearthstone Battlegrounds.

The thinking budget is separate from AP (Action Points).
It tracks MCTS simulations available to the agent per decision
and per recruit phase.

This class is deterministic and does not use wall-clock time
or hardware-dependent limits.
"""


class ThinkingBudget:
    """
    Tracks MCTS simulation budget for an agent.

    Budget is reset at the start of each recruit phase.

    Each decision can use at most the per-decision limit,
    additionally constrained by the remaining phase budget.
    """

    DEFAULT_PER_DECISION_LIMIT = 200
    DEFAULT_PHASE_BUDGET = 5000

    def __init__(
        self,
        per_decision_limit: int = DEFAULT_PER_DECISION_LIMIT,
        phase_budget: int = DEFAULT_PHASE_BUDGET,
    ):
        """
        Initialize thinking budget.

        Args:
            per_decision_limit:
                Maximum simulations for one decision.

            phase_budget:
                Maximum simulations for the entire recruit phase.
        """

        if per_decision_limit <= 0:
            raise ValueError(
                "per_decision_limit must be positive."
            )

        if phase_budget <= 0:
            raise ValueError(
                "phase_budget must be positive."
            )

        self.per_decision_limit = per_decision_limit
        self.phase_budget_max = phase_budget

        self.phase_simulations_used = 0
        self.phase_simulations_remaining = phase_budget

    # =========================================================
    # RECRUIT PHASE
    # =========================================================

    def reset_recruit_phase(self) -> None:
        """Reset the thinking budget for a new recruit phase."""

        self.phase_simulations_used = 0
        self.phase_simulations_remaining = (
            self.phase_budget_max
        )

    # =========================================================
    # DECISION BUDGET
    # =========================================================

    def get_allowed_simulations(self) -> int:
        """
        Return the maximum simulations allowed for the next decision.

        allowed =
            min(
                per_decision_limit,
                remaining_phase_budget,
            )
        """

        return min(
            self.per_decision_limit,
            self.phase_simulations_remaining,
        )

    def has_search_budget(self) -> bool:
        """Return True if MCTS may still perform simulations."""

        return (
            self.phase_simulations_remaining > 0
        )

    # =========================================================
    # RECORDING SIMULATIONS
    # =========================================================

    def record_simulations_used(
        self,
        simulations_used: int,
    ) -> None:
        """
        Record simulations consumed by one MCTS search.

        Raises an error if the search used more simulations
        than were allowed for that decision.
        """

        if simulations_used < 0:
            raise ValueError(
                "simulations_used cannot be negative."
            )

        allowed = self.get_allowed_simulations()

        if simulations_used > allowed:
            raise ValueError(
                f"MCTS exceeded thinking budget: "
                f"used {simulations_used}, "
                f"allowed {allowed}."
            )

        self.phase_simulations_used += (
            simulations_used
        )

        self.phase_simulations_remaining -= (
            simulations_used
        )

    # =========================================================
    # STATE QUERIES
    # =========================================================

    def get_phase_simulations_used(self) -> int:
        """Return simulations used this recruit phase."""

        return self.phase_simulations_used

    def get_phase_simulations_remaining(self) -> int:
        """Return simulations remaining this recruit phase."""

        return self.phase_simulations_remaining

    def get_phase_budget_max(self) -> int:
        """Return the maximum simulations per recruit phase."""

        return self.phase_budget_max

    def get_per_decision_limit(self) -> int:
        """Return the maximum simulations per decision."""

        return self.per_decision_limit

    # =========================================================
    # SUMMARY
    # =========================================================

    def __repr__(self) -> str:
        return (
            f"ThinkingBudget("
            f"used={self.phase_simulations_used}, "
            f"remaining={self.phase_simulations_remaining}, "
            f"per_decision_limit={self.per_decision_limit}"
            f")"
        )