"""Sensor-origin preserving M200 / FAST-LIO2 / OctoMap mapping."""
from pathlib import Path
import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def start(context):
    config_path = Path(LaunchConfiguration("fastlio_config").perform(context))
    config = yaml.safe_load(config_path.read_text())["/**"]["ros__parameters"]
    extrinsics = config["mapping"]
    sim = ParameterValue(LaunchConfiguration("use_sim_time"), value_type=bool)
    max_range = ParameterValue(LaunchConfiguration("max_range"), value_type=float)
    return [
        Node(package="pacecat_m_series_driver", executable="driver", name="m200_driver",
             condition=IfCondition(LaunchConfiguration("start_driver")),
             parameters=[{"adapter": LaunchConfiguration("adapter"),
                          "lidar_ip": LaunchConfiguration("lidar_ip"),
                          "frame_id": "m200_lidar", "output_custommsg": True,
                          "output_imu": True, "output_pointcloud": False,
                          "topic_custommsg": "/m200/raw_custom", "topic_imu": "/m200/imu_raw",
                          "timemode": 0, "use_sim_time": sim}], output="screen"),
        Node(package="voxroom_robot", executable="m200_input_bridge",
             parameters=[{"use_sim_time": sim, "front_only": False, "max_range": max_range,
                          "acceleration_scale": ParameterValue(LaunchConfiguration("acceleration_scale"), value_type=float)}], output="screen"),
        Node(package="fast_lio", executable="fastlio_mapping", name="laser_mapping",
             parameters=[str(config_path), {"use_sim_time": sim}], output="screen"),
        Node(package="voxroom_robot", executable="body_to_lidar",
             parameters=[{"extrinsic_T": extrinsics["extrinsic_T"],
                          "extrinsic_R": extrinsics["extrinsic_R"], "use_sim_time": sim}], output="screen"),
        Node(package="octomap_server", executable="octomap_server_node", name="octomap_server",
             parameters=[{"frame_id": "camera_init", "base_frame_id": "body", "resolution": .05,
                          "sensor_model.max_range": max_range, "sensor_model.hit": .7,
                          "sensor_model.miss": .3, "sensor_model.min": .01,
                          "sensor_model.max": .99, "filter_ground_plane": False,
                          "filter_speckles": False, "compress_map": True, "use_sim_time": sim}],
             remappings=[("cloud_in", "/m200/points_deskewed")], output="screen"),
        Node(package="voxroom_robot", executable="octomap_snapshot",
             parameters=[{"output_directory": LaunchConfiguration("output_directory"),
                          "use_sim_time": sim}], output="screen"),
    ]


def generate_launch_description():
    default_config = Path(get_package_share_directory("voxroom_robot")) / "config/fastlio_m200.yaml"
    return LaunchDescription([
        DeclareLaunchArgument("fastlio_config", default_value=str(default_config)),
        DeclareLaunchArgument("start_driver", default_value="false"),
        DeclareLaunchArgument("adapter", default_value="eth0"),
        DeclareLaunchArgument("lidar_ip", default_value="0.0.0.0", description="sensor address when start_driver is true"),
        DeclareLaunchArgument("acceleration_scale", default_value="9.80665", description="scale raw acceleration from g to m/s²; use 1 for SI input"),
        DeclareLaunchArgument("max_range", default_value="5.0"),
        DeclareLaunchArgument("output_directory", default_value="robot_outputs/observations"),
        DeclareLaunchArgument("use_sim_time", default_value="false"),
        OpaqueFunction(function=start),
    ])
