"""Portable sequential replay of the paper pipeline, independent of the simulator."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from voxroom_online.isaac_runtime.config import load_config
from voxroom_online.isaac_runtime.mapping.coordinate_transform import MapInfo
from voxroom_online.isaac_runtime.mapping.voxel_occupancy_door_wall_roomseg import VoxelOccupancyDoorWallRoomSegmenter
from voxroom_online.isaac_runtime.scripts.replay_voxel_roomseg_snapshots import _voxel_grid_from_snapshot


def synthetic_snapshot() -> dict[str, np.ndarray]:
    """Two synthetic rooms and one lintel; this is a software fixture, not evaluation data."""
    state = np.zeros((60, 64, 80), dtype=np.uint8)
    state[:, 4:60, 4:76] = 1
    state[:, 4:60, (4, 75)] = 2
    state[:, (4, 59), 4:76] = 2
    state[:, 4:60, 39:41] = 2
    state[:40, 26:38, 39:41] = 1
    free = np.count_nonzero(state == 1, axis=0) >= 6
    wall = (np.count_nonzero(state == 2, axis=0) >= 54) & ~free
    return {
        "voxel_occupancy_state_zyx": state,
        "voxel_sensor_range_count_zyx": (state != 0).astype(np.uint8),
        "voxel_occupancy_z_min_m": np.array(0.0),
        "voxel_occupancy_z_max_m": np.array(3.0),
        "voxel_occupancy_z_resolution_m": np.array(0.05),
        "voxel_occupancy_active_z_min_m": np.array(0.0),
        "voxel_occupancy_active_z_max_m": np.array(3.0),
        "observed_free_mask": free,
        "obstacle_mask": wall,
        "unknown_mask": ~(free | wall),
        "occupancy_map": wall,
        "agent_rc": np.array([32, 20]),
        "agent_yaw_deg": np.array(0.0),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/voxroom_online.yaml")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--snapshot", type=Path)
    inputs.add_argument("--sequence", type=Path, help="Directory of zero-padded roomseg_step_*.npz from one fixed-grid trajectory")
    inputs.add_argument("--demo", action="store_true", help="Generate synthetic software fixture")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--rules-only", action="store_true", help="Diagnostic ablation: bypass learned verification; never a full-method result")
    parser.add_argument("--output", type=Path, default=Path("outputs/replay"))
    args = parser.parse_args(argv)
    config = load_config(args.config)
    room_config = dict(config.mapping.room_segmentation)
    learning = dict(room_config["door_seed_learning"])
    learning["device"] = args.device
    learning["keep_threshold"] = 0.5
    learning["fallback_to_rule_seed_on_error"] = False
    if args.rules_only:
        learning["mode"] = "disabled"
    else:
        checkpoint = args.checkpoint or Path(learning["checkpoint_path"])
        if not checkpoint.is_file():
            parser.error("learned verification requires a compatible trained checkpoint; supply --checkpoint. Use --demo --rules-only only for a software smoke test.")
        learning.update(mode="inference", checkpoint_path=str(checkpoint))
    room_config["door_seed_learning"] = learning
    paths = [None] if args.demo else ([args.snapshot] if args.snapshot else sorted(args.sequence.glob("roomseg_step_*.npz")))
    if not paths:
        parser.error("no roomseg_step_*.npz snapshots found")
    args.output.mkdir(parents=True, exist_ok=True)
    segmenter = None
    previous_shape = None
    summaries = []
    for step, path in enumerate(paths):
        if path is None:
            arrays = synthetic_snapshot()
        else:
            with np.load(path, allow_pickle=False) as archive:
                arrays = {k: archive[k] for k in archive.files}
        required = ("voxel_occupancy_state_zyx", "voxel_sensor_range_count_zyx", "observed_free_mask", "obstacle_mask", "unknown_mask", "agent_rc")
        missing = [k for k in required if k not in arrays]
        if missing:
            raise ValueError("snapshot missing required evidence: " + ", ".join(missing))
        free = np.asarray(arrays["observed_free_mask"], dtype=bool)
        if free.ndim != 2 or (previous_shape is not None and free.shape != previous_shape):
            raise ValueError("sequential replay requires a fixed two-dimensional map grid")
        previous_shape = free.shape
        height, width = free.shape
        map_info = MapInfo(0.05, 0.0, width * 0.05, 0.0, height * 0.05, width, height)
        grid = _voxel_grid_from_snapshot(arrays, map_info, room_config["voxel_grid"])
        if segmenter is None:
            segmenter = VoxelOccupancyDoorWallRoomSegmenter(room_config, map_info)
        segmenter.update(
            occupancy_map=np.asarray(arrays.get("occupancy_map", arrays["obstacle_mask"])),
            observed_free_mask=free,
            obstacle_mask=np.asarray(arrays["obstacle_mask"], dtype=bool),
            unknown_mask=np.asarray(arrays["unknown_mask"], dtype=bool),
            voxel_grid=grid, step=step,
            agent_rc=np.asarray(arrays["agent_rc"], dtype=np.int32).reshape(2),
            agent_yaw_deg=float(np.asarray(arrays.get("agent_yaw_deg", 0.0)).item()),
        )
        result = segmenter.last_result
        if result is None:
            raise RuntimeError("segmentation returned no result")
        # The online planner API returns the navigation projection. Evaluation
        # must use the structural partition before this projection clips it.
        labels = np.asarray(result.layers["voxel_vertical_free_partition_room_label_map"], dtype=np.int32)
        structural_free = np.asarray(result.layers["voxel_vertical_free_xy"], dtype=bool)
        output_arrays = dict(pred_labels=labels, sfm_free=structural_free, navigation_labels=result.room_label_map, separators=result.separator_map)
        if "gt_labels" in arrays:
            if arrays["gt_labels"].shape != labels.shape:
                raise ValueError("gt_labels must match the map grid")
            output_arrays["gt_labels"] = arrays["gt_labels"]
        np.savez_compressed(args.output / f"prediction_{step:06d}.npz", **output_arrays)
        summaries.append({"step": step, "room_count": int(np.unique(labels[labels > 0]).size), "structural_free_cells": int(structural_free.sum())})
    report = {"synthetic_fixture": bool(args.demo), "method": "rules_only_diagnostic" if args.rules_only else "voxroom", "keep_threshold": 0.5, "snapshots": summaries}
    (args.output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
