#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <sensor_msgs/point_cloud2_iterator.hpp>
#include <geometry_msgs/msg/transform_stamped.hpp>
#include <tf2_ros/static_transform_broadcaster.h>
#include <tf2/LinearMath/Matrix3x3.h>
#include <tf2/LinearMath/Quaternion.h>
#include <m200_fastlio_octomap/core.hpp>
#include <algorithm>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

class BodyToLidar final: public rclcpp::Node {
 public:
  BodyToLidar(): Node("body_to_lidar") {
    body_=declare_parameter<std::string>("body_frame","body");
    lidar_=declare_parameter<std::string>("lidar_frame","m200_lidar");
    auto t=declare_parameter<std::vector<double>>("extrinsic_T",{-0.0178,0.0049,0.0383});
    auto r=declare_parameter<std::vector<double>>("extrinsic_R",{1.,0.,0.,0.,1.,0.,0.,0.,1.});
    if (t.size()!=3 || r.size()!=9 || body_==lidar_)
      throw std::invalid_argument("Bad extrinsic dimensions or equal frame names");
    std::copy(t.begin(),t.end(),t_.begin());
    std::copy(r.begin(),r.end(),r_.begin());
    m200::validate_extrinsic(r_,t_);
    auto input=declare_parameter<std::string>("input","/cloud_registered_body");
    auto output=declare_parameter<std::string>("output","/m200/points_deskewed");
    static_tf_=std::make_unique<tf2_ros::StaticTransformBroadcaster>(*this);
    geometry_msgs::msg::TransformStamped tf;
    tf.header.stamp=now(); tf.header.frame_id=body_; tf.child_frame_id=lidar_;
    tf.transform.translation.x=t_[0]; tf.transform.translation.y=t_[1]; tf.transform.translation.z=t_[2];
    tf2::Matrix3x3 rotation(r_[0],r_[1],r_[2],r_[3],r_[4],r_[5],r_[6],r_[7],r_[8]);
    tf2::Quaternion q; rotation.getRotation(q); q.normalize();
    tf.transform.rotation.x=q.x(); tf.transform.rotation.y=q.y();
    tf.transform.rotation.z=q.z(); tf.transform.rotation.w=q.w();
    static_tf_->sendTransform(tf);
    pub_=create_publisher<sensor_msgs::msg::PointCloud2>(output,rclcpp::QoS(10).reliable());
    sub_=create_subscription<sensor_msgs::msg::PointCloud2>(input,rclcpp::SensorDataQoS().keep_last(10),
        [this](sensor_msgs::msg::PointCloud2::ConstSharedPtr m){ callback(*m); });
  }
 private:
  void callback(const sensor_msgs::msg::PointCloud2 &in) {
    if (in.header.frame_id!=body_ || in.is_bigendian || in.height!=1 ||
        in.point_step==0 || in.row_step!=std::uint64_t(in.width)*in.point_step ||
        in.data.size()!=std::uint64_t(in.row_step)*in.height) {
      RCLCPP_ERROR_THROTTLE(get_logger(),*get_clock(),3000,"Unexpected frame/layout; expected pinned FAST-LIO body cloud. Dropped.");
      return;
    }
    for (const char *name:{"x","y","z"}) {
      auto it=std::find_if(in.fields.begin(),in.fields.end(),[&](const auto &f){return f.name==name;});
      if (it==in.fields.end() || it->datatype!=sensor_msgs::msg::PointField::FLOAT32 ||
          it->count!=1 || it->offset+sizeof(float)>in.point_step) {
        RCLCPP_ERROR(get_logger(),"Expected valid FLOAT32 x/y/z fields"); return;
      }
    }
    auto out=in;
    sensor_msgs::PointCloud2Iterator<float> x(out,"x"), y(out,"y"), z(out,"z");
    for (;x!=x.end();++x,++y,++z) {
      const auto p=m200::imu_to_lidar({double(*x),double(*y),double(*z)},r_,t_);
      *x=static_cast<float>(p[0]); *y=static_cast<float>(p[1]); *z=static_cast<float>(p[2]);
    }
    // Coordinates have ACTUALLY been transformed; stamp remains frame-end time.
    out.header.frame_id=lidar_;
    pub_->publish(out);
  }
  std::string body_,lidar_;
  m200::Mat3 r_{}; m200::Vec3 t_{};
  std::unique_ptr<tf2_ros::StaticTransformBroadcaster> static_tf_;
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr pub_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr sub_;
};
int main(int argc,char **argv) {
  rclcpp::init(argc,argv);
  try { rclcpp::spin(std::make_shared<BodyToLidar>()); }
  catch (const std::exception &e) { RCLCPP_FATAL(rclcpp::get_logger("body_to_lidar"),"%s",e.what()); rclcpp::shutdown(); return 1; }
  if (rclcpp::ok()) rclcpp::shutdown();
  return 0;
}
