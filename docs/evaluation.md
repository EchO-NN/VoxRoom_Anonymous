# Evaluation protocol

`scripts/evaluate_paper.py` computes the paper metrics from saved predictions,
ground-truth room labels, and the observed SFM domain. It requires NumPy and SciPy.

## Snapshot selection and domain

Coverage is the known traversable area in the current Nav-Free Map divided by
the traversable area of a reference map projected from complete scene geometry.
Select the first snapshot reaching each of 20%, 40%, 60%, 70%, 80%, and 90%, plus
the final exploration snapshot. Final is the last observation, at whatever
coverage exploration reaches. The reference map determines evaluation times;
segmentation uses the current observations.

For every method, evaluate on the same currently observed structural-free cells
in the SFM. Restrict final room annotations and predictions to this domain.
Disconnected visible fragments of the same annotated room retain the same room
ID. Unknown cells remain outside the domain. An unassigned prediction within the
domain contributes missing overlap. Ground-truth labels must cover the whole
evaluation domain.

All annotated room instances present in the evaluation domain enter the metrics.
Room-size filtering within a segmentation method is separate from scoring.

## Metrics and aggregation

At each snapshot, precision averages `max_j |P_i ∩ G_j| / |P_i|` over predicted
rooms. Recall averages `max_i |P_i ∩ G_j| / |G_j|` over ground-truth rooms. F1 is
`2PR / (P + R)` at that snapshot, or zero when both quantities are zero.

Room-mIoU uses Hungarian matching to maximize the summed room IoU, divided by
the number of ground-truth rooms. Unmatched ground-truth rooms contribute zero.

For each method:

1. For a stage-specific result, average the trajectories available at that stage
   within each scene, then average scenes equally.
2. For Average, first average valid stages within each trajectory, then average
   trajectories within a scene, then average scenes equally.
3. Compute population standard deviation (`ddof=0`) and minimum room-mIoU over
   valid stages within each trajectory. Average each statistic within scene and
   equally across scenes. These statistics measure segmentation quality over time.

Compute F1 per snapshot before averaging. Each scene has equal weight in the
final result.

The manifest audit checks 15 InteriorAgent and 59 GRScene test scenes, five
trajectories per scene, 370 snapshots per stage except 348 at 90%, and 2,568
snapshots in total. Methods must share their snapshot identities. Missing 90%
observations are permitted; missing other required stages are reported. The
audit checks snapshot counts and identifiers against this protocol.

## Run from label maps

Each NPZ snapshot must contain three arrays of the same two-dimensional shape:

| Key | Type and meaning |
| --- | --- |
| `gt_labels` | Nonnegative integer final annotation; positive room ID at every observed structural-free cell |
| `pred_labels` | Nonnegative integer prediction; zero means unassigned |
| `sfm_free` | Boolean/binary shared evaluation domain at this observation |

Create a UTF-8 CSV manifest with this header:

```csv
method,dataset,scene_id,trajectory_id,stage,snapshot
VoxRoom,interioragent,scene_001,trajectory_01,20,snapshots/example.npz
```

NPZ paths are relative to the CSV directory. Stage values are `20`, `40`, `60`,
`70`, `80`, `90`, and `final`; percentage suffixes are accepted. Keep scene IDs
consistent across trajectories and methods. Use dataset identifiers
`interioragent` and `grscene`.

```bash
python scripts/evaluate_paper.py --snapshots manifest.csv --out evaluation-output
```

Choose a new output directory. To evaluate a development subset, add
`--allow-incomplete`; `protocol_audit.json` lists the missing observations.

## Run from scalar scores

The score CSV has the identifier columns above and `precision`, `recall`, `f1`,
and `room_miou`, expressed as fractions in `[0, 1]`. Duplicate snapshot identities,
nonfinite scores, and a per-snapshot F1 inconsistent with P/R are errors.

```bash
python scripts/evaluate_paper.py \
  --scores data/snapshot_scores.csv \
  --out evaluation-output
```

The output comprises per-snapshot scores, scene-balanced stage and average
scores, population stability statistics, and a manifest audit. Summary accuracy
values are percentages; standard deviations are percentage points.

## Tests

The tests cover merge/split errors, disconnected room identity, unassigned
predictions, annotation holes, unequal trajectory/stage counts, per-snapshot F1,
duplicate records, final-stage semantics, and missing baseline observations.

```bash
python -m unittest discover -s tests -p test_paper_evaluation.py -v
```
