"""Season 14 Dark Gift discovery system.

This module owns the global Dark Gift button/lifecycle. Gift card behavior is
implemented through the ordinary EffectSystem attachment mechanism: the chosen
Gift is attached to the chosen physical minion, so its registered effect
identity follows that minion through hand, board and combat.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .lobby import card_minion_types


DARK_GIFT_COST = 3
DARK_GIFT_FIRST_TURN = 3
DARK_GIFT_MAX_USES = 3
DARK_GIFT_OPTIONS = 3

# Blizzard's Season 14 Dark Discovery minion-tier schedule.
DARK_DISCOVERY_TIERS = {
    3: (2,),
    4: (2, 3),
    5: (3,),
    6: (3, 4),
    7: (4,),
    8: (4, 5),
    9: (4, 5, 6),
    10: (5, 6),
}

# Explicit current hotfix exclusions/restrictions.
NEVER_OFFER_MINION_NAMES = {
    "Boom-in-a-Box",
    "Deadly Spore",
    "Leeroy the Reckless",
}

HAND_INTENDED_MINION_NAMES = {
    "Bream Counter",
    "Old Soul",
}

BATTLECRY_OR_CHOOSE_ONE_GIFTS = {
    "Double Vision",
    "Replication",
    "Gilding",
    "Echoing Voice",
}

DEATHRATTLE_ALLOWED_STAT_GIFTS = {
    "Sharpened Sword",
    "Death's Embrace",
}

STAT_GIFT_NAMES = {
    "Fortitude",
    "Sharpened Sword",
    "Toughened Shield",
    "Steady Growth",
    "Battle Scars",
    "Death's Embrace",
    "Spell Siphon",
    "Dexterity",
    "Incubation",
    "Offensive Sacrifice",
    "Defensive Sacrifice",
    "Transcendence",
    "Resistance",
    "Hostility",
    "Titanic Strength",
}

CHARISMA_BANNED_MINION_NAMES = {
    "Balinda Stonehearth",
    "Banana Slamma",
    "Barrier Banshee",
    "Cage Gnawer",
    "Lurking Leviathan",
    "Ravaging Scorpid",
    "Roaring Recruiter",
    "Snazzy Phantom",
    "Titus Rivendare",
    "Deathstrider",
}

RARE_GIFT_NAMES = {
    "Gilding",
    "Persisting Horror",
    "Titanic Strength",
    "Invulnerability",
}


@dataclass(frozen=True)
class DarkGiftOffer:
    minion: dict
    gift: dict


class DarkGiftSystem:
    """Own Dark Discovery use limits, pool reservations and paired offers."""

    RESOLVER_KEY = "dark_gift_discovery"

    def __init__(self, game):
        self.game = game
        self.uses_by_player: dict[int, int] = {}
        self.last_used_turn: dict[int, int] = {}
        self.game.effects.register_choice_resolver(
            self.RESOLVER_KEY,
            self._resolve_choice,
        )

    def reset(self):
        self.uses_by_player.clear()
        self.last_used_turn.clear()

    def uses(self, player_id: int) -> int:
        return int(self.uses_by_player.get(player_id, 0))

    def can_use(self, player_id: int) -> bool:
        game = self.game
        if game.phase != "recruit" or game.game_over:
            return False
        if int(game.round_number) < DARK_GIFT_FIRST_TURN:
            return False

        player = game.get_player(player_id)
        if player.eliminated:
            return False
        if self.uses(player_id) >= DARK_GIFT_MAX_USES:
            return False
        if self.last_used_turn.get(player_id) == int(game.round_number):
            return False
        if int(getattr(player, "gold", 0) or 0) < DARK_GIFT_COST:
            return False
        if len(getattr(player, "hand", ())) >= player.MAX_HAND_SIZE:
            return False
        if game.effects.get_pending_choice(player_id) is not None:
            return False

        return self._has_possible_offer(player_id)

    @staticmethod
    def tiers_for_turn(turn: int) -> tuple[int, ...]:
        turn = int(turn)
        if turn < DARK_GIFT_FIRST_TURN:
            return ()
        if turn >= 10:
            return DARK_DISCOVERY_TIERS[10]
        return DARK_DISCOVERY_TIERS.get(turn, ())

    def use(self, player_id: int):
        """Spend 3 Gold and start the mandatory paired Discover."""

        if not self.can_use(player_id):
            raise ValueError("Dark Discovery is not currently available.")

        offers = self._build_offers(player_id)
        if len(offers) != DARK_GIFT_OPTIONS:
            raise RuntimeError("Unable to construct three legal Dark Gift offers.")

        # Reserve the exact physical minion copies before spending Gold. This
        # makes simultaneous Dark Discoveries obey the same shared-pool races as
        # Tavern purchases.
        self._reserve_offered_minions(offers)

        try:
            self.game.effects.spend_gold(
                player_id,
                DARK_GIFT_COST,
                reason="dark_gift",
            )
            self.uses_by_player[player_id] = self.uses(player_id) + 1
            self.last_used_turn[player_id] = int(self.game.round_number)

            choice = self.game.effects.start_choice(
                player_id,
                self.RESOLVER_KEY,
                offers,
                kind="dark_gift",
                source_card_id=132180,
                metadata={
                    "reserved_offers": offers,
                    "turn": int(self.game.round_number),
                },
            )
            if choice is None:
                raise RuntimeError("Dark Gift Discover produced no options.")
            return choice
        except Exception:
            self._return_reserved_offers(offers)
            raise

    def _has_possible_offer(self, player_id: int) -> bool:
        minions = self._eligible_physical_minions(player_id)
        gifts = self._eligible_gifts(player_id)
        return bool(minions) and len({gift.get("name") for gift in gifts}) >= 3

    def _eligible_physical_minions(self, player_id: int) -> list[dict]:
        turn = int(self.game.round_number)
        tiers = set(self.tiers_for_turn(turn))
        seen_ids = set()
        candidates = []

        for card in self.game.pool.available_cards:
            if card.get("cardType") != "minion" or card.get("tier") not in tiers:
                continue
            card_id = card.get("id")
            if card_id in seen_ids:
                continue
            if not self._minion_offerable(card, turn):
                continue
            seen_ids.add(card_id)
            candidates.append(card)

        return candidates

    def _minion_offerable(self, card: dict, turn: int) -> bool:
        name = str(card.get("name", ""))
        if name in NEVER_OFFER_MINION_NAMES or name in HAND_INTENDED_MINION_NAMES:
            return False

        text = self._plain_text(card)
        keywords = self._keywords(card)

        if "Magnetic" in keywords:
            return False
        if "when you sell this" in text.casefold():
            return False
        if "in your hand" in text.casefold():
            return False
        if turn < 5 and (self._has_battlecry(card) or self._has_choose_one(card)):
            return False

        return True

    def _eligible_gifts(self, player_id: int) -> list[dict]:
        turn = int(self.game.round_number)
        gifts = []

        for card in self.game.pool.card_definitions:
            if card.get("cardType") != "spell":
                continue
            if "darkgift" not in card.get("categories", []):
                continue
            if card.get("pool") is not True:
                continue

            minimum = card.get("darkGiftMinTurn")
            maximum = card.get("darkGiftMaxTurn")
            if minimum is not None and turn < int(minimum):
                continue
            if maximum is not None and turn > int(maximum):
                continue

            if self._gift_globally_available(player_id, card):
                gifts.append(card)

        return gifts

    def _gift_globally_available(self, player_id: int, gift: dict) -> bool:
        name = str(gift.get("name", ""))
        active_types = set(getattr(self.game, "active_minion_types", ()))
        state = self.game.effects.get_player_state(player_id)
        player = self.game.get_player(player_id)

        if name == "Toughened Shield" and active_types & {"Quilboar", "Naga"}:
            return False
        if name in {"Resistance", "Transcendence"} and "Dragon" in active_types:
            return False
        if name == "Polarization" and int(player.tavern_tier) < 3:
            return False
        if name == "Battle Scars" and int(state.get("battlecries_triggered_game", 0) or 0) <= 0:
            return False
        if name == "Death's Embrace" and int(state.get("deathrattles_triggered_game", 0) or 0) <= 0:
            return False
        if name == "Spell Siphon" and int(state.get("tavern_spells_cast_game", 0) or 0) <= 0:
            return False

        # Only the greatest of the three tracked-history stat gifts is eligible.
        history_values = {
            "Battle Scars": int(state.get("battlecries_triggered_game", 0) or 0),
            "Death's Embrace": int(state.get("deathrattles_triggered_game", 0) or 0),
            "Spell Siphon": int(state.get("tavern_spells_cast_game", 0) or 0),
        }
        if name in history_values:
            greatest = max(history_values.values())
            if history_values[name] != greatest:
                return False

        return True

    def _gift_compatible(self, player_id: int, minion: dict, gift: dict) -> bool:
        name = str(gift.get("name", ""))
        minion_name = str(minion.get("name", ""))
        keywords = self._keywords(minion)
        typed = bool(self._real_types(minion))
        battlecry = self._has_battlecry(minion)
        choose_one = self._has_choose_one(minion)
        deathrattle = "Deathrattle" in keywords or "deathrattle" in self._plain_text(minion).casefold()
        avenge = "Avenge" in keywords or "avenge" in self._plain_text(minion).casefold()
        taunt = "Taunt" in keywords

        if battlecry or choose_one:
            if name not in BATTLECRY_OR_CHOOSE_ONE_GIFTS:
                return False

        if deathrattle and name in STAT_GIFT_NAMES and name not in DEATHRATTLE_ALLOWED_STAT_GIFTS:
            return False

        if name == "Sunken Persistence":
            return "Spellcraft" in keywords or minion_name == "Glowscale"
        if name == "Jaws of Death":
            return deathrattle
        if name == "Affinity":
            return typed
        if name == "Sharpened Sword":
            return not avenge
        if name == "Time Turning":
            return "end of your turn" in self._plain_text(minion).casefold()
        if name == "Furtiveness":
            return avenge
        if name == "Consanguinity":
            return self._is_type(minion, "Quilboar")
        if name == "Gilding":
            return "Activate" not in keywords
        if name == "Toreth's Blessing":
            return "Divine Shield" in keywords
        if name == "Amalgamation":
            return not typed
        if name == "Demonology":
            return self._is_type(minion, "Demon")
        if name == "Polarization":
            return self._is_type(minion, "Mech")
        if name == "Tarecgosa's Blessing":
            return self._is_type(minion, "Dragon")
        if name in {"Dexterity", "Incubation", "Offensive Sacrifice", "Defensive Sacrifice"}:
            return typed
        if name == "Echoing Voice":
            return battlecry
        if name == "Transcendence":
            return not typed and not battlecry and not choose_one
        if name == "Toxicity":
            return (
                self._is_type(minion, "Murloc")
                and "Venomous" not in keywords
                and "Poisonous" not in keywords
            )
        if name == "Charisma":
            return not taunt and not avenge and minion_name not in CHARISMA_BANNED_MINION_NAMES
        if name == "Resistance":
            return typed and not self._is_type(minion, "Beast") and not self._is_type(minion, "Undead")
        if name == "Hostility":
            return typed and not avenge and "Venomous" not in keywords and "Poisonous" not in keywords
        if name == "Golemancy":
            return typed and minion_name != "Stitched Salvager"
        if name == "Persisting Horror":
            return typed
        if name == "Titanic Strength":
            return not self._is_type(minion, "Dragon")
        if name == "Invulnerability":
            return typed and not taunt

        return True

    def _build_offers(self, player_id: int) -> list[DarkGiftOffer]:
        minions = self._eligible_physical_minions(player_id)
        gifts = self._eligible_gifts(player_id)
        if len(minions) < DARK_GIFT_OPTIONS or len(gifts) < DARK_GIFT_OPTIONS:
            return []

        preferred_type = self._most_common_type(player_id) if int(self.game.round_number) >= 6 else None

        for _ in range(200):
            selected_minions = self._choose_minions(minions, preferred_type)
            if len(selected_minions) != DARK_GIFT_OPTIONS:
                continue

            assignments = self._assign_unique_gifts(player_id, selected_minions, gifts)
            if assignments is None:
                continue

            offers = [
                DarkGiftOffer(minion=minion, gift=gift)
                for minion, gift in zip(selected_minions, assignments)
            ]

            lowest_tier = min(int(offer.minion.get("tier", 99) or 99) for offer in offers)
            if any(
                offer.gift.get("name") == "Gilding"
                and int(offer.minion.get("tier", 99) or 99) != lowest_tier
                for offer in offers
            ):
                continue

            return offers

        return []

    def _choose_minions(self, candidates: list[dict], preferred_type: str | None) -> list[dict]:
        rng = self.game.random
        first = None

        if preferred_type:
            matching = [card for card in candidates if self._is_type(card, preferred_type)]
            if matching:
                first = rng.choice(matching)

        chosen = [first] if first is not None else []
        used_ids = {first.get("id")} if first is not None else set()

        remaining = [card for card in candidates if card.get("id") not in used_ids]
        rng.shuffle(remaining)
        for card in remaining:
            chosen.append(card)
            used_ids.add(card.get("id"))
            if len(chosen) == DARK_GIFT_OPTIONS:
                break

        return chosen

    def _assign_unique_gifts(self, player_id: int, minions: list[dict], gifts: list[dict]):
        rng = self.game.random
        order = list(range(len(minions)))
        rng.shuffle(order)
        assigned = [None] * len(minions)

        def search(depth: int, used_names: set[str]) -> bool:
            if depth >= len(order):
                return True

            index = order[depth]
            minion = minions[index]
            compatible = [
                gift
                for gift in gifts
                if str(gift.get("name", "")) not in used_names
                and self._gift_compatible(player_id, minion, gift)
            ]
            rng.shuffle(compatible)
            compatible.sort(
                key=lambda gift: (
                    1 if gift.get("name") in RARE_GIFT_NAMES else 0,
                    0 if (gift.get("name") == "Harpy's Talons" and self._has_rally(minion)) else 1,
                )
            )

            for gift in compatible:
                assigned[index] = gift
                name = str(gift.get("name", ""))
                if search(depth + 1, used_names | {name}):
                    return True
                assigned[index] = None
            return False

        if not search(0, set()):
            return None
        return assigned

    def _reserve_offered_minions(self, offers: list[DarkGiftOffer]) -> None:
        for offer in offers:
            for index, physical in enumerate(self.game.pool.available_cards):
                if physical is offer.minion:
                    self.game.pool.available_cards.pop(index)
                    break
            else:
                raise RuntimeError("Dark Gift offered minion disappeared from the shared pool.")

    def _return_reserved_offers(self, offers: list[DarkGiftOffer], *, except_minion=None) -> None:
        for offer in offers:
            if offer.minion is except_minion:
                continue
            self.game.pool.return_card(offer.minion)

    def _resolve_choice(self, effects, player_id: int, option: DarkGiftOffer, metadata: dict):
        offers = list(metadata.get("reserved_offers", ()))
        selected = option.minion

        self._attach_gift(selected, option.gift)
        self._return_reserved_offers(offers, except_minion=selected)

        player = self.game.get_player(player_id)
        if len(player.hand) >= player.MAX_HAND_SIZE:
            # This should be impossible because the pending choice blocks all
            # other actions, but keep pool ownership correct if an external
            # caller mutates the hand illegally.
            self.game.pool.return_card(selected)
            raise ValueError("Hand became full during Dark Gift resolution.")

        player.hand.append(selected)
        effects.events.emit(
            effects.events and __import__("game.events", fromlist=["GameEvent"]).GameEvent.CARD_ADDED_TO_HAND,
            player_id=player_id,
            card=selected,
            dark_gift=option.gift,
        )
        return selected

    @staticmethod
    def _attach_gift(minion: dict, gift: dict) -> None:
        attached = deepcopy(gift)
        attached["_dark_gift"] = True
        minion.setdefault("_attachments", []).append(attached)
        minion.setdefault("_dark_gift_ids", []).append(attached.get("id"))
        minion.setdefault("_dark_gift_names", []).append(attached.get("name"))

    def _most_common_type(self, player_id: int) -> str | None:
        player = self.game.get_player(player_id)
        active = set(getattr(self.game, "active_minion_types", ()))
        counts: dict[str, int] = {}

        for card in player.board:
            for minion_type in self._real_types(card):
                if minion_type not in active:
                    continue
                counts[minion_type] = counts.get(minion_type, 0) + 1

        if not counts:
            return None

        highest = max(counts.values())
        tied = sorted(name for name, count in counts.items() if count == highest)
        return self.game.random.choice(tied)

    @staticmethod
    def _plain_text(card: dict) -> str:
        return str(card.get("text", "")).replace("<b>", "").replace("</b>", "")

    @staticmethod
    def _keywords(card: dict) -> set[str]:
        return {str(value) for value in card.get("keywords", ())}

    @staticmethod
    def _real_types(card: dict) -> tuple[str, ...]:
        return tuple(value for value in card_minion_types(card) if value != "All")

    @classmethod
    def _is_type(cls, card: dict, minion_type: str) -> bool:
        printed = set(card_minion_types(card))
        return "All" in printed or minion_type in printed

    @classmethod
    def _has_battlecry(cls, card: dict) -> bool:
        return "Battlecry" in cls._keywords(card) or "battlecry" in cls._plain_text(card).casefold()

    @classmethod
    def _has_choose_one(cls, card: dict) -> bool:
        return "Choose One" in cls._keywords(card) or "choose one" in cls._plain_text(card).casefold()

    @classmethod
    def _has_rally(cls, card: dict) -> bool:
        return "Rally" in cls._keywords(card) or "rally" in cls._plain_text(card).casefold()
