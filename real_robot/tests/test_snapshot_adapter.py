import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

SPEC = importlib.util.spec_from_file_location("snapshot_adapter", Path(__file__).parents[1] / "snapshot_adapter.py")
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


class AdapterTests(unittest.TestCase):
    def test_rate_gate_drops_duplicates_and_out_of_order_observations(self):
        gate = adapter.ObservationGate(2)
        self.assertTrue(gate.consume(100, 10))
        self.assertFalse(gate.consume(100, 12))
        self.assertFalse(gate.consume(90, 15))
        self.assertFalse(gate.consume(110, 11.9))
        self.assertTrue(gate.consume(110, 12))
        self.assertTrue(gate.consume(130, 16))

    def test_map_coordinates_preserve_minus_y_row_axis(self):
        observation = {"sensor_xyz_m": [0.125, .175, 1], "sensor_xyzw": [0, 0, 0, 1]}
        rc, yaw = adapter.sensor_cell_and_yaw(observation, [0, 0, .3, .2], (4, 6), .05)
        np.testing.assert_array_equal(rc, [0, 2])
        self.assertEqual(yaw, 0)
        observation["sensor_xyz_m"][1] = .025
        observation["sensor_xyzw"] = [0, 0, np.sqrt(.5), np.sqrt(.5)]
        rc, yaw = adapter.sensor_cell_and_yaw(observation, [0, 0, .3, .2], (4, 6), .05)
        np.testing.assert_array_equal(rc, [3, 2])
        self.assertAlmostEqual(yaw, 90)

    def test_invalid_pose_and_outside_origin_rejected(self):
        for xyz, q in (([1, 1, 1], [0, 0, 0, 1]), ([.1, .1, 1], [0, 0, 0, 2])):
            with self.assertRaises(ValueError):
                adapter.sensor_cell_and_yaw({"sensor_xyz_m": xyz, "sensor_xyzw": q}, [0, 0, .3, .2], (4, 6), .05)

    def test_dense_file_state_and_length_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            metadata = {"shape_zyx": [2, 2, 2], "resolution_m": .05}
            (path / "grid.json").write_text(json.dumps(metadata))
            state = np.array([0, 1, 2, 0, 1, 2, 0, 0], dtype=np.uint8)
            state.tofile(path / "state.u8")
            loaded, _ = adapter.read_dense_state(path)
            np.testing.assert_array_equal(loaded.ravel(), state)
            state[:-1].tofile(path / "state.u8")
            with self.assertRaises(ValueError):
                adapter.read_dense_state(path)

    def test_core_grid_keeps_unknown_voxels_unobserved(self):
        from voxroom_online.isaac_runtime.config import load_config
        config_path = Path(__file__).resolve().parents[2] / "configs/voxroom_online.yaml"
        room_config = dict(load_config(config_path).mapping.room_segmentation)
        state = np.zeros((82, 4, 6), dtype=np.uint8)
        state[4:30, 1:3, 1:5] = 1
        state[55:57, 1:3, 1:5] = 2
        observation = {"sensor_xyz_m": [.125, .125, 1], "sensor_xyzw": [0, 0, 0, 1]}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            metadata = dict(shape_zyx=list(state.shape), resolution_m=.05,
                            map_bounds_xyxy_m=[0, 0, .3, .2], z_min_m=-.1, z_max_m=4.)
            (path / "grid.json").write_text(json.dumps(metadata))
            state.tofile(path / "state.u8")
            grid, _, rc, _, _ = adapter.prepare_observation(path, observation, room_config)
            np.testing.assert_array_equal(grid.state, state)
            np.testing.assert_array_equal(grid.sensor_range_count, state != 0)
            np.testing.assert_array_equal(rc, [1, 2])
            self.assertIsNotNone(grid.ceiling_height_m)


if __name__ == "__main__":
    unittest.main()
