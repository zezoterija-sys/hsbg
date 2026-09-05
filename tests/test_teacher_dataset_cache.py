"""Cache/provenance tests for proper teacher datasets."""

from types import SimpleNamespace

import pytest

from training.teacher_cache import (
    load_teacher_dataset,
    save_teacher_dataset,
)
from training.teacher_data import (
    HeroTeacherSample,
    TeacherDataset,
    TeacherSample,
)
from training.teacher_validation import validate_disjoint_splits


class _ActionType:
    value = "end_turn"


class _Action:
    action_type = _ActionType()

    def __eq__(self, other):
        return isinstance(other, _Action)


def _dataset(seed: int, game_id: str) -> TeacherDataset:
    action = _Action()
    recruit = TeacherSample(
        observation=SimpleNamespace(),
        legal_actions=(action,),
        policy_target=(1.0,),
        game_id=game_id,
        game_seed=seed,
        player_id=0,
        round_number=1,
        chosen_action=action,
    )
    heroes = tuple(
        HeroTeacherSample(
            game_id=game_id,
            game_seed=seed,
            player_id=player_id,
            offered_hero_ids=(1, 2, 3, 4),
            chosen_hero_id=1,
            final_placement=player_id + 1,
            final_value=1.0 - 2.0 * player_id / 7.0,
        )
        for player_id in range(8)
    )
    return TeacherDataset(
        recruit_samples=(recruit,),
        hero_samples=heroes,
        game_seeds=(seed,),
    )


def test_cache_round_trip_and_metadata_guard(tmp_path):
    dataset = _dataset(11, "train-11")
    path = tmp_path / "dataset.pt"
    metadata = {"ruleset": "36.4.2", "cards_sha256": "abc"}
    save_teacher_dataset(path, dataset, metadata=metadata)

    loaded, loaded_metadata = load_teacher_dataset(
        path,
        expected_metadata=metadata,
    )
    assert loaded.game_seeds == (11,)
    assert loaded_metadata == metadata

    with pytest.raises(ValueError, match="metadata mismatch"):
        load_teacher_dataset(
            path,
            expected_metadata={"ruleset": "different"},
        )


def test_split_validation_is_by_whole_game():
    train = _dataset(11, "train-11")
    validation = _dataset(22, "val-22")
    validate_disjoint_splits(train, validation)

    with pytest.raises(ValueError, match="overlap"):
        validate_disjoint_splits(train, _dataset(11, "other-id"))
