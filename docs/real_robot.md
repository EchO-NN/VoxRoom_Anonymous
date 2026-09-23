# Real-robot setup and usage

The robot path uses **FAST-LIO2 → ROS 2 OctoMap → 0.05 m voxel map → VoxRoom**.
Simulation uses nvblox. Both paths share the repository's SFM construction,
candidate generation, learned verification and room-segmentation code.

## Dependencies and build

Use Ubuntu 24.04 with ROS 2 Jazzy, a C++17 compiler, colcon, OctoMap development
headers, and the root Python package with its trained Entry-Seed Verifier
checkpoint. Install the ROS development packages for `rclcpp`, `rclpy`,
`sensor_msgs`, `geometry_msgs`, `std_msgs`, `tf2_ros`, `octomap_msgs`, and
`octomap_server`. Source the ROS environment before building.

The workspace also requires these external ROS packages:

- `fast_lio` from FAST-LIO ROS 2, with its submodules;
- `pacecat_m_series_inter` and `pacecat_m_series_driver` from the M-Series driver;
- `livox_ros_driver2`, supplying the CustomMsg/CustomPoint interfaces expected by
  FAST-LIO. The M200 remains the physical sensor.

Source locations and deployment reference revisions are in
[the component notices](../real_robot/NOTICE.md). Build these dependencies in
an external overlay and source it. Then, from the repository root:

```bash
python -m pip install -e .
colcon build --base-paths real_robot/ros2/src \
  --build-base real_robot/ros2/build \
  --install-base real_robot/ros2/install \
  --packages-select voxroom_robot
source real_robot/ros2/install/setup.bash
```

Use the Python environment containing both the installed root package and ROS
Python bindings when running the segmentation node.

## Sensor and frame configuration

`real_robot/ros2/src/voxroom_robot/config/fastlio_m200.yaml` supplies the mapping
configuration. LiDAR-to-IMU rotation and translation must describe the actual
mounting. The same extrinsics are passed to FAST-LIO and `body_to_lidar` by the
launch file. Input acceleration uses g by default; set `acceleration_scale:=1.0`
if the driver already supplies m/s².

The input bridge uses one device-to-ROS clock offset for both LiDAR and IMU,
preserves per-point time offsets and rejects reversed sensor time. The
`body_to_lidar` adapter transforms the registered body-frame cloud back into
the LiDAR frame and publishes the corresponding static transform. OctoMap
therefore traces free-space rays from the physical scan origin rather than
from the map origin.

The mapping frame, `camera_init`, must have a gravity-aligned Z axis. Supply the
ground's Z coordinate in that frame with `--floor-z`; this is a calibration
input, not a segmentation parameter. `--ceiling-height` optionally supplies a
ceiling height above that ground. Otherwise the adapter estimates the ceiling
from the occupied-layer peak between 1.8 and 4.0 m in the currently accumulated
voxel evidence, and the shared core updates its active vertical interval.
Unknown voxels remain unknown; only known OctoMap voxels provide observation
support.

## Start mapping

With an independently started driver, provide `/m200/raw_custom` and
`/m200/imu_raw` in the driver's shared device time:

```bash
ros2 launch voxroom_robot mapping.launch.py \
  output_directory:=robot_outputs/observations
```

To start the driver as part of the launch, add `start_driver:=true`,
`adapter:=YOUR_INTERFACE`, and `lidar_ip:=YOUR_SENSOR_ADDRESS`. The launch does
not configure network interfaces. `max_range` defaults to 5.0 m and is passed
consistently to the input bridge and OctoMap. The occupancy resolution is 0.05 m.
For rosbag input, set `use_sim_time:=true` and play the bag with its clock.

The `octomap_snapshot` node samples the latest full probabilistic map every two
seconds and records the sensor pose at the same map timestamp. It publishes
each completed observation directory on `/voxroom/observation`. A full
probabilistic OctoMap is required; a binary occupancy tree discards the original
probability representation.

## Start room segmentation

From the repository root, in another sourced terminal:

```bash
python real_robot/run_online.py \
  --config configs/voxroom_online.yaml \
  --checkpoint checkpoints/entry_seed_verifier.pt \
  --floor-z YOUR_GROUND_Z \
  --bounds XMIN YMIN XMAX YMAX \
  --device cuda:0 --output robot_outputs/segmentation
```

Replace the ground height and bounds with numeric values in metres. Bounds
must be multiples of 0.05 m and cover the mapping area; they stay fixed for the
sequence. Map rows run from maximum to minimum Y, columns from minimum to
maximum X, and height is relative to the specified ground.

The node processes the latest available observation at a scheduled maximum of
0.5 Hz, carries segmentation state forward, and discards repeated or older
timestamps. The verifier uses a fixed score threshold of 0.5. A compatible
checkpoint is required; inference errors do not silently switch to a
rules-only method. Processing time is recorded with every output, so achieved
update rate can be checked on the deployed system.

Each timestamp directory contains:

| File | Contents |
| --- | --- |
| `dense/state.u8`, `dense/grid.json` | Floor-referenced voxel states and grid coordinates |
| `rooms.npz` | SFM room `labels`, separate `nav_labels`, SFM `evaluation_domain`, separators, timestamp and map bounds |
| `summary.json` | Room count, processing time, ceiling estimate and active vertical limit |

`/voxroom/result` publishes the path to each completed `rooms.npz`. These are
SFM room instances; navigation projection is available separately. They are
not globally persistent room-tracking IDs. Record LiDAR, IMU, pose and optional
RGB topics concurrently using the standard ROS bag tools. RGB is not required
by the verifier.

A saved observation can be processed with the same command plus
`--observation PATH_TO_OBSERVATION_DIRECTORY`; this mode needs the compiled
OctoMap exporter but does not start a ROS subscriber.

## Tests

```bash
python -m unittest discover -s real_robot/tests -v
g++ -std=c++17 \
  -Ireal_robot/ros2/src/voxroom_robot/include \
  real_robot/ros2/src/voxroom_robot/test/test_core.cpp \
  -o /tmp/voxroom_robot_core_test
/tmp/voxroom_robot_core_test
```

The Python tests exercise voxel-state preservation, coordinate conversion,
sensor pose validation and rate control. The C++ test covers rigid transforms,
the physical sensor origin, quaternion-compatible rotations, shared clock
offsets, point-time units and acceleration scale.
