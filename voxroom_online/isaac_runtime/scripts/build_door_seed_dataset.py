from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from voxroom_online.isaac_runtime.config import get_nested, load_config
from voxroom_online.isaac_runtime.door_seed_learning.config import DoorSeedLearningConfig
from voxroom_online.isaac_runtime.door_seed_learning.dedup import build_dataset_indexes
from voxroom_online.isaac_runtime.door_seed_learning.label_resolver import resolve_scene_labels
from voxroom_online.isaac_runtime.door_seed_learning.schema import read_json
from voxroom_online.isaac_runtime.door_seed_learning.scene_split import validate_paper_scene_split


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve labels and build deduplicated DoorSeed dataset indexes.")
    parser.add_argument("--collection-root", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--config", default="configs/voxroom_online.yaml")
    parser.add_argument("--split-file", required=True, help="Validated scene split JSON from create_door_seed_scene_split --manifest.")
    parser.add_argument("--allow-draft", action="store_true")
    parser.add_argument("--skip-resolve", action="store_true")
    args = parser.parse_args(argv)
    splits = _load_splits(args.split_file)
    cfg = load_config(args.config)
    learning_cfg = DoorSeedLearningConfig.from_mapping(get_nested(cfg, "mapping.room_segmentation.door_seed_learning", {}))
    root = Path(args.collection_root).expanduser()
    if not args.skip_resolve:
        for manifest_path in sorted(root.glob("*/manifest.json")):
            resolve_scene_labels(manifest_path.parent, require_approved=not bool(args.allow_draft))
    report = build_dataset_indexes(root, args.out_dir, config=learning_cfg, split_assignments=splits)
    print(report)
    return 0


def _load_splits(path: str) -> dict[str, str]:
    raw = read_json(path)
    validate_paper_scene_split(raw)
    return {str(scene): str(split) for scene, split in dict(raw["assignments"]).items()}



if __name__ == "__main__":
    raise SystemExit(main())
