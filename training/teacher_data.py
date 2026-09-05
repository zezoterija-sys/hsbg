"""Generate AI-safe imitation samples from the generic seed teacher."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import random
from typing import Sequence

from agents.observation import AgentMemory, AgentObservation, ObservationBuilder
from game.actions import Action
from game.bob import Bob
from training.teacher_policy import BasicTeacherPolicy


@dataclass(frozen=True)
class TeacherSample:
    observation: AgentObservation
    legal_actions: tuple[Action, ...]
    policy_target: tuple[float, ...]


@dataclass(frozen=True)
class TeacherDataConfig:
    cards_file: str = "data/raw/cards.json"
    seed: int = 0
    max_action_batches_per_round: int = 96
    max_rounds_per_game: int = 60

    def __post_init__(self) -> None:
        if self.max_action_batches_per_round <= 0:
            raise ValueError("max_action_batches_per_round must be positive.")
        if self.max_rounds_per_game <= 0:
            raise ValueError("max_rounds_per_game must be positive.")


class TeacherDataGenerator:
    """Run full real Bob games with no MCTS and collect teacher labels."""

    PLAYER_COUNT = 8

    def __init__(
        self,
        *,
        config: TeacherDataConfig | None = None,
        policy: BasicTeacherPolicy | None = None,
    ) -> None:
        self.config = config or TeacherDataConfig()
        self.policy = policy or BasicTeacherPolicy()

    def generate_games(self, games: int) -> list[TeacherSample]:
        if games <= 0:
            raise ValueError("games must be positive.")

        samples: list[TeacherSample] = []
        for game_index in range(int(games)):
            game_seed = self._derive_game_seed(game_index)
            game_samples = self._generate_one_game(game_seed)
            samples.extend(game_samples)
            print(
                f"Teacher game {game_index + 1}/{games} | "
                f"samples: {len(game_samples)} | total: {len(samples)}",
                flush=True,
            )
        return samples

    def _generate_one_game(self, game_seed: int) -> list[TeacherSample]:
        rng = random.Random(game_seed)

        with self._global_random_scope(game_seed):
            game = Bob(cards_file=self.config.cards_file)
            game.initialize_game()
            self._seed_game_components(game, rng)

            builders = {
                player_id: ObservationBuilder(AgentMemory(player_id))
                for player_id in range(self.PLAYER_COUNT)
            }

            self._choose_heroes(game, rng)

            samples: list[TeacherSample] = []
            current_round = 0
            batches_this_round = 0
            actions_taken: dict[int, int] = {
                player_id: 0
                for player_id in range(self.PLAYER_COUNT)
            }
            action_type_counts: dict[int, dict[str, int]] = {
                player_id: {}
                for player_id in range(self.PLAYER_COUNT)
            }

            while not game.game_over:
                if game.phase != "recruit":
                    raise RuntimeError(
                        f"Teacher runner expected recruit phase, got {game.phase!r}."
                    )

                if int(game.round_number) != current_round:
                    current_round = int(game.round_number)
                    batches_this_round = 0
                    actions_taken = {
                        player_id: 0
                        for player_id in range(self.PLAYER_COUNT)
                    }
                    action_type_counts = {
                        player_id: {}
                        for player_id in range(self.PLAYER_COUNT)
                    }
                    if current_round > self.config.max_rounds_per_game:
                        raise RuntimeError("Teacher game exceeded round safety limit.")

                if batches_this_round >= self.config.max_action_batches_per_round:
                    raise RuntimeError(
                        "Teacher game exceeded action-batch safety limit; "
                        f"round={current_round}."
                    )

                game.update_all_action_spaces()
                submissions: list[tuple[int, Action]] = []

                order = list(game.priority_order)
                order.extend(
                    pid for pid in range(self.PLAYER_COUNT)
                    if pid not in order
                )

                for player_id in order:
                    player = game.get_player(player_id)
                    if player.eliminated or player.waiting:
                        continue

                    legal = tuple(game.get_player_action_space(player_id))
                    if not legal:
                        continue

                    observation = builders[player_id].build(game)
                    decision = self.policy.decide(
                        observation,
                        legal,
                        rng,
                        action_type_counts=action_type_counts[player_id],
                        actions_taken_this_turn=actions_taken[player_id],
                    )

                    action_name = getattr(
                        decision.action.action_type,
                        "value",
                        str(decision.action.action_type),
                    )
                    actions_taken[player_id] += 1
                    action_type_counts[player_id][action_name] = (
                        action_type_counts[player_id].get(action_name, 0) + 1
                    )

                    samples.append(
                        TeacherSample(
                            observation=observation,
                            legal_actions=legal,
                            policy_target=decision.policy_target,
                        )
                    )
                    submissions.append((player_id, decision.action))

                if not submissions:
                    raise RuntimeError(
                        "Teacher runner produced no submissions while recruit "
                        "phase was active."
                    )

                executor = getattr(game, "execute_colliding_actions", None)
                if callable(executor):
                    executor(submissions)
                else:
                    for player_id, action in submissions:
                        game.execute_action(player_id, action)
                        if game.game_over:
                            break

                batches_this_round += 1

            return samples

    @staticmethod
    def _choose_heroes(game: Bob, rng: random.Random) -> None:
        for player_id in tuple(game.priority_order):
            choices = tuple(game.get_player(player_id).hero_choices)
            if not choices:
                raise RuntimeError("Hero selection offered no choices.")
            game.choose_hero(player_id, rng.choice(choices))

    @staticmethod
    def _seed_game_components(game: Bob, rng: random.Random) -> None:
        effects_rng = getattr(getattr(game, "effects", None), "random", None)
        if hasattr(effects_rng, "seed"):
            effects_rng.seed(rng.getrandbits(64))

        combat_engine = getattr(getattr(game, "combat", None), "engine", None)
        combat_rng = getattr(combat_engine, "random", None)
        if hasattr(combat_rng, "seed"):
            combat_rng.seed(rng.getrandbits(64))

    @contextmanager
    def _global_random_scope(self, seed: int):
        previous = random.getstate()
        try:
            random.seed(int(seed))
            yield
        finally:
            random.setstate(previous)

    def _derive_game_seed(self, game_index: int) -> int:
        value = (
            int(self.config.seed)
            + 0x9E3779B97F4A7C15 * (int(game_index) + 1)
        ) & ((1 << 64) - 1)
        value ^= value >> 30
        value = (value * 0xBF58476D1CE4E5B9) & ((1 << 64) - 1)
        value ^= value >> 27
        value = (value * 0x94D049BB133111EB) & ((1 << 64) - 1)
        value ^= value >> 31
        return value
