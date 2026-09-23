from __future__ import annotations

import numpy as np

from voxroom_online.isaac_runtime.env.isaac_process import IsaacSimServer


class _DepthOnlyCamera:
    def get_current_frame(self) -> dict:
        return {}

    def get_depth(self, device: str = "cpu") -> np.ndarray:
        _ = device
        return np.ones((4, 4), dtype=np.float32)


def test_camera_get_depth_fallback_is_explicit_image_plane_z() -> None:
    server = IsaacSimServer(width=4, height=4, enable_depth=True, verbose=False)
    server.camera = _DepthOnlyCamera()

    obs = server.get_observation(read_rgb=False, read_depth=True)

    assert obs["has_depth"] is True
    assert isinstance(obs["depth"], np.ndarray)
    assert obs["depth_source"] == "camera_get_depth"
    assert obs["depth_semantics"] == "image_plane_z"


def test_camera_fill_light_defaults_are_audited_without_isaac_runtime() -> None:
    server = IsaacSimServer(width=4, height=4, verbose=False)

    metadata = server.camera_fill_light_metadata()

    assert metadata == {
        "enabled": True,
        "applied": False,
        "type": "camera_mounted_sphere",
        "prim_path": "/World/Kaya/camera_rgbd/VoxRoomRgbFillLight",
        "intensity": 4000.0,
        "base_intensity": 4000.0,
        "radius_m": 0.35,
        "exposure": 0.0,
        "color_temperature_k": 5500.0,
        "auto_distance_enabled": True,
        "reference_distance_m": 2.0,
        "min_intensity": 500.0,
        "max_intensity": 8000.0,
        "auto_render_updates": 6,
        "last_depth_median_m": None,
        "adaptation_count": 0,
    }


def test_camera_fill_light_rejects_invalid_photometric_values() -> None:
    with np.testing.assert_raises_regex(ValueError, "intensity"):
        IsaacSimServer(camera_fill_light_intensity=-1.0, verbose=False)
    with np.testing.assert_raises_regex(ValueError, "radius"):
        IsaacSimServer(camera_fill_light_radius_m=0.0, verbose=False)


def test_camera_fill_light_distance_control_dims_near_and_boosts_far_surfaces() -> None:
    server = IsaacSimServer(verbose=False)

    near = server.camera_fill_light_intensity_from_depth(np.full((4, 4), 0.45, dtype=np.float32))
    reference = server.camera_fill_light_intensity_from_depth(np.full((4, 4), 2.0, dtype=np.float32))
    far = server.camera_fill_light_intensity_from_depth(np.full((4, 4), 3.0, dtype=np.float32))

    assert near == 500.0
    assert reference == 4000.0
    assert far == 8000.0
