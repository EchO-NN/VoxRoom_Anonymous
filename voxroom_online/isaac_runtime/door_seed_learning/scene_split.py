from __future__ import annotations

import json
import math
import os
import random
from pathlib import Path
from typing import Iterable, Mapping


SCENE_SPLIT_SCHEMA_VERSION = "door_seed_scene_split_v1"


def build_scene_split(
    scene_ids: Iterable[str],
    *,
    seed: int,
    development_fraction: float = 0.5,
    development_val_fraction: float = 0.2,
) -> dict[str, object]:
    scenes = sorted({str(scene_id).strip() for scene_id in scene_ids if str(scene_id).strip()})
    if len(scenes) < 4:
        raise ValueError("at least four physical scenes are required for train/val/test splitting")
    if not 0.0 < float(development_fraction) < 1.0:
        raise ValueError("development_fraction must be in (0, 1)")
    if not 0.0 < float(development_val_fraction) < 1.0:
        raise ValueError("development_val_fraction must be in (0, 1)")

    shuffled = list(scenes)
    random.Random(int(seed)).shuffle(shuffled)
    development_count = int(math.ceil(len(shuffled) * float(development_fraction)))
    development_count = min(max(2, development_count), len(shuffled) - 1)
    development_order = shuffled[:development_count]
    heldout_order = shuffled[development_count:]

    val_count = int(round(development_count * float(development_val_fraction)))
    val_count = min(max(1, val_count), development_count - 1)
    train_order = development_order[:-val_count]
    val_order = development_order[-val_count:]

    train = sorted(train_order)
    val = sorted(val_order)
    test = sorted(heldout_order)
    development = sorted(development_order)
    assignments = {
        **{scene: "train" for scene in train},
        **{scene: "val" for scene in val},
        **{scene: "test" for scene in test},
    }
    payload: dict[str, object] = {
        "schema_version": SCENE_SPLIT_SCHEMA_VERSION,
        "strategy": "seeded_scene_shuffle_ceil_half",
        "seed": int(seed),
        "scene_count": len(scenes),
        "development_fraction": float(development_fraction),
        "development_val_fraction": float(development_val_fraction),
        "counts": {
            "development_collection": len(development),
            "heldout_validation": len(test),
            "train": len(train),
            "val": len(val),
            "test": len(test),
        },
        "roles": {
            "development_collection": development,
            "heldout_validation": test,
        },
        # Top-level lists are directly accepted by build_door_seed_dataset.py.
        "train": train,
        "val": val,
        "test": test,
        "assignments": dict(sorted(assignments.items())),
    }
    validate_scene_split(payload, expected_scene_ids=scenes)
    return payload


def validate_scene_split(
    payload: Mapping[str, object],
    *,
    expected_scene_ids: Iterable[str] | None = None,
) -> None:
    if str(payload.get("schema_version", "")) != SCENE_SPLIT_SCHEMA_VERSION:
        raise ValueError("unsupported door seed scene split schema")
    for name in ("train", "val", "test"):
        values = payload.get(name, [])
        if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f"{name} must be a list of nonempty scene IDs")
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate scene IDs in {name}")
    split_sets = {
        name: set(payload[name]) for name in ("train", "val", "test")
    }
    if any(not values for values in split_sets.values()):
        raise ValueError("train, val, and test scene lists must all be non-empty")
    if split_sets["train"] & split_sets["val"]:
        raise ValueError("train and val scenes overlap")
    if split_sets["train"] & split_sets["test"]:
        raise ValueError("train and test scenes overlap")
    if split_sets["val"] & split_sets["test"]:
        raise ValueError("val and test scenes overlap")

    all_scenes = set().union(*split_sets.values())
    roles = payload.get("roles", {})
    if not isinstance(roles, Mapping):
        raise ValueError("roles must be an object")
    development = {str(value) for value in roles.get("development_collection", [])}
    heldout = {str(value) for value in roles.get("heldout_validation", [])}
    if development != split_sets["train"] | split_sets["val"]:
        raise ValueError("development_collection must equal train union val")
    if heldout != split_sets["test"]:
        raise ValueError("heldout_validation must equal test")
    if development & heldout:
        raise ValueError("development and heldout scenes overlap")

    assignments = payload.get("assignments", {})
    if not isinstance(assignments, Mapping):
        raise ValueError("assignments must be an object")
    expected_assignments = {
        scene: split for split, scenes in split_sets.items() for scene in scenes
    }
    normalized_assignments = {str(scene): str(split) for scene, split in assignments.items()}
    if normalized_assignments != expected_assignments:
        raise ValueError("assignments do not match train/val/test lists")
    if expected_scene_ids is not None:
        expected = {str(value) for value in expected_scene_ids}
        if all_scenes != expected:
            missing = sorted(expected - all_scenes)
            extra = sorted(all_scenes - expected)
            raise ValueError("scene split coverage mismatch: missing=%s extra=%s" % (missing, extra))


