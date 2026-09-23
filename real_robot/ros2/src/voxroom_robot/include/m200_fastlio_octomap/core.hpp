#pragma once
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <optional>
#include <stdexcept>

namespace m200 {
using Vec3 = std::array<double, 3>;
using Mat3 = std::array<double, 9>;  // row-major, p_I = R_IL * p_L + t_IL
inline constexpr double standard_gravity = 9.80665;
inline constexpr Mat3 identity{1,0,0,0,1,0,0,0,1};
inline double point_offset_ms(std::uint32_t ns) { return ns / 1.e6; }
inline Vec3 lidar_to_imu(const Vec3 &p, const Mat3 &r, const Vec3 &t) {
  Vec3 v{};
  for (int i=0; i<3; ++i) {
    v[i]=t[i];
    for (int j=0; j<3; ++j) v[i]+=r[i*3+j]*p[j];
  }
  return v;
}
inline Vec3 imu_to_lidar(const Vec3 &p, const Mat3 &r, const Vec3 &t) {
  Vec3 v{};
  for (int i=0; i<3; ++i)
    for (int j=0; j<3; ++j) v[i]+=r[j*3+i]*(p[j]-t[j]);
  return v;
}
inline void validate_extrinsic(const Mat3 &r, const Vec3 &t) {
  for (double x:t) if (!std::isfinite(x)) throw std::invalid_argument("Non-finite extrinsic T");
  for (double x:r) if (!std::isfinite(x)) throw std::invalid_argument("Non-finite extrinsic R");
  for (int i=0; i<3; ++i) for (int j=0; j<3; ++j) {
    double d=0;
    for (int k=0; k<3; ++k) d+=r[i*3+k]*r[j*3+k];
    if (std::abs(d-(i==j ? 1.0 : 0.0))>1.e-5)
      throw std::invalid_argument("Extrinsic R is not orthonormal");
  }
  const double det=r[0]*(r[4]*r[8]-r[5]*r[7])-r[1]*(r[3]*r[8]-r[5]*r[6])+r[2]*(r[3]*r[7]-r[4]*r[6]);
  if (std::abs(det-1.0)>1.e-5) throw std::invalid_argument("Extrinsic R must have det=+1");
}
// ONE shared device->ROS epoch offset, never a new receive timestamp per message.
class ClockMapper {
 public:
  explicit ClockMapper(bool rebase): rebase_(rebase) {}
  std::int64_t map(std::int64_t device_ns, std::int64_t ros_now_ns) {
    if (device_ns<0) throw std::invalid_argument("Negative device time");
    if (!offset_) {
      if (rebase_ && ros_now_ns<=0) throw std::runtime_error("Waiting for ROS clock");
      offset_=rebase_ ? ros_now_ns-device_ns : 0;
    }
    if (*offset_>0 && device_ns>std::numeric_limits<std::int64_t>::max()-*offset_)
      throw std::overflow_error("Timestamp overflow");
    auto result=device_ns+*offset_;
    if (result<0) throw std::runtime_error("Timestamp maps before ROS epoch");
    return result;
  }
 private:
  bool rebase_;
  std::optional<std::int64_t> offset_;
};
}  // namespace m200
