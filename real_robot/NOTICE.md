# Component notices

The M200 input bridge, body-to-LiDAR transform, clock helpers, and OctoMap
exporter retain the MIT notice in [LICENSE](LICENSE). The robot interface
imports the VoxRoom model and segmentation code from the repository root.

External dependencies retain their respective licenses:

| Component | Source |
| --- | --- |
| FAST-LIO ROS 2 | [Ericsii/FAST_LIO_ROS2](https://github.com/Ericsii/FAST_LIO_ROS2), deployment reference `2fffc570a25d0df172720bac034fbdb6a13d2162`, GPL-2.0 |
| ikd-Tree | FAST-LIO submodule; initialize the pinned submodules and retain their notices |
| M-Series driver and interfaces | [BlueSeaLidar/m-series](https://github.com/BlueSeaLidar/m-series), deployment reference `f61d31302f2cbbea5e2b19da7d97f52c30392fd3`; distributed separately under upstream terms |
| Livox ROS message definitions | [Livox-SDK/livox_ros_driver2](https://github.com/Livox-SDK/livox_ros_driver2); external message dependency, not the sensing device |
| OctoMap and ROS 2 octomap_server | [OctoMap](https://github.com/OctoMap/octomap) and [octomap_mapping](https://github.com/OctoMap/octomap_mapping) |

Install the drivers, SLAM packages, and hardware SDKs from their upstream
projects. Recordings and map data are supplied separately.
