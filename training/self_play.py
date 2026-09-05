"""
Eight-player self-play runner.

Real lobby:
- exactly 8 independent players,
- exactly 4 pure-MCTS seats (Brain A),
- exactly 4 neural-MCTS seats (Brain B),
- no team reward or same-brain cooperation,
- one shared NeuralBrain model for B seats,
- separate AgentMemory, RNG, thinking budget, and MCTS tree per seat.

Recruit scheduling:
All currently-active players choose one action from the same pre-action state.
When Bob exposes execute_colliding_actions(), those submissions are resolved as
one simultaneous batch using Bob's priority order. This matches the simulator's
explicit collision semantics instead of letting one player finish its entire
turn before everyone else.

Training leakage rule:
Brain-B decisions from the current live game remain in a private
GameTrajectory. They are committed to shared replay only after the game ends.
Training between rounds is allowed, but train_steps() can therefore see only
completed PREVIOUS games.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import json
from pathlib import Path
import random
from typing import Any, Iterable, Sequence

from agents.base_agent import BaseAgent
from agents.mcts_agent import MCTSAgent
from agents.mcts_core import MCTSConfig
from agents.neural_brain import NeuralBrain
from agents.neural_mcts_agent import NeuralMCTSAgent
from agents.puct_core import PUCTConfig
from agents.observation import AgentMemory, ObservationBuilder
from agents.rollout_policy import RandomPolicyConfig
from agents.simulation_environment import (
    DeterminizedBattlegroundsEnvironment,
)
from agents.thinking_budget import ThinkingBudget
from game.actions import Action
from game.bob import Bob
from training.basic_rewards import (
    BasicRewardConfig,
    basic_decision_reward,
)
from training.replay_buffer import (
    GameTrajectory,
    PendingDecision,
)
from training.trainer import (
    NeuralMCTSTrainer,
    TrainingStepStats,
)


BRAIN_A = "A"
BRAIN_B = "B"


@dataclass(frozen=True)
class SelfPlayConfig:
    cards_file: str = "data/raw/cards.json"
    seed: int = 0

    # Randomizing seats avoids accidentally measuring fixed player_id/priority
    # effects as "brain strength". Still exactly four seats per brain.
    shuffle_brain_seats: bool = True

    # Production defaults preserve the locked project search budget.
    per_decision_simulations: int = 200
    phase_simulations: int = 5000

    # Brain-B self-play behavior. Evaluation games should set this False so
    # PUCT uses no root Dirichlet noise and temperature 0.
    brain_b_training_mode: bool = True

    # Search-shape knobs. Defaults preserve the original behavior. The CLI
    # throughput profile lowers these for faster *imagined* searches only;
    # real-lobby AP/rules are unchanged.
    mcts_max_tree_depth: int = 64
    mcts_max_rollout_steps: int = 256
    puct_max_tree_depth: int = 64
    rollout_end_turn_probability: float = 0.10
    rollout_force_end_after_actions: int = 30

    # Keep evaluation games from contaminating replay or changing model weights.
    collect_training_data: bool = True
    enable_training_updates: bool = True

    # Optional real-lobby action trace for one seat. MCTS imagined actions are
    # never written to this file.
    trace_player_id: int | None = None
    trace_file: str | None = None

    # 100 AP means >100 batches should almost never be required. Extra room
    # allows zero-AP END_TURN and unusual mechanics while still detecting loops.
    max_action_batches_per_round: int = 160

    # Safe during a live lobby because replay contains completed games only.
    training_steps_between_rounds: int = 1
    training_steps_after_game: int = 1

    # Intermediate shaping. Final placement remains the main value target.
    combat_win_reward: float = 0.05
    combat_loss_reward: float = -0.05
    combat_tie_reward: float = 0.0

    # Very small generic END_TURN shaping for Brain B only.
    # Final placement/combat remain the dominant learning signal.
    basic_reward: BasicRewardConfig = field(
        default_factory=BasicRewardConfig
    )

    def __post_init__(self) -> None:
        if self.per_decision_simulations <= 0:
            raise ValueError(
                "per_decision_simulations must be positive."
            )
        if self.phase_simulations <= 0:
            raise ValueError(
                "phase_simulations must be positive."
            )
        if self.phase_simulations < self.per_decision_simulations:
            raise ValueError(
                "phase_simulations cannot be smaller than "
                "per_decision_simulations."
            )
        if self.max_action_batches_per_round <= 0:
            raise ValueError(
                "max_action_batches_per_round must be positive."
            )
        if self.mcts_max_tree_depth <= 0 or self.puct_max_tree_depth <= 0:
            raise ValueError("Search tree depths must be positive.")
        if self.mcts_max_rollout_steps <= 0:
            raise ValueError("mcts_max_rollout_steps must be positive.")
        if not 0.0 <= self.rollout_end_turn_probability <= 1.0:
            raise ValueError("rollout_end_turn_probability must be in [0, 1].")
        if self.rollout_force_end_after_actions <= 0:
            raise ValueError("rollout_force_end_after_actions must be positive.")
        if self.training_steps_between_rounds < 0:
            raise ValueError(
                "training_steps_between_rounds cannot be negative."
            )
        if self.training_steps_after_game < 0:
            raise ValueError(
                "training_steps_after_game cannot be negative."
            )
        if self.trace_player_id is not None and not (
            0 <= int(self.trace_player_id) < 8
        ):
            raise ValueError(
                "trace_player_id must be in player IDs 0..7."
            )
        if self.trace_player_id is not None and not self.trace_file:
            raise ValueError(
                "trace_file is required when trace_player_id is set."
            )

        for value in (
            self.combat_win_reward,
            self.combat_loss_reward,
            self.combat_tie_reward,
        ):
            if not -1.0 <= float(value) <= 1.0:
                raise ValueError(
                    "Combat reward shaping values must be in [-1, 1]."
                )


@dataclass(frozen=True)
class SeatAssignment:
    brain_a_player_ids: tuple[int, ...]
    brain_b_player_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        a = set(self.brain_a_player_ids)
        b = set(self.brain_b_player_ids)

        if len(a) != 4 or len(b) != 4:
            raise ValueError(
                "Self-play requires exactly four seats per brain."
            )
        if a & b:
            raise ValueError(
                "A player seat cannot belong to both brains."
            )
        if a | b != set(range(8)):
            raise ValueError(
                "Seat assignment must cover player IDs 0..7 exactly."
            )

    def brain_for(self, player_id: int) -> str:
        if player_id in self.brain_a_player_ids:
            return BRAIN_A
        if player_id in self.brain_b_player_ids:
            return BRAIN_B
        raise KeyError(player_id)


@dataclass(frozen=True)
class GameResult:
    game_id: str
    seed: int
    winner_id: int | None
    rounds_played: int
    action_batches: int
    actions_executed: int

    seat_assignment: SeatAssignment
    placements: dict[int, int]
    final_values: dict[int, float]

    brain_b_samples_committed: int
    training_steps_run: int
    latest_training_loss: float | None


@dataclass(frozen=True)
class _DecisionDraft:
    game_id: str
    player_id: int
    round_number: int
    observation: Any
    legal_actions: tuple[Action, ...]
    policy_target: tuple[float, ...]
    chosen_action: Action


@dataclass(frozen=True)
class _TraceDraft:
    game_id: str
    game_seed: int
    round_number: int
    player_id: int
    agent_name: str
    brain: str
    observation: Any
    legal_action_count: int
    action: Action


class SelfPlayRunner:
    """Run real 4-vs-4-brain, eight-player free-for-all games."""

    PLAYER_COUNT = 8
    BRAIN_SIZE = 4

    def __init__(
        self,
        *,
        config: SelfPlayConfig | None = None,
        brain: NeuralBrain | None = None,
        trainer: NeuralMCTSTrainer | None = None,
    ) -> None:
        self.config = config or SelfPlayConfig()

        self.brain = (
            brain
            if brain is not None
            else NeuralBrain(
                cards_file=self.config.cards_file,
                replay_seed=self.config.seed,
            )
        )

        self.trainer = (
            trainer
            if trainer is not None
            else NeuralMCTSTrainer(
                self.brain
            )
        )

        if self.trainer.brain is not self.brain:
            raise ValueError(
                "trainer and SelfPlayRunner must reference the same NeuralBrain."
            )

        self.games_completed = 0
        self._trace_path = (
            Path(self.config.trace_file)
            if self.config.trace_file
            else None
        )
        if self._trace_path is not None:
            self._trace_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

    # ==================================================================
    # PUBLIC API
    # ==================================================================

    def run_game(
        self,
        *,
        game_index: int | None = None,
        seed: int | None = None,
    ) -> GameResult:
        index = (
            self.games_completed
            if game_index is None
            else int(game_index)
        )

        game_seed = (
            self._derive_game_seed(index)
            if seed is None
            else int(seed)
        )

        game_id = f"game-{index:08d}-seed-{game_seed}"
        rng = random.Random(game_seed)

        print(
            f"Game {index + 1} started | Seed: {game_seed}",
            flush=True,
        )

        with self._global_random_scope(game_seed):
            game = Bob(
                cards_file=self.config.cards_file
            )
            game.initialize_game()
            self._seed_real_game_components(
                game,
                rng,
            )

            seats = self._assign_seats(
                rng
            )

            (
                agents,
                memories,
                builders,
            ) = self._build_agents(
                seats,
                game_seed,
            )

            self._run_hero_selection(
                game,
                agents,
            )

            trajectory = GameTrajectory(
                game_id
            )

            training_stats: list[
                TrainingStepStats
            ] = []

            action_batches = 0
            actions_executed = 0

            current_round = 0
            round_drafts: list[
                _DecisionDraft
            ] = []

            while not game.game_over:
                if game.phase != "recruit":
                    raise RuntimeError(
                        "SelfPlayRunner expected Bob to return to recruit "
                        f"phase, got {game.phase!r}."
                    )

                if game.round_number != current_round:
                    # The previous round's combat has completed if current_round
                    # was nonzero. Train now only from completed historical
                    # replay; current trajectory is still private.
                    if (
                        current_round > 0
                        and self.config.enable_training_updates
                    ):
                        training_stats.extend(
                            self.trainer.train_steps(
                                self.config.training_steps_between_rounds
                            )
                        )

                    current_round = int(
                        game.round_number
                    )

                    alive_count = sum(
                        1
                        for player in game.players
                        if not player.eliminated
                    )

                    print(
                        f"Game {index + 1} | "
                        f"Round {current_round} | "
                        f"Alive: {alive_count} | "
                        f"Actions: {actions_executed}",
                        flush=True,
                    )

                    self._reset_agents_for_recruit(
                        agents,
                        game,
                    )

                batch_count_for_round = 0

                while (
                    not game.game_over
                    and game.phase == "recruit"
                    and game.round_number == current_round
                ):
                    if (
                        batch_count_for_round
                        >= self.config.max_action_batches_per_round
                    ):
                        raise RuntimeError(
                            self._stuck_round_message(
                                game,
                                current_round,
                                batch_count_for_round,
                            )
                        )

                    submissions, drafts, trace_drafts = (
                        self._collect_action_batch(
                            game=game,
                            agents=agents,
                            builders=builders,
                            seats=seats,
                            game_id=game_id,
                            game_seed=game_seed,
                        )
                    )

                    if not submissions:
                        raise RuntimeError(
                            self._stuck_round_message(
                                game,
                                current_round,
                                batch_count_for_round,
                                reason=(
                                    "No submissions were produced while "
                                    "recruit phase was still active."
                                ),
                            )
                        )

                    round_drafts.extend(
                        drafts
                    )

                    before_round = int(
                        game.round_number
                    )

                    self._execute_batch(
                        game,
                        submissions,
                    )
                    self._write_trace_drafts(
                        trace_drafts,
                        game,
                    )

                    action_batches += 1
                    batch_count_for_round += 1
                    actions_executed += len(
                        submissions
                    )

                    # Bob resolves combat synchronously when the last living
                    # player becomes waiting. If the game continues it
                    # immediately starts the next recruit round.
                    combat_completed = (
                        game.game_over
                        or int(game.round_number)
                        != before_round
                        or game.phase == "game_over"
                    )

                    if combat_completed:
                        self._flush_round_drafts(
                            trajectory=trajectory,
                            drafts=round_drafts,
                            game=game,
                        )
                        round_drafts = []
                        break

            # Defensive: a game-over combat should already have flushed.
            if round_drafts:
                self._flush_round_drafts(
                    trajectory=trajectory,
                    drafts=round_drafts,
                    game=game,
                )

            placements = self._placements(
                game
            )
            final_values = {
                player_id: self.placement_value(
                    placement
                )
                for player_id, placement
                in placements.items()
            }

            if self.config.collect_training_data:
                samples_committed = (
                    self.trainer.commit_completed_game(
                        trajectory,
                        {
                            player_id: final_values[player_id]
                            for player_id
                            in seats.brain_b_player_ids
                        },
                    )
                )
            else:
                samples_committed = 0

            if self.config.enable_training_updates:
                training_stats.extend(
                    self.trainer.train_steps(
                        self.config.training_steps_after_game
                    )
                )

            winner_id = next(
                (
                    player_id
                    for player_id, placement
                    in placements.items()
                    if placement == 1
                ),
                None,
            )

            result = GameResult(
                game_id=game_id,
                seed=game_seed,
                winner_id=winner_id,
                rounds_played=int(
                    game.round_number
                ),
                action_batches=action_batches,
                actions_executed=actions_executed,
                seat_assignment=seats,
                placements=placements,
                final_values=final_values,
                brain_b_samples_committed=samples_committed,
                training_steps_run=len(
                    training_stats
                ),
                latest_training_loss=(
                    training_stats[-1].total_loss
                    if training_stats
                    else None
                ),
            )

        print(
            f"Game {index + 1} complete | "
            f"Winner: P{result.winner_id} | "
            f"Rounds: {result.rounds_played} | "
            f"Actions: {result.actions_executed}",
            flush=True,
        )

        self.games_completed += 1
        return result

    # ==================================================================
    # AGENTS / SEATS
    # ==================================================================

    def _assign_seats(
        self,
        rng: random.Random,
    ) -> SeatAssignment:
        player_ids = list(
            range(self.PLAYER_COUNT)
        )

        if self.config.shuffle_brain_seats:
            rng.shuffle(
                player_ids
            )

        a_ids = tuple(
            sorted(
                player_ids[
                    : self.BRAIN_SIZE
                ]
            )
        )
        b_ids = tuple(
            sorted(
                player_ids[
                    self.BRAIN_SIZE :
                ]
            )
        )

        return SeatAssignment(
            brain_a_player_ids=a_ids,
            brain_b_player_ids=b_ids,
        )

    def _build_agents(
        self,
        seats: SeatAssignment,
        game_seed: int,
    ) -> tuple[
        dict[int, BaseAgent],
        dict[int, AgentMemory],
        dict[int, ObservationBuilder],
    ]:
        agents: dict[
            int,
            BaseAgent,
        ] = {}
        memories: dict[
            int,
            AgentMemory,
        ] = {}
        builders: dict[
            int,
            ObservationBuilder,
        ] = {}

        a_number = {
            player_id: index + 1
            for index, player_id
            in enumerate(
                seats.brain_a_player_ids
            )
        }
        b_number = {
            player_id: index + 1
            for index, player_id
            in enumerate(
                seats.brain_b_player_ids
            )
        }

        for player_id in range(
            self.PLAYER_COUNT
        ):
            memory = AgentMemory(
                player_id
            )
            memories[player_id] = memory
            builders[player_id] = (
                ObservationBuilder(
                    memory
                )
            )

            environment = (
                DeterminizedBattlegroundsEnvironment(
                    cards_file=self.config.cards_file,
                    random_policy_config=RandomPolicyConfig(
                        end_turn_probability=(
                            self.config.rollout_end_turn_probability
                        ),
                        force_end_after_actions=(
                            self.config.rollout_force_end_after_actions
                        ),
                    ),
                )
            )

            agent_seed = self._derive_agent_seed(
                game_seed,
                player_id,
            )

            thinking_budget = ThinkingBudget(
                per_decision_limit=(
                    self.config.per_decision_simulations
                ),
                phase_budget=(
                    self.config.phase_simulations
                ),
            )

            if player_id in seats.brain_a_player_ids:
                agents[player_id] = MCTSAgent(
                    player_id=player_id,
                    environment=environment,
                    name=(
                        f"A{a_number[player_id]}"
                    ),
                    seed=agent_seed,
                    thinking_budget=thinking_budget,
                    config=MCTSConfig(
                        max_tree_depth=self.config.mcts_max_tree_depth,
                        max_rollout_steps=self.config.mcts_max_rollout_steps,
                    ),
                )
            else:
                agents[player_id] = (
                    NeuralMCTSAgent(
                        player_id=player_id,
                        environment=environment,
                        brain=self.brain,
                        name=(
                            f"B{b_number[player_id]}"
                        ),
                        seed=agent_seed,
                        thinking_budget=thinking_budget,
                        config=PUCTConfig(
                            max_tree_depth=self.config.puct_max_tree_depth
                        ),
                        training_mode=(
                            self.config.brain_b_training_mode
                        ),
                    )
                )

        return (
            agents,
            memories,
            builders,
        )

    # ==================================================================
    # HERO SELECTION
    # ==================================================================

    @staticmethod
    def _run_hero_selection(
        game: Bob,
        agents: dict[int, BaseAgent],
    ) -> None:
        if game.phase != "hero_selection":
            raise RuntimeError(
                "Bob was expected to begin in hero_selection."
            )

        # Bob's last choose_hero call automatically starts recruit round 1.
        selection_order = tuple(
            game.priority_order
        )

        for player_id in selection_order:
            player = game.get_player(
                player_id
            )
            choices = tuple(
                player.hero_choices
            )

            selected = agents[
                player_id
            ].choose_hero(
                choices
            )

            game.choose_hero(
                player_id,
                selected,
            )

        if (
            not game.game_over
            and game.phase != "recruit"
        ):
            raise RuntimeError(
                "Hero selection completed without entering recruit phase."
            )

    # ==================================================================
    # RECRUIT DECISIONS
    # ==================================================================

    @staticmethod
    def _reset_agents_for_recruit(
        agents: dict[int, BaseAgent],
        game: Bob,
    ) -> None:
        for player in game.players:
            if player.eliminated:
                continue

            agents[
                player.player_id
            ].reset_recruit_phase()

    def _collect_action_batch(
        self,
        *,
        game: Bob,
        agents: dict[int, BaseAgent],
        builders: dict[int, ObservationBuilder],
        seats: SeatAssignment,
        game_id: str,
        game_seed: int,
    ) -> tuple[
        list[tuple[int, Action]],
        list[_DecisionDraft],
        list[_TraceDraft],
    ]:
        # Regenerate all action spaces once. Every agent in this batch then sees
        # the same pre-action real game state.
        game.update_all_action_spaces()

        submissions: list[
            tuple[int, Action]
        ] = []
        drafts: list[
            _DecisionDraft
        ] = []
        trace_drafts: list[
            _TraceDraft
        ] = []

        decision_order = [
            player_id
            for player_id in game.priority_order
            if (
                0 <= player_id
                < self.PLAYER_COUNT
            )
        ]

        # Defensive coverage if a future phase priority list omits a seat.
        decision_order.extend(
            player_id
            for player_id in range(
                self.PLAYER_COUNT
            )
            if player_id
            not in decision_order
        )

        for player_id in decision_order:
            player = game.get_player(
                player_id
            )

            if (
                player.eliminated
                or player.waiting
            ):
                continue

            legal_actions = tuple(
                game.get_player_action_space(
                    player_id
                )
            )

            if not legal_actions:
                continue

            observation = builders[
                player_id
            ].build(
                game
            )

            agent = agents[
                player_id
            ]

            action = agent.choose_action(
                observation,
                legal_actions,
            )

            if action not in legal_actions:
                raise RuntimeError(
                    f"{agent.name} returned illegal action {action}."
                )

            submissions.append(
                (
                    player_id,
                    action,
                )
            )

            if (
                self.config.trace_player_id is not None
                and player_id == int(self.config.trace_player_id)
            ):
                trace_drafts.append(
                    _TraceDraft(
                        game_id=game_id,
                        game_seed=game_seed,
                        round_number=int(game.round_number),
                        player_id=player_id,
                        agent_name=agent.name,
                        brain=seats.brain_for(player_id),
                        observation=observation,
                        legal_action_count=len(legal_actions),
                        action=action,
                    )
                )

            if player_id in seats.brain_b_player_ids:
                neural_agent = agent

                if not isinstance(
                    neural_agent,
                    NeuralMCTSAgent,
                ):
                    raise TypeError(
                        "Brain B seat does not contain NeuralMCTSAgent."
                    )

                policy_target = (
                    neural_agent
                    .get_last_policy_target(
                        legal_actions
                    )
                )

                # No search occurs for a forced one-action decision, and the
                # phase budget can eventually be exhausted. Preserve value
                # training data using the neural policy itself in those cases.
                if policy_target is None:
                    if len(legal_actions) == 1:
                        policy_target = (1.0,)
                    else:
                        policy_target = (
                            self.brain
                            .evaluate(
                                observation,
                                legal_actions,
                            )
                            .priors
                        )

                drafts.append(
                    _DecisionDraft(
                        game_id=game_id,
                        player_id=player_id,
                        round_number=int(
                            game.round_number
                        ),
                        observation=observation,
                        legal_actions=legal_actions,
                        policy_target=tuple(
                            float(value)
                            for value
                            in policy_target
                        ),
                        chosen_action=action,
                    )
                )

        return submissions, drafts, trace_drafts

    @staticmethod
    def _execute_batch(
        game: Bob,
        submissions: Sequence[
            tuple[int, Action]
        ],
    ) -> None:
        collision_executor = getattr(
            game,
            "execute_colliding_actions",
            None,
        )

        if (
            callable(
                collision_executor
            )
            and len(submissions) > 1
        ):
            collision_executor(
                list(submissions)
            )
            return

        # Compatibility fallback for older Bob versions.
        for player_id, action in submissions:
            game.execute_action(
                player_id,
                action,
            )

            if game.game_over:
                break

    # ==================================================================
    # OPTIONAL SINGLE-AGENT REAL-LOBBY TRACE
    # ==================================================================

    def _write_trace_drafts(
        self,
        drafts: Sequence[_TraceDraft],
        game: Bob,
    ) -> None:
        if self._trace_path is None or not drafts:
            return

        with self._trace_path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            for draft in drafts:
                player = game.get_player(draft.player_id)
                view = draft.observation.self_player
                record = {
                    "game_id": draft.game_id,
                    "seed": draft.game_seed,
                    "round": draft.round_number,
                    "player_id": draft.player_id,
                    "agent": draft.agent_name,
                    "brain": draft.brain,
                    "legal_action_count": draft.legal_action_count,
                    "chosen_action": self._action_record(draft.action),
                    "before": {
                        "health": int(view.health),
                        "armor": int(view.armor),
                        "gold": int(view.gold),
                        "max_gold": int(view.max_gold),
                        "ap": int(view.ap),
                        "tavern_tier": int(view.tavern_tier),
                        "waiting": bool(view.waiting),
                        "hero_id": view.hero_id,
                        "hero_power_id": self._trace_card_id(view.hero_power),
                        "board": self._trace_zone(view.board),
                        "hand": self._trace_zone(view.hand),
                        "tavern": self._trace_zone(view.tavern_slots),
                        "tavern_spell": self._trace_card(view.tavern_spell),
                    },
                    "after": {
                        "health": int(getattr(player, "health", 0)),
                        "armor": int(getattr(player, "armor", 0)),
                        "gold": int(getattr(player, "gold", 0)),
                        "max_gold": int(getattr(player, "max_gold", 10)),
                        "ap": int(getattr(player, "ap", 0)),
                        "tavern_tier": int(getattr(player, "tavern_tier", 1)),
                        "waiting": bool(getattr(player, "waiting", False)),
                        "board": self._trace_zone(getattr(player, "board", ())),
                        "hand": self._trace_zone(getattr(player, "hand", ())),
                        "tavern": self._trace_zone(
                            getattr(getattr(player, "tavern", None), "slots", ())
                        ),
                        "tavern_spell": self._trace_card(
                            getattr(getattr(player, "tavern", None), "spell", None)
                        ),
                    },
                }
                handle.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )

    @staticmethod
    def _action_record(action: Action) -> dict[str, Any]:
        return {
            "text": repr(action),
            "type": action.action_type.value,
            "target_idx": getattr(action, "target_idx", None),
            "position_idx": getattr(action, "position_idx", None),
            "option_idx": getattr(action, "option_idx", None),
            "effect_target_player_id": getattr(action, "effect_target_player_id", None),
            "effect_target_zone": getattr(action, "effect_target_zone", None),
            "effect_target_idx": getattr(action, "effect_target_idx", None),
            "ap_cost": int(action.ap_cost),
        }

    @staticmethod
    def _trace_card_id(card: Any) -> int | None:
        if not isinstance(card, dict):
            return None
        value = card.get("id")
        return value if isinstance(value, int) else None

    @classmethod
    def _trace_card(cls, card: Any) -> dict[str, Any] | None:
        if not isinstance(card, dict):
            return None
        return {
            "id": cls._trace_card_id(card),
            "name": card.get("name"),
            "attack": int(card.get("attack", 0) or 0),
            "health": int(card.get("health", 0) or 0),
            "tier": int(card.get("tier", 0) or 0),
            "golden": bool(
                card.get("isGolden")
                or card.get("golden")
                or card.get("is_golden")
            ),
        }

    @classmethod
    def _trace_zone(cls, cards: Iterable[Any]) -> list[dict[str, Any] | None]:
        return [cls._trace_card(card) for card in cards]

    # ==================================================================
    # TRAJECTORY / REWARDS
    # ==================================================================

    def _flush_round_drafts(
        self,
        *,
        trajectory: GameTrajectory,
        drafts: Iterable[
            _DecisionDraft
        ],
        game: Bob,
    ) -> None:
        rewards = {
            player.player_id: self._combat_reward(
                player
            )
            for player in game.players
        }

        for draft in drafts:
            combat_reward = rewards.get(
                draft.player_id,
                0.0,
            )

            basic_reward = basic_decision_reward(
                draft.observation,
                draft.chosen_action,
                self.config.basic_reward,
            )

            trajectory.add(
                PendingDecision(
                    game_id=draft.game_id,
                    player_id=draft.player_id,
                    round_number=draft.round_number,
                    observation=draft.observation,
                    legal_actions=draft.legal_actions,
                    policy_target=draft.policy_target,
                    shaped_reward=(
                        float(combat_reward)
                        + float(basic_reward)
                    ),
                )
            )

    def _combat_reward(
        self,
        player: Any,
    ) -> float:
        if bool(
            getattr(
                player,
                "last_combat_tied",
                False,
            )
        ):
            return float(
                self.config
                .combat_tie_reward
            )

        if bool(
            getattr(
                player,
                "last_combat_won",
                False,
            )
        ):
            return float(
                self.config
                .combat_win_reward
            )

        return float(
            self.config
            .combat_loss_reward
        )

    @staticmethod
    def placement_value(
        placement: int,
    ) -> float:
        """
        Individual final-placement value.

        1st -> +1
        8th -> -1
        linearly spaced between them.
        """
        placement = int(
            placement
        )

        if not 1 <= placement <= 8:
            raise ValueError(
                f"placement must be 1..8, got {placement}."
            )

        return 1.0 - (
            2.0
            * (placement - 1)
            / 7.0
        )

    @staticmethod
    def _placements(
        game: Bob,
    ) -> dict[int, int]:
        result: dict[
            int,
            int,
        ] = {}

        for player in game.players:
            placement = getattr(
                player,
                "placement",
                None,
            )

            if placement is None:
                raise RuntimeError(
                    f"Game ended without placement for "
                    f"player {player.player_id}."
                )

            result[
                player.player_id
            ] = int(
                placement
            )

        if sorted(
            result.values()
        ) != list(
            range(1, 9)
        ):
            raise RuntimeError(
                "Final placements are not exactly 1 through 8."
            )

        return result

    # ==================================================================
    # RNG
    # ==================================================================

    @staticmethod
    def _seed_real_game_components(
        game: Bob,
        rng: random.Random,
    ) -> None:
        effects_rng = getattr(
            getattr(
                game,
                "effects",
                None,
            ),
            "random",
            None,
        )

        if hasattr(
            effects_rng,
            "seed",
        ):
            effects_rng.seed(
                rng.getrandbits(64)
            )

        combat_engine = getattr(
            getattr(
                game,
                "combat",
                None,
            ),
            "engine",
            None,
        )
        combat_rng = getattr(
            combat_engine,
            "random",
            None,
        )

        if hasattr(
            combat_rng,
            "seed",
        ):
            combat_rng.seed(
                rng.getrandbits(64)
            )

    @contextmanager
    def _global_random_scope(
        self,
        seed: int,
    ):
        """
        Bob/CardPool currently use module-global random in several places.
        Preserve the caller's random state while making one self-play game
        deterministic from its game seed.
        """
        previous = random.getstate()

        try:
            random.seed(
                int(seed)
            )
            yield
        finally:
            random.setstate(
                previous
            )

    def _derive_game_seed(
        self,
        game_index: int,
    ) -> int:
        # SplitMix-style integer scrambling. No Python hash(), whose randomized
        # process seed would hurt reproducibility.
        value = (
            int(self.config.seed)
            + 0x9E3779B97F4A7C15
            * (int(game_index) + 1)
        ) & ((1 << 64) - 1)

        value ^= value >> 30
        value = (
            value
            * 0xBF58476D1CE4E5B9
        ) & ((1 << 64) - 1)
        value ^= value >> 27
        value = (
            value
            * 0x94D049BB133111EB
        ) & ((1 << 64) - 1)
        value ^= value >> 31

        return value

    @staticmethod
    def _derive_agent_seed(
        game_seed: int,
        player_id: int,
    ) -> int:
        return (
            int(game_seed)
            ^ (
                0xD1B54A32D192ED03
                * (int(player_id) + 1)
            )
        ) & ((1 << 64) - 1)

    # ==================================================================
    # DIAGNOSTICS
    # ==================================================================

    @staticmethod
    def _stuck_round_message(
        game: Bob,
        round_number: int,
        batch_count: int,
        *,
        reason: str | None = None,
    ) -> str:
        player_state = [
            {
                "id": player.player_id,
                "waiting": bool(
                    player.waiting
                ),
                "eliminated": bool(
                    player.eliminated
                ),
                "gold": int(
                    getattr(
                        player,
                        "gold",
                        0,
                    )
                ),
                "ap": int(
                    getattr(
                        player,
                        "ap",
                        0,
                    )
                ),
                "legal_actions": len(
                    game.get_player_action_space(
                        player.player_id
                    )
                ),
            }
            for player in game.players
        ]

        prefix = (
            reason
            or "Exceeded self-play action-batch safety limit."
        )

        return (
            f"{prefix} "
            f"round={round_number}, "
            f"batches={batch_count}, "
            f"phase={game.phase!r}, "
            f"players={player_state}"
        )

    def __repr__(self) -> str:
        return (
            f"SelfPlayRunner("
            f"games_completed={self.games_completed}, "
            f"replay_size={len(self.brain.replay_buffer)}"
            f")"
        )
