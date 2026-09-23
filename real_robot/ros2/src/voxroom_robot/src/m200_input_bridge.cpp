#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <std_msgs/msg/string.hpp>
#include <pacecat_m_series_inter/msg/custom_msg.hpp>
#include <livox_ros_driver2/msg/custom_msg.hpp>
#include <m200_fastlio_octomap/core.hpp>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <sstream>
#include <chrono>

class InputBridge final : public rclcpp::Node {
  using Pace = pacecat_m_series_inter::msg::CustomMsg;
  using Livox = livox_ros_driver2::msg::CustomMsg;
  using Imu = sensor_msgs::msg::Imu;
 public:
  InputBridge(): Node("m200_input_bridge"),
      mapper_(declare_parameter<bool>("rebase_timestamps", true)) {
    lidar_frame_=declare_parameter<std::string>("lidar_frame", "m200_lidar");
    imu_frame_=declare_parameter<std::string>("imu_frame", "body");
    acceleration_scale_=declare_parameter<double>("acceleration_scale", 9.80665);
    blind_=declare_parameter<double>("blind", 0.20);
    max_range_=declare_parameter<double>("max_range", 0.0);  // Zero disables the upper bound in standalone use.
    max_scan_gap_=declare_parameter<double>("max_scan_gap", 0.5);
    front_only_=declare_parameter<bool>("front_only", false);
    auto lidar_in=declare_parameter<std::string>("lidar_in", "/m200/raw_custom");
    auto imu_in=declare_parameter<std::string>("imu_in", "/m200/imu_raw");
    auto lidar_out=declare_parameter<std::string>("lidar_out", "/livox/lidar");
    auto imu_out=declare_parameter<std::string>("imu_out", "/livox/imu");
    if (!std::isfinite(acceleration_scale_) || acceleration_scale_<=0 || !std::isfinite(blind_) || blind_<0 ||
        !std::isfinite(max_scan_gap_) || max_scan_gap_<=0 || !std::isfinite(max_range_) || max_range_<0 ||
        (max_range_>0 && max_range_<=blind_))
      throw std::invalid_argument("Invalid scale or blind radius");
    // The pinned FAST-LIO Livox and IMU subscriptions request RELIABLE QoS.
    cloud_pub_=create_publisher<Livox>(lidar_out, rclcpp::QoS(20).reliable());
    imu_pub_=create_publisher<Imu>(imu_out, rclcpp::QoS(1000).reliable());
    clock_pub_=create_publisher<std_msgs::msg::String>("/m200/clock_observation", rclcpp::SensorDataQoS().keep_last(1000));
    scan_time_pub_=create_publisher<std_msgs::msg::String>("/m200/scan_timing", rclcpp::SensorDataQoS().keep_last(100));
    cloud_sub_=create_subscription<Pace>(lidar_in, rclcpp::SensorDataQoS().keep_last(20),
        [this](Pace::ConstSharedPtr m){ cloud(*m); });
    imu_sub_=create_subscription<Imu>(imu_in, rclcpp::SensorDataQoS().keep_last(1000),
        [this](Imu::ConstSharedPtr m){ imu(*m); });
    RCLCPP_INFO(get_logger(), "Acceleration scale %.8f; supply device-time cloud AND IMU (timemode=0).", acceleration_scale_);
    RCLCPP_INFO(get_logger(), "LiDAR horizontal field: %s", front_only_ ? "front 180 deg, m200_lidar +X, azimuth [-90,+90]" : "full 360 deg");
    RCLCPP_INFO(get_logger(), "LiDAR maximum Euclidean range: %.3f m (0 means unlimited)", max_range_);
  }
 private:
  static std::int64_t stamp_ns(const builtin_interfaces::msg::Time &s) {
    return std::int64_t(s.sec)*1000000000LL+s.nanosec;
  }
  static builtin_interfaces::msg::Time stamp_msg(std::int64_t ns) {
    if (ns<0 || ns/1000000000LL>std::numeric_limits<std::int32_t>::max())
      throw std::out_of_range("Timestamp outside builtin_interfaces/Time range");
    builtin_interfaces::msg::Time s;
    s.sec=static_cast<std::int32_t>(ns/1000000000LL);
    s.nanosec=static_cast<std::uint32_t>(ns%1000000000LL);
    return s;
  }
  bool monotonic(std::int64_t t, std::optional<std::int64_t> &last, const char *name) {
    if (last && t<*last) {
      RCLCPP_FATAL(get_logger(), "%s timestamp went backwards. Restart the WHOLE mapping session; do not mix epochs.", name);
      rclcpp::shutdown();
      return false;
    }
    if (last && t==*last) return false;  // discard duplicate
    last=t;
    return true;
  }
  std::optional<std::int64_t> mapped(std::int64_t t) {
    try { return mapper_.map(t, now().nanoseconds()); }
    catch (const std::exception &e) {
      RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 3000, "%s", e.what());
      return std::nullopt;
    }
  }
  void cloud(const Pace &in) {
    const auto raw=stamp_ns(in.header.stamp);
    if (raw<0 || std::uint64_t(raw)!=in.timebase || in.point_num!=in.points.size()) {
      RCLCPP_ERROR_THROTTLE(get_logger(), *get_clock(), 3000,
          "Invalid CustomMsg: require header==timebase and point_num==points.size(). Dropped.");
      return;
    }
    if (!monotonic(raw,last_cloud_,"LiDAR")) return;
    auto t=mapped(raw);
    if (!t) return;
    Livox out;
    out.header=in.header;
    out.header.frame_id=lidar_frame_;
    out.header.stamp=stamp_msg(*t);
    out.timebase=static_cast<std::uint64_t>(*t);
    out.lidar_id=in.lidar_id;
    out.rsvd={0,0,0};
    out.points.reserve(in.points.size());
    std::uint32_t last_offset=0;
    for (const auto &p:in.points) {
      // Pacecat SDK PacketToPoints marks optical-cover returns with bit 7;
      // OutlierFilter uses bit 6. Neither is a Livox tag or a corrupt frame.
      if (p.line!=0 || (p.tag & 0x3fU)!=0 || p.offset_time<last_offset || p.offset_time>200000000U) {
        RCLCPP_ERROR_THROTTLE(get_logger(), *get_clock(), 3000,
            "Invalid point: line=%u tag=0x%02x offset_ns=%u previous_ns=%u; frame dropped.",
            unsigned(p.line), unsigned(p.tag), p.offset_time, last_offset);
        return;
      }
      last_offset=p.offset_time;
      if (p.tag & 0xc0U) continue;
      const double r2=double(p.x)*p.x+double(p.y)*p.y+double(p.z)*p.z;
      if (!std::isfinite(r2) || r2<=blind_*blind_) continue;
      if (max_range_>0 && r2>max_range_*max_range_) continue;
      // Filter in the original sensor frame, before FAST-LIO deskew/registration.
      // +X is device azimuth zero; keep both +/-90-degree boundary rays.
      if (front_only_ && p.x<0.f) continue;
      livox_ros_driver2::msg::CustomPoint q;
      q.x=p.x; q.y=p.y; q.z=p.z;
      q.reflectivity=p.reflectivity; q.tag=p.tag; q.line=p.line;
      // Keep ORIGINAL frame reference; never subtract first surviving offset.
      q.offset_time=p.offset_time;
      out.points.push_back(q);
    }
    if (out.points.size()<10 || last_offset==0) {
      RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 3000, "Too few valid points / no per-point time; dropped.");
      return;
    }
    if (last_published_cloud_ && (raw-*last_published_cloud_)*1.e-9>max_scan_gap_) {
      RCLCPP_FATAL(get_logger(), "Valid LiDAR scans interrupted for %.3f s (limit %.3f s). "
                   "Tracking continuity is lost; restart the mapping session.",
                   (raw-*last_published_cloud_)*1.e-9, max_scan_gap_);
      rclcpp::shutdown();
      return;
    }
    out.point_num=static_cast<std::uint32_t>(out.points.size());
    cloud_pub_->publish(out);
    std::ostringstream timing;
    timing << "{\"start_ns\":" << *t << ",\"end_ns\":" << *t+out.points.back().offset_time
           << ",\"raw_start_ns\":" << raw << ",\"points\":" << out.point_num << "}";
    std_msgs::msg::String scan_time;
    scan_time.data=timing.str();
    scan_time_pub_->publish(scan_time);
    last_published_cloud_=raw;
  }
  void imu(const Imu &in) {
    const auto receipt_ns=now().nanoseconds();
    const auto steady_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
    const auto raw=stamp_ns(in.header.stamp);
    if (!monotonic(raw,last_imu_,"IMU")) return;
    auto t=mapped(raw);
    if (!t) return;
    Imu out=in;
    out.header.stamp=stamp_msg(*t);
    out.header.frame_id=imu_frame_;
    out.linear_acceleration.x*=acceleration_scale_;
    out.linear_acceleration.y*=acceleration_scale_;
    out.linear_acceleration.z*=acceleration_scale_;
    if (out.linear_acceleration_covariance[0]>=0)
      for (auto &v:out.linear_acceleration_covariance) v*=acceleration_scale_*acceleration_scale_;
    // No attitude estimator in this bridge; orientation is deliberately unavailable.
    out.orientation.x=out.orientation.y=out.orientation.z=0.0;
    out.orientation.w=1.0;
    out.orientation_covariance.fill(0.0);
    out.orientation_covariance[0]=-1.0;
    const double vals[]={out.linear_acceleration.x,out.linear_acceleration.y,out.linear_acceleration.z,
                         out.angular_velocity.x,out.angular_velocity.y,out.angular_velocity.z};
    for (double v:vals) if (!std::isfinite(v)) return;
    imu_pub_->publish(out);
    // Observe the shared clock without changing FAST-LIO timestamps or point offsets.
    // This is callback receipt time, not a measured physical acquisition time.
    if (!get_parameter("use_sim_time").as_bool()) {
      std::ostringstream data;
      data << "{\"device_ns\":" << raw << ",\"lio_ns\":" << *t
           << ",\"host_ns\":" << receipt_ns << ",\"steady_ns\":" << steady_ns << "}";
      std_msgs::msg::String observation;
      observation.data=data.str();
      clock_pub_->publish(observation);
    }
  }
  m200::ClockMapper mapper_;
  std::string lidar_frame_,imu_frame_;
  double acceleration_scale_,blind_,max_range_,max_scan_gap_;
  bool front_only_;
  std::optional<std::int64_t> last_cloud_,last_imu_,last_published_cloud_;
  rclcpp::Publisher<Livox>::SharedPtr cloud_pub_;
  rclcpp::Publisher<Imu>::SharedPtr imu_pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr clock_pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr scan_time_pub_;
  rclcpp::Subscription<Pace>::SharedPtr cloud_sub_;
  rclcpp::Subscription<Imu>::SharedPtr imu_sub_;
};
int main(int argc,char **argv) {
  rclcpp::init(argc,argv);
  try { rclcpp::spin(std::make_shared<InputBridge>()); }
  catch (const std::exception &e) { RCLCPP_FATAL(rclcpp::get_logger("m200_input_bridge"),"%s",e.what()); rclcpp::shutdown(); return 1; }
  if (rclcpp::ok()) rclcpp::shutdown();
  return 0;
}
