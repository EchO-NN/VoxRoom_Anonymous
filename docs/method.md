# Method

VoxRoom combines accumulated voxel evidence and planar structural context to segment rooms during exploration.

The implementation uses `vertical_free`, `Vertical Free Map`, and `context_source: vertical` as implementation names for the manuscript's **Structural Free Map (SFM)**. The separate Nav-Free Map (NFM) serves navigation and coverage measurement.

## Mapping and column classification

The simulation configuration integrates rendered depth and simulator poses with the nvblox backend at **0.05 m** XY and Z resolution. Free, occupied, and unknown are distinct states. The auxiliary sensor-range record provides observation support and never changes unknown voxels into occupied voxels. Navigation blind-zone convenience updates do not write synthetic free evidence into the voxel map by default.

For the effective structural height interval with N voxels, let f, o, and u count the free, occupied, and unknown states. Let e count the union of free observations, occupied observations, and sensor-range support. An observed voxel with sensor-range support counts once in e.

| Paper quantity | Default | Implementation |
| --- | ---: | --- |
| Strict-wall occupied ratio, τ_s | 0.9 | `wall_occupied_ratio_min_for_xy_wall` |
| Occluded-wall occupied + unknown ratio, τ_c | 0.9 | `wall_generalized_occupied_ratio_min_for_xy_wall` |
| Occluded-wall actual occupied count, η_c | 9 | `wall_min_actual_occupied_z_cells_for_xy_wall` |
| Occluded-wall unknown ratio, τ_u | strictly below 0.7 | `unknown_ratio_min_for_xy_unknown` |
| Occluded-wall effective support ratio, τ_e | at least 0.7 | `min_effective_range_ratio_for_occluded_wall` |
| Cumulative free count, τ_f | 6 | `min_free_z_cells_for_xy_free` |

The classifier first marks columns with f ≥ 6 structural-free. Among the remaining columns, a strict wall has o/N ≥ 0.9; an occluded wall has (o+u)/N ≥ 0.9, o ≥ 9, u/N < 0.7, and e/N ≥ 0.7. Both wall criteria are retained. All other columns remain unknown.

Free observations may be separated by furniture or unknown layers. The SFM does not require a contiguous free-height run. The default does not promote navigation-free cells or fill unknown holes into SFM free space. It also does not erase structural evidence solely because the navigation-height slice is unknown.

Source: [`voxel_roomseg_evidence.py`](../voxroom_online/isaac_runtime/mapping/voxel_roomseg_evidence.py).

## Candidate generation

For each voxel column, 3D screening computes the mean free and occupied height indices. Its transition reference is **mean free height + half the cumulative number of free voxels**, as in Eq. (4); the free-height span is not substituted for the cumulative count. Both column classification and screening use the effective structural height interval.

| Screening condition | Default |
| --- | ---: |
| Lower-segment (free + unknown) fraction | ≥ 0.9 |
| Upper-segment (occupied + unknown) fraction | ≥ 0.9 |
| Actual free voxels in the lower segment | ≥ 8 |
| Actual occupied voxels in the upper segment | ≥ 6 |
| Unknown fraction in each segment | ≤ 0.3 |
| Mean occupied height relative to mean free height | strictly greater |

The lower segment contains height indices below the transition; the upper segment extends from the transition to the highest observed occupied index. Index arithmetic determines segment membership, avoiding metre-coordinate rounding at an exact bin boundary. A lower support count includes only actual free voxels. The default does not impose an additional absolute lintel-height threshold or minimum seed-component extent.

The complementary 2D generator casts rays on the SFM, stops at occupied or unknown cells (including near the robot), detects adjacent-ray range discontinuities, pairs supported opening endpoints, and rasterizes segments. Both sources are restricted to structural-free cells and combined using a **union**. The default processes candidates supported at the current update. Historical unions remain an optional annotation/collection facility.

Sources: [`voxel_door_detector.py`](../voxroom_online/isaac_runtime/mapping/voxel_door_detector.py), [`stage_extractor.py`](../voxroom_online/isaac_runtime/door_seed_learning/stage_extractor.py), [`hybrid_raw_seed.py`](../voxroom_online/isaac_runtime/door_seed_learning/hybrid_raw_seed.py), and [`hough_raw_seed.py`](../voxroom_online/isaac_runtime/evaluation/online_roomseg/hough_raw_seed.py).

Ray-casting settings are defined in `hough_raw_seed.py`; the remaining geometric and runtime settings are in `configs/voxroom_online.yaml`.

## Entry-Seed Verifier and training

| Component | Implementation |
| --- | --- |
| Local input | 4 × Z × 19 × 19: unknown, free, occupied, normalized height above the common ground reference |
| Shared vertical encoder | 1D CNN, width 40; two Transformer layers, four attention heads |
| Column pooling | Mean + maximum over height → 80 channels |
| Local spatial encoder | Residual 2D CNN; spatial mean + maximum → 224 features |
| SFM context | 3 × 41 × 41: unknown, structural-free, occupied |
| Context encoder | Residual 2D CNN; spatial mean + maximum → 224 features |
| Fusion | 448 → 160 → 40 → 1; sigmoid |
| Acceptance | Probability ≥ 0.5 |
| Optimizer | AdamW, learning rate 3 × 10⁻⁴ |
| Training batch | 64 |
| Loss | Binary cross-entropy with positive-class weight **5.60** |
| Checkpoint selection | Validation candidate-classification F1 at fixed threshold **0.5** |

