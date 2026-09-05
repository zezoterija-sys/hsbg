"""
AI-safe observation and per-seat opponent memory.

This module is the information boundary between Bob's full simulator state and
an AI agent. Agents should receive AgentObservation objects, never Bob itself.

Important design rules:
- The controlled player sees its own full visible recruit state.
- Opponent public stats are visible.
- Opponent boards are remembered only after they were actually observed.
- Board memories carry an age in rounds.
- Tavern-tier changes are remembered as public events.
- The shared pool's *rules* are known, but exact hidden remaining contents are
  never exposed.
- Pool evidence is descriptive, not a hard "copies remaining" oracle.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional


CardData = dict[str, Any]
BoardData = tuple[CardData | None, ...]


def _copy_card(card: Any) -> CardData | None:
    if not isinstance(card, dict):
        return None
    return deepcopy(card)


def _copy_zone(cards: Iterable[Any]) -> BoardData:
    return tuple(_copy_card(card) for card in cards)


def _hero_id(hero: Any) -> int | str | None:
    if isinstance(hero, dict):
        return hero.get("id")
    if isinstance(hero, (int, str)):
        return hero
    return None


def _card_id(card: Any) -> int | None:
    if not isinstance(card, dict):
        return None
    card_id = card.get("id")
    return card_id if isinstance(card_id, int) else None


@dataclass(frozen=True)
class TavernUpgradeMemory:
    """A public Tavern-tier change observed by this player."""

    player_id: int
    old_tier: int
    new_tier: int
    seen_round: int
    rounds_old: int


@dataclass(frozen=True)
class OpponentBoardMemory:
    """Last board this player actually observed for one opponent."""

    player_id: int
    seen_round: int
    rounds_old: int
    board: BoardData


@dataclass(frozen=True)
class PublicOpponentView:
    """Information about an opponent that a normal player may know."""

    player_id: int
    hero_id: int | str | None
    health: int
    armor: int
    tavern_tier: int
    eliminated: bool
    placement: int | None
    last_opponent_id: int | None
    last_seen_board: OpponentBoardMemory | None


@dataclass(frozen=True)
class OwnPlayerView:
    """Full visible state for the controlled player."""

    player_id: int
    hero_id: int | str | None
    hero_power: CardData | None
    health: int
    armor: int
    gold: int
    ap: int
    tavern_tier: int
    waiting: bool
    eliminated: bool
    placement: int | None
    board: BoardData
    hand: BoardData
    tavern_slots: BoardData
    tavern_spell: CardData | None
    tavern_frozen: bool
    effect_state: Mapping[str, Any]
    max_gold: int = 10
    hero_power_cost: int = 0


@dataclass(frozen=True)
class RememberedPoolEvidence:
    """
    Stale evidence that copies of one card were seen on an opponent board.

    This is deliberately NOT interpreted as copies still removed from the pool.
    An old board may have changed, a minion may have been sold, or generated
    copies may exist.
    """

    card_id: int
    visible_equivalents: int
    rounds_old: int
    opponent_id: int


@dataclass(frozen=True)
class PoolKnowledge:
    """
    Legal pool knowledge available to the agent.

    initial_*_copies_by_tier are game rules.
    own_visible_counts are cards currently visible in the controlled player's
    own zones.
    opponent_memory_evidence is stale evidence only.

    There is intentionally no exact_remaining_counts field.
    """

    initial_minion_copies_by_tier: Mapping[int, int]
    initial_spell_copies_by_tier: Mapping[int, int]
    own_visible_counts: Mapping[int, int]
    opponent_memory_evidence: tuple[RememberedPoolEvidence, ...]


@dataclass(frozen=True)
class ChoiceView:
    """An own pending Discover / Choose One decision, when one exists."""

    options: tuple[Any, ...]
    resolver_key: str | None = None
    kind: str = "choice"
    source_card_id: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    source_card: CardData | None = None


@dataclass(frozen=True)
class AgentObservation:
    """Complete AI-visible snapshot for one player seat."""

    player_id: int
    round_number: int
    phase: str | None
    game_over: bool

    self_player: OwnPlayerView
    opponents: tuple[PublicOpponentView, ...]

    last_opponent_id: int | None
    pool: PoolKnowledge

    recent_tavern_upgrades: tuple[TavernUpgradeMemory, ...]
    pending_choice: ChoiceView | None = None

    def opponent(self, player_id: int) -> PublicOpponentView:
        for opponent in self.opponents:
            if opponent.player_id == player_id:
                return opponent
        raise KeyError(f"No opponent with player_id={player_id}.")


@dataclass
class _StoredBoardMemory:
    seen_round: int
    board: BoardData


class AgentMemory:
    """
    Per-seat memory.

    Each of the eight agents gets its own AgentMemory. Same-brain agents must
    never share this object.
    """

    def __init__(self, player_id: int) -> None:
        self.player_id = player_id
        self._boards: dict[int, _StoredBoardMemory] = {}
        self._last_public_tiers: dict[int, int] = {}
        self._upgrade_history: list[tuple[int, int, int, int]] = []
        self._last_synced_combat_round: int | None = None

    def reset_game(self) -> None:
        self._boards.clear()
        self._last_public_tiers.clear()
        self._upgrade_history.clear()
        self._last_synced_combat_round = None

    def seed_from_observation(
        self,
        observation: AgentObservation,
    ) -> None:
        """
        Seed a simulation-side memory object from an existing observation.

        This copies only information already available to the controlled
        player. It is used when a determinized MCTS world is created.
        """
        if observation.player_id != self.player_id:
            raise ValueError(
                "Observation player_id does not match AgentMemory player_id."
            )

        self.reset_game()

        for opponent in observation.opponents:
            self._last_public_tiers[
                opponent.player_id
            ] = opponent.tavern_tier

            memory = opponent.last_seen_board
            if memory is not None:
                self._boards[
                    opponent.player_id
                ] = _StoredBoardMemory(
                    seen_round=memory.seen_round,
                    board=_copy_zone(memory.board),
                )

        self._upgrade_history = [
            (
                event.player_id,
                event.old_tier,
                event.new_tier,
                event.seen_round,
            )
            for event in observation.recent_tavern_upgrades
        ]

        # The current recruit round follows the previous combat round.
        # Mark that already-known combat as synchronized so the first simulated
        # observation cannot overwrite real remembered information with a
        # freshly sampled determinization.
        self._last_synced_combat_round = max(
            0,
            int(observation.round_number) - 1,
        )

    def observe_opponent_board(
        self,
        opponent_id: int,
        board: Iterable[Any],
        round_number: int,
    ) -> None:
        if opponent_id == self.player_id:
            raise ValueError("Cannot store own board as opponent memory.")
        self._boards[opponent_id] = _StoredBoardMemory(
            seen_round=int(round_number),
            board=_copy_zone(board),
        )

    def sync_public_tavern_tiers(
        self,
        players: Iterable[Any],
        round_number: int,
    ) -> None:
        """
        Record public Tavern-tier changes.

        This uses only current public Tavern tiers. It does not inspect shops,
        hands, gold, or hidden pool state.
        """
        current_round = int(round_number)

        for player in players:
            pid = int(getattr(player, "player_id"))
            if pid == self.player_id:
                continue

            tier = int(getattr(player, "tavern_tier", 1))
            previous = self._last_public_tiers.get(pid)

            if previous is not None and tier > previous:
                self._upgrade_history.append(
                    (pid, previous, tier, current_round)
                )

            self._last_public_tiers[pid] = tier

    def sync_last_combat_from_game(self, game: Any) -> None:
        """
        Learn the board of the opponent just fought.

        Player.last_combat_board is the board that entered combat. Reading the
        opponent's snapshot here is fair because this controlled player saw
        that board during its own combat.

        This method intentionally learns only the controlled player's actual
        last opponent, never arbitrary opponents.
        """
        round_number = int(getattr(game, "round_number", 0))
        combat_round = round_number - 1

        if combat_round < 1:
            return

        if self._last_synced_combat_round == combat_round:
            return

        player = game.get_player(self.player_id)
        opponent_id = getattr(player, "last_opponent_id", None)

        if opponent_id is None:
            return

        opponent = game.get_player(opponent_id)
        board = getattr(opponent, "last_combat_board", None)

        if board is None:
            return

        self.observe_opponent_board(
            opponent_id=opponent_id,
            board=board,
            round_number=combat_round,
        )
        self._last_synced_combat_round = combat_round

    def get_board_memory(
        self,
        opponent_id: int,
        current_round: int,
    ) -> OpponentBoardMemory | None:
        stored = self._boards.get(opponent_id)
        if stored is None:
            return None

        return OpponentBoardMemory(
            player_id=opponent_id,
            seen_round=stored.seen_round,
            rounds_old=max(0, int(current_round) - stored.seen_round),
            board=_copy_zone(stored.board),
        )

    def get_upgrade_history(
        self,
        current_round: int,
    ) -> tuple[TavernUpgradeMemory, ...]:
        current = int(current_round)
        return tuple(
            TavernUpgradeMemory(
                player_id=pid,
                old_tier=old,
                new_tier=new,
                seen_round=seen_round,
                rounds_old=max(0, current - seen_round),
            )
            for pid, old, new, seen_round in self._upgrade_history
        )


class ObservationBuilder:
    """Build AgentObservation snapshots from the real game."""

    def __init__(self, memory: AgentMemory) -> None:
        self.memory = memory

    def build(self, game: Any) -> AgentObservation:
        player_id = self.memory.player_id
        player = game.get_player(player_id)
        round_number = int(getattr(game, "round_number", 0))

        self.memory.sync_public_tavern_tiers(
            getattr(game, "players", ()),
            round_number,
        )
        self.memory.sync_last_combat_from_game(game)

        self_view = self._build_self_view(game, player)

        opponents = tuple(
            self._build_opponent_view(other, round_number)
            for other in getattr(game, "players", ())
            if int(getattr(other, "player_id")) != player_id
        )

        return AgentObservation(
            player_id=player_id,
            round_number=round_number,
            phase=getattr(game, "phase", None),
            game_over=bool(getattr(game, "game_over", False)),
            self_player=self_view,
            opponents=opponents,
            last_opponent_id=getattr(player, "last_opponent_id", None),
            pool=self._build_pool_knowledge(game, self_view, opponents),
            recent_tavern_upgrades=self.memory.get_upgrade_history(
                round_number
            ),
            pending_choice=self._build_pending_choice(game, player_id),
        )

    def _build_self_view(self, game: Any, player: Any) -> OwnPlayerView:
        tavern = getattr(player, "tavern", None)

        hero_power = None
        get_power = getattr(player, "get_hero_power", None)
        if callable(get_power):
            hero_power = _copy_card(get_power())

        effects = getattr(game, "effects", None)
        effect_state: dict[str, Any] = {}
        if effects is not None:
            get_state = getattr(effects, "get_player_state", None)
            if callable(get_state):
                raw_state = get_state(int(getattr(player, "player_id")))
                if isinstance(raw_state, dict):
                    effect_state = deepcopy(raw_state)

        return OwnPlayerView(
            player_id=int(getattr(player, "player_id")),
            hero_id=_hero_id(getattr(player, "hero", None)),
            hero_power=hero_power,
            health=int(getattr(player, "health", 0)),
            armor=int(getattr(player, "armor", 0)),
            gold=int(getattr(player, "gold", 0)),
            ap=int(getattr(player, "ap", 0)),
            tavern_tier=int(getattr(player, "tavern_tier", 1)),
            waiting=bool(getattr(player, "waiting", False)),
            eliminated=bool(getattr(player, "eliminated", False)),
            placement=getattr(player, "placement", None),
            board=_copy_zone(getattr(player, "board", ())),
            hand=_copy_zone(getattr(player, "hand", ())),
            tavern_slots=_copy_zone(
                getattr(tavern, "slots", ()) if tavern is not None else ()
            ),
            tavern_spell=_copy_card(
                getattr(tavern, "spell", None) if tavern is not None else None
            ),
            tavern_frozen=bool(
                getattr(tavern, "frozen", False)
                if tavern is not None
                else False
            ),
            effect_state=effect_state,
            max_gold=int(getattr(player, "max_gold", 10) or 10),
            hero_power_cost=int(
                getattr(player, "hero_power_cost", 0) or 0
            ),
        )

    def _build_opponent_view(
        self,
        opponent: Any,
        round_number: int,
    ) -> PublicOpponentView:
        pid = int(getattr(opponent, "player_id"))

        return PublicOpponentView(
            player_id=pid,
            hero_id=_hero_id(getattr(opponent, "hero", None)),
            health=int(getattr(opponent, "health", 0)),
            armor=int(getattr(opponent, "armor", 0)),
            tavern_tier=int(getattr(opponent, "tavern_tier", 1)),
            eliminated=bool(getattr(opponent, "eliminated", False)),
            placement=getattr(opponent, "placement", None),
            last_opponent_id=getattr(opponent, "last_opponent_id", None),
            last_seen_board=self.memory.get_board_memory(
                pid,
                round_number,
            ),
        )

    def _build_pool_knowledge(
        self,
        game: Any,
        self_view: OwnPlayerView,
        opponents: tuple[PublicOpponentView, ...],
    ) -> PoolKnowledge:
        pool = getattr(game, "pool", None)

        minion_rules = dict(
            getattr(pool, "MINION_COPY_COUNTS", {})
            if pool is not None
            else {}
        )
        spell_rules = dict(
            getattr(pool, "TAVERN_SPELL_COPY_COUNTS", {})
            if pool is not None
            else {}
        )

        own_counts: Counter[int] = Counter()

        for zone in (
            self_view.board,
            self_view.hand,
            self_view.tavern_slots,
        ):
            for card in zone:
                card_id = _card_id(card)
                if card_id is not None:
                    own_counts[card_id] += self._visible_copy_equivalent(card)

        spell_id = _card_id(self_view.tavern_spell)
        if spell_id is not None:
            own_counts[spell_id] += 1

        remembered: list[RememberedPoolEvidence] = []

        for opponent in opponents:
            memory = opponent.last_seen_board
            if memory is None:
                continue

            counts: Counter[int] = Counter()
            for card in memory.board:
                card_id = _card_id(card)
                if card_id is not None:
                    counts[card_id] += self._visible_copy_equivalent(card)

            remembered.extend(
                RememberedPoolEvidence(
                    card_id=card_id,
                    visible_equivalents=count,
                    rounds_old=memory.rounds_old,
                    opponent_id=opponent.player_id,
                )
                for card_id, count in counts.items()
            )

        return PoolKnowledge(
            initial_minion_copies_by_tier=minion_rules,
            initial_spell_copies_by_tier=spell_rules,
            own_visible_counts=dict(own_counts),
            opponent_memory_evidence=tuple(remembered),
        )

    @staticmethod
    def _visible_copy_equivalent(card: Any) -> int:
        """
        Represent a visible Golden card as evidence of three base copies.

        This remains evidence only. Generated cards and later sales mean this
        number must never be converted directly into an exact remaining-pool
        count.
        """
        if not isinstance(card, dict):
            return 0

        is_golden = bool(
            card.get("isGolden")
            or card.get("golden")
            or card.get("is_golden")
        )
        return 3 if is_golden else 1

    @staticmethod
    def _build_pending_choice(
        game: Any,
        player_id: int,
    ) -> ChoiceView | None:
        effects = getattr(game, "effects", None)
        if effects is None:
            return None

        getter = getattr(effects, "get_pending_choice", None)
        if not callable(getter):
            return None

        pending = getter(player_id)
        if pending is None:
            return None

        options = tuple(
            deepcopy(option)
            for option in getattr(pending, "options", ())
        )

        source = _copy_card(
            getattr(pending, "source_card", None)
        )

        source_card_id = getattr(
            pending,
            "source_card_id",
            None,
        )

        return ChoiceView(
            options=options,
            resolver_key=getattr(
                pending,
                "resolver_key",
                None,
            ),
            kind=str(
                getattr(
                    pending,
                    "kind",
                    "choice",
                )
            ),
            source_card_id=(
                int(source_card_id)
                if isinstance(source_card_id, int)
                else None
            ),
            metadata=deepcopy(
                getattr(
                    pending,
                    "metadata",
                    {},
                )
            ),
            source_card=source,
        )
