"""Battlegrounds Solos lobby composition rules.

Battlegrounds rolls five active minion types for a normal lobby. Neutral
minions and All-type minions remain available; a dual-type minion is available
when either of its types is active.

The ten eligible Season 14 types are kept here as game rules instead of being
inferred from whatever happens to be present in a raw card dump.
"""

from __future__ import annotations

from collections.abc import Iterable
import random


SEASON_14_MINION_TYPES: tuple[str, ...] = (
    "Beast",
    "Demon",
    "Dragon",
    "Elemental",
    "Mech",
    "Murloc",
    "Naga",
    "Pirate",
    "Quilboar",
    "Undead",
)

LOBBY_MINION_TYPE_COUNT = 5


def roll_active_minion_types(
    rng: random.Random,
    *,
    eligible_types: Iterable[str] = SEASON_14_MINION_TYPES,
    count: int = LOBBY_MINION_TYPE_COUNT,
) -> tuple[str, ...]:
    """Return one deterministic seeded Solos minion-type roll."""

    types = tuple(dict.fromkeys(str(value) for value in eligible_types))
    if count <= 0:
        raise ValueError("Lobby minion-type count must be positive.")
    if len(types) < count:
        raise ValueError("Not enough eligible minion types for the lobby roll.")

    # Sorting is only for stable public representation. The sample itself is
    # still random and consumes the caller's seeded game RNG.
    return tuple(sorted(rng.sample(types, count)))


def card_minion_types(card) -> tuple[str, ...]:
    """Normalize a card's printed minion types."""

    if not isinstance(card, dict):
        return ()

    values = card.get("minionTypes")
    if not values:
        single = card.get("minionType")
        values = (single,) if single else ()

    return tuple(
        str(value)
        for value in values
        if value
    )


def is_minion_available_for_lobby(
    card,
    active_minion_types: Iterable[str] | None,
) -> bool:
    """Return whether a Tavern minion belongs in this lobby's type pool.

    ``None`` deliberately means no type filtering. That compatibility mode is
    useful for isolated card/effect tests; real Bob games always provide the
    five rolled lobby types.
    """

    if active_minion_types is None:
        return True

    active = {str(value) for value in active_minion_types}
    printed = set(card_minion_types(card))

    # Typeless/general minions appear regardless of the five rolled types.
    if not printed:
        return True

    # Amalgams / All-type minions are relevant in every typed lobby.
    if "All" in printed:
        return True

    # Blizzard's dual-type rule: either active type is enough.
    return bool(printed & active)
