"""Local cache and provenance helpers for proper teacher datasets."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, is_dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import torch

from training.teacher_data import (
    TEACHER_DATA_VERSION,
    TeacherDataset,
)


CACHE_VERSION = 1


def sha256_file(path: str | Path) -> str:
    source = Path(path)
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_revision(project_root: str | Path = ".") -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(project_root),
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def git_is_dirty(project_root: str | Path = ".") -> bool | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=Path(project_root),
            check=True,
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return None


def dataset_signature(dataset: TeacherDataset) -> str:
    """Stable metadata/content signature without serializing large observations."""
    digest = hashlib.sha256()
    digest.update(str(TEACHER_DATA_VERSION).encode())
    for seed in dataset.game_seeds:
        digest.update(f"g:{int(seed)};".encode())
    for sample in dataset.recruit_samples:
        chosen = getattr(sample, "chosen_action", None)
        action_name = getattr(
            getattr(chosen, "action_type", None),
            "value",
            str(getattr(chosen, "action_type", "")),
        )
        digest.update(
            (
                f"r:{sample.game_seed}:{sample.player_id}:"
                f"{sample.round_number}:{action_name}:"
                f"{len(sample.legal_actions)};"
            ).encode()
        )
    for sample in dataset.hero_samples:
        digest.update(
            (
                f"h:{sample.game_seed}:{sample.player_id}:"
                f"{','.join(map(str, sample.offered_hero_ids))}:"
                f"{sample.chosen_hero_id}:{sample.final_placement};"
            ).encode()
        )
    return digest.hexdigest()


def save_teacher_dataset(
    path: str | Path,
    dataset: TeacherDataset,
    *,
    metadata: dict[str, Any],
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cache_version": CACHE_VERSION,
        "teacher_data_version": TEACHER_DATA_VERSION,
        "dataset": dataset,
        "metadata": dict(metadata),
        "dataset_signature": dataset_signature(dataset),
    }
    torch.save(payload, destination)
    return destination


def load_teacher_dataset(
    path: str | Path,
    *,
    expected_metadata: dict[str, Any] | None = None,
) -> tuple[TeacherDataset, dict[str, Any]]:
    source = Path(path)
    payload = torch.load(source, map_location="cpu", weights_only=False)

    if int(payload.get("cache_version", -1)) != CACHE_VERSION:
        raise ValueError("Unsupported teacher cache version.")
    if int(payload.get("teacher_data_version", -1)) != TEACHER_DATA_VERSION:
        raise ValueError("Teacher data schema mismatch.")

    dataset = payload.get("dataset")
    if not isinstance(dataset, TeacherDataset):
        raise ValueError("Teacher cache does not contain a TeacherDataset.")

    actual_signature = dataset_signature(dataset)
    if actual_signature != payload.get("dataset_signature"):
        raise ValueError("Teacher cache signature mismatch/corruption.")

    metadata = dict(payload.get("metadata", {}))
    for key, expected in dict(expected_metadata or {}).items():
        actual = metadata.get(key)
        if actual != expected:
            raise ValueError(
                f"Teacher cache metadata mismatch for {key!r}: "
                f"expected {expected!r}, got {actual!r}."
            )

    return dataset, metadata


def _action_name(sample: Any) -> str:
    chosen = getattr(sample, "chosen_action", None)
    if chosen is not None:
        return getattr(
            getattr(chosen, "action_type", None),
            "value",
            str(getattr(chosen, "action_type", "unknown")),
        )

    target = tuple(float(v) for v in sample.policy_target)
    index = max(range(len(target)), key=target.__getitem__)
    action = sample.legal_actions[index]
    return getattr(
        getattr(action, "action_type", None),
        "value",
        str(getattr(action, "action_type", "unknown")),
    )


def summarize_teacher_dataset(dataset: TeacherDataset) -> dict[str, Any]:
    samples_per_game = Counter(
        str(sample.game_id) for sample in dataset.recruit_samples
    )
    samples_per_round = Counter(
        int(sample.round_number) for sample in dataset.recruit_samples
    )
    samples_per_player = Counter(
        int(sample.player_id) for sample in dataset.recruit_samples
    )
    samples_per_action = Counter(
        _action_name(sample) for sample in dataset.recruit_samples
    )
    legal_action_counts = Counter(
        len(sample.legal_actions) for sample in dataset.recruit_samples
    )
    selected_heroes = Counter(
        int(sample.chosen_hero_id) for sample in dataset.hero_samples
    )

    return {
        "teacher_data_version": TEACHER_DATA_VERSION,
        "games": len(dataset.game_seeds),
        "recruit_samples": len(dataset.recruit_samples),
        "hero_samples": len(dataset.hero_samples),
        "game_seeds": [int(seed) for seed in dataset.game_seeds],
        "dataset_signature": dataset_signature(dataset),
        "samples_per_game": dict(sorted(samples_per_game.items())),
        "samples_per_round": {
            str(key): value for key, value in sorted(samples_per_round.items())
        },
        "samples_per_player": {
            str(key): value for key, value in sorted(samples_per_player.items())
        },
        "samples_per_action_type": dict(sorted(samples_per_action.items())),
        "legal_action_count_distribution": {
            str(key): value for key, value in sorted(legal_action_counts.items())
        },
        "selected_hero_distribution": {
            str(key): value for key, value in sorted(selected_heroes.items())
        },
    }


def json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(json_safe(payload), handle, indent=2, sort_keys=True)
        handle.write("\n")
    return destination
