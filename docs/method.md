# Method

VoxRoom combines accumulated voxel evidence and planar structural context to segment rooms during exploration.

In the code, `vertical_free`, `Vertical Free Map`, and `context_source: vertical` refer to the **Structural Free Map (SFM)**. The Nav-Free Map (NFM) serves navigation and coverage measurement.

## Mapping and column classification

Simulation integrates rendered depth and simulator poses with nvblox at **0.05 m** XY and Z resolution. Voxels store free, occupied, or unknown states. The sensor-range record tracks observation support separately from occupancy.

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

The free count sums observations across heights, including layers separated by furniture or unknown space. SFM classification uses this column evidence independently of the navigation-height slice.

Source: [`voxel_roomseg_evidence.py`](../voxroom_online/isaac_runtime/mapping/voxel_roomseg_evidence.py).

## Candidate generation

For each voxel column, 3D screening computes the mean free and occupied height indices. The transition reference is **mean free height + half the cumulative number of free voxels** (Eq. 4). Classification and screening use the same effective structural height interval.

| Screening condition | Default |
| --- | ---: |
| Lower-segment (free + unknown) fraction | ≥ 0.9 |
| Upper-segment (occupied + unknown) fraction | ≥ 0.9 |
| Actual free voxels in the lower segment | ≥ 8 |
| Actual occupied voxels in the upper segment | ≥ 6 |
| Unknown fraction in each segment | ≤ 0.3 |
| Mean occupied height relative to mean free height | strictly greater |

The lower segment contains height indices below the transition. The upper segment extends from the transition to the highest observed occupied index. Segment membership is computed in voxel indices, and lower support counts actual free voxels.

The 2D generator casts rays on the SFM, stopping at occupied or unknown cells. It detects adjacent-ray range discontinuities, pairs opening endpoints, and rasterizes the resulting segments. The **union** of 3D and 2D candidates is restricted to SFM free cells. Both sources are computed from the current accumulated observations at each update.

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

Accuracy and PR-AUC break ties in validation F1. Grouped sampling draws one observation per candidate-coordinate group each epoch. Augmentation applies four right-angle rotations and one horizontal reflection to both the local patch and context.

Supply a scene manifest CSV with `scene_id,dataset,split` columns, using `interioragent` or `grscene` and `train`, `val`, or `test`. Give every scene a unique ID. The validator checks for 8/2/15 InteriorAgent and 8/2/59 GRScene training/validation/test scenes and keeps the supplied assignments.

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

Each update rebuilds separators from the current verified seeds and accumulated map. Previous separators are discarded. The minimum room-area setting is 0.5 m², and the wall-only extension stage is disabled.

Source: [`voxel_occupancy_door_wall_roomseg.py`](../voxroom_online/isaac_runtime/mapping/voxel_occupancy_door_wall_roomseg.py).

## Evaluation protocol

The paper's development split is **16 training scenes** (8 InteriorAgent + 8 GRScene) and **4 validation scenes** (2 + 2), with **200,867** and **44,516** candidate observations. Testing uses **15 InteriorAgent scenes + 59 GRScene apartments**, five valid initial poses each: **370 trajectories**. There is no scene overlap between splits.

Test trajectories use the shared TVARS exploration policy, terminate when no valid frontier remains or at 5000 control steps, and evaluate the first snapshot reaching **20%, 40%, 60%, 70%, 80%, 90%, and Final**. Random-frontier exploration is the training collection policy. Use the shared test trajectories for evaluation; the general simulation template defaults to the training collection policy.

All methods are evaluated on the same currently observed SFM structural-free domain. A final-map ground-truth room retains its identity even when restriction to the current domain leaves disconnected observed fragments. Precision and recall use best-overlap predicted/ground-truth regions; F1 is calculated per snapshot. Room-mIoU maximizes total IoU with one-to-one Hungarian matching and divides by the number of ground-truth rooms, including unmatched rooms as zero.

For the overall Average, average valid snapshots within each trajectory, then trajectories within each scene, then scenes equally. Stage results use the corresponding snapshot from each trajectory. Population standard deviation and minimum are computed per trajectory before the same scene-balanced aggregation. The paper uses DUDE concavity 1.5 m and a Morphological room-area range of 0.8–15 m², selected by post-hoc sweeps.

The paper reports nine robot runs across five apartments at 0.5 Hz, using a verifier trained in simulation. Timing measurements use an RTX 4070 Laptop GPU and TensorRT FP16. See [real-robot setup](real_robot.md) for the released sensor and mapping interfaces and the [release contents](../README.md#training-and-evaluation) for available experiment artifacts.

## Tests

[`test_paper_alignment.py`](../tests/test_paper_alignment.py) compares SFM classification with literal equations on randomized columns, checks overlapping sensor evidence is counted once, verifies cumulative free evidence across gaps, compares 3D screening against an independent equation implementation on 1,003 partial columns, tests effective height selection, tests F1-based checkpoint selection, and runs all three network branch configurations.
