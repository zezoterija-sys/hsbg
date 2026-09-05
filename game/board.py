"""
Game board and state management.

The Player owns the actual board and hand.
This module provides board/state utilities without creating
a second player-state system.

The board uses seven fixed positions.
Empty positions are represented by None.
"""

from copy import deepcopy


class GameState:
    """
    Snapshot of one player's current game state.

    The snapshot contains copied state rather than references
    to the live Player or Bob objects.
    """

    def __init__(self, player, game=None):

        # -----------------------------------------------------
        # PLAYER
        # -----------------------------------------------------

        self.player_id = player.player_id

        self.gold = player.gold
        self.ap = player.ap

        self.hero = player.hero

        self.tavern_tier = player.tavern_tier

        self.waiting = player.waiting

        # Card objects may later contain runtime modifications,
        # so board and hand are copied.
        self.board = deepcopy(player.board)
        self.hand = deepcopy(player.hand)

        # -----------------------------------------------------
        # TAVERN
        # -----------------------------------------------------

        self.tavern = {
            "tier": player.tavern.tier,
            "frozen": player.tavern.frozen,
            "slots": deepcopy(player.tavern.slots),
            "spell": deepcopy(player.tavern.spell),
        }

        # -----------------------------------------------------
        # GAME
        # -----------------------------------------------------

        if game is not None:
            self.round_number = game.round_number
            self.phase = game.phase
            self.priority_order = (
                game.priority_order.copy()
            )
        else:
            self.round_number = None
            self.phase = None
            self.priority_order = []

    def copy(self):
        """Create an independent copy of this snapshot."""

        return deepcopy(self)

    def __repr__(self):

        occupied_board_slots = sum(
            minion is not None
            for minion in self.board
        )

        return (
            f"GameState("
            f"player={self.player_id}, "
            f"round={self.round_number}, "
            f"phase={self.phase}, "
            f"gold={self.gold}, "
            f"ap={self.ap}, "
            f"tavern_tier={self.tavern_tier}, "
            f"board={occupied_board_slots}/7, "
            f"hand={len(self.hand)}, "
            f"waiting={self.waiting}"
            f")"
        )


class GameBoard:
    """
    Board manager for a player.

    The actual board list belongs to Player.

    The board always contains seven fixed positions.
    Empty positions contain None.
    """

    MAX_BOARD_SIZE = 7
    MAX_HAND_SIZE = 10

    def __init__(self, player, game=None):
        self.player = player
        self.game = game

    # =========================================================
    # BOARD
    # =========================================================

    def is_full(self):
        """Return True if all seven board positions are occupied."""

        return all(
            minion is not None
            for minion in self.player.board
        )

    def has_empty_space(self):
        """Return True if the board has an empty position."""

        return any(
            minion is None
            for minion in self.player.board
        )

    def add_minion(self, minion, position=None):
        """
        Add a minion to an empty board position.

        If no position is supplied, use the first empty position.
        """

        if self.is_full():
            raise ValueError(
                "Board is full."
            )

        if position is None:
            position = self.player.board.index(None)

        if (
            position < 0
            or position >= self.MAX_BOARD_SIZE
        ):
            raise ValueError(
                "Invalid board position."
            )

        if self.player.board[position] is not None:
            raise ValueError(
                "Board position is occupied."
            )

        self.player.board[position] = minion

    def remove_minion(self, position):
        """
        Remove and return a minion from a board position.

        The board position remains and becomes None.
        """

        if (
            position < 0
            or position >= self.MAX_BOARD_SIZE
        ):
            raise ValueError(
                "Invalid board position."
            )

        minion = self.player.board[position]

        if minion is None:
            raise ValueError(
                "Board position is empty."
            )

        self.player.board[position] = None

        return minion

    def reposition(self, from_idx, to_idx):
        """Swap two occupied board positions."""

        if (
            from_idx < 0
            or from_idx >= self.MAX_BOARD_SIZE
        ):
            raise ValueError(
                "Invalid source position."
            )

        if (
            to_idx < 0
            or to_idx >= self.MAX_BOARD_SIZE
        ):
            raise ValueError(
                "Invalid destination position."
            )

        if from_idx == to_idx:
            raise ValueError(
                "Source and destination must be different."
            )

        if self.player.board[from_idx] is None:
            raise ValueError(
                "Source position is empty."
            )

        if self.player.board[to_idx] is None:
            raise ValueError(
                "Destination position is empty."
            )

        self.player.board[from_idx], self.player.board[to_idx] = (
            self.player.board[to_idx],
            self.player.board[from_idx],
        )

    # =========================================================
    # HAND
    # =========================================================

    def hand_is_full(self):
        """Return True if the player's hand has ten cards."""

        return (
            len(self.player.hand)
            >= self.MAX_HAND_SIZE
        )

    def add_to_hand(self, card):
        """Add a card to the player's hand."""

        if self.hand_is_full():
            raise ValueError(
                "Hand is full."
            )

        self.player.hand.append(card)

    def remove_from_hand(self, position):
        """Remove and return a card from the player's hand."""

        if (
            position < 0
            or position >= len(self.player.hand)
        ):
            raise ValueError(
                "Invalid hand position."
            )

        return self.player.hand.pop(
            position
        )

    # =========================================================
    # STATE
    # =========================================================

    def get_state(self):
        """Return an independent snapshot of the player's state."""

        return GameState(
            player=self.player,
            game=self.game,
        )

    # =========================================================
    # DEBUG
    # =========================================================

    def __repr__(self):

        occupied_board_slots = sum(
            minion is not None
            for minion in self.player.board
        )

        return (
            f"GameBoard("
            f"player={self.player.player_id}, "
            f"board={occupied_board_slots}/"
            f"{self.MAX_BOARD_SIZE}, "
            f"hand={len(self.player.hand)}/"
            f"{self.MAX_HAND_SIZE}"
            f")"
        )