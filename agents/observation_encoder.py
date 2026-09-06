"""
Structured tensor encoding for AgentObservation.

Schema v5 adds own Hero Power use counters to the scalar features.
Card/hero identity and own-mechanic state preserve the AI information firewall.
Only information already present in AgentObservation is encoded.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import torch

from agents.observation import AgentObservation

def _prefixed(prefix: str, names: Iterable[str]) -> tuple[str, ...]:
    return tuple(f"{prefix}{name}" for name in names)


def _opponent_feature_names(
    count: int,
    names: Iterable[str],
) -> tuple[str, ...]:
    return tuple(
        f"opponent_{slot}_{name}"
        for slot in range(count)
        for name in names
    )


class CardVocabulary:
    """Stable card-id -> embedding-index mapping."""

    PAD_INDEX = 0
    UNK_INDEX = 1
    FIRST_CARD_INDEX = 2

    def __init__(self, card_ids: Iterable[int]) -> None:
        unique_ids = sorted({int(card_id) for card_id in card_ids})
        self._card_ids = tuple(unique_ids)
        self._id_to_index = {
            card_id: index
            for index, card_id in enumerate(
                unique_ids,
                start=self.FIRST_CARD_INDEX,
            )
        }
        self._index_to_id = {
            index: card_id
            for card_id, index in self._id_to_index.items()
        }
        payload = ",".join(str(card_id) for card_id in self._card_ids)
        self.fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def from_cards_file(
        cls,
        cards_file: str | Path = "data/raw/cards.json",
    ) -> "CardVocabulary":
        path = Path(cards_file)
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        if not isinstance(data, list):
            raise ValueError("Card database must contain a JSON list.")

        return cls(
            card["id"]
            for card in data
            if isinstance(card, dict)
            and isinstance(card.get("id"), int)
        )

    def encode(self, card_id: int | None) -> int:
        if card_id is None:
            return self.PAD_INDEX
        try:
            numeric_id = int(card_id)
        except (TypeError, ValueError):
            return self.UNK_INDEX
        return self._id_to_index.get(numeric_id, self.UNK_INDEX)

    def decode(self, index: int) -> int | None:
        if index in (self.PAD_INDEX, self.UNK_INDEX):
            return None
        return self._index_to_id.get(int(index))

    def __len__(self) -> int:
        return len(self._id_to_index) + self.FIRST_CARD_INDEX


@dataclass(frozen=True)
class EncodedObservation:
    """
    One observation encoded for the neural model.

    Shapes before batching:
      scalar_features: [S]
      card_ids:        [C]
      card_features:   [C, F]
      card_mask:       [C]
      identity_ids:    [I]
      identity_mask:   [I]
    """

    scalar_features: torch.Tensor
    card_ids: torch.Tensor
    card_features: torch.Tensor
    card_mask: torch.Tensor
    identity_ids: torch.Tensor
    identity_mask: torch.Tensor

    def to(self, device: torch.device | str) -> "EncodedObservation":
        return EncodedObservation(
            scalar_features=self.scalar_features.to(device),
            card_ids=self.card_ids.to(device),
            card_features=self.card_features.to(device),
            card_mask=self.card_mask.to(device),
            identity_ids=self.identity_ids.to(device),
            identity_mask=self.identity_mask.to(device),
        )


class ObservationEncoder:
    """Convert AgentObservation into stable model tensors."""

    SCHEMA_VERSION = 5

    # Fixed schema order, independent of future engine lobby rules.
    LOBBY_MINION_TYPES = (
        "Beast", "Demon", "Dragon", "Elemental", "Mech", "Murloc",
        "Naga", "Pirate", "Quilboar", "Undead",
    )

    OWN_BOARD_SLOTS = 7
    OWN_HAND_SLOTS = 10
    OWN_TAVERN_SLOTS = 6
    OWN_TAVERN_SPELL_SLOTS = 1
    OPPONENT_COUNT = 7
    OPPONENT_BOARD_SLOTS = 7

    OWN_CARD_SLOTS = (
        OWN_BOARD_SLOTS
        + OWN_HAND_SLOTS
        + OWN_TAVERN_SLOTS
        + OWN_TAVERN_SPELL_SLOTS
    )
    OPPONENT_CARD_SLOTS = OPPONENT_COUNT * OPPONENT_BOARD_SLOTS
    TOTAL_CARD_SLOTS = OWN_CARD_SLOTS + OPPONENT_CARD_SLOTS

    # Identity slots use the same CardVocabulary/embedding as cards.
    # 0 own hero, 1 own hero power, 2 pending-choice source,
    # 3 last Tavern spell, 4..10 public opponent heroes.
    OWN_HERO_IDENTITY_SLOT = 0
    OWN_HERO_POWER_IDENTITY_SLOT = 1
    CHOICE_SOURCE_IDENTITY_SLOT = 2
    LAST_TAVERN_SPELL_IDENTITY_SLOT = 3
    OPPONENT_HERO_IDENTITY_START = 4
    OWN_FIXED_IDENTITY_SLOTS = 4
    IDENTITY_SLOTS = OWN_FIXED_IDENTITY_SLOTS + OPPONENT_COUNT

    PHASES = (
        "hero_selection",
        "recruit",
        "combat",
        "game_over",
    )

    CARD_ZONES = (
        "own_board",
        "own_hand",
        "own_tavern",
        "own_tavern_spell",
        "opponent_board",
    )

    # Visible enchantments change how a card plays even when ID/stats match.
    # Keep this inventory fixed as part of schema v3.
    DARK_GIFT_IDS = (
        132192, 132200, 132201, 132202, 132203, 132205, 132207, 132208,
        132276, 132279, 132441, 132442, 132443, 132445, 132448, 132485,
        132553, 132554, 132555, 132732, 132733, 132734, 132790, 132833,
        132835, 133310, 133344, 133351, 133353, 133359, 133361, 133363,
        133421, 133423, 133424, 133457, 133472, 133474, 133476, 133478,
        133480, 133482, 133860,
    )
    VISIBLE_KEYWORDS = (
        "Taunt", "Divine Shield", "Reborn", "Venomous", "Poisonous",
        "Windfury", "Stealth", "Immune", "Deathrattle", "Rally",
        "Battlecry", "Magnetic", "Spellcraft", "Avenge",
    )

    CARD_FEATURE_NAMES = (
        "attack",
        "health",
        "tier",
        "cost",
        "golden",
        "own_visible_count",
        "remembered_pool_pressure",
        "memory_age",
        "discover_tier",
        "golden_reward_suppressed",
    ) + _prefixed("zone_", CARD_ZONES) + (
        "position",
        "owner_player_id",
    ) + tuple(f"dark_gift_{card_id}" for card_id in DARK_GIFT_IDS) + tuple(
        f"keyword_{keyword.lower().replace(' ', '_')}" for keyword in VISIBLE_KEYWORDS
    )
    CARD_FEATURE_SIZE = len(CARD_FEATURE_NAMES)

    # Fixed own-effect keys. Unknown/new engine keys are intentionally ignored
    # until this schema is deliberately versioned again.
    EFFECT_SCALAR_SPECS = (
        ("dark_gift_uses", 3.0),
        ("dark_gift_last_used_turn", 30.0),
        ("dark_gift_fodder_refreshes", 20.0),
        ("free_refreshes", 10.0),
        ("health_refreshes_remaining", 10.0),
        ("gold_spent_turn", 20.0),
        ("gold_spent_game", 200.0),
        ("spells_cast_game", 100.0),
        ("tavern_spells_cast_game", 100.0),
        ("golden_minions_played", 30.0),
        ("battlecries_triggered_game", 100.0),
        ("deathrattles_triggered_game", 100.0),
        ("rallies_triggered_game", 100.0),
        ("choose_one_both_remaining", 10.0),
        ("zesty_shaker_used", 5.0),
        ("magicfin_uses", 10.0),
        ("automata_summoned", 30.0),
        ("eternal_knights_died", 50.0),
        ("mrrgltons_played", 30.0),
        ("pending_gold_next_turn", 20.0),
        ("blood_gem_attack_bonus", 100.0),
        ("blood_gem_health_bonus", 100.0),
        ("blood_gem_barrage_refreshes", 20.0),
        ("elemental_effect_attack_bonus", 100.0),
        ("elemental_effect_health_bonus", 100.0),
        ("tavern_spell_attack_bonus", 100.0),
        ("tavern_spell_health_bonus", 100.0),
        ("tavern_all_attack", 200.0),
        ("tavern_all_health", 200.0),
        ("tavern_elemental_attack", 200.0),
        ("tavern_elemental_health", 200.0),
        ("tavern_tier3_attack", 200.0),
        ("tavern_tier3_health", 200.0),
        ("undead_global_attack", 200.0),
        ("beetle_global_attack", 200.0),
        ("beetle_global_health", 200.0),
        ("air_baller_future_attack", 200.0),
        ("air_baller_future_health", 200.0),
        ("tasty_lobster_future_attack", 200.0),
        ("tasty_lobster_future_health", 200.0),
        ("darkcrest_strategy_tier", 6.0),
        ("fodder_pending_count", 20.0),
        ("fodder_per_refresh", 10.0),
        ("fodder_refreshes_remaining", 20.0),
        ("queued_crater_golden", 5.0),
    )

    EFFECT_DERIVED_NAMES = (
        "effect_refresh_random_buffs_count",
        "effect_refresh_random_buffs_attack_total",
        "effect_refresh_random_buffs_health_total",
        "effect_queued_crater_choices_count",
        "effect_has_last_tavern_spell",
    )

    GLOBAL_SCALAR_NAMES = (
        "round_number",
        "game_over",
        *(f"phase_{phase}" for phase in PHASES),
        *(f"lobby_type_{tribe.lower()}" for tribe in LOBBY_MINION_TYPES),
    )

    SELF_SCALAR_NAMES = (
        "self_health",
        "self_armor",
        "self_gold",
        "self_max_gold",
        "self_ap",
        "self_tavern_tier",
        "self_waiting",
        "self_eliminated",
        "self_placement",
        "self_tavern_frozen",
        "self_hero_power_cost",
        "self_board_count",
        "self_hand_count",
        "self_tavern_minion_count",
        "self_has_tavern_spell",
        "self_hero_power_uses_turn",
        "self_hero_power_uses_game",
        "self_hero_power_extra_uses_turn",
    )

    CHOICE_SCALAR_NAMES = (
        "has_pending_choice",
        "pending_choice_option_count",
        "pending_choice_discover",
        "pending_choice_choose_one",
        "pending_choice_other",
    )

    OPPONENT_SCALAR_BASE_NAMES = (
        "present",
        "health",
        "armor",
        "tier",
        "eliminated",
        "placement",
        "was_last_opponent",
        "has_board_memory",
        "board_memory_age",
        "has_recent_upgrade",
        "recent_upgrade_age",
    )
    OPPONENT_SCALARS = len(OPPONENT_SCALAR_BASE_NAMES)

    POOL_SCALAR_NAMES = tuple(
        [f"minion_pool_rule_tier_{tier}" for tier in range(1, 7)]
        + [f"spell_pool_rule_tier_{tier}" for tier in range(1, 7)]
    )

    EFFECT_SCALAR_NAMES = _prefixed(
        "effect_",
        tuple(key for key, _ in EFFECT_SCALAR_SPECS),
    ) + EFFECT_DERIVED_NAMES

    SCALAR_FEATURE_NAMES = (
        GLOBAL_SCALAR_NAMES
        + SELF_SCALAR_NAMES
        + CHOICE_SCALAR_NAMES
        + _opponent_feature_names(
            OPPONENT_COUNT,
            OPPONENT_SCALAR_BASE_NAMES,
        )
        + POOL_SCALAR_NAMES
        + EFFECT_SCALAR_NAMES
    )
    SCALAR_FEATURE_SIZE = len(SCALAR_FEATURE_NAMES)

    def __init__(self, vocabulary: CardVocabulary) -> None:
        self.vocabulary = vocabulary

    @classmethod
    def scalar_index(cls, name: str) -> int:
        try:
            return cls.SCALAR_FEATURE_NAMES.index(name)
        except ValueError as exc:
            raise KeyError(name) from exc

    def encode(self, observation: AgentObservation) -> EncodedObservation:
        scalar_features = self._encode_scalars(observation)

        card_ids: list[int] = []
        card_features: list[list[float]] = []
        card_mask: list[bool] = []
        pool_pressure = self._remembered_pool_pressure(observation)

        self._append_zone(
            card_ids, card_features, card_mask,
            observation.self_player.board,
            self.OWN_BOARD_SLOTS,
            observation,
            pool_pressure,
            memory_age=0,
            zone_name="own_board",
            owner_player_id=observation.player_id,
        )
        self._append_zone(
            card_ids, card_features, card_mask,
            observation.self_player.hand,
            self.OWN_HAND_SLOTS,
            observation,
            pool_pressure,
            memory_age=0,
            zone_name="own_hand",
            owner_player_id=observation.player_id,
        )
        self._append_zone(
            card_ids, card_features, card_mask,
            observation.self_player.tavern_slots,
            self.OWN_TAVERN_SLOTS,
            observation,
            pool_pressure,
            memory_age=0,
            zone_name="own_tavern",
            owner_player_id=observation.player_id,
        )
        self._append_zone(
            card_ids, card_features, card_mask,
            (observation.self_player.tavern_spell,),
            self.OWN_TAVERN_SPELL_SLOTS,
            observation,
            pool_pressure,
            memory_age=0,
            zone_name="own_tavern_spell",
            owner_player_id=observation.player_id,
        )

        opponents = sorted(observation.opponents, key=lambda item: item.player_id)
        for opponent in opponents[: self.OPPONENT_COUNT]:
            memory = opponent.last_seen_board
            board = () if memory is None else memory.board
            age = 0 if memory is None else memory.rounds_old
            self._append_zone(
                card_ids, card_features, card_mask,
                board,
                self.OPPONENT_BOARD_SLOTS,
                observation,
                pool_pressure,
                memory_age=age,
                zone_name="opponent_board",
                owner_player_id=opponent.player_id,
            )

        for _ in range(self.OPPONENT_COUNT - min(len(opponents), self.OPPONENT_COUNT)):
            self._append_zone(
                card_ids, card_features, card_mask,
                (),
                self.OPPONENT_BOARD_SLOTS,
                observation,
                pool_pressure,
                memory_age=0,
                zone_name="opponent_board",
                owner_player_id=None,
            )

        if len(card_ids) != self.TOTAL_CARD_SLOTS:
            raise RuntimeError("ObservationEncoder card-slot count mismatch.")

        identity_ids, identity_mask = self._encode_identities(observation, opponents)

        return EncodedObservation(
            scalar_features=torch.tensor(scalar_features, dtype=torch.float32),
            card_ids=torch.tensor(card_ids, dtype=torch.long),
            card_features=torch.tensor(card_features, dtype=torch.float32),
            card_mask=torch.tensor(card_mask, dtype=torch.bool),
            identity_ids=torch.tensor(identity_ids, dtype=torch.long),
            identity_mask=torch.tensor(identity_mask, dtype=torch.bool),
        )

    def _encode_identities(
        self,
        observation: AgentObservation,
        opponents: list[Any],
    ) -> tuple[list[int], list[bool]]:
        player = observation.self_player
        effect_state = player.effect_state if isinstance(player.effect_state, Mapping) else {}
        pending = observation.pending_choice

        raw_ids: list[int | None] = [
            self._numeric_id(player.hero_id),
            self._card_id(player.hero_power),
            self._numeric_id(getattr(pending, "source_card_id", None)) if pending else None,
            self._card_id(effect_state.get("last_tavern_spell")),
        ]

        raw_ids.extend(
            self._numeric_id(opponent.hero_id)
            for opponent in opponents[: self.OPPONENT_COUNT]
        )
        raw_ids.extend([None] * (self.IDENTITY_SLOTS - len(raw_ids)))
        raw_ids = raw_ids[: self.IDENTITY_SLOTS]

        return (
            [self.vocabulary.encode(card_id) for card_id in raw_ids],
            [card_id is not None for card_id in raw_ids],
        )

    def _encode_scalars(self, observation: AgentObservation) -> list[float]:
        values: list[float] = []
        values.extend([
            self._bounded_scale(observation.round_number, 30.0),
            float(observation.game_over),
        ])
        values.extend(
            1.0 if observation.phase == phase else 0.0
            for phase in self.PHASES
        )
        active_types = set(observation.active_minion_types)
        values.extend(float(tribe in active_types) for tribe in self.LOBBY_MINION_TYPES)

        player = observation.self_player
        values.extend([
            self._bounded_scale(player.health, 60.0),
            self._bounded_scale(player.armor, 30.0),
            self._bounded_scale(player.gold, max(10.0, float(player.max_gold or 10))),
            self._bounded_scale(player.max_gold, 20.0),
            self._bounded_scale(player.ap, 100.0),
            self._bounded_scale(player.tavern_tier, 6.0),
            float(player.waiting),
            float(player.eliminated),
            self._placement_feature(player.placement),
            float(player.tavern_frozen),
            self._bounded_scale(player.hero_power_cost, 10.0),
            self._bounded_scale(self._present_count(player.board), 7.0),
            self._bounded_scale(self._present_count(player.hand), 10.0),
            self._bounded_scale(self._present_count(player.tavern_slots), 6.0),
            float(isinstance(player.tavern_spell, dict)),
            self._bounded_scale(player.hero_power_state.get("uses_turn", 0), 10.0),
            self._bounded_scale(player.hero_power_state.get("uses_game", 0), 100.0),
            self._bounded_scale(player.hero_power_state.get("extra_uses_turn", 0), 10.0),
        ])

        pending = observation.pending_choice
        kind = str(getattr(pending, "kind", "") or "").casefold() if pending else ""
        is_discover = "discover" in kind
        is_choose_one = "choose" in kind and "one" in kind
        values.extend([
            float(pending is not None),
            self._bounded_scale(len(pending.options) if pending else 0, 8.0),
            float(is_discover),
            float(is_choose_one),
            float(pending is not None and not is_discover and not is_choose_one),
        ])

        opponents = sorted(observation.opponents, key=lambda item: item.player_id)
        upgrade_by_player: dict[int, int] = {}
        for event in observation.recent_tavern_upgrades:
            age = max(0, int(event.rounds_old))
            old = upgrade_by_player.get(int(event.player_id))
            if old is None or age < old:
                upgrade_by_player[int(event.player_id)] = age

        for index in range(self.OPPONENT_COUNT):
            if index >= len(opponents):
                values.extend([0.0] * self.OPPONENT_SCALARS)
                continue
            opponent = opponents[index]
            memory = opponent.last_seen_board
            upgrade_age = upgrade_by_player.get(int(opponent.player_id))
            values.extend([
                1.0,
                self._bounded_scale(opponent.health, 60.0),
                self._bounded_scale(opponent.armor, 30.0),
                self._bounded_scale(opponent.tavern_tier, 6.0),
                float(opponent.eliminated),
                self._placement_feature(opponent.placement),
                float(opponent.player_id == observation.last_opponent_id),
                float(memory is not None),
                self._bounded_scale(memory.rounds_old if memory is not None else 0, 20.0),
                float(upgrade_age is not None),
                self._bounded_scale(upgrade_age or 0, 20.0),
            ])

        minion_rules = observation.pool.initial_minion_copies_by_tier
        spell_rules = observation.pool.initial_spell_copies_by_tier
        for tier in range(1, 7):
            values.append(self._bounded_scale(int(minion_rules.get(tier, 0)), 20.0))
        for tier in range(1, 7):
            values.append(self._bounded_scale(int(spell_rules.get(tier, 0)), 20.0))

        values.extend(self._encode_effect_state(player.effect_state))

        if len(values) != self.SCALAR_FEATURE_SIZE:
            raise RuntimeError(
                f"ObservationEncoder scalar feature-size mismatch: "
                f"got {len(values)}, expected {self.SCALAR_FEATURE_SIZE}."
            )
        return values

    def _encode_effect_state(self, raw_state: Mapping[str, Any] | Any) -> list[float]:
        state = raw_state if isinstance(raw_state, Mapping) else {}
        values = [
            self._bounded_scale(self._number(state.get(key)), denominator)
            for key, denominator in self.EFFECT_SCALAR_SPECS
        ]

        refresh_buffs = state.get("refresh_random_buffs", ())
        buff_pairs = []
        if isinstance(refresh_buffs, (list, tuple)):
            for item in refresh_buffs:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    buff_pairs.append((self._number(item[0]), self._number(item[1])))

        queued = state.get("queued_crater_choices", ())
        queued_count = len(queued) if isinstance(queued, (list, tuple)) else 0

        values.extend([
            self._bounded_scale(len(buff_pairs), 20.0),
            self._bounded_scale(sum(a for a, _ in buff_pairs), 200.0),
            self._bounded_scale(sum(h for _, h in buff_pairs), 200.0),
            self._bounded_scale(queued_count, 10.0),
            float(isinstance(state.get("last_tavern_spell"), dict)),
        ])
        return values

    def _append_zone(
        self,
        ids: list[int],
        features: list[list[float]],
        masks: list[bool],
        cards: Iterable[Any],
        capacity: int,
        observation: AgentObservation,
        pool_pressure: Mapping[int, float],
        memory_age: int,
        *,
        zone_name: str,
        owner_player_id: int | None,
    ) -> None:
        zone = list(cards)[:capacity]
        zone_one_hot = [1.0 if zone_name == known else 0.0 for known in self.CARD_ZONES]

        for position, card in enumerate(zone):
            card_id = self._card_id(card)
            ids.append(self.vocabulary.encode(card_id))
            present = isinstance(card, dict)
            masks.append(present)

            if not present:
                features.append([0.0] * self.CARD_FEATURE_SIZE)
                continue

            own_visible_count = (
                observation.pool.own_visible_counts.get(card_id, 0)
                if card_id is not None else 0
            )
            pressure = float(pool_pressure.get(card_id, 0.0)) if card_id is not None else 0.0

            row = [
                self._bounded_scale(self._number(card.get("attack")), 200.0),
                self._bounded_scale(self._number(card.get("health")), 200.0),
                self._bounded_scale(self._number(card.get("tier")), 6.0),
                self._bounded_scale(self._number(card.get("manaCost")), 10.0),
                float(self._is_golden(card)),
                self._bounded_scale(own_visible_count, 6.0),
                min(1.0, max(0.0, pressure)),
                self._bounded_scale(memory_age, 20.0),
                self._bounded_scale(self._number(card.get("_discover_tier")), 6.0),
                float(bool(card.get("_no_triple_reward") or card.get("_dark_gift_no_triple_reward"))),
                *zone_one_hot,
                self._bounded_scale(position, max(1.0, float(capacity - 1))),
                self._bounded_scale(owner_player_id or 0, 7.0),
            ]
            gifts = set(card.get("_dark_gift_ids", ()))
            keywords = {str(value).casefold() for value in card.get("keywords", ())}
            row.extend(float(gift_id in gifts) for gift_id in self.DARK_GIFT_IDS)
            row.extend(float(keyword.casefold() in keywords) for keyword in self.VISIBLE_KEYWORDS)
            if len(row) != self.CARD_FEATURE_SIZE:
                raise RuntimeError("ObservationEncoder card feature-size mismatch.")
            features.append(row)

        for _ in range(capacity - len(zone)):
            ids.append(CardVocabulary.PAD_INDEX)
            features.append([0.0] * self.CARD_FEATURE_SIZE)
            masks.append(False)

    @staticmethod
    def _remembered_pool_pressure(observation: AgentObservation) -> dict[int, float]:
        result: dict[int, float] = {}
        for evidence in observation.pool.opponent_memory_evidence:
            age_discount = 1.0 / (1.0 + max(0, evidence.rounds_old))
            contribution = float(evidence.visible_equivalents) * age_discount / 6.0
            result[evidence.card_id] = result.get(evidence.card_id, 0.0) + contribution
        return result

    @staticmethod
    def _card_id(card: Any) -> int | None:
        if not isinstance(card, Mapping):
            return None
        return ObservationEncoder._numeric_id(card.get("id"))

    @staticmethod
    def _numeric_id(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_golden(card: Mapping[str, Any]) -> bool:
        return bool(card.get("isGolden") or card.get("golden") or card.get("is_golden"))

    @staticmethod
    def _number(value: Any) -> float:
        if isinstance(value, bool):
            return float(value)
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _present_count(cards: Iterable[Any]) -> int:
        return sum(1 for card in cards if isinstance(card, dict))

    @staticmethod
    def _bounded_scale(value: int | float, denominator: float) -> float:
        if denominator <= 0:
            raise ValueError("Scale denominator must be positive.")
        scaled = float(value) / float(denominator)
        return min(1.0, max(-1.0, scaled))

    @staticmethod
    def _placement_feature(placement: int | None) -> float:
        if placement is None:
            return 0.0
        return (9.0 - float(placement)) / 8.0
