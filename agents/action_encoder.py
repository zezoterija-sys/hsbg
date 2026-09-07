"""
Stable feature encoding for variable Battlegrounds actions.

Schema v3 adds the Season 14 Dark Discovery action and paired Dark Gift choice
semantics while retaining the observation-aware candidate features introduced
in schema v2.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable, TYPE_CHECKING

from game.actions import Action

if TYPE_CHECKING:
    from agents.observation import AgentObservation


class ActionEncoder:
    SCHEMA_VERSION = 3

    ACTION_TYPE_NAMES = (
        "refresh",
        "buy_minion",
        "buy_spell",
        "sell_minion",
        "play_minion",
        "cast_spell",
        "hero_power",
        "activate",
        "dark_gift",
        "freeze",
        "unfreeze",
        "upgrade_tavern",
        "reposition",
        "choose_option",
        "end_turn",
    )

    EFFECT_ZONES = (
        "board",
        "hand",
        "tavern",
        "combat",
        "hero_power",
        "trinket",
        "event_source",
    )

    MAX_TARGET_INDEX = 9
    MAX_POSITION_INDEX = 6
    MAX_OPTION_INDEX = 7
    MAX_PLAYER_ID = 7
    MAX_EFFECT_TARGET_INDEX = 9

    # Non-card Choose One options are often stable semantic strings such as
    # "improve" or "gems". Dark Gift choices use the same deterministic bucket
    # for the Gift identity while the paired minion occupies the card-ID feature.
    CHOICE_TOKEN_BUCKETS = 32

    @classmethod
    def feature_size(cls) -> int:
        return (
            len(cls.ACTION_TYPE_NAMES)
            + cls._index_block_size(cls.MAX_TARGET_INDEX)
            + cls._index_block_size(cls.MAX_POSITION_INDEX)
            + cls._index_block_size(cls.MAX_OPTION_INDEX)
            + cls._index_block_size(cls.MAX_PLAYER_ID)
            + 1 + len(cls.EFFECT_ZONES) + 1
            + cls._index_block_size(cls.MAX_EFFECT_TARGET_INDEX)
            + 1 + cls.CHOICE_TOKEN_BUCKETS
        )

    @classmethod
    def encode(
        cls,
        action: Action,
        observation: "AgentObservation | None" = None,
    ) -> list[float]:
        action_name = action.action_type.value

        if action_name not in cls.ACTION_TYPE_NAMES:
            raise ValueError(
                f"Unsupported ActionType for action schema v{cls.SCHEMA_VERSION}: "
                f"{action_name!r}. Update ActionEncoder explicitly."
            )

        features: list[float] = []
        features.extend(
            1.0 if name == action_name else 0.0
            for name in cls.ACTION_TYPE_NAMES
        )
        features.extend(cls._encode_index(getattr(action, "target_idx", None), cls.MAX_TARGET_INDEX))
        features.extend(cls._encode_index(getattr(action, "position_idx", None), cls.MAX_POSITION_INDEX))
        features.extend(cls._encode_index(getattr(action, "option_idx", None), cls.MAX_OPTION_INDEX))
        features.extend(cls._encode_index(getattr(action, "effect_target_player_id", None), cls.MAX_PLAYER_ID))

        zone = getattr(action, "effect_target_zone", None)
        if hasattr(zone, "value"):
            zone = zone.value
        features.append(1.0 if zone is not None else 0.0)
        features.extend(1.0 if zone == known_zone else 0.0 for known_zone in cls.EFFECT_ZONES)
        features.append(1.0 if zone is not None and zone not in cls.EFFECT_ZONES else 0.0)
        features.extend(cls._encode_index(getattr(action, "effect_target_idx", None), cls.MAX_EFFECT_TARGET_INDEX))

        token = cls.choice_option_token(action, observation)
        token_block = [0.0] * (1 + cls.CHOICE_TOKEN_BUCKETS)
        if token is not None:
            token_block[0] = 1.0
            token_block[1 + cls._stable_bucket(token)] = 1.0
        features.extend(token_block)

        if len(features) != cls.feature_size():
            raise RuntimeError("ActionEncoder internal feature-size mismatch.")
        return features

    @classmethod
    def encode_many(
        cls,
        actions: Iterable[Action],
        observation: "AgentObservation | None" = None,
    ) -> list[list[float]]:
        return [cls.encode(action, observation) for action in actions]

    @classmethod
    def candidate_card_id(
        cls,
        action: Action,
        observation: "AgentObservation | None",
    ) -> int | None:
        """Return the visible card identity this concrete candidate operates on."""
        if observation is None:
            return None

        player = observation.self_player
        action_name = action.action_type.value
        target_idx = getattr(action, "target_idx", None)

        if action_name == "choose_option":
            pending = observation.pending_choice
            option_idx = getattr(action, "option_idx", None)
            if pending is None or option_idx is None:
                return None
            if not 0 <= option_idx < len(pending.options):
                return None
            return cls._extract_card_id(pending.options[option_idx])

        if action_name == "buy_minion":
            return cls._zone_card_id(player.tavern_slots, target_idx)
        if action_name == "buy_spell":
            return cls._extract_card_id(player.tavern_spell)
        if action_name in ("sell_minion", "activate", "reposition"):
            return cls._zone_card_id(player.board, target_idx)
        if action_name in ("play_minion", "cast_spell"):
            return cls._zone_card_id(player.hand, target_idx)
        if action_name == "hero_power":
            return cls._extract_card_id(player.hero_power)
        return None

    @classmethod
    def choice_option_token(
        cls,
        action: Action,
        observation: "AgentObservation | None",
    ) -> str | None:
        if observation is None or action.action_type.value != "choose_option":
            return None
        pending = observation.pending_choice
        option_idx = getattr(action, "option_idx", None)
        if pending is None or option_idx is None or not 0 <= option_idx < len(pending.options):
            return None
        option = pending.options[option_idx]

        # Season 14 DarkGiftOffer: card identity is encoded separately through
        # ``candidate_card_id`` and the Gift name becomes the semantic token.
        gift = getattr(option, "gift", None)
        if isinstance(gift, dict):
            gift_name = gift.get("name")
            if isinstance(gift_name, str) and gift_name:
                return f"dark_gift:{gift_name.casefold()}"

        if isinstance(option, str):
            return option.casefold()
        if isinstance(option, dict):
            if isinstance(option.get("id"), int):
                return None  # card embedding carries the identity
            nested_gift = option.get("gift")
            if isinstance(nested_gift, dict):
                gift_name = nested_gift.get("name")
                if isinstance(gift_name, str) and gift_name:
                    return f"dark_gift:{gift_name.casefold()}"
            for key in ("key", "name", "slug", "type"):
                value = option.get(key)
                if isinstance(value, str) and value:
                    return value.casefold()
        return None

    @classmethod
    def _stable_bucket(cls, token: str) -> int:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % cls.CHOICE_TOKEN_BUCKETS

    @staticmethod
    def _extract_card_id(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value

        # Season 14 DarkGiftOffer pairs one physical minion with one Gift.
        minion = getattr(value, "minion", None)
        if isinstance(minion, dict):
            card_id = minion.get("id")
            return card_id if isinstance(card_id, int) else None

        if isinstance(value, dict):
            card_id = value.get("id")
            if isinstance(card_id, int):
                return card_id
            nested_minion = value.get("minion")
            if isinstance(nested_minion, dict):
                card_id = nested_minion.get("id")
                return card_id if isinstance(card_id, int) else None
        return None

    @classmethod
    def _zone_card_id(cls, zone: Any, index: Any) -> int | None:
        if not isinstance(index, int):
            return None
        try:
            value = zone[index]
        except (IndexError, TypeError, KeyError):
            return None
        return cls._extract_card_id(value)

    @staticmethod
    def _index_block_size(max_index: int) -> int:
        return 1 + (max_index + 1) + 1

    @staticmethod
    def _encode_index(value: int | None, max_index: int) -> list[float]:
        block = [0.0] * ActionEncoder._index_block_size(max_index)
        if value is None:
            return block
        block[0] = 1.0
        if 0 <= value <= max_index:
            block[1 + value] = 1.0
        else:
            block[-1] = 1.0
        return block
