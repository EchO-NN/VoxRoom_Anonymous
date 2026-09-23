"""ROS-independent conversion from floor-referenced OctoMap exports."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np


class ObservationGate:
    """Consume increasing observation times at a maximum wall-clock rate."""
    def __init__(self, period_seconds=2.0):
        if not math.isfinite(period_seconds) or period_seconds <= 0:
            raise ValueError("period_seconds must be positive")
        self.period = float(period_seconds)
        self.last_stamp = -1
        self.last_started = -math.inf

    def ready(self, stamp_ns, monotonic_seconds):
        return int(stamp_ns) > self.last_stamp and monotonic_seconds - self.last_started >= self.period

    def consume(self, stamp_ns, monotonic_seconds):
        if not self.ready(stamp_ns, monotonic_seconds):
            return False
        self.last_stamp = int(stamp_ns)
        self.last_started = float(monotonic_seconds)
        return True


def sensor_cell_and_yaw(observation, bounds, shape, resolution):
    """World +X maps to columns; world -Y maps to rows."""
    xyz = np.asarray(observation["sensor_xyz_m"], dtype=float)
    q = np.asarray(observation["sensor_xyzw"], dtype=float)
    if xyz.shape != (3,) or q.shape != (4,) or not np.isfinite(xyz).all() or not np.isfinite(q).all():
        raise ValueError("invalid sensor pose")
    if not np.isclose(np.linalg.norm(q), 1.0, atol=1e-4):
        raise ValueError("sensor orientation must be a unit quaternion")
    xmin, ymin, xmax, ymax = map(float, bounds)
    height, width = shape
    if not (xmin <= xyz[0] < xmax and ymin < xyz[1] <= ymax):
        raise ValueError("sensor origin is outside the fixed map grid")
    row = int(math.floor((ymax - xyz[1]) / resolution))
    col = int(math.floor((xyz[0] - xmin) / resolution))
    if not (0 <= row < height and 0 <= col < width):
        raise ValueError("sensor cell is outside the fixed map grid")
    x, y, z, w = q
    yaw_world = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    # The common ray extractor uses row=-sin(yaw), column=cos(yaw).
    return np.array([row, col], dtype=np.int32), math.degrees(yaw_world)


def read_dense_state(directory):
    directory = Path(directory)
    metadata = json.loads((directory / "grid.json").read_text())
    shape = tuple(int(v) for v in metadata["shape_zyx"])
    resolution = float(metadata["resolution_m"])
    if len(shape) != 3 or min(shape) <= 0 or not np.isclose(resolution, .05):
        raise ValueError("expected positive Z/Y/X dimensions at 0.05 m")
    state = np.fromfile(directory / "state.u8", dtype=np.uint8)
    if state.size != math.prod(shape) or not np.isin(state, (0, 1, 2)).all():
        raise ValueError("invalid dense occupancy state data")
    return state.reshape(shape), metadata


def prepare_observation(directory, observation, room_config, ceiling_height_m=None):
    from voxroom_online.isaac_runtime.mapping.coordinate_transform import MapInfo
    from voxroom_online.isaac_runtime.mapping.voxel_occupancy_grid import (
        VoxelOccupancyGrid3D, NavigationProjectionConfig,
    )
    state, metadata = read_dense_state(directory)
    _, height, width = state.shape
    xmin, ymin, xmax, ymax = metadata["map_bounds_xyxy_m"]
    resolution = float(metadata["resolution_m"])
    info = MapInfo(resolution, xmin, xmax, ymin, ymax, width, height)
    grid = VoxelOccupancyGrid3D.zeros((height, width), info, room_config["voxel_grid"])
    if grid.state.shape != state.shape:
        raise ValueError("OctoMap export and core voxel height dimensions differ")
    if not np.isclose(grid.z_min_m, metadata["z_min_m"]) or not np.isclose(grid.z_max_m, metadata["z_max_m"]):
        raise ValueError("OctoMap export and core voxel height reference differ")
    grid.state[:] = state
    grid.log_odds[state == 1] = grid.config.free_logodds_threshold
    grid.log_odds[state == 2] = grid.config.occupied_logodds_threshold
    # OctoMap has no camera frustum. Known free/occupied voxels are the available
    # observation-support evidence; unknown voxels are not fabricated as seen.
    grid.sensor_range_count[:] = (state != 0).astype(np.uint8)
    if ceiling_height_m is None:
        z = np.asarray(grid.z_centers_m)
        candidates = np.flatnonzero((z >= 1.8) & (z <= 4.0))
        counts = np.count_nonzero(state[candidates] == 2, axis=(1, 2))
        if len(counts) and counts.max() > 0:
            ceiling_height_m = float(z[candidates[int(counts.argmax())]])
        status = "occupied-layer peak from current accumulated observations"
    else:
        if not math.isfinite(ceiling_height_m) or ceiling_height_m <= 0:
            raise ValueError("ceiling height must be positive and finite")
        status = "supplied floor-relative ceiling calibration"
    grid.set_active_z_from_ceiling(ceiling_height_m, status=status)
    nav = grid.project_navigation(
        config=NavigationProjectionConfig.from_mapping(room_config["voxel_navigation_projection"]),
        force_full=True, incremental=False,
    )
    rc, yaw = sensor_cell_and_yaw(observation, metadata["map_bounds_xyxy_m"], (height, width), resolution)
    return grid, nav, rc, yaw, metadata
