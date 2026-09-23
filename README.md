# VoxRoom

**Room Segmentation from Partial Observations during Robot Exploration**

The implementation constructs a
Structural Free Map (SFM), combines 3D column evidence with 2D ray-casting entry
candidates, verifies candidates with a dual-branch neural network, and fits
separators to partition the observed structural-free domain.

[Project page](site/index.html) · [Method and parameters](docs/method.md) ·
[Evaluation](docs/evaluation.md) · [Real robot](docs/real_robot.md)

## Overview

The SFM aggregates free-space evidence across heights to preserve structural
connectivity in clutter. The Nav-Free Map is used separately for navigation and
exploration coverage. Both simulation and real-robot interfaces share the same
segmentation and verification modules.

## Install and run a CPU smoke test

From the extracted repository directory, using Python 3.11 or newer:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[learning,test]'
voxroom-replay --demo --rules-only --output outputs/smoke
pytest -q
```

The generated two-room fixture tests the geometry path. `--rules-only` explicitly
bypasses the verifier and is a diagnostic ablation, not the full method. Outputs
are room-label arrays, the structural evaluation domain, separators, and a JSON
summary. No simulator, scene assets, or downloads are needed for this smoke test.

## Replay observed voxels with learned verification

```bash
voxroom-replay --snapshot data/roomseg_step_000100.npz \
  --checkpoint checkpoints/entry_seed_verifier.pt --device cpu \
  --output outputs/replay
```

For a fixed-grid trajectory, `--sequence data/trajectory/roomseg_snapshots`
processes zero-padded `roomseg_step_*.npz` in order and preserves separator memory.
Each NPZ must contain:

| Key | Shape / meaning |
| --- | --- |
| `voxel_occupancy_state_zyx` | `[Z,H,W]`, unknown=0, free=1, occupied=2 |
| `voxel_sensor_range_count_zyx` | `[Z,H,W]`, auxiliary range observations |
| `observed_free_mask`, `obstacle_mask`, `unknown_mask` | `[H,W]` navigation observations |
| `agent_rc` | `[2]`, current row and column for 2D ray casting |
| `agent_yaw_deg` | Optional scalar, defaults to zero |
| `voxel_occupancy_z_min_m`, `voxel_occupancy_z_max_m` | Vertical storage bounds |
| `voxel_occupancy_z_resolution_m` | 0.05 m |
| `voxel_occupancy_active_z_min_m`, `voxel_occupancy_active_z_max_m` | Ground-to-upper-structure interval |

The XY resolution is 0.05 m. Learned replay requires a trained checkpoint and
valid input metadata. Failure to load weights or incompatible preprocessing is
an error rather than a switch to geometric-only results.

## Training and evaluation

```bash
voxroom-train --help
python scripts/evaluate_paper.py --help
```

Training configuration: [configs/paper_training.yaml](configs/paper_training.yaml).
The development split is 16 training scenes and 4 disjoint validation
scenes, with 8/8 and 2/2 InteriorAgent/GRScene scenes respectively. Scene assets,
annotations, scene splits, and collected candidate manifests are inputs to
training. See the method
documentation for the training command and exact defaults.

The paper evaluator uses the observed SFM domain, retains disconnected fragments
of a ground-truth room under one identity, and aggregates stages → trajectories →
scenes. It checks completeness of the stated test protocol unless an incomplete
diagnostic report is explicitly requested.

## Simulation and real-world inputs

The simulator runtime is retained under `voxroom_online/isaac_runtime`. Full
online collection requires Isaac Sim, nvblox, and separately obtained scene
assets; configure their paths in `configs/voxroom_online.yaml`. The portable
replay and training paths do not require launching Isaac Sim.

The robot pipeline uses FAST-LIO2 poses and OctoMap occupancy in a gravity-aligned
frame. See [real-robot setup](docs/real_robot.md) for dependencies and launch
commands.

## Videos and local project page

```bash
python -m http.server 8000 --directory site
```

Open `http://localhost:8000`. Both videos and all page assets are local. The page
has no analytics, remote fonts, embeds, or author-account links.

Inline playback uses images sampled from the original silent videos at 12 fps;
the original MP4 and WebM files are also available from each player. The source
ZIP includes the original videos and omits the generated image sheets. Rebuild
the sheets with `python scripts/build_video_playback.py` before previewing the
website from that ZIP (requires FFmpeg and Pillow).

## Attribution

Third-party provenance and required notices are retained in
[THIRD_PARTY.md](THIRD_PARTY.md) and [LICENSE](LICENSE). Bibliographic author
metadata for this work is withheld during anonymous review.
