# Real-robot integration

This module connects a PACECAT LDS-M200-E LiDAR, FAST-LIO2 and ROS 2 OctoMap to
the shared VoxRoom implementation in the repository root. It includes the
sensor message and clock bridge, sensor-origin transform, probabilistic-map
exporter, and online segmentation entry point.

See [setup and usage](../docs/real_robot.md) and [component notices](NOTICE.md).

```text
ros2/src/voxroom_robot/   ROS 2 adapters, configuration and mapping launch
snapshot_adapter.py      dense-voxel conversion and observation rate control
run_online.py            shared-core inference and room output
tests/                   conversion and rate-control tests
```