def write_scene_split(path: str | Path, payload: Mapping[str, object]) -> None:
    validate_scene_split(payload)
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(dict(payload), handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)


PAPER_SPLIT_COUNTS = {
    "interioragent": {"train": 8, "val": 2, "test": 15},
    "grscene": {"train": 8, "val": 2, "test": 59},
}


def build_paper_scene_split(rows: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """Validate explicit physical-scene assignments without selecting scenes."""
    datasets: dict[str, str] = {}
    assignments: dict[str, str] = {}
    for row_number, row in enumerate(rows, start=2):
        scene = str(row.get("scene_id", "")).strip()
        dataset = str(row.get("dataset", "")).strip().lower()
        split = str(row.get("split", "")).strip().lower()
        if not scene or scene in {".", ".."} or any(c in scene for c in ("/", "\\", "\n", "\r")):
            raise ValueError(f"row {row_number}: scene_id must be a nonempty scene identifier, not a path")
        if dataset not in PAPER_SPLIT_COUNTS:
            raise ValueError(f"row {row_number}: dataset must be interioragent or grscene")
        if split not in {"train", "val", "test"}:
            raise ValueError(f"row {row_number}: split must be train, val, or test")
        if scene in assignments:
            raise ValueError(f"duplicate scene_id {scene!r}: scenes must be unique and splits disjoint")
        datasets[scene] = dataset
        assignments[scene] = split
    partitions = {
        split: sorted(scene for scene, assigned in assignments.items() if assigned == split)
        for split in ("train", "val", "test")
    }
    development = sorted(partitions["train"] + partitions["val"])
    payload: dict[str, object] = {
        "schema_version": SCENE_SPLIT_SCHEMA_VERSION,
        "strategy": "explicit_paper_manifest",
        "scene_count": len(assignments),
        "counts": {
            "train": len(partitions["train"]), "val": len(partitions["val"]),
            "test": len(partitions["test"]),
            "development_collection": len(development),
            "heldout_validation": len(partitions["test"]),
        },
        "roles": {"development_collection": development, "heldout_validation": partitions["test"]},
        **partitions,
        "assignments": dict(sorted(assignments.items())),
        "scene_datasets": dict(sorted(datasets.items())),
        "counts_by_dataset": {
            dataset: {
                split: sum(datasets[scene] == dataset for scene in partitions[split])
                for split in ("train", "val", "test")
            }
            for dataset in PAPER_SPLIT_COUNTS
        },
    }
    validate_paper_scene_split(payload)
    return payload


def read_paper_scene_manifest(path: str | Path) -> dict[str, object]:
    import csv

    with Path(path).expanduser().open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or len(reader.fieldnames) != 3 or set(reader.fieldnames) != {"scene_id", "dataset", "split"}:
            raise ValueError("scene manifest CSV must have exactly scene_id,dataset,split columns")
        rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ValueError("scene manifest CSV has a malformed row")
    return build_paper_scene_split(rows)


def validate_paper_scene_split(payload: Mapping[str, object]) -> None:
    validate_scene_split(payload)
    datasets = payload.get("scene_datasets")
    if not isinstance(datasets, Mapping):
        raise ValueError("scene split requires scene_datasets; create it from an explicit scene manifest")
    assignments = dict(payload["assignments"])
    if set(datasets) != set(assignments):
        raise ValueError("scene_datasets must describe exactly the assigned scene IDs")
    if any(value not in PAPER_SPLIT_COUNTS for value in datasets.values()):
        raise ValueError("scene_datasets must use interioragent or grscene")
    counts = {
        dataset: {
            split: sum(datasets[scene] == dataset and assigned == split for scene, assigned in assignments.items())
            for split in ("train", "val", "test")
        }
        for dataset in PAPER_SPLIT_COUNTS
    }
    if counts != PAPER_SPLIT_COUNTS:
        raise ValueError(f"paper scene counts must be {PAPER_SPLIT_COUNTS}; found {counts}")
    expected_counts = {
        "train": 16, "val": 4, "test": 74,
        "development_collection": 20, "heldout_validation": 74,
    }
    if payload.get("counts") != expected_counts or payload.get("scene_count") != 94:
        raise ValueError("scene split count metadata does not match its assignments")
    if payload.get("counts_by_dataset") != counts:
        raise ValueError("per-dataset count metadata does not match its assignments")
