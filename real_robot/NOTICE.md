# Component notices

The M200 input bridge, body-to-LiDAR transform, clock/transform helpers and
OctoMap dense exporter are adapted from the existing robot deployment. Their
MIT notice is preserved in [LICENSE](LICENSE). The VoxRoom algorithm is imported
from the repository root; this directory does not contain a separate model or
segmentation implementation.

External dependencies retain their respective licenses:

| Component | Source |
| --- | --- |
| FAST-LIO ROS 2 | [Ericsii/FAST_LIO_ROS2](https://github.com/Ericsii/FAST_LIO_ROS2), deployment reference `2fffc570a25d0df172720bac034fbdb6a13d2162`, GPL-2.0 |
| ikd-Tree | FAST-LIO submodule; initialize the pinned submodules and retain their notices |
| M-Series driver and interfaces | [BlueSeaLidar/m-series](https://github.com/BlueSeaLidar/m-series), deployment reference `f61d31302f2cbbea5e2b19da7d97f52c30392fd3`; distributed separately under upstream terms |
| Livox ROS message definitions | [Livox-SDK/livox_ros_driver2](https://github.com/Livox-SDK/livox_ros_driver2); external message dependency, not the sensing device |
| OctoMap and ROS 2 octomap_server | [OctoMap](https://github.com/OctoMap/octomap) and [octomap_mapping](https://github.com/OctoMap/octomap_mapping) |

No manufacturer driver source, SLAM source, hardware SDK, system binaries,
recordings, or map data are redistributed in this directory.
