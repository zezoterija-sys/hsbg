"""
Shared card pool for the game.

The pool contains the actual available copies of cards.

Raw card definitions come from cards.json and are normalized through the
selected versioned Battlegrounds ruleset before entering runtime state.
Each available pool entry is an independent card copy.

This simulator targets Battlegrounds Solos: Duos-only cards are excluded while
Solos-only cards are explicitly allowed. Real games also provide the five
active lobby minion types; isolated tests may omit them to inspect the complete
card database without lobby filtering.
"""

import json
import random
from copy import deepcopy
from pathlib import Path

from .lobby import is_minion_available_for_lobby
from .rulesets import CURRENT_RULESET


class CardPool:
    """Shared pool of available minion and Tavern spell copies."""

    # Current Solos physical-copy counts by Tavern Tier.
    MINION_COPY_COUNTS = {
        1: 15,
        2: 15,
        3: 13,
        4: 11,
        5: 9,
        6: 7,
    }

    TAVERN_SPELL_COPY_COUNTS = {
        1: 5,
        2: 7,
        3: 9,
        4: 11,
        5: 9,
        6: 7,
    }

    def __init__(
        self,
        cards_file="data/raw/cards.json",
        rng=None,
        ruleset=CURRENT_RULESET,
        active_minion_types=None,
    ):
        self.cards_file = Path(cards_file)
        self.random = rng if rng is not None else random.Random()
        self.ruleset = ruleset
        self.active_minion_types = (
            None
            if active_minion_types is None
            else tuple(sorted({str(value) for value in active_minion_types}))
        )

        # Runtime card definitions are independent normalized copies. The raw
        # JSON is never modified in place.
        self.card_definitions = []
        self.card_definitions_by_id = {}
        self.available_cards = []

        self.load_cards()
        self.build_pool()

    def load_cards(self):
        """Load and normalize card definitions for the active ruleset."""

        if not self.cards_file.exists():
            raise FileNotFoundError(
                f"Card database not found: {self.cards_file}"
            )

        with self.cards_file.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, list):
            raise ValueError("Card database must contain a JSON list.")

        self.card_definitions = self.ruleset.normalize_cards(data)
        self.card_definitions_by_id = {
            card["id"]: card
            for card in self.card_definitions
            if "id" in card
        }

    def is_pool_card(self, card):
        """Check whether a card belongs in the active Solos shared pool."""

        if not isinstance(card, dict):
            return False

        card_type = card.get("cardType")

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

            categories = card.get("categories", [])
            if "tavern" not in categories:
                return False
            if "token" in categories:
                return False
            if card.get("tier") not in self.MINION_COPY_COUNTS:
                return False

            return is_minion_available_for_lobby(
                card,
                self.active_minion_types,
            )

        if card_type == "spell":
            if card.get("pool") is not True:
                return False

            categories = card.get("categories", [])
            if "tavern" not in categories:
                return False
            if card.get("isDuosOnly", False):
                return False
            if card.get("isQuest", False):
                return False
            if card.get("isReward", False):
                return False

            return card.get("tier") in self.TAVERN_SPELL_COPY_COUNTS

        return False

    def get_copy_count(self, card):
        """Return the number of physical copies for a card."""

        card_type = card.get("cardType")
        tier = card.get("tier")

        if card_type == "minion":
            return self.MINION_COPY_COUNTS.get(tier, 0)
        if card_type == "spell":
            return self.TAVERN_SPELL_COPY_COUNTS.get(tier, 0)
        return 0

    def build_pool(self):
        """Create all independent available card copies."""

        self.available_cards.clear()

        for definition in self.card_definitions:
            if not self.is_pool_card(definition):
                continue

            for _ in range(self.get_copy_count(definition)):
                self.available_cards.append(deepcopy(definition))

    def get_random_card(
        self,
        card_type=None,
        min_tier=None,
        max_tier=None,
    ):
        """Get and remove one matching random physical copy."""

        candidate_indices = []
        for index, card in enumerate(self.available_cards):
            if self._matches_request(
                card,
                card_type=card_type,
                min_tier=min_tier,
                max_tier=max_tier,
            ):
                candidate_indices.append(index)

        if not candidate_indices:
            return None

        selected_index = self.random.choice(candidate_indices)
        return self.available_cards.pop(selected_index)

    def get_random_cards(
        self,
        count,
        card_type=None,
        min_tier=None,
        max_tier=None,
    ):
        """Get multiple random physical copies without replacement."""

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

    def get_random_minion(
        self,
        tier=None,
        min_tier=None,
        max_tier=None,
    ):
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
        if tier is not None:
            min_tier = tier
            max_tier = tier

        return self.get_random_cards(
            count=count,
            card_type="minion",
            min_tier=min_tier,
            max_tier=max_tier,
        )

    def get_random_spell(
        self,
        tier=None,
        min_tier=None,
        max_tier=None,
    ):
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
        if tier is not None:
            min_tier = tier
            max_tier = tier

        return self.get_random_cards(
            count=count,
            card_type="spell",
            min_tier=min_tier,
            max_tier=max_tier,
        )

    def return_card(self, card):
        """Return a fresh normalized copy of one pool card."""

        if card.get("_triple_component_ids"):
            for card_id in card["_triple_component_ids"]:
                definition = self.card_definitions_by_id.get(card_id)
                if definition is not None and self.is_pool_card(definition):
                    self.available_cards.append(deepcopy(definition))
            return

        if not self.is_pool_card(card):
            raise ValueError(
                f"Card cannot be returned to the pool: "
                f"{card.get('name', 'Unknown')}"
            )

        card_id = card.get("id")
        definition = self.card_definitions_by_id.get(card_id)

        if definition is None:
            raise ValueError(f"Unknown card ID: {card_id}")
        if not self.is_pool_card(definition):
            raise ValueError(
                f"Card does not belong in the pool: "
                f"{definition.get('name', 'Unknown')}"
            )

        self.available_cards.append(deepcopy(definition))

    def return_cards(self, cards):
        for card in cards:
            self.return_card(card)

    def _matches_request(
        self,
        card,
        card_type=None,
        min_tier=None,
        max_tier=None,
    ):
        if card_type is not None and card.get("cardType") != card_type:
            return False

        tier = card.get("tier")
        if min_tier is not None and (tier is None or tier < min_tier):
            return False
        if max_tier is not None and (tier is None or tier > max_tier):
            return False
        return True

    def _get_candidates(
        self,
        card_type=None,
        min_tier=None,
        max_tier=None,
    ):
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

    def available_count(self):
        return len(self.available_cards)

    def available_count_for(
        self,
        card_type=None,
        min_tier=None,
        max_tier=None,
    ):
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
        lobby = (
            "all-types"
            if self.active_minion_types is None
            else ",".join(self.active_minion_types)
        )
        return (
            f"CardPool(available={len(self.available_cards)}, "
            f"definitions={len(self.card_definitions)}, "
            f"ruleset={self.ruleset.ruleset_id}, "
            f"lobby={lobby})"
        )
