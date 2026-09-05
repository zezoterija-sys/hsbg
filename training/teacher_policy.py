"""Generic rule teacher used only to warm-start Brain B.

The teacher is intentionally shallow. It does not know hidden state, card tier
lists, compositions, or opponent private information. It sees exactly the same
AgentObservation + legal-action set as an agent and teaches broad sanity:
- resolve mandatory choices,
- play minions already bought,
- build a board before wasting resources,
- buy broadly reasonable visible minions,
- take broadly sensible Tavern upgrades,
- avoid gratuitous selling/refresh loops,
- stop when little productive value remains.

The goal is not to encode strong Battlegrounds strategy. It is to keep the
neural policy from starting from completely random behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Any, Mapping, Sequence

from agents.observation import AgentObservation
from game.actions import Action


@dataclass(frozen=True)
class TeacherPolicyConfig:
    label_smoothing: float = 0.02

    # Coarse upgrade curve. Target tier N becomes increasingly attractive at
    # or after this recruit round, provided the player has some board presence.
    upgrade_round_t2: int = 2
    upgrade_round_t3: int = 5
    upgrade_round_t4: int = 7
    upgrade_round_t5: int = 9
    upgrade_round_t6: int = 11

    # Hard guard against repeated legal no-op-ish actions. This is a teacher
    # behavior limit only; it does not change the simulator's 100-AP rule.
    max_actions_per_turn: int = 24

    def __post_init__(self) -> None:
        if not 0.0 <= self.label_smoothing < 1.0:
            raise ValueError("label_smoothing must be in [0, 1).")
        if self.max_actions_per_turn <= 0:
            raise ValueError("max_actions_per_turn must be positive.")


@dataclass(frozen=True)
class TeacherDecision:
    action: Action
    policy_target: tuple[float, ...]
    scores: tuple[float, ...]


class BasicTeacherPolicy:
    """Deterministic-by-score generic teacher with seeded tie-breaking."""

    def __init__(
        self,
        config: TeacherPolicyConfig | None = None,
    ) -> None:
        self.config = config or TeacherPolicyConfig()

    def decide(
        self,
        observation: AgentObservation,
        legal_actions: Sequence[Action],
        rng: random.Random,
        *,
        action_type_counts: Mapping[str, int] | None = None,
        actions_taken_this_turn: int = 0,
    ) -> TeacherDecision:
        actions = tuple(legal_actions)
        if not actions:
            raise ValueError("legal_actions cannot be empty.")

        counts = dict(action_type_counts or {})

        # Absolute termination guard for teacher-data generation. END_TURN is
        # zero AP and should always exist in normal recruit states. Mandatory
        # CHOOSE_OPTION still takes priority because the engine requires it.
        mandatory_indices = [
            index
            for index, action in enumerate(actions)
            if self._action_name(action) == "choose_option"
        ]
        end_indices = [
            index
            for index, action in enumerate(actions)
            if self._action_name(action) == "end_turn"
        ]

        if mandatory_indices:
            candidate_indices = mandatory_indices
        elif (
            actions_taken_this_turn >= self.config.max_actions_per_turn
            and end_indices
        ):
            candidate_indices = end_indices
        else:
            candidate_indices = list(range(len(actions)))

        raw_scores = [
            self.score_action(observation, action, actions)
            for action in actions
        ]
        scores = tuple(
            score + self._repeat_adjustment(action, counts)
            for action, score in zip(actions, raw_scores)
        )

        best = max(scores[index] for index in candidate_indices)
        best_indices = [
            index
            for index in candidate_indices
            if math.isclose(scores[index], best, rel_tol=0.0, abs_tol=1e-9)
        ]
        chosen_index = rng.choice(best_indices)

        target = self._policy_target(len(actions), chosen_index)

        return TeacherDecision(
            action=actions[chosen_index],
            policy_target=target,
            scores=scores,
        )

    def score_action(
        self,
        observation: AgentObservation,
        action: Action,
        legal_actions: Sequence[Action],
    ) -> float:
        view = observation.self_player
        name = getattr(action.action_type, "value", str(action.action_type))

        board_count = self._count_cards(view.board)
        hand_minions = self._count_minions(view.hand)
        board_space = max(0, 7 - board_count)
        gold = max(0, int(view.gold))
        round_number = max(1, int(observation.round_number))
        tier = max(1, int(view.tavern_tier))
        legal_names = {
            getattr(item.action_type, "value", str(item.action_type))
            for item in legal_actions
        }

        # Mandatory Discover / Choose One resolution should never be delayed.
        if name == "choose_option":
            return 1000.0 + self._card_quality(
                self._choice_option(observation, action)
            )

        # Playing a minion already paid for is almost always basic good hygiene.
        if name == "play_minion":
            card = self._zone_card(view.hand, action.target_idx)
            return 120.0 + self._card_quality(card) + 3.0 * board_space

        if name == "buy_minion":
            card = self._zone_card(view.tavern_slots, action.target_idx)
            score = 72.0 + self._card_quality(card)
            if board_count + hand_minions < 7:
                score += 18.0
            if board_count == 0:
                score += 18.0
            if gold == 3:
                score += 5.0
            return score

        if name == "cast_spell":
            # Legal-action generation already ensures the spell can be cast.
            # Prefer using held resources before refreshing/selling.
            return 58.0 + self._card_quality(
                self._zone_card(view.hand, action.target_idx)
            )

        if name == "buy_spell":
            # Useful, but generic minion board development comes first.
            return 45.0 + self._card_quality(view.tavern_spell) * 0.35

        if name == "activate":
            return 43.0 + self._card_quality(
                self._zone_card(view.board, action.target_idx)
            ) * 0.15

        if name == "hero_power":
            cost = max(0, int(getattr(view, "hero_power_cost", 0) or 0))
            score = 30.0
            if cost == 0:
                score += 18.0
            elif cost <= 1:
                score += 8.0
            if board_count == 0 and "buy_minion" in legal_names:
                score -= 12.0
            return score

        if name == "upgrade_tavern":
            target_tier = min(6, tier + 1)
            target_round = self._upgrade_target_round(target_tier)
            overdue = round_number - target_round
            score = 20.0 + max(-12.0, min(24.0, overdue * 4.0))

            # Do not teach an empty-board greed curve.
            if board_count == 0:
                score -= 35.0
            elif board_count >= min(4, tier + 1):
                score += 12.0

            # If a minion is already in hand and can be played, do that first.
            if board_space > 0 and hand_minions > 0 and "play_minion" in legal_names:
                score -= 30.0
            return score

        if name == "refresh":
            # Refreshing is the easiest random policy loop. It should be a
            # fallback search action, not something preferred over development.
            score = 5.0
            if "play_minion" in legal_names:
                score -= 45.0
            if "buy_minion" in legal_names:
                score -= 28.0
            if gold <= 2:
                score -= 20.0
            if board_count >= 4 and gold >= 4:
                score += 10.0
            return score

        if name == "sell_minion":
            # Never teach "selling is bad" as an absolute rule, but make it a
            # strong last resort absent any strategic card-specific knowledge.
            score = -45.0
            if board_count <= 1:
                score -= 40.0
            if board_count == 7 and hand_minions > 0:
                score += 22.0
            return score

        if name == "freeze":
            # Mildly useful when the shop contains visible minions but there is
            # not enough gold to buy one now.
            shop_count = self._count_cards(view.tavern_slots)
            return 12.0 if shop_count and gold < 3 else 2.0

        if name == "unfreeze":
            return 7.0

        if name == "reposition":
            # No combat heuristic here. Repositioning without matchup/card
            # knowledge should not consume lots of AP in the seed teacher.
            return -8.0

        if name == "end_turn":
            score = 18.0 + 2.5 * board_count

            # Strongly discourage the exact failure mode we observed: ending an
            # empty turn while enough gold/shop actions are available.
            if board_count == 0:
                score -= 55.0
                if gold >= 3 and "buy_minion" in legal_names:
                    score -= 35.0

            if board_space > 0 and hand_minions > 0 and "play_minion" in legal_names:
                score -= 70.0

            productive = legal_names & {
                "play_minion",
                "buy_minion",
                "cast_spell",
                "buy_spell",
                "upgrade_tavern",
                "activate",
                "hero_power",
            }
            if not productive:
                score += 55.0

            # Ending with little unusable gold is fine; ending with a pile of
            # spendable gold should be less attractive.
            if gold == 0:
                score += 28.0
            elif gold == 1:
                score += 20.0
            elif gold == 2:
                score += 10.0
            elif gold >= 4:
                score -= 18.0

            return score

        # Unknown future action types remain selectable, just not preferred by
        # the basic teacher until deliberately modeled.
        return 0.0

    def _repeat_adjustment(
        self,
        action: Action,
        counts: Mapping[str, int],
    ) -> float:
        """Discourage generic teacher loops without changing legal actions."""
        name = self._action_name(action)
        used = max(0, int(counts.get(name, 0) or 0))

        if used <= 0:
            return 0.0

        # These are the common loop sources. A shallow generic teacher does not
        # need to teach repeated use when it lacks card-specific strategy.
        if name == "hero_power":
            return -120.0 * used
        if name == "activate":
            return -80.0 * used
        if name in {"freeze", "unfreeze"}:
            return -150.0 * used
        if name == "reposition":
            return -150.0 * used

        # Multiple refreshes can be sensible, so make them progressively less
        # attractive rather than banning them outright.
        if name == "refresh":
            return -18.0 * used

        return 0.0

    def _policy_target(
        self,
        action_count: int,
        chosen_index: int,
    ) -> tuple[float, ...]:
        smoothing = float(self.config.label_smoothing)
        base = smoothing / action_count
        target = [base] * action_count
        target[chosen_index] += 1.0 - smoothing
        return tuple(target)

    @staticmethod
    def _action_name(action: Action) -> str:
        return getattr(
            action.action_type,
            "value",
            str(action.action_type),
        )

    def _upgrade_target_round(self, target_tier: int) -> int:
        return {
            2: self.config.upgrade_round_t2,
            3: self.config.upgrade_round_t3,
            4: self.config.upgrade_round_t4,
            5: self.config.upgrade_round_t5,
            6: self.config.upgrade_round_t6,
        }.get(int(target_tier), 99)

    @staticmethod
    def _count_cards(cards: Any) -> int:
        try:
            return sum(card is not None for card in cards)
        except TypeError:
            return 0

    @staticmethod
    def _count_minions(cards: Any) -> int:
        total = 0
        try:
            iterator = iter(cards)
        except TypeError:
            return 0
        for card in iterator:
            if not isinstance(card, dict):
                continue
            if str(card.get("cardType", "minion")).lower() == "minion":
                total += 1
        return total

    @staticmethod
    def _zone_card(zone: Any, index: Any) -> dict[str, Any] | None:
        if not isinstance(index, int):
            return None
        try:
            card = zone[index]
        except (IndexError, TypeError, KeyError):
            return None
        return card if isinstance(card, dict) else None

    @staticmethod
    def _choice_option(
        observation: AgentObservation,
        action: Action,
    ) -> dict[str, Any] | None:
        pending = observation.pending_choice
        option_idx = getattr(action, "option_idx", None)
        if pending is None or not isinstance(option_idx, int):
            return None
        if not 0 <= option_idx < len(pending.options):
            return None
        option = pending.options[option_idx]
        return option if isinstance(option, dict) else None

    @staticmethod
    def _card_quality(card: Any) -> float:
        if not isinstance(card, dict):
            return 0.0
        tier = max(0, int(card.get("tier", 0) or 0))
        attack = max(0, int(card.get("attack", 0) or 0))
        health = max(0, int(card.get("health", 0) or 0))
        golden = bool(card.get("golden", False))
        # Generic visible-stat signal only. No card IDs, tribe tierlists, or
        # hand-authored card-specific strategy.
        return (
            3.0 * tier
            + 0.18 * min(60, attack + health)
            + (5.0 if golden else 0.0)
        )
