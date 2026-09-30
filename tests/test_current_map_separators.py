"""Separators follow the current accumulated map on every update."""

import numpy as np
import yaml

from voxroom_online.isaac_runtime.config import load_config, load_yaml
from voxroom_online.isaac_runtime.mapping.coordinate_transform import MapInfo
from voxroom_online.isaac_runtime.mapping import voxel_occupancy_door_wall_roomseg as roomseg
from voxroom_online.isaac_runtime.mapping.online_roomseg.separator_candidates import SeparatorCandidate
from voxroom_online.isaac_runtime.scripts.replay_voxel_roomseg_snapshots import (
    _voxel_grid_from_snapshot,
    main as replay_snapshots,
)
from voxroom_online.review_replay import synthetic_snapshot


def _setup():
    config = dict(load_config("configs/voxroom_online.yaml").mapping.room_segmentation)
    config["door_seed_learning"] = {"mode": "disabled"}
    map_info = MapInfo(0.05, 0.0, 4.0, 0.0, 3.2, 80, 64)
    return config, map_info


def _update(segmenter, snapshot, map_info, step):
    grid = _voxel_grid_from_snapshot(snapshot, map_info, {})
    segmenter.update(
        occupancy_map=snapshot["occupancy_map"],
        observed_free_mask=snapshot["observed_free_mask"],
        obstacle_mask=snapshot["obstacle_mask"],
        unknown_mask=snapshot["unknown_mask"],
        voxel_grid=grid,
        step=step,
    )
    return segmenter.last_result


def _without_lintel():
    snapshot = synthetic_snapshot()
    snapshot["voxel_occupancy_state_zyx"][:, 26:38, 39:41] = 1
    return snapshot


def _room_count(result):
    labels = result.layers["voxel_vertical_free_partition_room_label_map"]
    return np.unique(labels[labels > 0]).size


def test_door_is_recomputed_when_voxel_evidence_changes():
    config, map_info = _setup()
    segmenter = roomseg.VoxelOccupancyDoorWallRoomSegmenter(config, map_info)
    first = _update(segmenter, synthetic_snapshot(), map_info, step=0)
    assert first.door_cut_map.any()
    assert _room_count(first) == 2

    unchanged = _update(segmenter, synthetic_snapshot(), map_info, step=1)
    np.testing.assert_array_equal(unchanged.door_cut_map, first.door_cut_map)

    opened = _update(segmenter, _without_lintel(), map_info, step=2)
    assert not opened.door_cut_map.any()
    assert _room_count(opened) == 1

    fresh = roomseg.VoxelOccupancyDoorWallRoomSegmenter(config, map_info)
    fresh_result = _update(fresh, _without_lintel(), map_info, step=2)
    np.testing.assert_array_equal(opened.separator_map, fresh_result.separator_map)
    np.testing.assert_array_equal(opened.room_label_map, fresh_result.room_label_map)


def test_corridor_cut_expires_when_current_candidates_are_empty(monkeypatch):
    config, map_info = _setup()
    config["voxel_step2"] = {**config["voxel_step2"], "enabled": True}
    segmenter = roomseg.VoxelOccupancyDoorWallRoomSegmenter(config, map_info)
    candidate = SeparatorCandidate(
        candidate_id=1,
        kind="line_extension_corridor_separator",
        p0_rc=np.array([25, 40]),
        p1_rc=np.array([38, 40]),
        theta=np.pi / 2,
        length_m=0.65,
        confidence=1.0,
        source_segment_ids=[],
        accepted=True,
    )
    current_candidates = [candidate]

    def selected_candidates(_candidates, *, shape, **_kwargs):
        mask = np.zeros(shape, dtype=bool)
        for item in current_candidates:
            mask |= item.mask(shape)
        return list(current_candidates), [], mask, {}

    # Control the candidates at the topology stage; use the real partitioner.
    monkeypatch.setattr(roomseg, "_filter_step2_candidates_small_known_side", selected_candidates)
    first = _update(segmenter, _without_lintel(), map_info, step=0)
    assert first.step2_extension_separator_map.any()
    assert _room_count(first) == 2

    current_candidates.clear()
    second = _update(segmenter, _without_lintel(), map_info, step=1)
    assert not second.step2_extension_separator_map.any()
    assert _room_count(second) == 1


def test_snapshot_replay_passes_and_preserves_agent_pose(tmp_path, monkeypatch):
    snapshot = synthetic_snapshot()
    snapshot["agent_yaw_deg"] = np.array(137.0)
    path = tmp_path / "roomseg_step_000000.npz"
    np.savez_compressed(path, **snapshot)
    config = load_yaml("configs/voxroom_online.yaml")
    config["mapping"]["room_segmentation"]["door_seed_learning"]["mode"] = "disabled"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config))
    update = roomseg.VoxelOccupancyDoorWallRoomSegmenter.update
    received = {}

    def update_with_pose(self, *args, **kwargs):
        received["agent_rc"] = kwargs["agent_rc"]
        received["agent_yaw_deg"] = kwargs["agent_yaw_deg"]
        return update(self, *args, **kwargs)

    monkeypatch.setattr(roomseg.VoxelOccupancyDoorWallRoomSegmenter, "update", update_with_pose)
    output = tmp_path / "replayed"
    assert replay_snapshots([
        "--snapshot", str(path), "--config", str(config_path), "--out-dir", str(output),
        "--no-save-overlay", "--no-save-debug-mask",
    ]) == 0
    np.testing.assert_array_equal(received["agent_rc"], snapshot["agent_rc"])
    assert received["agent_yaw_deg"] == 137.0
    with np.load(output / path.name, allow_pickle=False) as replayed:
        assert replayed["agent_yaw_deg"].item() == 137.0
        assert np.unique(replayed["voxel_final_room_label_map"]).tolist() == [0, 1, 2]
