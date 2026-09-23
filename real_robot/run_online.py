#!/usr/bin/env python3
"""Process causal OctoMap observations with the repository's shared VoxRoom core."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import time

import numpy as np

from snapshot_adapter import ObservationGate, prepare_observation


class SegmentStream:
    def __init__(self, args, exporter):
        from voxroom_online.isaac_runtime.config import load_config
        config = load_config(args.config)
        self.config = dict(config.mapping.room_segmentation)
        self.config["door_seed_learning"] = dict(self.config["door_seed_learning"])
        self.config["door_seed_learning"].update(
            mode="inference", checkpoint_path=str(args.checkpoint.resolve()), device=args.device,
            keep_threshold=.5, keep_uninformative_seed=False, fallback_to_rule_seed_on_error=False,
        )
        if not args.checkpoint.is_file():
            raise ValueError("a compatible trained Entry-Seed Verifier checkpoint is required")
        self.args, self.exporter = args, exporter
        self.segmenter = None
        self.grid_identity = None
        self.step = 0
        self.gate = ObservationGate(2.0)
        args.output.mkdir(parents=True, exist_ok=True)

    def process(self, observation_directory):
        from voxroom_online.isaac_runtime.mapping.voxel_occupancy_door_wall_roomseg import VoxelOccupancyDoorWallRoomSegmenter
        directory = Path(observation_directory)
        observation = json.loads((directory / "observation.json").read_text())
        started = time.monotonic()
        stamp = int(observation["stamp_ns"])
        if not self.gate.consume(stamp, started):
            return None
        destination = self.args.output / str(stamp)
        destination.mkdir(exist_ok=False)
        dense = destination / "dense"
        subprocess.run([str(self.exporter), str(directory / "map.ot"), str(self.args.floor_z),
                        str(dense), *map(str, self.args.bounds)], check=True,
                       stdout=subprocess.DEVNULL)
        grid, nav, rc, yaw, metadata = prepare_observation(
            dense, observation, self.config, self.args.ceiling_height,
        )
        identity = (tuple(grid.state.shape), tuple(metadata["map_bounds_xyxy_m"]), metadata["floor_z_in_room_map_m"])
        if self.grid_identity is not None and self.grid_identity != identity:
            raise ValueError("grid or ground reference changed during a sequence")
        self.grid_identity = identity
        if self.segmenter is None:
            self.segmenter = VoxelOccupancyDoorWallRoomSegmenter(self.config, grid.map_info)
        self.segmenter.update(occupancy_map=nav.occupied, observed_free_mask=nav.free,
                              obstacle_mask=nav.occupied, unknown_mask=nav.unknown,
                              voxel_grid=grid, step=self.step, agent_rc=rc, agent_yaw_deg=yaw)
        result = self.segmenter.last_result
        if result is None:
            raise RuntimeError("segmentation produced no result")
        labels = np.asarray(result.layers["voxel_vertical_free_partition_room_label_map"], dtype=np.int32)
        np.savez_compressed(destination / "rooms.npz", labels=labels,
                            nav_labels=np.asarray(result.room_label_map, dtype=np.int32),
                            evaluation_domain=result.layers["voxel_vertical_free_xy"],
                            separators=result.separator_map, stamp_ns=np.int64(stamp),
                            agent_rc=rc, map_bounds_xyxy_m=np.asarray(metadata["map_bounds_xyxy_m"]))
        report = dict(stamp_ns=stamp, step=self.step, scheduled_rate_hz=.5,
                      processing_seconds=time.monotonic() - started,
                      room_count=int(np.unique(labels[labels > 0]).size),
                      ceiling_height_m=grid.ceiling_height_m,
                      active_z_max_m=grid.active_z_max_m)
        (destination / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
        self.step += 1
        return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/voxroom_online.yaml"))
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--floor-z", type=float, required=True, help="ground height in the gravity-aligned mapping frame")
    parser.add_argument("--ceiling-height", type=float, help="optional known ceiling height above ground")
    parser.add_argument("--bounds", type=float, nargs=4, required=True, metavar=("XMIN", "YMIN", "XMAX", "YMAX"), help="fixed voxel-aligned world bounds covering the mapping area")
    parser.add_argument("--output", type=Path, default=Path("robot_outputs/segmentation"))
    parser.add_argument("--observation", type=Path, help="process one saved observation instead of subscribing")
    parser.add_argument("--exporter", type=Path, help="override path to the compiled OctoMap exporter")
    args, ros_args = parser.parse_known_args()
    if not np.isfinite(args.floor_z) or not np.isfinite(args.bounds).all():
        parser.error("floor and bounds must be finite")
    if args.exporter:
        exporter = args.exporter
    else:
        from ament_index_python.packages import get_package_prefix
        exporter = Path(get_package_prefix("voxroom_robot")) / "lib/voxroom_robot/octomap_export_voxroom"
    stream = SegmentStream(args, exporter)
    if args.observation:
        print(stream.process(args.observation))
        return
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
    rclpy.init(args=ros_args)

    class OnlineNode(Node):
        def __init__(self):
            super().__init__("voxroom_online")
            self.latest = None
            self.subscription = self.create_subscription(String, "/voxroom/observation", self.receive, 1)
            self.publisher = self.create_publisher(String, "/voxroom/result", 1)
            self.timer = self.create_timer(.1, self.tick)

        def receive(self, message):
            self.latest = message.data

        def tick(self):
            if self.latest is None:
                return
            result = stream.process(self.latest)
            if result is not None:
                notification = String()
                notification.data = str(result / "rooms.npz")
                self.publisher.publish(notification)

    node = OnlineNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
