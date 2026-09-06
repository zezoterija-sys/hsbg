"""Automated multi-game engine playtest for the real Bob controller.

This is deliberately NOT an AI agent.  It is a simple legal-action driver whose
job is to exercise the game engine through many complete games and expose
runtime/integration/state bugs.

Run from the project root:
    python tests/test_bob_multigame_playtest.py

Optional heavier run:
    python tests/test_bob_multigame_playtest.py --games 100 --seed 12345
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game.actions import ActionType
from game.bob import Bob


CARDS_FILE = ROOT / "data" / "raw" / "cards.json"

DEFAULT_GAMES = 20
DEFAULT_SEED = 20260905
MAX_ROUNDS_PER_GAME = 50
MAX_DECISIONS_PER_PLAYER_PER_ROUND = 24
MAX_ACTIONS_PER_RECRUIT_ROUND = 8 * (MAX_DECISIONS_PER_PLAYER_PER_ROUND + 4)


# The driver is intentionally biased toward actions that put real minions into
# combat.  It is not trying to play well; it is trying to exercise the engine.
ACTION_WEIGHTS = {
    ActionType.PLAY_MINION: 14.0,
    ActionType.CAST_SPELL: 10.0,
    ActionType.BUY_MINION: 12.0,
    ActionType.BUY_SPELL: 7.0,
    ActionType.ACTIVATE: 5.0,
    ActionType.UPGRADE_TAVERN: 4.0,
    ActionType.REFRESH: 2.5,
    ActionType.HERO_POWER: 1.5,
    ActionType.SELL_MINION: 0.7,
    ActionType.FREEZE: 0.4,
    ActionType.UNFREEZE: 0.8,
    ActionType.REPOSITION: 0.2,
    ActionType.END_TURN: 1.0,
    ActionType.CHOOSE_OPTION: 1.0,
}


def fail(message: str) -> None:
    raise AssertionError(message)


def validate_player(player, *, game_index: int, round_number: int) -> None:
    prefix = f"game={game_index} round={round_number} player={player.player_id}"

    if not isinstance(player.board, list):
        fail(f"{prefix}: board is not a list: {type(player.board).__name__}")
    if len(player.board) != 7:
        fail(f"{prefix}: board length is {len(player.board)}, expected 7")

    if not isinstance(player.hand, list):
        fail(f"{prefix}: hand is not a list: {type(player.hand).__name__}")
    if len(player.hand) > 10:
        fail(f"{prefix}: hand size is {len(player.hand)}, exceeds 10")

    if player.gold < 0:
        fail(f"{prefix}: negative Gold: {player.gold}")

    max_gold = int(getattr(player, "max_gold", 10) or 10)
    if player.gold > max_gold:
        fail(f"{prefix}: Gold {player.gold} exceeds max_gold {max_gold}")

    if player.ap < 0:
        fail(f"{prefix}: negative AP: {player.ap}")

    if player.health < 0:
        fail(f"{prefix}: negative Health: {player.health}")
    if player.armor < 0:
        fail(f"{prefix}: negative Armor: {player.armor}")

    if player.eliminated and not player.waiting:
        fail(f"{prefix}: eliminated player is not locked/waiting")

    tavern = getattr(player, "tavern", None)
    if tavern is None:
        fail(f"{prefix}: Tavern is missing")
    if not isinstance(tavern.slots, list):
        fail(f"{prefix}: Tavern slots are not a list")
    if len(tavern.slots) > 6:
        fail(f"{prefix}: Tavern has {len(tavern.slots)} slots, exceeds 6")


def validate_game_state(bob, *, game_index: int) -> None:
    if len(bob.players) != 8:
        fail(f"game={game_index}: Bob has {len(bob.players)} players, expected 8")

    if sorted(player.player_id for player in bob.players) != list(range(8)):
        fail(f"game={game_index}: player IDs are not exactly 0..7")

    if sorted(bob.priority_order) != list(range(8)):
        fail(f"game={game_index}: invalid priority order {bob.priority_order}")

    alive = [player for player in bob.players if not player.eliminated]
    if not 0 <= len(alive) <= 8:
        fail(f"game={game_index}: impossible alive-player count {len(alive)}")

    placements = [
        player.placement
        for player in bob.players
        if player.placement is not None
    ]
    if len(placements) != len(set(placements)):
        fail(f"game={game_index}: duplicate placements detected: {placements}")

    for player in bob.players:
        validate_player(
            player,
            game_index=game_index,
            round_number=bob.round_number,
        )

    if bob.game_over:
        if bob.phase != "game_over":
            fail(
                f"game={game_index}: game_over=True but phase={bob.phase!r}"
            )
        if len(alive) > 1:
            fail(
                f"game={game_index}: game over with {len(alive)} living players"
            )
    elif bob.phase not in {"hero_selection", "recruit", "combat"}:
        fail(f"game={game_index}: unexpected phase {bob.phase!r}")


def choose_action(rng, legal_actions, decisions_this_round):
    """Choose one legal action; mandatory choices are always resolved first."""
    choices = [
        action
        for action in legal_actions
        if action.action_type == ActionType.CHOOSE_OPTION
    ]
    if choices:
        return rng.choice(choices)

    end_turn_actions = [
        action
        for action in legal_actions
        if action.action_type == ActionType.END_TURN
    ]

    # Prevent one random driver from burning all 100 AP forever.
    if decisions_this_round >= MAX_DECISIONS_PER_PLAYER_PER_ROUND:
        if not end_turn_actions:
            fail(
                "Decision cap reached but END_TURN is not legal. "
                f"Legal actions: {legal_actions}"
            )
        return end_turn_actions[0]

    # During the first couple of decisions, strongly prefer actual economy /
    # board development if such an action exists.
    productive_types = {
        ActionType.PLAY_MINION,
        ActionType.CAST_SPELL,
        ActionType.BUY_MINION,
        ActionType.BUY_SPELL,
    }
    productive = [
        action for action in legal_actions
        if action.action_type in productive_types
    ]
    if decisions_this_round < 2 and productive:
        return rng.choice(productive)

    actions = list(legal_actions)
    weights = []
    for action in actions:
        weight = ACTION_WEIGHTS.get(action.action_type, 1.0)

        # END_TURN gradually becomes more likely as the player has taken more
        # decisions this round.
        if action.action_type == ActionType.END_TURN:
            weight += decisions_this_round * 0.35

        weights.append(weight)

    return rng.choices(actions, weights=weights, k=1)[0]


def choose_heroes(bob, rng) -> None:
    if bob.phase != "hero_selection":
        fail(f"Expected hero_selection, got {bob.phase!r}")

    # Copy IDs first because the eighth choice automatically starts recruit.
    player_ids = [player.player_id for player in bob.players]
    for player_id in player_ids:
        player = bob.get_player(player_id)
        if not player.hero_choices:
            fail(f"Player {player_id} has no hero choices")
        bob.choose_hero(player_id, rng.choice(player.hero_choices))

    if bob.phase != "recruit" or bob.round_number != 1:
        fail(
            "Hero selection did not flow into round 1 recruit: "
            f"phase={bob.phase!r}, round={bob.round_number}"
        )


def play_one_recruit_round(bob, rng, *, game_index: int, action_counter: Counter) -> int:
    """Drive the current recruit phase until Bob synchronously resolves combat."""
    expected_round = bob.round_number
    decisions = Counter()
    actions_this_round = 0

    while (
        not bob.game_over
        and bob.phase == "recruit"
        and bob.round_number == expected_round
    ):
        submissions = []
        # Gather all choices from one pre-action state. Mandatory continuations
        # remain eligible after the seat's ordinary budget is exhausted.
        for player_id in bob.recruitment.eligible_player_ids():
            legal_actions = bob.get_player_action_space(player_id)
            if not legal_actions:
                fail(f"game={game_index} round={expected_round} player={player_id}: "
                     "scheduler-eligible player has no legal actions")
            action = choose_action(rng, legal_actions, decisions[player_id])
            submissions.append((player_id, action))

        if not submissions:
            fail(f"game={game_index} round={expected_round}: no eligible batch")
        try:
            bob.resolve_action_batch(submissions)
        except Exception as exc:
            raise RuntimeError(
                f"Engine failure: game={game_index}, round={expected_round}, "
                f"batch={submissions!r}"
            ) from exc
        for player_id, action in submissions:
            decisions[player_id] += 1
            action_counter[action.action_type.value] += 1
            actions_this_round += 1
        validate_game_state(bob, game_index=game_index)
        if actions_this_round > MAX_ACTIONS_PER_RECRUIT_ROUND:
            fail(f"game={game_index} round={expected_round}: action limit exceeded")

    # Bob resolves combat synchronously inside the final END_TURN and either
    # enters the next recruit phase or game_over before execute_action returns.
    if not bob.game_over:
        if bob.phase != "recruit":
            fail(
                f"game={game_index} round={expected_round}: expected next recruit "
                f"after combat, got phase={bob.phase!r}"
            )
        if bob.round_number != expected_round + 1:
            fail(
                f"game={game_index}: round jumped from {expected_round} "
                f"to {bob.round_number}"
            )

    return actions_this_round


def run_game(game_index: int, seed: int):
    rng = random.Random(seed)

    bob = Bob(cards_file=str(CARDS_FILE), seed=seed)
    bob.initialize_game()
    validate_game_state(bob, game_index=game_index)

    choose_heroes(bob, rng)
    validate_game_state(bob, game_index=game_index)

    action_counter = Counter()
    total_actions = 0
    combat_rounds = 0
    elimination_events = 0

    while not bob.game_over:
        print(
            f"Game {game_index} | Round {bob.round_number} | "
            f"Alive: {sum(not p.eliminated for p in bob.players)}",
            flush=True,
            )
        if bob.phase != "recruit":
            fail(
                f"game={game_index}: driver expected recruit phase, got {bob.phase!r}"
            )

        if bob.round_number > MAX_ROUNDS_PER_GAME:
            fail(
                f"game={game_index}: did not finish within "
                f"{MAX_ROUNDS_PER_GAME} rounds; alive="
                f"{[p.player_id for p in bob.players if not p.eliminated]}"
            )

        alive_before = sum(not player.eliminated for player in bob.players)
        total_actions += play_one_recruit_round(
            bob,
            rng,
            game_index=game_index,
            action_counter=action_counter,
        )
        combat_rounds += 1

        alive_after = sum(not player.eliminated for player in bob.players)
        elimination_events += max(0, alive_before - alive_after)

        validate_game_state(bob, game_index=game_index)

    alive = [player for player in bob.players if not player.eliminated]
    winner_id = alive[0].player_id if len(alive) == 1 else None

    # A normal completed eight-player game should have one survivor.  Keep the
    # zero-survivor case visible rather than silently accepting it.
    if len(alive) != 1:
        fail(
            f"game={game_index}: game_over reached with {len(alive)} survivors: "
            f"{[player.player_id for player in alive]}"
        )

    if alive[0].placement != 1:
        fail(
            f"game={game_index}: winner player {winner_id} has placement "
            f"{alive[0].placement!r}, expected 1"
        )

    all_placements = sorted(
        player.placement
        for player in bob.players
        if player.placement is not None
    )
    if all_placements != list(range(1, 9)):
        fail(
            f"game={game_index}: final placements are {all_placements}, "
            "expected exactly 1..8"
        )

    return {
        "winner_id": winner_id,
        "rounds": combat_rounds,
        "actions": total_actions,
        "eliminations": elimination_events,
        "action_counter": action_counter,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run automated full-game Bob engine playtests."
    )
    parser.add_argument("--games", type=int, default=DEFAULT_GAMES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    if args.games <= 0:
        raise SystemExit("--games must be positive")

    assert CARDS_FILE.exists(), f"Card database not found: {CARDS_FILE}"

    master_rng = random.Random(args.seed)
    results = []
    combined_actions = Counter()

    for game_index in range(1, args.games + 1):
        game_seed = master_rng.randrange(0, 2**63)
        try:
            result = run_game(game_index, game_seed)
        except Exception:
            print()
            print(
                f"[FAIL] Game {game_index}/{args.games} | seed={game_seed}"
            )
            print(
                "Re-run with the same --seed value to reproduce the driver "
                "sequence up to this game."
            )
            raise

        results.append(result)
        combined_actions.update(result["action_counter"])

        print(
            f"[PASS] Game {game_index:>3}/{args.games} | "
            f"seed={game_seed} | winner=P{result['winner_id']} | "
            f"rounds={result['rounds']} | actions={result['actions']}"
        )

    round_counts = [result["rounds"] for result in results]
    action_counts = [result["actions"] for result in results]
    winners = Counter(result["winner_id"] for result in results)

    print()
    print("AUTOMATED MULTI-GAME PLAYTEST PASSED")
    print(f"Games: {args.games}")
    print(
        "Rounds/game: "
        f"min={min(round_counts)}, "
        f"avg={sum(round_counts) / len(round_counts):.1f}, "
        f"max={max(round_counts)}"
    )
    print(
        "Actions/game: "
        f"min={min(action_counts)}, "
        f"avg={sum(action_counts) / len(action_counts):.1f}, "
        f"max={max(action_counts)}"
    )
    print(
        "Winners: "
        + ", ".join(
            f"P{player_id}={count}"
            for player_id, count in sorted(winners.items())
        )
    )
    print(
        "Actions exercised: "
        + ", ".join(
            f"{action_type}={count}"
            for action_type, count in sorted(combined_actions.items())
        )
    )


if __name__ == "__main__":
    main()
