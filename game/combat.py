"""Combat engine and combat-phase controller."""

from copy import deepcopy
from dataclasses import dataclass, field
import random
from typing import Optional

from .events import EventDispatcher, GameEvent


@dataclass
class CombatSide:
    player_id: int
    tavern_tier: int
    board: list[dict]
    is_ghost: bool = False
    next_attacker_index: int = 0
    dead_minions: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class CombatPairing:
    player_a_id: int
    player_b_id: int
    player_b_is_ghost: bool = False


@dataclass
class CombatResult:
    player_a_id: int
    player_b_id: int
    winner_id: Optional[int]
    loser_id: Optional[int]
    tie: bool
    damage_to_a: int
    damage_to_b: int
    surviving_a: list[dict]
    surviving_b: list[dict]
    attacks: int
    player_b_is_ghost: bool = False


@dataclass
class CombatRoundResult:
    pairings: list[CombatPairing]
    results: list[CombatResult]
    eliminated_player_ids: list[int]
    game_over: bool
    winner_id: Optional[int] = None


class CombatEngine:
    MAX_BOARD_SIZE = 7
    MAX_ATTACKS = 2000

    def __init__(self, events=None, rng=None, priority_order=None):
        self.events = events if events is not None else EventDispatcher()
        self.random = rng if rng is not None else random.Random()
        self.priority_order = list(priority_order or [])
        self._next_combat_id = 1

    # =========================================================
    # EVENTS / PRIORITY
    # =========================================================

    def emit(self, event_type, **context):
        context.setdefault("engine", self)
        return self.events.emit(event_type, **context)

    def set_priority_order(self, priority_order):
        self.priority_order = list(priority_order)

    def _priority_position(self, player_id):
        try:
            return self.priority_order.index(player_id)
        except ValueError:
            return 999

    # =========================================================
    # CARD PREPARATION / KEYWORDS
    # =========================================================

    @staticmethod
    def _normalize_keyword(value):
        return str(value).strip().casefold().replace("-", " ")

    def has_keyword(self, minion, keyword):
        wanted = self._normalize_keyword(keyword)
        return any(
            self._normalize_keyword(value) == wanted
            for value in minion.get("keywords", [])
        )

    def _prepare_minion(self, definition):
        minion = deepcopy(definition)
        minion["attack"] = int(minion.get("attack", 0) or 0)
        minion["health"] = int(minion.get("health", 0) or 0)
        minion.setdefault("keywords", [])

        minion["_combat_id"] = self._next_combat_id
        self._next_combat_id += 1

        minion["_combat_divine_shield"] = self.has_keyword(minion, "Divine Shield")
        minion["_combat_reborn_available"] = self.has_keyword(minion, "Reborn")
        minion["_combat_venomous_available"] = self.has_keyword(minion, "Venomous")
        minion["_combat_stealth"] = self.has_keyword(minion, "Stealth")

        # Current BG cards using the Immune keyword use it while attacking.
        minion["_combat_immune_while_attacking"] = self.has_keyword(minion, "Immune")
        minion["_combat_is_attacking"] = False
        return minion

    @staticmethod
    def _safe_combat_copy(minion):
        """
        Copy a combat minion without following temporary object references
        to other minions or CombatSide objects.
        """
        if not isinstance(minion, dict):
            return deepcopy(minion)

        unsafe_keys = {
            "_combat_last_damage_source",
            "_combat_last_damage_source_side",
        }

        return {
            key: deepcopy(value)
            for key, value in minion.items()
            if key not in unsafe_keys
        }

    def _safe_board_copy(self, board):
        return [
            self._safe_combat_copy(minion)
            for minion in board
        ]

    def create_side(self, player_id, tavern_tier, board, is_ghost=False):
        compact_board = [
            self._prepare_minion(minion)
            for minion in board
            if isinstance(minion, dict)
        ]
        return CombatSide(
            player_id=player_id,
            tavern_tier=int(tavern_tier),
            board=compact_board,
            is_ghost=is_ghost,
        )

    # =========================================================
    # BASIC QUERIES
    # =========================================================

    @staticmethod
    def get_attack(minion):
        return max(0, int(minion.get("attack", 0) or 0))

    @staticmethod
    def is_alive(minion):
        return int(minion.get("health", 0) or 0) > 0

    def can_attack(self, minion):
        return self.is_alive(minion) and self.get_attack(minion) > 0

    def side_can_attack(self, side):
        return any(self.can_attack(minion) for minion in side.board)

    def get_attack_targets(self, defending_side):
        targetable = [
            minion
            for minion in defending_side.board
            if self.is_alive(minion) and not minion.get("_combat_stealth", False)
        ]
        if not targetable:
            return []

        taunts = [minion for minion in targetable if self.has_keyword(minion, "Taunt")]
        return taunts if taunts else targetable

    def _next_attacker(self, side):
        if not side.board:
            return None

        start = side.next_attacker_index % len(side.board)
        for offset in range(len(side.board)):
            idx = (start + offset) % len(side.board)
            minion = side.board[idx]
            if self.can_attack(minion):
                side.next_attacker_index = (idx + 1) % max(1, len(side.board))
                return minion
        return None

    def _attacks_per_turn(self, minion):
        if self.has_keyword(minion, "Mega-Windfury"):
            return 4
        if self.has_keyword(minion, "Windfury"):
            return 2
        return 1

    # =========================================================
    # SUMMONING
    # =========================================================

    def summon(self, side, minion, position=None):
        if len(side.board) >= self.MAX_BOARD_SIZE:
            return None

        runtime = self._prepare_minion(minion)
        if position is None:
            position = len(side.board)
        position = max(0, min(int(position), len(side.board)))
        side.board.insert(position, runtime)

        self.emit(
            GameEvent.MINION_SUMMONED,
            player_id=side.player_id,
            side=side,
            minion=runtime,
            position=position,
        )
        return runtime

    # =========================================================
    # DAMAGE
    # =========================================================

    def _is_immune(self, minion):
        return bool(
            minion.get("_combat_immune", False)
            or (
                minion.get("_combat_immune_while_attacking", False)
                and minion.get("_combat_is_attacking", False)
            )
        )

    def deal_minion_damage(
        self,
        source,
        target,
        amount,
        source_side=None,
        target_side=None,
    ):
        amount = max(0, int(amount or 0))
        if amount <= 0 or not self.is_alive(target):
            return 0

        if self._is_immune(target):
            return 0

        if target.get("_combat_divine_shield", False):
            target["_combat_divine_shield"] = False
            self.emit(
                GameEvent.DIVINE_SHIELD_LOST,
                minion=target,
                side=target_side,
                player_id=getattr(target_side, "player_id", None),
                source_minion=source,
                source_side=source_side,
            )
            return 0

        target["health"] = int(target.get("health", 0) or 0) - amount
        target["_combat_last_damage_source"] = source
        target["_combat_last_damage_source_side"] = source_side

        self.emit(
            GameEvent.MINION_DAMAGED,
            minion=target,
            side=target_side,
            player_id=getattr(target_side, "player_id", None),
            source_minion=source,
            source_side=source_side,
            amount=amount,
        )

        if (
            source is not None
            and source.get("_combat_venomous_available", False)
            and amount > 0
        ):
            source["_combat_venomous_available"] = False
            target["health"] = min(0, int(target.get("health", 0) or 0))

        return amount

    # =========================================================
    # DEATH PROCESSING
    # =========================================================

    def _collect_dead(self, side):
        return [
            (position, minion)
            for position, minion in enumerate(side.board)
            if not self.is_alive(minion)
        ]

    def _death_sort_key(self, entry):
        side, position, _ = entry
        return (self._priority_position(side.player_id), position)

    def resolve_deaths(self, side_a, side_b):
        """Resolve all currently-dead minions, including deaths caused by effects."""

        while True:
            dead_entries = [
                (side_a, position, minion)
                for position, minion in self._collect_dead(side_a)
            ] + [
                (side_b, position, minion)
                for position, minion in self._collect_dead(side_b)
            ]

            if not dead_entries:
                return

            dead_entries.sort(key=self._death_sort_key)

            # All simultaneous deaths leave the board before any one of their
            # Deathrattles resolves.
            for side in (side_a, side_b):
                dead_ids = {
                    id(minion)
                    for entry_side, _, minion in dead_entries
                    if entry_side is side
                }
                side.board[:] = [
                    minion for minion in side.board if id(minion) not in dead_ids
                ]
                if side.board:
                    side.next_attacker_index %= len(side.board)
                else:
                    side.next_attacker_index = 0

            for side, death_position, minion in dead_entries:
                side.dead_minions.append(
                    self._safe_combat_copy(minion)
                )
                self.emit(
                    GameEvent.MINION_DIED,
                    player_id=side.player_id,
                    side=side,
                    minion=minion,
                    death_position=death_position,
                    killer=minion.get("_combat_last_damage_source"),
                    killer_side=minion.get("_combat_last_damage_source_side"),
                )

                if self.has_keyword(minion, "Deathrattle"):
                    self.emit(
                        GameEvent.DEATHRATTLE,
                        player_id=side.player_id,
                        side=side,
                        minion=minion,
                        death_position=death_position,
                        killer=minion.get("_combat_last_damage_source"),
                        killer_side=minion.get("_combat_last_damage_source_side"),
                    )

                if minion.get("_combat_reborn_available", False) and len(side.board) < 7:
                    reborn = {
                        key: deepcopy(value)
                        for key, value in minion.items()
                        if not key.startswith("_combat_")
                    }
                    reborn["health"] = 1
                    reborn["keywords"] = [
                        keyword
                        for keyword in reborn.get("keywords", [])
                        if self._normalize_keyword(keyword) != "reborn"
                    ]
                    # Reborn creates a new runtime minion. Old combat flags are
                    # excluded before the copy reaches summon/_prepare_minion.
                    runtime = self.summon(side, reborn, position=death_position)
                    if runtime is not None:
                        self.emit(
                            GameEvent.REBORN,
                            player_id=side.player_id,
                            side=side,
                            minion=runtime,
                            original_minion=minion,
                            position=death_position,
                        )

                self.emit(
                    GameEvent.AFTER_MINION_DIED,
                    player_id=side.player_id,
                    side=side,
                    minion=minion,
                    death_position=death_position,
                )

    # =========================================================
    # ATTACKING
    # =========================================================

    def _break_stealth(self, attacker, side):
        if attacker.get("_combat_stealth", False):
            attacker["_combat_stealth"] = False
            self.emit(
                GameEvent.STEALTH_LOST,
                player_id=side.player_id,
                side=side,
                minion=attacker,
            )

    def attack(self, attacker, attacking_side, defending_side):
        if attacker not in attacking_side.board or not self.can_attack(attacker):
            return False

        legal_targets = self.get_attack_targets(defending_side)
        if not legal_targets:
            return False
        target = self.random.choice(legal_targets)

        self.emit(
            GameEvent.BEFORE_ATTACK,
            player_id=attacking_side.player_id,
            attacker=attacker,
            target=target,
            attacking_side=attacking_side,
            defending_side=defending_side,
            source_side=attacking_side,
            target_side=defending_side,
        )
        self.resolve_deaths(attacking_side, defending_side)

        if attacker not in attacking_side.board or not self.can_attack(attacker):
            return False

        if target not in defending_side.board or target.get("_combat_stealth", False):
            legal_targets = self.get_attack_targets(defending_side)
            if not legal_targets:
                return False
            target = self.random.choice(legal_targets)

        self._break_stealth(attacker, attacking_side)
        attacker["_combat_is_attacking"] = True

        # Rally and other "whenever this attacks" effects resolve here, before
        # combat damage.
        self.emit(
            GameEvent.ATTACK,
            player_id=attacking_side.player_id,
            attacker=attacker,
            target=target,
            attacking_side=attacking_side,
            defending_side=defending_side,
            source_side=attacking_side,
            target_side=defending_side,
        )
        self.resolve_deaths(attacking_side, defending_side)

        if attacker not in attacking_side.board or not self.can_attack(attacker):
            attacker["_combat_is_attacking"] = False
            return True

        if target not in defending_side.board:
            legal_targets = self.get_attack_targets(defending_side)
            if not legal_targets:
                attacker["_combat_is_attacking"] = False
                return True
            target = self.random.choice(legal_targets)

        attacker_attack = self.get_attack(attacker)
        target_attack = self.get_attack(target)
        target_health_before = int(target.get("health", 0) or 0)
        target_position_before = (
            defending_side.board.index(target)
            if target in defending_side.board
            else None
        )

        self.deal_minion_damage(
            attacker,
            target,
            attacker_attack,
            source_side=attacking_side,
            target_side=defending_side,
        )
        self.deal_minion_damage(
            target,
            attacker,
            target_attack,
            source_side=defending_side,
            target_side=attacking_side,
        )

        attacker["_combat_is_attacking"] = False
        self.resolve_deaths(attacking_side, defending_side)

        self.emit(
            GameEvent.AFTER_ATTACK,
            player_id=attacking_side.player_id,
            attacker=attacker,
            target=target,
            attacker_attack=attacker_attack,
            target_health_before=target_health_before,
            target_position_before=target_position_before,
            target_died=(int(target.get("health", 0) or 0) <= 0),
            excess_damage=max(0, attacker_attack - max(0, target_health_before)),
            attacking_side=attacking_side,
            defending_side=defending_side,
            source_side=attacking_side,
            target_side=defending_side,
        )
        return True

    def _attack_turn(self, attacking_side, defending_side):
        attacker = self._next_attacker(attacking_side)
        if attacker is None:
            return 0

        attacks_done = 0
        for _ in range(self._attacks_per_turn(attacker)):
            if attacker not in attacking_side.board or not self.can_attack(attacker):
                break
            if not self.get_attack_targets(defending_side):
                break
            if self.attack(attacker, attacking_side, defending_side):
                attacks_done += 1
        return attacks_done

    def _first_attacking_side(self, side_a, side_b):
        if len(side_a.board) > len(side_b.board):
            return side_a
        if len(side_b.board) > len(side_a.board):
            return side_b
        return self.random.choice([side_a, side_b])

    # =========================================================
    # COMBAT RESULT
    # =========================================================

    @staticmethod
    def _combat_damage(winner_side):
        return int(winner_side.tavern_tier) + sum(
            max(0, int(minion.get("tier", 0) or 0))
            for minion in winner_side.board
            if int(minion.get("health", 0) or 0) > 0
        )

    def run(self, side_a, side_b):
        self.emit(GameEvent.COMBAT_START, side_a=side_a, side_b=side_b)
        self.resolve_deaths(side_a, side_b)

        current = self._first_attacking_side(side_a, side_b)
        other = side_b if current is side_a else side_a
        attacks = 0

        while side_a.board and side_b.board and attacks < self.MAX_ATTACKS:
            current_can = self.side_can_attack(current) and bool(self.get_attack_targets(other))
            other_can = self.side_can_attack(other) and bool(self.get_attack_targets(current))

            if not current_can and not other_can:
                break
            if not current_can and other_can:
                current, other = other, current
                continue

            attacks += self._attack_turn(current, other)
            current, other = other, current

        if side_a.board and not side_b.board:
            winner_id = side_a.player_id
            loser_id = side_b.player_id
            damage_to_a = 0
            damage_to_b = self._combat_damage(side_a)
            tie = False
        elif side_b.board and not side_a.board:
            winner_id = side_b.player_id
            loser_id = side_a.player_id
            damage_to_a = self._combat_damage(side_b)
            damage_to_b = 0
            tie = False
        else:
            winner_id = None
            loser_id = None
            damage_to_a = 0
            damage_to_b = 0
            tie = True

        result = CombatResult(
            player_a_id=side_a.player_id,
            player_b_id=side_b.player_id,
            winner_id=winner_id,
            loser_id=loser_id,
            tie=tie,
            damage_to_a=damage_to_a,
            damage_to_b=damage_to_b,
            surviving_a=self._safe_board_copy(side_a.board),
            surviving_b=self._safe_board_copy(side_b.board),
            attacks=attacks,
            player_b_is_ghost=side_b.is_ghost,
        )

        self.emit(
            GameEvent.COMBAT_END,
            side_a=side_a,
            side_b=side_b,
            result=result,
        )
        return result


