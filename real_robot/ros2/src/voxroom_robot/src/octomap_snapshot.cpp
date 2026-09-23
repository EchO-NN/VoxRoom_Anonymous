// Causal 0.5 Hz hand-off from full probabilistic OctoMap to the shared VoxRoom core.
#include <rclcpp/rclcpp.hpp>
#include <octomap_msgs/msg/octomap.hpp>
#include <octomap_msgs/conversions.h>
#include <octomap/OcTree.h>
#include <std_msgs/msg/string.hpp>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <memory>
#include <sstream>
#include <cmath>

class OctomapSnapshot : public rclcpp::Node {
 public:
  OctomapSnapshot() : Node("voxroom_octomap_snapshot") {
    output_ = declare_parameter<std::string>("output_directory", "robot_outputs/observations");
    sensor_frame_ = declare_parameter<std::string>("sensor_frame", "m200_lidar");
    const auto topic = declare_parameter<std::string>("octomap_topic", "/octomap_full");
    std::filesystem::create_directories(output_);
    buffer_ = std::make_unique<tf2_ros::Buffer>(get_clock());
    listener_ = std::make_shared<tf2_ros::TransformListener>(*buffer_);
    publisher_ = create_publisher<std_msgs::msg::String>("/voxroom/observation", rclcpp::QoS(1).reliable());
    subscription_ = create_subscription<octomap_msgs::msg::Octomap>(topic,
        rclcpp::QoS(1).reliable().transient_local(),
        [this](octomap_msgs::msg::Octomap::ConstSharedPtr message) { latest_ = message; });
    timer_ = create_wall_timer(std::chrono::seconds(2), [this]() { export_latest(); });
  }
 private:
  void export_latest() {
    auto message = latest_;
    if (!message) return;
    const auto stamp = rclcpp::Time(message->header.stamp);
    if (stamp.nanoseconds() <= last_stamp_) return;
    try {
      if (message->binary || std::abs(message->resolution - .05) > 1.e-8)
        throw std::runtime_error("Require full probabilistic OctoMap at 0.05 m");
      const auto pose = buffer_->lookupTransform(message->header.frame_id, sensor_frame_,
          stamp, rclcpp::Duration::from_seconds(.2));
      std::unique_ptr<octomap::AbstractOcTree> tree(octomap_msgs::fullMsgToMap(*message));
      if (!dynamic_cast<octomap::OcTree *>(tree.get()))
        throw std::runtime_error("Expected an OcTree message");
      const auto name = std::to_string(stamp.nanoseconds());
      const auto destination = std::filesystem::absolute(output_) / name;
      const auto temporary = std::filesystem::absolute(output_) / (name + ".tmp");
      if (std::filesystem::exists(destination) || std::filesystem::exists(temporary))
        throw std::runtime_error("Observation output already exists; choose a fresh session directory");
      std::filesystem::create_directories(temporary);
      if (!tree->write((temporary / "map.ot").string()))
        throw std::runtime_error("Cannot write full occupancy tree");
      const auto &p = pose.transform.translation;
      const auto &q = pose.transform.rotation;
      std::ofstream metadata(temporary / "observation.json");
      metadata << std::setprecision(17) << "{\"stamp_ns\":" << stamp.nanoseconds()
          << ",\"sensor_xyz_m\":[" << p.x << ',' << p.y << ',' << p.z << ']'
          << ",\"sensor_xyzw\":[" << q.x << ',' << q.y << ',' << q.z << ',' << q.w << "]}\n";
      metadata.close();
      if (!metadata) throw std::runtime_error("Cannot write observation metadata");
      std::filesystem::rename(temporary, destination);
      std_msgs::msg::String notification;
      notification.data = destination.string();
      publisher_->publish(notification);
      last_stamp_ = stamp.nanoseconds();
    } catch (const std::exception &error) {
      RCLCPP_ERROR(get_logger(), "Snapshot skipped: %s", error.what());
    }
  }
  std::string output_, sensor_frame_;
  int64_t last_stamp_ = -1;
  octomap_msgs::msg::Octomap::ConstSharedPtr latest_;
  std::unique_ptr<tf2_ros::Buffer> buffer_;
  std::shared_ptr<tf2_ros::TransformListener> listener_;
  rclcpp::Subscription<octomap_msgs::msg::Octomap>::SharedPtr subscription_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  try { rclcpp::spin(std::make_shared<OctomapSnapshot>()); }
  catch (const std::exception &error) {
    RCLCPP_FATAL(rclcpp::get_logger("voxroom_octomap_snapshot"), "%s", error.what());
    rclcpp::shutdown(); return 1;
  }
  rclcpp::shutdown(); return 0;
}
