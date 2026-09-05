"""Generate imitation and hero-outcome samples from the generic seed teacher.

The teacher uses only real Bob states and legal actions. Recruit samples train
only Brain B's policy prior. Hero choices are deliberately RANDOM during data
generation so completed-game outcomes can train an unbiased first-pass hero
preference model without a hand-authored hero tier list.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import random
from typing import Sequence

from agents.observation import AgentMemory, AgentObservation, ObservationBuilder
from game.actions import Action
from game.bob import Bob
from training.teacher_policy import BasicTeacherPolicy


TEACHER_DATA_VERSION = 2


@dataclass(frozen=True)
class TeacherSample:
    observation: AgentObservation
    legal_actions: tuple[Action, ...]
    policy_target: tuple[float, ...]

    game_id: str = ""
    game_seed: int = 0
    player_id: int = -1
    round_number: int = 0
    decision_type: str = "recruit"
    chosen_action: Action | None = None


@dataclass(frozen=True)
class HeroTeacherSample:
    """One randomly explored hero choice plus its eventual placement value."""

    game_id: str
    game_seed: int
    player_id: int
    offered_hero_ids: tuple[int, ...]
    chosen_hero_id: int
    final_placement: int
    final_value: float


@dataclass(frozen=True)
class TeacherDataset:
    recruit_samples: tuple[TeacherSample, ...]
    hero_samples: tuple[HeroTeacherSample, ...]
    game_seeds: tuple[int, ...]

    def __len__(self) -> int:
        return len(self.recruit_samples)


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


@dataclass(frozen=True)
class _HeroChoiceRecord:
    player_id: int
    offered_hero_ids: tuple[int, ...]
    chosen_hero_id: int


@dataclass(frozen=True)
class _GeneratedGame:
    recruit_samples: tuple[TeacherSample, ...]
    hero_samples: tuple[HeroTeacherSample, ...]


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
        """Backward-compatible API returning recruit-policy samples only."""
        return list(self.generate_dataset(games).recruit_samples)

    def generate_dataset(self, games: int) -> TeacherDataset:
        if games <= 0:
            raise ValueError("games must be positive.")

        recruit_samples: list[TeacherSample] = []
        hero_samples: list[HeroTeacherSample] = []
        game_seeds: list[int] = []

        for game_index in range(int(games)):
            game_seed = self._derive_game_seed(game_index)
            generated = self._generate_one_game(
                game_seed=game_seed,
                game_index=game_index,
            )
            game_seeds.append(game_seed)
            recruit_samples.extend(generated.recruit_samples)
            hero_samples.extend(generated.hero_samples)

            print(
                f"Teacher game {game_index + 1}/{games} | "
                f"recruit samples: {len(generated.recruit_samples)} | "
                f"hero samples: {len(generated.hero_samples)} | "
                f"total recruit: {len(recruit_samples)}",
                flush=True,
            )

        return TeacherDataset(
            recruit_samples=tuple(recruit_samples),
            hero_samples=tuple(hero_samples),
            game_seeds=tuple(game_seeds),
        )

    def _generate_one_game(
        self,
        *,
        game_seed: int,
        game_index: int,
    ) -> _GeneratedGame:
        rng = random.Random(game_seed)
        game_id = f"teacher-{int(game_index):05d}-seed-{int(game_seed)}"

        with self._global_random_scope(game_seed):
            game = Bob(cards_file=self.config.cards_file)
            game.initialize_game()
            self._seed_game_components(game, rng)

            builders = {
                player_id: ObservationBuilder(AgentMemory(player_id))
                for player_id in range(self.PLAYER_COUNT)
            }

            hero_records = self._choose_heroes_randomly(game, rng)

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
                        raise RuntimeError(
                            "Teacher game exceeded round safety limit."
                        )

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
                    if player.eliminated:
                        continue

                    legal = tuple(game.get_player_action_space(player_id))
                    if not legal:
                        continue

                    # A final-AP action may create a mandatory zero-AP choice
                    # while Player.waiting is already true. Do not strand it.
                    if player.waiting and not any(
                        getattr(action.action_type, "value", "") == "choose_option"
                        for action in legal
                    ):
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
                            game_id=game_id,
                            game_seed=int(game_seed),
                            player_id=int(player_id),
                            round_number=int(current_round),
                            decision_type="recruit",
                            chosen_action=decision.action,
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

            hero_samples = self._finalize_hero_samples(
                game=game,
                records=hero_records,
                game_id=game_id,
                game_seed=game_seed,
            )

            return _GeneratedGame(
                recruit_samples=tuple(samples),
                hero_samples=tuple(hero_samples),
            )

    @staticmethod
    def _choose_heroes_randomly(
        game: Bob,
        rng: random.Random,
    ) -> tuple[_HeroChoiceRecord, ...]:
        """
        Choose heroes uniformly from each legal offer.

        Random assignment is deliberate: it supplies exploratory outcome data
        without injecting a hand-written hero tier list into Brain B.
        """
        records: list[_HeroChoiceRecord] = []
        for player_id in tuple(game.priority_order):
            choices = tuple(
                int(hero_id)
                for hero_id in game.get_player(player_id).hero_choices
            )
            if not choices:
                raise RuntimeError("Hero selection offered no choices.")
            chosen = int(rng.choice(choices))
            records.append(
                _HeroChoiceRecord(
                    player_id=int(player_id),
                    offered_hero_ids=choices,
                    chosen_hero_id=chosen,
                )
            )
            game.choose_hero(player_id, chosen)
        return tuple(records)

    @staticmethod
    def _finalize_hero_samples(
        *,
        game: Bob,
        records: Sequence[_HeroChoiceRecord],
        game_id: str,
        game_seed: int,
    ) -> tuple[HeroTeacherSample, ...]:
        result: list[HeroTeacherSample] = []
        for record in records:
            player = game.get_player(record.player_id)
            placement = getattr(player, "placement", None)
            if placement is None:
                raise RuntimeError(
                    "Teacher game ended without final placement for "
                    f"player {record.player_id}."
                )
            placement = int(placement)
            value = TeacherDataGenerator.placement_value(placement)
            result.append(
                HeroTeacherSample(
                    game_id=game_id,
                    game_seed=int(game_seed),
                    player_id=record.player_id,
                    offered_hero_ids=record.offered_hero_ids,
                    chosen_hero_id=record.chosen_hero_id,
                    final_placement=placement,
                    final_value=value,
                )
            )
        return tuple(result)

    @staticmethod
    def placement_value(placement: int) -> float:
        """Same linear 1st=+1, 8th=-1 placement scale used by self-play."""
        placement = int(placement)
        if not 1 <= placement <= 8:
            raise ValueError("placement must be between 1 and 8.")
        return 1.0 - 2.0 * float(placement - 1) / 7.0

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
