"""Independent equation checks for the manuscript-aligned review release."""
from types import SimpleNamespace

import numpy as np

from voxroom_online.isaac_runtime.mapping.voxel_occupancy_grid import (
    VOXEL_FREE as F, VOXEL_OCCUPIED as O, VOXEL_UNKNOWN as U,
)
from voxroom_online.isaac_runtime.mapping.voxel_roomseg_evidence import (
    VoxelRoomsegEvidenceConfig, classify_voxel_columns_for_roomseg,
)
from voxroom_online.isaac_runtime.mapping.voxel_door_detector import (
    VoxelDoorDetectorConfig, classify_voxel_door_seeds_centroid_ratio_vectorized,
    _door_scan_z_bounds,
)
from voxroom_online.isaac_runtime.door_seed_learning.training import (
    TrainingConfig, fixed_f1_checkpoint_selection_score, select_operating_metrics,
)


def classify_sfm(states, sensor=None, navigation_free=None):
    states = np.asarray(states, dtype=np.uint8)
    shape = states.shape[1:]
    zeros = np.zeros(shape, dtype=bool)
    return classify_voxel_columns_for_roomseg(
        state_active=states, sensor_range_active=sensor,
        navigation_free_mask=zeros if navigation_free is None else navigation_free,
        navigation_obstacle_mask=zeros, navigation_unknown_mask=~zeros,
        cfg=VoxelRoomsegEvidenceConfig(),
    )


def test_sfm_matches_equations_on_random_columns():
    rng = np.random.default_rng(19)
    # Mix observation distributions so all three output classes occur.
    blocks = [rng.choice([U, F, O], size=(30, 1, 200), p=p) for p in (
        (.05, .02, .93), (.4, .03, .57), (.8, .03, .17), (.4, .4, .2),
    )]
    state = np.concatenate(blocks, axis=2)
    sensor = rng.integers(0, 2, size=state.shape, dtype=np.uint8)
    n_f, n_o, n_u = [(state == value).sum(axis=0) for value in (F, O, U)]
    n_e = ((state == F) | (state == O) | (sensor > 0)).sum(axis=0)
    expected_free = n_f >= 6
    expected_wall = ~expected_free & (
        (n_o / 30 >= .9)
        | (((n_o + n_u) / 30 >= .9) & (n_o >= 9) & (n_u / 30 < .7) & (n_e / 30 >= .7))
    )
    result = classify_sfm(state, sensor)
    np.testing.assert_array_equal(result['vertical_free'], expected_free)
    np.testing.assert_array_equal(result['wall'], expected_wall)
    np.testing.assert_array_equal(result['unknown'], ~(expected_free | expected_wall))


def test_sensor_support_is_a_union_not_double_counted():
    state = np.array([O] * 9 + [U] * 11, dtype=np.uint8).reshape(20, 1, 1)
    sensor = (state == O).astype(np.uint8)
    result = classify_sfm(state, sensor)
    assert result['effective_range_count'][0, 0] == 9
    assert not result['wall'][0, 0]  # 45% support cannot pass the 70% gate.
    sensor[9:14] = 1
    assert classify_sfm(state, sensor)['wall'][0, 0]


def test_free_accumulates_across_gaps_without_navigation_promotion():
    state = np.full((30, 1, 3), U, dtype=np.uint8)
    state[[0, 3, 6, 9, 12, 15], 0, 0] = F
    state[[0, 3, 6, 9, 12], 0, 1] = F
    result = classify_sfm(state, navigation_free=np.ones((1, 3), dtype=bool))
    np.testing.assert_array_equal(result['vertical_free'], [[True, False, False]])


def paper_seed(column):
    """Literal equations (4)-(6), independently using integer height indices."""
    z = np.arange(len(column))
    free, occupied = z[column == F], z[column == O]
    if not len(free) or not len(occupied):
        return False
    h = free.mean() + len(free) / 2
    lower = column[z < h]
    upper = column[(z >= h) & (z <= occupied.max())]
    if not len(lower) or not len(upper):
        return False
    return bool(
        ((lower == F) | (lower == U)).mean() >= .9
        and ((upper == O) | (upper == U)).mean() >= .9
        and (lower == F).sum() >= 8 and (upper == O).sum() >= 6
        and (lower == U).mean() <= .3 and (upper == U).mean() <= .3
        and occupied.mean() > free.mean()
    )


