#include <m200_fastlio_octomap/core.hpp>
#include <iostream>
#include <stdexcept>
#include <cmath>
void check(bool ok, const char *what) { if (!ok) throw std::runtime_error(what); }
void close(double a, double b) { check(std::abs(a-b)<1.e-8,"numeric mismatch"); }
int main() {
  using namespace m200;
  const Vec3 t{-0.0178,0.0049,0.0383};
  validate_extrinsic(identity,t);
  Vec3 p{1.2,-2.3,3.4};
  auto pi=lidar_to_imu(p,identity,t);
  auto back=imu_to_lidar(pi,identity,t);
  for(int i=0;i<3;++i) close(back[i],p[i]);
  auto origin=imu_to_lidar(t,identity,t);
  for(double a:origin) close(a,0.0);
  const Mat3 rot{0,-1,0,1,0,0,0,0,1};
  validate_extrinsic(rot,t);
  back=imu_to_lidar(lidar_to_imu(p,rot,t),rot,t);
  for(int i=0;i<3;++i) close(back[i],p[i]);
  bool rejected=false;
  try { validate_extrinsic(Mat3{-1,0,0,0,1,0,0,0,1},t); } catch(...) { rejected=true; }
  check(rejected,"Reflection must be rejected");
  ClockMapper rebase(true);
  constexpr std::int64_t d=58467061000000LL, h=1788670000000000000LL;
  close(double(rebase.map(d,h)-h),0);
  check(rebase.map(d+10000000,h+95000000)==h+10000000,"Receive jitter changed sensor timing");
  check(rebase.map(d+100530117,h+500000000)==h+100530117,"Pointcloud clock offset differs from IMU");
  ClockMapper preserve(false);
  check(preserve.map(d,h)==d,"Preserve mode changed sensor time");
  close(point_offset_ms(100530117),100.530117);
  close(1.0*standard_gravity,9.80665);
  std::cout<<"PASS: rigid transform, optical origin, rotation validation, common clock, ns->ms, g scale.\n";
}
