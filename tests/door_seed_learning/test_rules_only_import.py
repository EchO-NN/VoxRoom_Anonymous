from __future__ import annotations

import subprocess
import sys


def test_disabled_roomseg_import_does_not_import_torch() -> None:
    code = """
import sys
from voxroom_online.isaac_runtime.mapping.voxel_occupancy_door_wall_roomseg import VoxelOccupancyDoorWallRoomSegConfig
cfg = VoxelOccupancyDoorWallRoomSegConfig.from_mapping({'door_seed_learning': {'mode': 'disabled'}})
assert cfg.door_seed_learning.mode == 'disabled'
assert 'torch' not in sys.modules
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
