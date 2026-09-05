#!/usr/bin/env python3
"""
Live human-readable viewer for Battlegrounds AI JSONL traces.

Example:
    python scripts/watch_trace.py runs/bg_ai/player_0_actions.jsonl

The process stays running and prints each newly appended trace record.
Press Ctrl+C to stop watching.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def card_text(card: Any) -> str:
    if not isinstance(card, dict):
        return "-"

    name = card.get("name") or f"Card {card.get('id', '?')}"
    attack = card.get("attack", 0)
    health = card.get("health", 0)
    tier = card.get("tier", "?")
    golden = " GOLDEN" if card.get("golden") else ""
    return f"{name} [{attack}/{health}, T{tier}{golden}]"


def zone_text(cards: Any) -> str:
    if not isinstance(cards, list):
        return "(empty)"

    visible = [
        f"{idx}:{card_text(card)}"
        for idx, card in enumerate(cards)
        if isinstance(card, dict)
    ]
    return " | ".join(visible) if visible else "(empty)"


def short_action(action: dict[str, Any], before: dict[str, Any]) -> str:
    action_type = str(action.get("type", "?")).upper()
    text = action.get("text") or action_type.lower()

    detail = []

    target_idx = action.get("target_idx")
    if target_idx is not None:
        detail.append(f"target={target_idx}")

        # Resolve target index to a readable card where possible.
        action_type_lower = str(action.get("type", "")).lower()

        if "buy" in action_type_lower:
            tavern = before.get("tavern") or []
            if 0 <= target_idx < len(tavern):
                card = tavern[target_idx]
                if isinstance(card, dict):
                    detail.append(card.get("name", f"card {card.get('id', '?')}"))

        elif "play" in action_type_lower:
            hand = before.get("hand") or []
            if 0 <= target_idx < len(hand):
                card = hand[target_idx]
                if isinstance(card, dict):
                    detail.append(card.get("name", f"card {card.get('id', '?')}"))

        elif "sell" in action_type_lower:
            board = before.get("board") or []
            if 0 <= target_idx < len(board):
                card = board[target_idx]
                if isinstance(card, dict):
                    detail.append(card.get("name", f"card {card.get('id', '?')}"))

    for key, label in (
        ("position_idx", "position"),
        ("option_idx", "option"),
        ("effect_target_idx", "effect_target"),
        ("effect_target_player_id", "target_player"),
        ("effect_target_zone", "target_zone"),
    ):
        value = action.get(key)
        if value is not None:
            detail.append(f"{label}={value}")

    suffix = f" ({', '.join(str(x) for x in detail)})" if detail else ""
    return f"{action_type}{suffix}"


def changed(before: dict[str, Any], after: dict[str, Any], key: str) -> bool:
    return before.get(key) != after.get(key)


def delta_text(before: dict[str, Any], after: dict[str, Any]) -> str:
    pieces = []

    for key, label in (
        ("health", "HP"),
        ("armor", "Armor"),
        ("gold", "Gold"),
        ("ap", "AP"),
        ("tavern_tier", "Tier"),
    ):
        if changed(before, after, key):
            pieces.append(
                f"{label} {before.get(key, '?')}->{after.get(key, '?')}"
            )

    if changed(before, after, "waiting"):
        pieces.append(
            f"Waiting {before.get('waiting', False)}->{after.get('waiting', False)}"
        )

    if changed(before, after, "board"):
        pieces.append("Board changed")

    if changed(before, after, "hand"):
        pieces.append("Hand changed")

    if changed(before, after, "tavern"):
        pieces.append("Shop changed")

    if changed(before, after, "tavern_spell"):
        pieces.append("Spell changed")

    return ", ".join(pieces) if pieces else "no visible state change"


def format_record(record: dict[str, Any]) -> str:
    before = record.get("before") or {}
    after = record.get("after") or {}
    action = record.get("chosen_action") or {}

    round_number = record.get("round", "?")
    player_id = record.get("player_id", "?")
    brain = record.get("brain", "?")
    agent = record.get("agent", "?")

    lines = [
        "",
        "=" * 90,
        f"ROUND {round_number} | P{player_id} | Brain {brain} / {agent}",
        (
            f"Before: HP {before.get('health', '?')} +{before.get('armor', '?')} armor"
            f" | Gold {before.get('gold', '?')}/{before.get('max_gold', '?')}"
            f" | AP {before.get('ap', '?')}"
            f" | Tavern T{before.get('tavern_tier', '?')}"
        ),
        f"Board: {zone_text(before.get('board'))}",
        f"Hand:  {zone_text(before.get('hand'))}",
        f"Shop:  {zone_text(before.get('tavern'))}",
        f"Spell: {card_text(before.get('tavern_spell'))}",
        "",
        f">>> {short_action(action, before)}",
        f"    {delta_text(before, after)}",
    ]

    if str(action.get("type", "")).lower() == "end_turn":
        lines.append(
            f"    END TURN with {after.get('gold', '?')} gold and "
            f"{sum(isinstance(c, dict) for c in after.get('board', []))} minions"
        )

    return "\n".join(lines)


def watch(path: Path, from_start: bool, poll_interval: float) -> None:
    print(f"Watching: {path}")
    print("Press Ctrl+C to stop.\n")

    # Wait for the trace file if the experiment has not created it yet.
    while not path.exists():
        time.sleep(poll_interval)

    with path.open("r", encoding="utf-8") as f:
        if not from_start:
            f.seek(0, 2)

        while True:
            line = f.readline()

            if not line:
                time.sleep(poll_interval)
                continue

            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # In case we catch the file between write/flush operations,
                # wait briefly and ignore malformed partial input.
                continue

            print(format_record(record), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_file", type=Path)
    parser.add_argument(
        "--from-start",
        action="store_true",
        help="Print existing records first, then continue watching.",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=0.10,
        help="Polling interval in seconds (default: 0.10).",
    )
    args = parser.parse_args()

    try:
        watch(
            args.trace_file,
            from_start=args.from_start,
            poll_interval=max(0.02, args.poll),
        )
    except KeyboardInterrupt:
        print("\nStopped watching.")


if __name__ == "__main__":
    main()
