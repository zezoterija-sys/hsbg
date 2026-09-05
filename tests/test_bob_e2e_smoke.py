"""End-to-end Bob smoke test.

Exercises the real game orchestration path without relying on any specific
random Tavern minion:

    initialize game
    -> hero selection for all 8 players
    -> round 1 recruit initialization
    -> one real Refresh action
    -> all players end turn
    -> real combat round
    -> automatic round 2 recruit initialization

Run from the project root with:
    python tests/test_bob_e2e_smoke.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game.actions import ActionType
from game.bob import Bob


CARDS_FILE = ROOT / "data" / "raw" / "cards.json"


def passed(name):
    print(f"[PASS] {name}")


def get_action(bob, player_id, action_type):
    """Return the first currently legal action of the requested type."""
    actions = bob.get_player_action_space(player_id)
    for action in actions:
        if action.action_type == action_type:
            return action

    available = ", ".join(action.action_type.value for action in actions)
    raise AssertionError(
        f"Player {player_id} has no legal {action_type.value} action. "
        f"Available: [{available}]"
    )


# ---------------------------------------------------------------------------
# 1. Construct and initialize the real game controller.
# ---------------------------------------------------------------------------
assert CARDS_FILE.exists(), f"Card database not found: {CARDS_FILE}"

bob = Bob(cards_file=str(CARDS_FILE))
bob.initialize_game()

assert bob.phase == "hero_selection"
assert bob.round_number == 0
assert bob.game_over is False
assert len(bob.players) == 8
assert sorted(bob.priority_order) == list(range(8))

for player in bob.players:
    assert player.hero is None
    assert len(player.hero_choices) == 4
    assert player.ap == 1

all_offers = [
    hero_id
    for player in bob.players
    for hero_id in player.hero_choices
]
assert len(all_offers) == 32
assert len(set(all_offers)) == 32

passed("Bob initializes 8-player unique hero selection")


# ---------------------------------------------------------------------------
# 2. Choose one offered hero for every player.
#    The final selection should automatically start round 1 recruitment.
# ---------------------------------------------------------------------------
chosen_heroes = {}

for player in bob.players:
    hero_id = player.hero_choices[0]
    chosen_heroes[player.player_id] = hero_id
    bob.choose_hero(player.player_id, hero_id)

assert len(set(chosen_heroes.values())) == 8
assert bob.phase == "recruit"
assert bob.round_number == 1

for player in bob.players:
    assert player.hero is not None
    assert player.hero_choices == []
    assert player.eliminated is False
    assert player.waiting is False
    assert player.gold == 3
    assert player.ap == 100
    assert player.tavern_tier == 1
    assert any(card is not None for card in player.tavern.slots)

passed("Hero selection flows automatically into round 1 recruitment")


# ---------------------------------------------------------------------------
# 3. Execute one ordinary recruit action through Bob.
#    Refresh is deterministic at the rules level and avoids depending on the
#    identity/effect of a random shop minion.
# ---------------------------------------------------------------------------
p0 = bob.get_player(0)
refresh_action = get_action(bob, 0, ActionType.REFRESH)

gold_before = p0.gold
ap_before = p0.ap

bob.execute_action(0, refresh_action)

assert bob.phase == "recruit"
assert bob.round_number == 1
assert p0.gold == gold_before - 1
assert p0.ap == ap_before - 1
assert p0.waiting is False
assert any(card is not None for card in p0.tavern.slots)

passed("Real Bob -> ActionSpace -> Refresh -> Effects/Tavern/Pool path")


# ---------------------------------------------------------------------------
# 4. End every player's recruit turn through the real Action API.
#    The eighth END_TURN should trigger:
#        RECRUIT_END -> Bob.combat_phase() -> Combat.run_round()
#        -> Bob.start_recruit_phase() -> round 2
# ---------------------------------------------------------------------------
for player_id in range(8):
    assert bob.phase == "recruit"
    end_turn = get_action(bob, player_id, ActionType.END_TURN)
    bob.execute_action(player_id, end_turn)

    # For the first seven players the current recruit phase must still exist.
    if player_id < 7:
        assert bob.phase == "recruit"
        assert bob.round_number == 1
        assert bob.get_player(player_id).waiting is True

passed("All eight END_TURN actions resolve through Recruitment")


# ---------------------------------------------------------------------------
# 5. Empty boards produce four ties, then Bob should automatically initialize
#    round 2 instead of stopping in combat.
# ---------------------------------------------------------------------------
assert bob.last_combat_result is not None
assert bob.last_combat_result.game_over is False
assert len(bob.last_combat_result.pairings) == 4
assert len(bob.last_combat_result.results) == 4
assert all(result.tie for result in bob.last_combat_result.results)
assert bob.last_combat_result.eliminated_player_ids == []

assert bob.game_over is False
assert bob.phase == "recruit"
assert bob.round_number == 2
assert len(bob.get_alive_players()) == 8

passed("Recruit completion runs a real 8-player combat round")


# ---------------------------------------------------------------------------
# 6. Verify the automatic next recruit phase was fully prepared.
# ---------------------------------------------------------------------------
for player in bob.players:
    assert player.eliminated is False
    assert player.waiting is False
    assert player.gold == 4
    assert player.ap == 100
    assert any(card is not None for card in player.tavern.slots)

    legal_actions = bob.get_player_action_space(player.player_id)
    assert legal_actions
    assert any(
        action.action_type == ActionType.END_TURN
        for action in legal_actions
    )

passed("Round 2 resources, Taverns, and action spaces initialize correctly")


print()
print("ALL BOB END-TO-END SMOKE TESTS PASSED")
