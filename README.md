# VoxRoom

**Room Segmentation from Partial Observations during Robot Exploration**

[Project page and videos](site/index.html) · [Method](docs/method.md) ·
[Evaluation](docs/evaluation.md) · [Real robot](docs/real_robot.md)

On Anonymous GitHub, open the repository's GitHub Pages link to view the project page.

VoxRoom segments rooms from the observations collected during robot exploration.
It builds a Structural Free Map (SFM), combines 3D column evidence with 2D
ray-casting entry candidates, verifies candidates with a dual-branch network,
and fits separators to partition the observed free space. A separate Nav-Free
Map supports navigation and coverage measurement.

At each update, candidates and separators are computed from the current
accumulated voxel observations. Separators from previous updates are discarded.
Simulation, replay, and real-robot inputs use the same segmentation core.

## Install and try the geometry pipeline

Use Python 3.11 or newer. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[learning,test]'
voxroom-replay --demo --rules-only --output outputs/smoke
pytest -q
```

This runs a generated two-room example without a simulator or scene assets.
`--rules-only` skips the learned verifier. The output contains room labels,
the SFM evaluation domain, separators, and a JSON summary.

## Replay with the learned verifier

```bash
voxroom-replay --snapshot data/roomseg_step_000100.npz \
  --checkpoint checkpoints/entry_seed_verifier.pt --device cpu \
  --output outputs/replay
```

For a trajectory on a fixed grid, use
`--sequence data/trajectory/roomseg_snapshots`. Replay processes zero-padded
`roomseg_step_*.npz` files in order and computes segmentation for each snapshot.
Each NPZ contains:

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

The XY resolution is 0.05 m. Learned inference requires a trained checkpoint
with matching architecture and preprocessing.

## Training and evaluation

```bash
voxroom-train --help
python scripts/evaluate_paper.py --help
```

[Training instructions](docs/method.md#entry-seed-verifier-and-training) use the
settings in [configs/paper_training.yaml](configs/paper_training.yaml). The paper
uses 16 training scenes and 4 validation scenes: 8/8 and 2/2
InteriorAgent/GRScene scenes, respectively.

The [evaluator](docs/evaluation.md) scores the observed SFM domain and averages
stages within trajectories, trajectories within scenes, and scenes equally.
Ground-truth room identities are preserved across disconnected visible fragments.

This release includes the implementation, configurations, and evaluation tools.
The trained checkpoint, exact scene lists, candidate annotations, shared test
trajectories, and raw experiment data are not included. Scene assets must be
obtained separately. The website reports results from the paper; reproducing
those tables requires these experiment inputs. The released verifier uses
PyTorch; the TensorRT FP16 deployment used for the paper's timing measurements
is not included.

## Simulation and robot inputs

The simulator runtime is in `voxroom_online/isaac_runtime`. Online collection
uses Isaac Sim, nvblox, and scene assets configured in
`configs/voxroom_online.yaml`. Replay and training can run independently of
Isaac Sim.

The robot pipeline uses FAST-LIO2 poses and OctoMap occupancy in a
gravity-aligned frame. See [robot setup](docs/real_robot.md) for dependencies
and launch commands.

## License and attribution

See [LICENSE](LICENSE) and [THIRD_PARTY.md](THIRD_PARTY.md) for the project
license and third-party notices.
