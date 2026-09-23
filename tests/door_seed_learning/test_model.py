from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from voxroom_online.isaac_runtime.door_seed_learning.model import (
    MODEL_ARCHITECTURE_VERSION,
    PREPROCESSOR_VERSION,
    DoorSeedModelConfig,
    build_door_seed_model,
)
from voxroom_online.isaac_runtime.door_seed_learning.config import DoorSeedLearningConfig
from voxroom_online.isaac_runtime.door_seed_learning.inference import DoorSeedInferenceEngine
from voxroom_online.isaac_runtime.door_seed_learning.schema import (
    DATASET_SCHEMA_VERSION,
    sha256_bytes,
    source_tree_hash,
)
from voxroom_online.isaac_runtime.door_seed_learning.stage_extractor import extract_door_seed_stage
from voxroom_online.isaac_runtime.mapping.coordinate_transform import MapInfo
from voxroom_online.isaac_runtime.mapping.voxel_door_detector import VoxelDoorDetectorConfig
from voxroom_online.isaac_runtime.mapping.voxel_occupancy_grid import VoxelOccupancyGrid3D


@pytest.mark.parametrize("batch_size", [1, 3])
def test_model_outputs_one_raw_logit_for_vertical_and_nav_context(batch_size: int) -> None:
    model = build_door_seed_model(DoorSeedModelConfig(z_count=12)).eval()
    assert not any(isinstance(module, torch.nn.Sigmoid) for module in model.modules())
    voxel = torch.randn(batch_size, 4, 12, 19, 19)
    for context in (torch.randn(batch_size, 3, 41, 41), torch.zeros(batch_size, 3, 41, 41)):
        with torch.inference_mode():
            logits = model(voxel, context)
        assert logits.shape == (batch_size, 1)
        assert torch.isfinite(logits).all()


def test_model_state_dict_round_trip_preserves_logits(tmp_path: Path) -> None:
    config = DoorSeedModelConfig(z_count=12)
    model = build_door_seed_model(config).eval()
    voxel = torch.randn(2, 4, 12, 19, 19)
    context = torch.randn(2, 3, 41, 41)
    with torch.inference_mode():
        expected = model(voxel, context)
    path = tmp_path / "state.pt"
    torch.save(model.state_dict(), path)
    restored = build_door_seed_model(config).eval()
    restored.load_state_dict(torch.load(path, map_location="cpu", weights_only=True), strict=True)
    with torch.inference_mode():
        actual = restored(voxel, context)
    torch.testing.assert_close(actual, expected, rtol=0.0, atol=0.0)


def test_checkpoint_requires_scene_metadata_and_cross_consistent_z_count(tmp_path: Path) -> None:
    config = DoorSeedModelConfig(z_count=12)
    model = build_door_seed_model(config)
    z_centers = np.arange(12, dtype=np.float32) * 0.05
    checkpoint = {
        "model_state_dict": model.state_dict(),
        "model_config": config.to_dict(),
        "model_architecture_version": MODEL_ARCHITECTURE_VERSION,
        "preprocessor_version": PREPROCESSOR_VERSION,
        "context_source": "vertical",
        "local_patch_size": 19,
        "context_patch_size": 41,
        "z_count": 12,
        "z_min_m": 0.0,
        "z_resolution_m": 0.05,
        "xy_resolution_m": 0.05,
        "z_centers_sha256": sha256_bytes(np.ascontiguousarray(z_centers).tobytes()),
        "raw_seed_config_hash": "raw-hash",
        "input_semantics_hash": "semantics-hash",
        "height_scale_m": 4.0,
        "voxel_state_mapping": {"unknown": [0, 3], "free": [1], "occupied": [2]},
        "recommended_keep_threshold": 0.4,
        "achieved_recall": 0.99,
        "negative_rejection_rate": 0.5,
        "training_scene_ids": ["scene_train"],
        "validation_scene_ids": ["scene_val"],
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "source_code_hash": source_tree_hash(Path(__file__).parents[2] / "voxroom_online/isaac_runtime/door_seed_learning"),
    }
    valid_path = tmp_path / "valid.pt"
    torch.save(checkpoint, valid_path)
    engine = DoorSeedInferenceEngine(
        DoorSeedLearningConfig(
            mode="inference",
            checkpoint_path=str(valid_path),
            context_source="vertical",
            device="cpu",
        ).validate()
    )
    assert engine.model is not None
    with pytest.raises(ValueError, match="input_semantics_hash"):
        engine._validate_runtime_metadata(
            z_centers_m=z_centers,
            z_min_m=0.0,
            z_resolution_m=0.05,
            xy_resolution_m=0.05,
            raw_seed_config_hash="raw-hash",
            input_semantics_hash="wrong-semantics-hash",
        )

    malformed = dict(checkpoint)
    malformed.pop("training_scene_ids")
    malformed_path = tmp_path / "missing-scenes.pt"
    torch.save(malformed, malformed_path)
    with pytest.raises(ValueError, match="training_scene_ids"):
        DoorSeedInferenceEngine(
            DoorSeedLearningConfig(
                mode="inference",
                checkpoint_path=str(malformed_path),
                context_source="vertical",
                device="cpu",
            ).validate()
        )

    inconsistent = dict(checkpoint)
    inconsistent["z_count"] = 13
    inconsistent_path = tmp_path / "bad-z.pt"
    torch.save(inconsistent, inconsistent_path)
    with pytest.raises(ValueError, match="z_count"):
        DoorSeedInferenceEngine(
            DoorSeedLearningConfig(
                mode="inference",
                checkpoint_path=str(inconsistent_path),
                context_source="vertical",
                device="cpu",
            ).validate()
        )


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is unavailable")
def test_cuda_forward_and_checkpoint_round_trip(tmp_path: Path) -> None:
    config = DoorSeedModelConfig(z_count=12)
    model = build_door_seed_model(config).cuda().eval()
    voxel = torch.randn(3, 4, 12, 19, 19, device="cuda")
    context = torch.randn(3, 3, 41, 41, device="cuda")
    with torch.inference_mode():
        expected = model(voxel, context)
    path = tmp_path / "cuda-state.pt"
    torch.save({key: value.detach().cpu() for key, value in model.state_dict().items()}, path)
    restored = build_door_seed_model(config).cuda().eval()
    restored.load_state_dict(torch.load(path, map_location="cpu", weights_only=True), strict=True)
    with torch.inference_mode():
        actual = restored(voxel, context)
    torch.testing.assert_close(actual, expected, rtol=0.0, atol=0.0)