def test_3d_screening_matches_equations_with_partial_observations():
    rng = np.random.default_rng(41)
    columns = []
    for _ in range(1000):
        split = int(rng.integers(8, 29))
        col = np.array([F] * split + [O] * (40 - split), dtype=np.uint8)
        col[rng.random(40) < .25] = U
        col[rng.random(40) < .04] = F
        columns.append(col)
    columns.extend([
        np.array([F] * 8 + [O] * 32, dtype=np.uint8),
        np.array([U] * 12 + [F] * 12 + [O] * 16, dtype=np.uint8),
        np.array([F, U] * 10 + [O] * 20, dtype=np.uint8),
    ])
    state = np.stack(columns, axis=1)[:, None, :]
    z = .125 + .05 * np.arange(40)
    result = classify_voxel_door_seeds_centroid_ratio_vectorized(
        state, z, np.arange(40), VoxelDoorDetectorConfig(), shape=(1, len(columns)),
        return_debug=True,
    )
    expected = np.array([[paper_seed(c) for c in columns]])
    assert expected.any() and (~expected).any()
    np.testing.assert_array_equal(result[0], expected)


def test_door_screening_uses_effective_structural_height():
    grid = SimpleNamespace(active_z_min_m=.1, active_z_max_m=2.55, z_max_m=4.)
    lower, upper, source = _door_scan_z_bounds(grid, VoxelDoorDetectorConfig())
    assert (lower, upper, source) == (.1, 2.55, 'effective_structural_interval')


def test_checkpoint_selection_prioritizes_f1_at_fixed_half():
    # Higher accuracy must not displace a model with higher validation F1.
    high_f1 = fixed_f1_checkpoint_selection_score(f1=.9, accuracy=.8, pr_auc=.8)
    high_acc = fixed_f1_checkpoint_selection_score(f1=.85, accuracy=.99, pr_auc=.99)
    assert high_f1 > high_acc
    cfg = TrainingConfig()
    assert (cfg.batch_size, cfg.learning_rate, cfg.positive_class_weight) == (64, 3e-4, 5.6)
    assert cfg.train_mirror_lr_once and cfg.grouped_coordinate_sampling
    assert cfg.checkpoint_selection_mode == 'fixed_f1'
    result = select_operating_metrics(
        [1, 0], [.5, .49], threshold_selection_mode='fixed',
        fixed_keep_threshold=.5, target_recall=.98,
    )
    assert result['f1'] == 1.


def test_paper_network_dimensions_and_both_branch_ablations():
    import torch
    from voxroom_online.isaac_runtime.door_seed_learning.model import (
        DoorSeedModelConfig, build_door_seed_model,
    )
    torch.set_num_threads(1)
    for voxel_branch, context_branch in ((True, True), (True, False), (False, True)):
        model = build_door_seed_model(DoorSeedModelConfig(
            z_count=8, use_voxel_branch=voxel_branch, use_context_branch=context_branch,
        )).eval()
        with torch.inference_mode():
            logits = model(torch.zeros(1, 4, 8, 19, 19), torch.zeros(1, 3, 41, 41))
        assert logits.shape == (1, 1)
        assert [m.out_features for m in model.classifier if isinstance(m, torch.nn.Linear)] == [160, 40, 1]
        assert model.classifier[0].in_features == 224 * (voxel_branch + context_branch)
        if voxel_branch:
            assert len(model.column_transformer.layers) == 2
            assert model.column_transformer.layers[0].self_attn.num_heads == 4
            assert model.column_transformer.layers[0].self_attn.embed_dim == 40


def test_2d_rays_stop_at_unknown_even_near_robot():
    from voxroom_online.isaac_runtime.evaluation.online_roomseg.hough_raw_seed import range_jump_door_points
    # A remote wall behind unknown space must not generate a ray-length jump.
    # The legacy 30-cell robot disk would artificially reveal that wall.
    occupied = np.zeros((161, 161), dtype=bool)
    occupied[70:91, 90] = True
    unknown = np.ones_like(occupied)
    unknown[79:82, 79:82] = False
    unknown[occupied] = False
    points = range_jump_door_points(
        obstacle_mask=occupied, unknown_mask=unknown,
        agent_rc=(80, 80), yaw_deg=0., resolution_m=.05,
    )
    assert points == ()
    legacy = range_jump_door_points(
        obstacle_mask=occupied, unknown_mask=unknown,
        agent_rc=(80, 80), yaw_deg=0., resolution_m=.05, bot_near_range_cells=30,
    )
    assert legacy  # confirms this fixture distinguishes the old behavior