The positive-class weight is fixed to 5.60. Accuracy and PR-AUC resolve exact F1 ties only. Grouped sampling chooses one historical observation per candidate-coordinate group each epoch. Rotations and one horizontal reflection are applied consistently to the local patch and context. Augmentation uses four right-angle rotations and one horizontal reflection.

Supply a scene manifest CSV with `scene_id,dataset,split` columns, using `interioragent` or `grscene` and `train`, `val`, or `test`. Scene IDs must be globally unique. The split validator requires exactly 8/2/15 InteriorAgent and 8/2/59 GRScene training/validation/test scenes. It preserves the supplied assignments and does not randomly select scenes.

Validate the manifest, build candidate indexes, and train with the defaults in [`paper_training.yaml`](../configs/paper_training.yaml):

```bash
python -m voxroom_online.isaac_runtime.scripts.create_door_seed_scene_split \
  --manifest /path/to/scene_manifest.csv --out data/scene_split.json
python -m voxroom_online.isaac_runtime.scripts.build_door_seed_dataset \
  --collection-root /path/to/collections --split-file data/scene_split.json \
  --out-dir data/door_seed_dataset
python -m voxroom_online.isaac_runtime.scripts.train_door_seed_classifier \
  --index data/door_seed_dataset/dataset_vertical.jsonl \
  --out-dir outputs/verifier --context-source vertical \
  --checkpoint-selection-mode fixed_f1 --threshold-selection-mode fixed \
  --fixed-keep-threshold 0.5 --batch-size 64 \
  --learning-rate 0.0003 --positive-class-weight 5.60 \
  --train-rotation-degrees 0,90,180,270 --train-mirror-lr-once
```

The architecture supports separately trained local-only (`--local-only`, A6) and context-only (`--context-only`, A5) variants. A4 uses `--context-source nav`. A1/A2 change candidate sources before dataset construction and training; A7 replaces geometric candidates with all SFM structural-free cells. A3 omits verification. Train a separate model for every ablation except A3.

Sources: [`model.py`](../voxroom_online/isaac_runtime/door_seed_learning/model.py), [`training.py`](../voxroom_online/isaac_runtime/door_seed_learning/training.py), and [`dataset.py`](../voxroom_online/isaac_runtime/door_seed_learning/dataset.py).

## Separators and segmentation

Verified entry seeds are grouped spatially; neighboring aligned fragments can merge. Line fitting and geometric checks assess residuals, seed support, and continuity. Structural evidence constrains endpoint extension and gap closure. Accepted segments act as virtual separators when connected regions are extracted on the SFM; unknown regions remain unassigned. Navigation labels are a separate projection of these structural room regions.

Separator construction includes wall anchors, line merging, cut validation, incremental updates, and room identity tracking. The minimum room-area setting is 0.5 m². The wall-only extension stage is disabled.

Source: [`voxel_occupancy_door_wall_roomseg.py`](../voxroom_online/isaac_runtime/mapping/voxel_occupancy_door_wall_roomseg.py).

## Evaluation protocol

The paper's development split is **16 training scenes** (8 InteriorAgent + 8 GRScene) and **4 validation scenes** (2 + 2), with **200,867** and **44,516** candidate observations. Testing uses **15 InteriorAgent scenes + 59 GRScene apartments**, five valid initial poses each: **370 trajectories**. There is no scene overlap between splits.

Test trajectories use the shared TVARS exploration policy, terminate when no valid frontier remains or at 5000 control steps, and evaluate the first snapshot reaching **20%, 40%, 60%, 70%, 80%, 90%, and Final**. Random-frontier exploration is the training collection policy. Use the shared test trajectories for evaluation; the general simulation template defaults to the training collection policy.

All methods are evaluated on the same currently observed SFM structural-free domain. A final-map ground-truth room retains its identity even when restriction to the current domain leaves disconnected observed fragments. Precision and recall use best-overlap predicted/ground-truth regions; F1 is calculated per snapshot. Room-mIoU maximizes total IoU with one-to-one Hungarian matching and divides by the number of ground-truth rooms, including unmatched rooms as zero.

For the overall Average, first average valid snapshots within each trajectory, then trajectories within each scene, then scenes equally. Stage-wise results first select the matching progress stage and then average within scene and across scenes. Population standard deviation and minimum are computed per trajectory before the same scene-balanced aggregation. Pooling all checkpoints together is a different protocol. Paper baseline settings include DUDE concavity 1.5 m and Morphological room-area range 0.8–15 m², chosen with post-hoc sweeps as disclosed in the manuscript.

The real-robot paper protocol has nine runs across five apartments, 0.5 Hz updates, and a verifier trained exclusively in simulation. The real-robot runtime measurements use an RTX 4070 Laptop GPU and TensorRT FP16. See [real-robot setup](real_robot.md) for the sensor and mapping interfaces.

## Tests

[`test_paper_alignment.py`](../tests/test_paper_alignment.py) compares SFM classification with literal equations on randomized columns, checks overlapping sensor evidence is counted once, verifies cumulative free evidence across gaps, compares 3D screening against an independent equation implementation on 1,003 partial columns, tests effective height selection, tests F1-based checkpoint selection, and runs all three network branch configurations.
