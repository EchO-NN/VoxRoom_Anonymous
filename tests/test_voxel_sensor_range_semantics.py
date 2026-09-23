from __future__ import annotations

import numpy as np

from voxroom_online.isaac_runtime.mapping.coordinate_transform import MapInfo
from voxroom_online.isaac_runtime.mapping.voxel_occupancy_grid import VOXEL_OCCUPIED, VOXEL_UNKNOWN, VoxelOccupancyGrid3D
from voxroom_online.isaac_runtime.mapping.voxel_roomseg_evidence import (
    VoxelRoomsegEvidenceConfig,
    classify_voxel_columns_for_roomseg,
)
from voxroom_online.isaac_runtime.sensors.camera_geometry import CameraIntrinsics
from voxroom_online.isaac_runtime.sensors.depth_backproject import distance_to_camera_to_image_plane_depth
from voxroom_online.real_runtime.geometry import RigidTransform


def _one_cell_voxel_grid() -> VoxelOccupancyGrid3D:
    return VoxelOccupancyGrid3D.zeros(
        (1, 1),
        MapInfo(resolution_m=0.05, min_x=0.0, max_x=0.05, min_y=0.0, max_y=0.05, width=1, height=1),
        cfg={"z_min_m": 0.0, "z_max_m": 0.05, "z_resolution_m": 0.05},
    )


def test_effective_frustum_marks_sensor_range_without_occupancy_evidence() -> None:
    grid = _one_cell_voxel_grid()
    grid.config.sensor_range_mark_effective_frustum_enabled = True
    updates = grid.mark_sensor_effective_range_rays(
        camera_origin_world=np.array([0.025, 0.025, 0.025], dtype=np.float32),
        range_endpoints_world=np.array([[0.025, 0.025, 0.025]], dtype=np.float32),
        floor_z=0.0,
    )

    assert updates > 0
    assert int(grid.sensor_range_count[0, 0, 0]) > 0
    assert int(grid.state[0, 0, 0]) == int(VOXEL_UNKNOWN)
    assert int(grid.log_odds[0, 0, 0]) == 0


def test_projective_frustum_volume_marks_sensor_range_by_image_plane_depth() -> None:
    grid = VoxelOccupancyGrid3D.zeros(
        (3, 3),
        MapInfo(resolution_m=0.05, min_x=0.0, max_x=0.15, min_y=0.0, max_y=0.15, width=3, height=3),
        cfg={
            "z_min_m": 0.0,
            "z_max_m": 0.15,
            "z_resolution_m": 0.05,
            "sensor_range_projective_frustum_volume_enabled": True,
            "sensor_range_mark_effective_frustum_enabled": False,
        },
    )
    intr = CameraIntrinsics(width=5, height=5, fx=2.0, fy=2.0, cx=2.0, cy=2.0)

    debug = grid.mark_sensor_projective_frustum_volume(
        camera_pose_world=(-0.10, 0.075, 0.075, 0.0),
        intr=intr,
        floor_z=0.0,
        depth_min_m=0.01,
        depth_max_m=0.30,
    )

    assert int(debug["voxel_sensor_projective_frustum_updates"]) > 0
    assert debug["voxel_sensor_range_mark_mode"] == "projective_frustum_volume"
    assert debug["voxel_sensor_projective_frustum_enabled"] is True
    assert debug["voxel_sensor_depth_range_semantics"] == "image_plane_z"
    assert int(debug["voxel_sensor_projective_frustum_candidate_voxels"]) > 0
    assert int(debug["voxel_sensor_projective_frustum_inside_voxels"]) > 0
    assert int(debug["voxel_sensor_range_projective_candidate_voxels"]) == int(debug["voxel_sensor_projective_frustum_candidate_voxels"])
    assert int(debug["voxel_sensor_range_projective_inside_voxels"]) == int(debug["voxel_sensor_projective_frustum_inside_voxels"])
    assert int(debug["voxel_sensor_range_projective_updates"]) == int(debug["voxel_sensor_projective_frustum_updates"])
    assert grid.last_projective_frustum_xy is not None
    assert grid.last_projective_frustum_xy.shape == grid.shape
    assert int(debug["voxel_sensor_projective_frustum_xy_cells"]) == int(
        np.count_nonzero(grid.last_projective_frustum_xy)
    )
    assert int(np.count_nonzero(grid.last_projective_frustum_xy)) > 0
    assert int(np.count_nonzero(grid.sensor_range_count)) > 0
    assert int(np.count_nonzero(grid.state == VOXEL_UNKNOWN)) == int(grid.state.size)
    assert int(np.count_nonzero(grid.log_odds)) == 0