class Combat:
    """Game-level pairing, ghost, damage, and elimination controller."""

    def __init__(self, bob, events=None, rng=None):
        self.bob = bob
        self.events = events if events is not None else bob.events
        self.random = rng if rng is not None else random.Random()
        self.engine = CombatEngine(
            events=self.events,
            rng=self.random,
            priority_order=getattr(bob, "priority_order", []),
        )
        self.last_eliminated_player_id = None

    def _alive_players(self):
        return [player for player in self.bob.players if not player.eliminated]

    def _player(self, player_id):
        return self.bob.get_player(player_id)

    def _is_rematch(self, a_id, b_id):
        a = self._player(a_id)
        b = self._player(b_id)
        return a.last_opponent_id == b_id or b.last_opponent_id == a_id

    def _pair_recursive(self, ids, allow_rematch=False):
        if not ids:
            return []

        first = ids[0]
        candidates = ids[1:].copy()
        self.random.shuffle(candidates)
        candidates.sort(key=lambda other: self._is_rematch(first, other) and not allow_rematch)

        for opponent in candidates:
            if not allow_rematch and self._is_rematch(first, opponent):
                continue
            remaining = [value for value in ids[1:] if value != opponent]
            rest = self._pair_recursive(remaining, allow_rematch=allow_rematch)
            if rest is not None:
                return [(first, opponent)] + rest
        return None

    def _pair_even_players(self, ids):
        shuffled = ids.copy()
        self.random.shuffle(shuffled)
        result = self._pair_recursive(shuffled, allow_rematch=False)
        if result is None:
            result = self._pair_recursive(shuffled, allow_rematch=True)
        if result is None:
            raise RuntimeError("Unable to construct combat pairings.")
        return result

    def _get_ghost_player_id(self):
        """
        Return the most recently eliminated player for ghost combat.

        Normal real games track this directly in last_eliminated_player_id.
        Reconstructed MCTS worlds can lack that runtime-only history, so
        recover it from public elimination/placement state when necessary.
        """
        ghost_id = self.last_eliminated_player_id

        if ghost_id is not None:
            try:
                ghost = self._player(ghost_id)
            except (IndexError, ValueError):
                ghost = None

            if ghost is not None and ghost.eliminated:
                return ghost_id

        eliminated = [
            player
            for player in self.bob.players
            if player.eliminated
        ]

        if not eliminated:
            return None

        with_placement = [
            player
            for player in eliminated
            if player.placement is not None
        ]

        if with_placement:
            # Eliminations progress 8th -> 7th -> ... -> 2nd.
            # Therefore the lowest placement number among eliminated
            # players is the most recently eliminated ghost.
            ghost = min(
                with_placement,
                key=lambda player: int(player.placement),
            )
        elif len(eliminated) == 1:
            # Defensive fallback for partially reconstructed states where
            # exactly one eliminated player exists but placement is absent.
            ghost = eliminated[0]
        else:
            return None

        self.last_eliminated_player_id = ghost.player_id
        return ghost.player_id

    def create_pairings(self):
        alive_ids = [player.player_id for player in self._alive_players()]
        if len(alive_ids) <= 1:
            return []

        pairings = []

        if len(alive_ids) % 2 == 1:
            ghost_id = self._get_ghost_player_id()

            if ghost_id is None:
                raise RuntimeError(
                    "Odd number of living players but no eliminated player "
                    "is available for ghost combat."
                )

            candidates = alive_ids.copy()
            self.random.shuffle(candidates)
            candidates.sort(
                key=lambda player_id: self._player(player_id).last_opponent_id == ghost_id
            )

            ghost_opponent = candidates[0]
            alive_ids.remove(ghost_opponent)

            pairings.append(
                CombatPairing(
                    player_a_id=ghost_opponent,
                    player_b_id=ghost_id,
                    player_b_is_ghost=True,
                )
            )

        for a_id, b_id in self._pair_even_players(alive_ids):
            pairings.append(CombatPairing(a_id, b_id, False))

        return pairings

    def _snapshot_alive_boards(self):
        snapshots = {}
        for player in self._alive_players():
            board = player.snapshot_combat_board()
            for index, minion in enumerate(board):
                if isinstance(minion, dict):
                    minion["_persistent_board_index"] = index
            snapshots[player.player_id] = board
            player.last_combat_board = deepcopy(board)
        return snapshots

    def _ghost_board(self, player):
        getter = getattr(player, "get_last_combat_board", None)
        if callable(getter):
            return getter()
        return deepcopy(getattr(player, "last_combat_board", None) or [None] * 7)

    def _resolve_pairing(self, pairing, snapshots):
        player_a = self._player(pairing.player_a_id)
        player_b = self._player(pairing.player_b_id)

        board_a = snapshots[player_a.player_id]
        board_b = (
            self._ghost_board(player_b)
            if pairing.player_b_is_ghost
            else snapshots[player_b.player_id]
        )

        side_a = self.engine.create_side(
            player_a.player_id,
            player_a.tavern_tier,
            board_a,
        )
        side_b = self.engine.create_side(
            player_b.player_id,
            player_b.tavern_tier,
            board_b,
            is_ghost=pairing.player_b_is_ghost,
        )

        player_a.set_last_opponent(player_b.player_id)
        if not pairing.player_b_is_ghost:
            player_b.set_last_opponent(player_a.player_id)

        return self.engine.run(side_a, side_b)

    def _apply_persistent_poet(self, player, survivors):
        """Persist combat gains on Dragons adjacent to Persistent Poet."""
        POET_ID = 108463
        board = player.board
        protected = {}
        for index, card in enumerate(board):
            if not isinstance(card, dict) or card.get("id") != POET_ID:
                continue
            multiplier = 2 if card.get("isGolden", False) else 1
            for neighbor in (index - 1, index + 1):
                if not 0 <= neighbor < len(board):
                    continue
                target = board[neighbor]
                if not isinstance(target, dict):
                    continue
                types = set(target.get("minionTypes") or [])
                if target.get("minionType"):
                    types.add(target.get("minionType"))
                if "Dragon" not in types and "All" not in types:
                    continue
                protected[neighbor] = max(protected.get(neighbor, 0), multiplier)

        for board_index, multiplier in protected.items():
            original = board[board_index]
            runtime = next(
                (
                    minion for minion in survivors
                    if isinstance(minion, dict)
                    and minion.get("_persistent_board_index") == board_index
                ),
                None,
            )
            if runtime is None:
                continue
            attack_gain = max(
                0,
                int(runtime.get("attack", 0) or 0)
                - int(original.get("attack", 0) or 0),
            )
            health_gain = max(
                0,
                int(runtime.get("health", 0) or 0)
                - int(original.get("health", 0) or 0),
            )
            original["attack"] = int(original.get("attack", 0) or 0) + attack_gain * multiplier
            original["health"] = int(original.get("health", 0) or 0) + health_gain * multiplier

            existing = {str(value).casefold() for value in original.get("keywords", [])}
            for keyword in runtime.get("keywords", []):
                normalized = str(keyword).casefold()
                if normalized in existing:
                    continue
                if normalized in {"magnetic"}:
                    continue
                original.setdefault("keywords", []).append(keyword)
                original.setdefault("_permanent_keyword_grants", []).append(keyword)
                existing.add(normalized)

    def _record_combat_results(self, pairings, results):
        for pairing, result in zip(pairings, results):
            player_a = self._player(pairing.player_a_id)
            player_a.last_combat_won = result.winner_id == player_a.player_id
            player_a.last_combat_tied = result.tie
            self._apply_persistent_poet(player_a, result.surviving_a)

            if not pairing.player_b_is_ghost:
                player_b = self._player(pairing.player_b_id)
                player_b.last_combat_won = result.winner_id == player_b.player_id
                player_b.last_combat_tied = result.tie
                self._apply_persistent_poet(player_b, result.surviving_b)

    def _apply_player_damage(self, player, amount, opponent_id):
        if amount <= 0 or player.eliminated:
            return
        armor_damage, health_damage = player.take_damage(amount)
        self.events.emit(
            GameEvent.PLAYER_DAMAGED,
            player_id=player.player_id,
            opponent_id=opponent_id,
            amount=amount,
            armor_damage=armor_damage,
            health_damage=health_damage,
        )

    def _ordered_eliminated(self, players):
        def key(player):
            try:
                return self.bob.priority_order.index(player.player_id)
            except ValueError:
                return 999
        return sorted(players, key=key)

    def _assign_elimination_placements(self, alive_before, eliminated):
        ordered = self._ordered_eliminated(eliminated)
        first_place = alive_before - len(ordered) + 1
        for offset, player in enumerate(ordered):
            player.set_placement(first_place + offset)
        return ordered

    def run_round(self):
        alive = self._alive_players()
        if len(alive) <= 1:
            winner_id = alive[0].player_id if alive else None
            if alive and alive[0].placement is None:
                alive[0].set_placement(1)
            return CombatRoundResult([], [], [], True, winner_id=winner_id)

        self.engine.set_priority_order(self.bob.priority_order)
        self.events.emit(
            GameEvent.COMBAT_PHASE_START,
            round_number=self.bob.round_number,
        )

        alive_before = len(alive)
        snapshots = self._snapshot_alive_boards()
        pairings = self.create_pairings()
        results = [self._resolve_pairing(pairing, snapshots) for pairing in pairings]
        self._record_combat_results(pairings, results)

        # Apply hero damage only after every pairing has resolved so simultaneous
        # eliminations are truly simultaneous.
        for pairing, result in zip(pairings, results):
            player_a = self._player(pairing.player_a_id)
            player_b = self._player(pairing.player_b_id)

            if result.damage_to_a > 0:
                self._apply_player_damage(player_a, result.damage_to_a, player_b.player_id)
            if result.damage_to_b > 0 and not pairing.player_b_is_ghost:
                self._apply_player_damage(player_b, result.damage_to_b, player_a.player_id)

        newly_eliminated = [
            player
            for player in alive
            if player.health <= 0 or player.eliminated
        ]
        for player in newly_eliminated:
            player.mark_eliminated()

        ordered_eliminated = self._assign_elimination_placements(
            alive_before,
            newly_eliminated,
        )
        if ordered_eliminated:
            self.last_eliminated_player_id = ordered_eliminated[0].player_id

        for player in ordered_eliminated:
            self.events.emit(
                GameEvent.PLAYER_ELIMINATED,
                player_id=player.player_id,
                placement=player.placement,
            )

        remaining = self._alive_players()
        game_over = len(remaining) <= 1
        winner_id = remaining[0].player_id if len(remaining) == 1 else None

        if winner_id is not None:
            winner = remaining[0]
            if winner.placement is None:
                winner.set_placement(1)
            self.events.emit(GameEvent.GAME_END, winner_id=winner_id)

        self.events.emit(
            GameEvent.COMBAT_PHASE_END,
            round_number=self.bob.round_number,
            eliminated_player_ids=[player.player_id for player in ordered_eliminated],
            game_over=game_over,
            winner_id=winner_id,
        )

        return CombatRoundResult(
            pairings=pairings,
            results=results,
            eliminated_player_ids=[player.player_id for player in ordered_eliminated],
            game_over=game_over,
            winner_id=winner_id,
        )
