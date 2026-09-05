"""Regression tests for odd-player combat ghost pairing."""

from pathlib import Path

from game.bob import Bob


CARDS_FILE = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "raw"
    / "cards.json"
)


def _make_bob():
    """Create a lightweight Bob with players but without starting a game."""
    bob = Bob(cards_file=str(CARDS_FILE))
    bob.create_players()
    bob.priority_order = list(range(bob.PLAYER_COUNT))
    return bob


def _eliminate(player, placement):
    """Set only the public state needed by combat pairing."""
    player.eliminated = True
    player.waiting = True
    player.placement = placement


def test_odd_survivors_recover_missing_ghost_from_placements():
    """
    Regression for MCTS reconstructed worlds.

    Five players are alive, three are eliminated, and combat runtime history
    has lost last_eliminated_player_id. Pairing must recover the most recently
    eliminated player from placement data instead of passing five players to
    _pair_even_players().
    """
    bob = _make_bob()

    # P0-P4 alive.
    # P5 died first (8th), then P6 (7th), then P7 most recently (6th).
    _eliminate(bob.get_player(5), 8)
    _eliminate(bob.get_player(6), 7)
    _eliminate(bob.get_player(7), 6)

    bob.combat.last_eliminated_player_id = None

    pairings = bob.combat.create_pairings()

    assert bob.combat.last_eliminated_player_id == 7
    assert len(pairings) == 3

    ghost_pairings = [
        pairing
        for pairing in pairings
        if pairing.player_b_is_ghost
    ]

    assert len(ghost_pairings) == 1
    assert ghost_pairings[0].player_b_id == 7

    # Every living player must appear exactly once.
    living_ids = set(range(5))
    paired_living_ids = []

    for pairing in pairings:
        paired_living_ids.append(pairing.player_a_id)
        if not pairing.player_b_is_ghost:
            paired_living_ids.append(pairing.player_b_id)

    assert set(paired_living_ids) == living_ids
    assert len(paired_living_ids) == len(living_ids)


def test_odd_survivors_keep_valid_tracked_ghost():
    """Normal real-game ghost history should remain authoritative."""
    bob = _make_bob()

    _eliminate(bob.get_player(5), 8)
    _eliminate(bob.get_player(6), 7)
    _eliminate(bob.get_player(7), 6)

    # Pretend runtime history explicitly says P6 is the current ghost.
    bob.combat.last_eliminated_player_id = 6

    pairings = bob.combat.create_pairings()

    ghost_pairings = [
        pairing
        for pairing in pairings
        if pairing.player_b_is_ghost
    ]

    assert bob.combat.last_eliminated_player_id == 6
    assert len(ghost_pairings) == 1
    assert ghost_pairings[0].player_b_id == 6


def test_odd_lobby_without_any_eliminated_player_fails_clearly():
    """
    An odd survivor count with no possible ghost is an invalid reconstructed
    state and should fail with a useful error rather than the old opaque
    even-pairing failure.
    """
    bob = _make_bob()

    # Make exactly five players visible to Combat as alive without providing
    # any eliminated player that could legally act as a ghost.
    bob.players = bob.players[:5]
    bob.combat.last_eliminated_player_id = None

    try:
        bob.combat.create_pairings()
    except RuntimeError as exc:
        assert "no eliminated player" in str(exc).lower()
    else:
        raise AssertionError(
            "Expected RuntimeError for odd lobby with no available ghost."
        )
