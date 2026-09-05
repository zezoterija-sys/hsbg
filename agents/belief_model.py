"""
Hidden-information belief sampling for Battlegrounds MCTS.

This module never sees the real hidden game state. It samples plausible hidden
boards, hands, Taverns, and physical-pool occupancy using only:
- AgentObservation,
- public pool rules,
- card definitions in a fresh simulation CardPool,
- the controlled player's own visible cards,
- remembered opponent boards with age.

The goal is not to "fear" a contested pool. Old sightings decay as evidence.
A remembered card is more likely to remain in an opponent's sampled board when
the observation is fresh, and increasingly likely to have changed when stale.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
import random
from typing import Any, Iterable

from agents.observation import (
    AgentObservation,
    PublicOpponentView,
)


@dataclass(frozen=True)
class BeliefConfig:
    # Probability a remembered board card survives one round unchanged.
    per_round_memory_retention: float = 0.72

    # Hidden hand size is sampled from [0, this cap], further constrained by
    # round number.
    max_sampled_hand_size: int = 5

    # Chance that an unknown hidden hand draw is a Tavern spell instead of a
    # minion.
    hidden_hand_spell_probability: float = 0.12

    def __post_init__(self) -> None:
        if not 0.0 <= self.per_round_memory_retention <= 1.0:
            raise ValueError(
                "per_round_memory_retention must be in [0, 1]."
            )
        if self.max_sampled_hand_size < 0:
            raise ValueError(
                "max_sampled_hand_size cannot be negative."
            )
        if not 0.0 <= self.hidden_hand_spell_probability <= 1.0:
            raise ValueError(
                "hidden_hand_spell_probability must be in [0, 1]."
            )


class PoolBeliefModel:
    """
    Samples hidden current state while respecting finite physical copies.

    Cards marked _generated never consume physical Tavern-pool copies.
    Golden pool cards consume three base-copy equivalents when the runtime card
    preserves enough identity for that to be inferred.
    """

    def __init__(
        self,
        config: BeliefConfig | None = None,
    ) -> None:
        self.config = config or BeliefConfig()

    # ==================================================================
    # KNOWN VISIBLE CARDS
    # ==================================================================

    def remove_known_visible_cards(
        self,
        pool: Any,
        observation: AgentObservation,
    ) -> None:
        """Remove the controlled player's known physical copies from the pool."""
        player = observation.self_player

        zones = (
            player.board,
            player.hand,
            player.tavern_slots,
            (player.tavern_spell,),
        )

        for zone in zones:
            for card in zone:
                self.consume_visible_card(
                    pool,
                    card,
                )

    def consume_visible_card(
        self,
        pool: Any,
        card: Any,
    ) -> int:
        """
        Remove physical copy equivalents represented by one visible runtime card.

        Returns the number of copies successfully removed.
        """
        if not isinstance(card, dict):
            return 0

        if card.get("_generated", False):
            return 0

        card_id = self._base_pool_card_id(
            pool,
            card,
        )

        if card_id is None:
            return 0

        copies = 3 if self._is_golden(card) else 1

        removed = 0

        for _ in range(copies):
            if self._remove_one_by_id(
                pool,
                card_id,
            ):
                removed += 1
            else:
                break

        return removed

    # ==================================================================
    # OPPONENT STATE
    # ==================================================================

    def sample_opponent_board(
        self,
        opponent: PublicOpponentView,
        pool: Any,
        round_number: int,
        rng: random.Random,
    ) -> list[dict | None]:
        """
        Sample a sparse seven-slot board.

        Fresh remembered boards are strongly preserved. Older memories retain
        progressively fewer cards. Missing slots are filled from the physical
        pool using the opponent's public Tavern tier.
        """
        target_count = self._plausible_board_size(
            opponent,
            round_number,
            rng,
        )

        retained: list[dict] = []

        memory = opponent.last_seen_board

        if memory is not None:
            retention_probability = (
                self.config.per_round_memory_retention
                ** max(0, memory.rounds_old)
            )

            for card in memory.board:
                if not isinstance(card, dict):
                    continue

                if len(retained) >= target_count:
                    break

                if rng.random() > retention_probability:
                    continue

                candidate = deepcopy(card)

                # If the remembered card represented a physical pool copy, this
                # determinization treats it as still held only if a compatible
                # physical copy can be removed from the sampled pool. Generated
                # cards do not consume pool copies.
                if (
                    not candidate.get("_generated", False)
                    and self._base_pool_card_id(
                        pool,
                        candidate,
                    )
                    is not None
                ):
                    removed = self.consume_visible_card(
                        pool,
                        candidate,
                    )

                    # If all physical copies are already accounted for by known
                    # information, do not invent an impossible retained copy.
                    if removed == 0:
                        continue

                retained.append(candidate)

        while len(retained) < target_count:
            card = self.draw_random_card(
                pool,
                rng,
                card_type="minion",
                max_tier=opponent.tavern_tier,
            )

            if card is None:
                break

            retained.append(card)

        board: list[dict | None] = retained[:7]
        board.extend(
            [None] * (7 - len(board))
        )
        return board

    def sample_hidden_hand(
        self,
        tavern_tier: int,
        round_number: int,
        pool: Any,
        rng: random.Random,
    ) -> list[dict]:
        """
        Sample an opponent hand.

        This is deliberately broad/noisy. Hidden hands should create plausible
        future actions and pool pressure, not pretend to be knowable exactly.
        """
        round_cap = min(
            self.config.max_sampled_hand_size,
            max(0, 1 + round_number // 3),
        )

        count = rng.randint(
            0,
            round_cap,
        ) if round_cap > 0 else 0

        result: list[dict] = []

        for _ in range(count):
            card_type = (
                "spell"
                if rng.random()
                < self.config.hidden_hand_spell_probability
                else "minion"
            )

            card = self.draw_random_card(
                pool,
                rng,
                card_type=card_type,
                max_tier=tavern_tier,
            )

            if card is None and card_type == "spell":
                card = self.draw_random_card(
                    pool,
                    rng,
                    card_type="minion",
                    max_tier=tavern_tier,
                )

            if card is None:
                break

            result.append(card)

        return result

    def sample_hidden_tavern(
        self,
        tavern_tier: int,
        pool: Any,
        rng: random.Random,
    ) -> tuple[list[dict | None], dict | None]:
        slots = self.tavern_slot_count(
            tavern_tier
        )

        minions: list[dict | None] = []

        for _ in range(slots):
            card = self.draw_random_card(
                pool,
                rng,
                card_type="minion",
                max_tier=tavern_tier,
            )
            minions.append(card)

        spell = self.draw_random_card(
            pool,
            rng,
            card_type="spell",
            max_tier=tavern_tier,
        )

        return minions, spell

    # ==================================================================
    # PHYSICAL POOL SAMPLING
    # ==================================================================

    def draw_random_card(
        self,
        pool: Any,
        rng: random.Random,
        *,
        card_type: str | None = None,
        min_tier: int | None = None,
        max_tier: int | None = None,
    ) -> dict | None:
        """
        Draw one physical copy using the MCTS agent's RNG rather than module
        global random state.
        """
        available = getattr(
            pool,
            "available_cards",
            None,
        )

        if not isinstance(available, list):
            raise TypeError(
                "Simulation pool must expose available_cards as a list."
            )

        indices: list[int] = []

        for index, card in enumerate(available):
            if not isinstance(card, dict):
                continue

            if (
                card_type is not None
                and card.get("cardType") != card_type
            ):
                continue

            tier = card.get("tier")

            if (
                min_tier is not None
                and (
                    tier is None
                    or int(tier) < min_tier
                )
            ):
                continue

            if (
                max_tier is not None
                and (
                    tier is None
                    or int(tier) > max_tier
                )
            ):
                continue

            indices.append(index)

        if not indices:
            return None

        selected_index = rng.choice(
            indices
        )
        definition = available.pop(
            selected_index
        )

        # Physical/runtime cards must never alias the pool definition object.
        return deepcopy(definition)

    # ==================================================================
    # HELPERS
    # ==================================================================

    @staticmethod
    def tavern_slot_count(
        tavern_tier: int,
    ) -> int:
        tier = int(tavern_tier)
        return (
            3
            + int(tier >= 2)
            + int(tier >= 4)
            + int(tier >= 6)
        )

    @staticmethod
    def _plausible_board_size(
        opponent: PublicOpponentView,
        round_number: int,
        rng: random.Random,
    ) -> int:
        memory = opponent.last_seen_board

        if memory is not None:
            observed = sum(
                isinstance(card, dict)
                for card in memory.board
            )

            # Small uncertainty around the last observed board size.
            delta = rng.choice(
                (-1, 0, 0, 0, 1)
            )
            return max(
                0,
                min(7, observed + delta),
            )

        # Broad round-based prior when this opponent has never been seen.
        center = min(
            7,
            max(
                1,
                2 + int(round_number) // 2,
            ),
        )

        return max(
            0,
            min(
                7,
                center + rng.choice(
                    (-1, 0, 0, 1)
                ),
            ),
        )

    @staticmethod
    def _looks_like_pool_card(
        pool: Any,
        card: dict,
    ) -> bool:
        checker = getattr(
            pool,
            "is_pool_card",
            None,
        )

        if not callable(checker):
            return False

        try:
            return bool(checker(card))
        except Exception:
            return False

    @staticmethod
    def _is_golden(
        card: dict,
    ) -> bool:
        return bool(
            card.get("isGolden")
            or card.get("golden")
            or card.get("is_golden")
        )

    @staticmethod
    def _remove_one_by_id(
        pool: Any,
        card_id: int,
    ) -> bool:
        available = getattr(
            pool,
            "available_cards",
            None,
        )

        if not isinstance(available, list):
            return False

        for index, definition in enumerate(
            available
        ):
            if (
                isinstance(definition, dict)
                and definition.get("id") == card_id
            ):
                available.pop(index)
                return True

        return False

    @classmethod
    def _base_pool_card_id(
        cls,
        pool: Any,
        card: dict,
    ) -> int | None:
        card_id = card.get("id")

        if (
            isinstance(card_id, int)
            and cls._pool_contains_id(
                pool,
                card_id,
            )
        ):
            return card_id

        # Some golden runtime definitions point back to the normal card.
        parent_id = card.get("parentId")

        if (
            cls._is_golden(card)
            and isinstance(parent_id, int)
            and cls._pool_contains_id(
                pool,
                parent_id,
            )
        ):
            return parent_id

        return None

    @staticmethod
    def _pool_contains_id(
        pool: Any,
        card_id: int,
    ) -> bool:
        definitions = getattr(
            pool,
            "card_definitions",
            (),
        )

        return any(
            isinstance(definition, dict)
            and definition.get("id") == card_id
            and (
                not callable(
                    getattr(
                        pool,
                        "is_pool_card",
                        None,
                    )
                )
                or pool.is_pool_card(
                    definition
                )
            )
            for definition in definitions
        )
