from __future__ import annotations

import numpy as np
import pytest
from types import SimpleNamespace

from voxroom_online.isaac_runtime.mapping.voxel_occupancy_door_wall_roomseg import (
    VoxelOccupancyDoorWallRoomSegConfig,
    _filter_small_room_labels,
    _project_room_labels_to_navigation_free,
)
from voxroom_online.isaac_runtime.scripts.run_one_episode import (
    _roomseg_debug_for_layer_dump,
)


def test_voxroom_keeps_exactly_half_square_meter_and_drops_smaller() -> None:
    labels = np.zeros((20, 30), dtype=np.int32)
    labels.reshape(-1)[:199] = 1
    labels.reshape(-1)[200:400] = 2

    filtered, debug = _filter_small_room_labels(
        labels,
        min_area_m2=0.5,
        resolution_m=0.05,
    )

    assert debug["min_area_m2"] == pytest.approx(0.5)
    assert debug["min_cells"] == 200
    assert debug["removed_label_count"] == 1
    assert int(np.count_nonzero(filtered)) == 200


def test_voxroom_projects_vertical_partition_labels_to_navigation_free() -> None:
    vertical_labels = np.zeros((5, 7), dtype=np.int32)
    vertical_labels[1:4, 1:6] = 1
    navigation_free = np.zeros_like(vertical_labels, dtype=bool)
    navigation_free[2:4, 2:5] = True

    projected, debug = _project_room_labels_to_navigation_free(
        vertical_labels,
        navigation_free_mask=navigation_free,
    )

    assert np.array_equal(projected > 0, navigation_free)
    assert debug["partition_source"] == "voxel_vertical_free_xy"
    assert debug["projection_target"] == "voxel_nav_free_xy"
    assert debug["labels_removed_by_navigation_projection_cells"] == 9


def test_voxroom_default_min_room_area_is_half_square_meter() -> None:
    assert VoxelOccupancyDoorWallRoomSegConfig().min_room_area_m2 == pytest.approx(0.5)


def test_voxel_snapshot_common_domains_use_real_voxel_layers() -> None:
    vertical = np.zeros((4, 6), dtype=bool)
    vertical[1:3, 1:5] = True
    navigation = np.zeros_like(vertical)
    navigation[2, 2:4] = True
    segmenter = SimpleNamespace(
        last_result=SimpleNamespace(
            layers={
                "voxel_vertical_free_xy": vertical,
                "voxel_nav_free_xy": navigation,
            },
            room_label_map=navigation.astype(np.int32),
        )
    )

    debug = _roomseg_debug_for_layer_dump({}, segmenter)

    assert np.array_equal(debug["vertical_free_room_domain"], vertical)
    assert np.array_equal(debug["navigation_free_room_domain"], navigation)
