"""
Shared card pool for the game.

The pool contains the actual available copies of cards.

Card definitions come from cards.json.
Each available pool entry is an independent card copy.

Minions and Tavern spells use different copy counts.
"""

import json
import random
from copy import deepcopy
from pathlib import Path


class CardPool:
    """Shared pool of available minion and Tavern spell copies."""

    MINION_COPY_COUNTS = {
        1: 18,
        2: 18,
        3: 15,
        4: 15,
        5: 11,
        6: 11,
    }

    TAVERN_SPELL_COPY_COUNTS = {
        1: 5,
        2: 7,
        3: 9,
        4: 11,
        5: 9,
        6: 7,
    }

    def __init__(self, cards_file="data/raw/cards.json"):
        self.cards_file = Path(cards_file)

        # Original immutable-style card definitions loaded from JSON.
        self.card_definitions = []

        # Fast lookup of original definitions by card ID.
        self.card_definitions_by_id = {}

        # Independent physical copies currently available.
        self.available_cards = []

        self.load_cards()
        self.build_pool()

    # =========================================================
    # LOADING
    # =========================================================

    def load_cards(self):
        """Load card definitions from the JSON database."""

        if not self.cards_file.exists():
            raise FileNotFoundError(
                f"Card database not found: {self.cards_file}"
            )

        with self.cards_file.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if not isinstance(data, list):
            raise ValueError(
                "Card database must contain a JSON list."
            )

        self.card_definitions = data

        self.card_definitions_by_id = {
            card["id"]: card
            for card in self.card_definitions
            if "id" in card
        }

    # =========================================================
    # CARD FILTERING
    # =========================================================

    def is_pool_card(self, card):
        """
        Check whether a card belongs in our shared pool.

        Currently the pool contains:
        - Normal Tavern minions
        - Tavern spells
        """

        if not isinstance(card, dict):
            return False

        card_type = card.get("cardType")

        # -----------------------------------------------------
        # MINIONS
        # -----------------------------------------------------

        if card_type == "minion":

            if card.get("pool") is not True:
                return False

            if card.get("isHero", False):
                return False

            if card.get("isHeroSkin", False):
                return False

            if card.get("isQuest", False):
                return False

            if card.get("isReward", False):
                return False

            if card.get("isDuosOnly", False):
                return False

            if card.get("isSolosOnly", False):
                return False

            categories = card.get("categories", [])

            # Only normal Tavern minions belong in the pool.
            if "tavern" not in categories:
                return False

            # Generated tokens do not belong in the Tavern pool.
            if "token" in categories:
                return False

            return (
                card.get("tier")
                in self.MINION_COPY_COUNTS
            )

        # -----------------------------------------------------
        # TAVERN SPELLS
        # -----------------------------------------------------

        if card_type == "spell":

            if card.get("pool") is not True:
                return False

            categories = card.get("categories", [])

            if "tavern" not in categories:
                return False

            if card.get("isDuosOnly", False):
                return False

            if card.get("isSolosOnly", False):
                return False

            if card.get("isQuest", False):
                return False

            if card.get("isReward", False):
                return False

            return (
                card.get("tier")
                in self.TAVERN_SPELL_COPY_COUNTS
            )

        return False

    # =========================================================
    # COPY COUNTS
    # =========================================================

    def get_copy_count(self, card):
        """Return the number of physical copies for a card."""

        card_type = card.get("cardType")
        tier = card.get("tier")

        if card_type == "minion":
            return self.MINION_COPY_COUNTS.get(
                tier,
                0,
            )

        if card_type == "spell":
            return self.TAVERN_SPELL_COPY_COUNTS.get(
                tier,
                0,
            )

        return 0

    # =========================================================
    # BUILD POOL
    # =========================================================

    def build_pool(self):
        """Create all independent available card copies."""

        self.available_cards.clear()

        for definition in self.card_definitions:

            if not self.is_pool_card(definition):
                continue

            copy_count = self.get_copy_count(
                definition
            )

            for _ in range(copy_count):
                self.available_cards.append(
                    deepcopy(definition)
                )

    # =========================================================
    # GENERIC CARD DRAWING
    # =========================================================

    def get_random_card(
        self,
        card_type=None,
        min_tier=None,
        max_tier=None,
    ):
        """
        Get one random available card.

        The exact selected physical copy is removed from the pool.
        """

        candidate_indices = []

        for index, card in enumerate(
            self.available_cards
        ):
            if not self._matches_request(
                card,
                card_type=card_type,
                min_tier=min_tier,
                max_tier=max_tier,
            ):
                continue

            candidate_indices.append(index)

        if not candidate_indices:
            return None

        selected_index = random.choice(
            candidate_indices
        )

        return self.available_cards.pop(
            selected_index
        )

    def get_random_cards(
        self,
        count,
        card_type=None,
        min_tier=None,
        max_tier=None,
    ):
        """
        Get multiple random available cards.

        Each returned physical copy is removed from the pool.
        """

        cards = []

        for _ in range(count):

            card = self.get_random_card(
                card_type=card_type,
                min_tier=min_tier,
                max_tier=max_tier,
            )

            if card is None:
                break

            cards.append(card)

        return cards

    # =========================================================
    # MINION REQUESTS
    # =========================================================

    def get_random_minion(
        self,
        tier=None,
        min_tier=None,
        max_tier=None,
    ):
        """
        Get one random available minion.

        Exact tier:
            get_random_minion(tier=3)

        Tier range:
            get_random_minion(min_tier=1, max_tier=3)
        """

        if tier is not None:
            min_tier = tier
            max_tier = tier

        return self.get_random_card(
            card_type="minion",
            min_tier=min_tier,
            max_tier=max_tier,
        )

    def get_random_minions(
        self,
        count,
        tier=None,
        min_tier=None,
        max_tier=None,
    ):
        """
        Get multiple random available minions.

        Exact tier:
            get_random_minions(3, tier=2)

        Tier range:
            get_random_minions(
                3,
                min_tier=1,
                max_tier=3,
            )
        """

        if tier is not None:
            min_tier = tier
            max_tier = tier

        return self.get_random_cards(
            count=count,
            card_type="minion",
            min_tier=min_tier,
            max_tier=max_tier,
        )

    # =========================================================
    # SPELL REQUESTS
    # =========================================================

    def get_random_spell(
        self,
        tier=None,
        min_tier=None,
        max_tier=None,
    ):
        """
        Get one random available Tavern spell.

        Exact tier:
            get_random_spell(tier=3)

        Tier range:
            get_random_spell(min_tier=1, max_tier=3)
        """

        if tier is not None:
            min_tier = tier
            max_tier = tier

        return self.get_random_card(
            card_type="spell",
            min_tier=min_tier,
            max_tier=max_tier,
        )

    def get_random_spells(
        self,
        count,
        tier=None,
        min_tier=None,
        max_tier=None,
    ):
        """
        Get multiple random available Tavern spells.

        Exact tier:
            get_random_spells(2, tier=3)

        Tier range:
            get_random_spells(
                2,
                min_tier=1,
                max_tier=3,
            )
        """

        if tier is not None:
            min_tier = tier
            max_tier = tier

        return self.get_random_cards(
            count=count,
            card_type="spell",
            min_tier=min_tier,
            max_tier=max_tier,
        )

    # =========================================================
    # RETURNING
    # =========================================================

    def return_card(self, card):
        """
        Return one card copy to the shared pool.

        A fresh copy of the original card definition is returned.
        Runtime changes such as buffs are therefore discarded.
        """

        if not self.is_pool_card(card):
            raise ValueError(
                f"Card cannot be returned to the pool: "
                f"{card.get('name', 'Unknown')}"
            )

        card_id = card.get("id")

        definition = self.card_definitions_by_id.get(
            card_id
        )

        if definition is None:
            raise ValueError(
                f"Unknown card ID: {card_id}"
            )

        if not self.is_pool_card(definition):
            raise ValueError(
                f"Card does not belong in the pool: "
                f"{definition.get('name', 'Unknown')}"
            )

        self.available_cards.append(
            deepcopy(definition)
        )

    def return_cards(self, cards):
        """Return multiple card copies to the shared pool."""

        for card in cards:
            self.return_card(card)

    # =========================================================
    # CANDIDATES
    # =========================================================

    def _matches_request(
        self,
        card,
        card_type=None,
        min_tier=None,
        max_tier=None,
    ):
        """Check whether one card matches a pool request."""

        if (
            card_type is not None
            and card.get("cardType") != card_type
        ):
            return False

        tier = card.get("tier")

        if min_tier is not None:
            if tier is None or tier < min_tier:
                return False

        if max_tier is not None:
            if tier is None or tier > max_tier:
                return False

        return True

    def _get_candidates(
        self,
        card_type=None,
        min_tier=None,
        max_tier=None,
    ):
        """Find available physical copies matching the request."""

        return [
            card
            for card in self.available_cards
            if self._matches_request(
                card,
                card_type=card_type,
                min_tier=min_tier,
                max_tier=max_tier,
            )
        ]

    # =========================================================
    # INFORMATION
    # =========================================================

    def available_count(self):
        """Return the total number of available physical copies."""

        return len(self.available_cards)

    def available_count_for(
        self,
        card_type=None,
        min_tier=None,
        max_tier=None,
    ):
        """Return the number of matching available copies."""

        return len(
            self._get_candidates(
                card_type=card_type,
                min_tier=min_tier,
                max_tier=max_tier,
            )
        )

    def __len__(self):
        return len(self.available_cards)

    def __repr__(self):
        return (
            f"CardPool("
            f"available={len(self.available_cards)}, "
            f"definitions={len(self.card_definitions)}"
            f")"
        )