@pytest.mark.parametrize("failure", ["nan", "oom"])
def test_model_nan_and_oom_use_only_explicit_rules_fallback(failure: str) -> None:
    class FailingModel(torch.nn.Module):
        def forward(self, voxel, context):
            if failure == "oom":
                raise RuntimeError("CUDA out of memory in test model")
            return torch.full((voxel.shape[0], 1), float("nan"), device=voxel.device)

    grid, stage = _single_seed_stage()
    engine = DoorSeedInferenceEngine.__new__(DoorSeedInferenceEngine)
    engine.config = DoorSeedLearningConfig(
        mode="inference",
        checkpoint_path="unused.pt",
        context_source="vertical",
        device="cpu",
        fallback_to_rule_seed_on_error=True,
    ).validate()
    z = np.asarray(grid.z_centers_m, dtype=np.float32)
    engine.model = FailingModel()
    engine.checkpoint = {
        "z_count": len(z),
        "z_min_m": float(grid.z_min_m),
        "z_resolution_m": float(grid.z_resolution_m),
        "xy_resolution_m": float(grid.map_info.resolution_m),
        "z_centers_sha256": sha256_bytes(np.ascontiguousarray(z).tobytes()),
        "raw_seed_config_hash": stage.raw_seed_config_hash,
        "input_semantics_hash": stage.input_semantics_hash,
    }
    engine.device = torch.device("cpu")
    engine.load_error = None
    engine.fallback_count = 0
    engine.inference_count = 0
    output = engine.filter_stage(stage=stage, voxel_grid=grid, seed_connectivity=8)
    assert output.fallback_reason is not None
    assert engine.fallback_count == 1
    np.testing.assert_array_equal(output.seed_result.door_seed_mask, stage.raw_seed_mask_xy)


def _single_seed_stage():
    height = width = 11
    map_info = MapInfo(
        resolution_m=0.05,
        min_x=0.0,
        max_x=width * 0.05,
        min_y=0.0,
        max_y=height * 0.05,
        width=width,
        height=height,
    )
    grid = VoxelOccupancyGrid3D.zeros(
        (height, width),
        map_info,
        {"z_min_m": 0.0, "z_max_m": 0.6, "z_resolution_m": 0.05, "outside_boundary_enabled": False},
    )
    nav = np.ones((height, width), dtype=bool)
    stage = extract_door_seed_stage(
        voxel_grid=grid,
        navigation_free_mask=nav,
        navigation_obstacle_mask=np.zeros((height, width), dtype=bool),
        unknown_mask=np.zeros((height, width), dtype=bool),
        door_seed_no_clearance_free_mask=nav,
        resolution_m=0.05,
        voxel_evidence_config={},
        door_config=VoxelDoorDetectorConfig(),
    )
    mask = np.zeros((height, width), dtype=bool)
    mask[5, 5] = True
    raw = stage.raw_seed_result
    reason = np.asarray(raw.door_seed_reject_reason_map, dtype=np.uint8).copy()
    reason[mask] = 1
    raw = replace(
        raw,
        door_seed_mask=mask.copy(),
        door_seed_component_map=np.zeros((height, width), dtype=np.int32),
        door_seed_reject_reason_map=reason,
        seed_evidence=[],
    )
    return grid, replace(stage, raw_seed_result=raw, raw_seed_mask_xy=mask)