def test_projective_frustum_volume_respects_camera_pitch() -> None:
    map_info = MapInfo(
        resolution_m=0.1,
        min_x=-0.2,
        max_x=2.0,
        min_y=-1.0,
        max_y=1.0,
        width=22,
        height=20,
    )
    cfg = {
        "z_min_m": 0.0,
        "z_max_m": 2.0,
        "z_resolution_m": 0.1,
        "active_z_min_m": 0.0,
        "active_z_max_cap_m": 2.0,
        "sensor_range_projective_frustum_volume_enabled": True,
        "sensor_range_mark_effective_frustum_enabled": False,
    }
    level_grid = VoxelOccupancyGrid3D.zeros((20, 22), map_info, cfg=cfg)
    pitched_grid = VoxelOccupancyGrid3D.zeros((20, 22), map_info, cfg=cfg)
    intr = CameraIntrinsics(width=5, height=5, fx=20.0, fy=20.0, cx=2.0, cy=2.0)
    level = RigidTransform((0.0, 0.0, 1.0), (0.0, 0.0, 0.0)).matrix()
    pitched_down = RigidTransform((0.0, 0.0, 1.0), (0.0, 30.0, 0.0)).matrix()

    level_grid.mark_sensor_projective_frustum_volume(
        camera_pose_world=level,
        intr=intr,
        floor_z=0.0,
        depth_min_m=0.2,
        depth_max_m=1.5,
        active_z_only=False,
    )
    pitched_grid.mark_sensor_projective_frustum_volume(
        camera_pose_world=pitched_down,
        intr=intr,
        floor_z=0.0,
        depth_min_m=0.2,
        depth_max_m=1.5,
        active_z_only=False,
    )

    level_z = np.nonzero(level_grid.sensor_range_count)[0]
    pitched_z = np.nonzero(pitched_grid.sensor_range_count)[0]
    assert level_z.size > 0 and pitched_z.size > 0
    assert float(np.mean(pitched_z)) < float(np.mean(level_z)) - 2.0


def test_distance_to_camera_converts_to_image_plane_z_depth() -> None:
    intr = CameraIntrinsics(width=3, height=3, fx=1.0, fy=1.0, cx=1.0, cy=1.0)
    distance = np.full((3, 3), 5.0, dtype=np.float32)

    z_depth = distance_to_camera_to_image_plane_depth(distance, intr)

    assert np.isclose(float(z_depth[1, 1]), 5.0)
    assert float(z_depth[0, 0]) < 5.0
    expected_corner = 5.0 / np.sqrt(3.0)
    assert np.isclose(float(z_depth[0, 0]), expected_corner, atol=1.0e-5)


def test_in_range_unknown_requires_sensor_frustum_evidence() -> None:
    state = np.full((1, 1, 1), VOXEL_UNKNOWN, dtype=np.uint8)
    cfg = VoxelRoomsegEvidenceConfig(sensor_range_count_threshold_for_roomseg=1)
    nav_free = np.zeros((1, 1), dtype=bool)
    nav_obstacle = np.zeros((1, 1), dtype=bool)

    no_frustum = classify_voxel_columns_for_roomseg(
        state_active=state,
        cfg=cfg,
        navigation_free_mask=nav_free,
        navigation_obstacle_mask=nav_obstacle,
        sensor_range_active=np.zeros_like(state, dtype=np.uint8),
    )
    in_frustum = classify_voxel_columns_for_roomseg(
        state_active=state,
        cfg=cfg,
        navigation_free_mask=nav_free,
        navigation_obstacle_mask=nav_obstacle,
        sensor_range_active=np.ones_like(state, dtype=np.uint8),
    )

    assert int(no_frustum["in_range_unknown_count"][0, 0]) == 0
    assert int(no_frustum["outside_range_unknown_count"][0, 0]) == 1
    assert int(in_frustum["in_range_unknown_count"][0, 0]) == 1
    assert int(in_frustum["outside_range_unknown_count"][0, 0]) == 0
    assert int(no_frustum["effective_range_count"][0, 0]) == 0
    assert int(in_frustum["effective_range_count"][0, 0]) == 1
    assert bool(no_frustum["unknown"][0, 0])
    assert bool(in_frustum["unknown"][0, 0])


def test_any_unknown_promotes_generalized_wall_occupancy() -> None:
    cfg = VoxelRoomsegEvidenceConfig(
        sensor_range_count_threshold_for_roomseg=1,
        wall_min_actual_occupied_z_cells_for_xy_wall=8,
    )
    nav_free = np.zeros((1, 1), dtype=bool)
    nav_obstacle = np.zeros((1, 1), dtype=bool)

    for mark_unknown_in_sensor_range in (False, True):
        state = np.full((10, 1, 1), VOXEL_UNKNOWN, dtype=np.uint8)
        state[:8, 0, 0] = VOXEL_OCCUPIED
        sensor_range = np.zeros_like(state, dtype=np.uint8)
        if mark_unknown_in_sensor_range:
            sensor_range[8:, 0, 0] = 1

        result = classify_voxel_columns_for_roomseg(
            state_active=state,
            cfg=cfg,
            navigation_free_mask=nav_free,
            navigation_obstacle_mask=nav_obstacle,
            sensor_range_active=sensor_range,
        )

        assert int(result["occupied_count"][0, 0]) == 8
        assert int(result["unknown_count"][0, 0]) == 2
        assert int(result["generalized_occupied_count"][0, 0]) == 10
        assert bool(result["wall_generalized_raw"][0, 0])
        assert bool(result["wall"][0, 0])
        assert bool(result["wall_from_in_range_unknown"][0, 0])


def test_generalized_wall_requires_nine_actual_occupied_cells_by_default() -> None:
    cfg = VoxelRoomsegEvidenceConfig.from_mapping({"wall_min_occupied_z_cells_for_xy_wall": 3})

    assert cfg.wall_min_occupied_z_cells_for_xy_wall == 3
    assert cfg.wall_min_actual_occupied_z_cells_for_xy_wall == 9
