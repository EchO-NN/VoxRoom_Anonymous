// Export a probability OcTree to floor-relative VoxRoom [Z,row(-Y),col(+X)].
#include <octomap/OcTree.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <random>
#include <stdexcept>
#include <vector>

template<class T> void write_binary(const std::filesystem::path &path,const std::vector<T> &data) {
  std::ofstream f(path,std::ios::binary);
  f.write(reinterpret_cast<const char *>(data.data()),data.size()*sizeof(T));
  if (!f) throw std::runtime_error("Cannot write "+path.string());
}

int main(int argc,char **argv) {
  try {
    if (argc!=4 && argc!=8) throw std::runtime_error("usage: octomap_export_voxroom MAP.ot FLOOR_Z OUTPUT_DIR [X_MIN Y_MIN X_MAX Y_MAX]");
    const double floor=std::stod(argv[2]), zmin=-.1, zmax=4.;
    if (!std::isfinite(floor)) throw std::runtime_error("Floor height must be finite");
    const std::filesystem::path output(argv[3]);
    if (std::filesystem::exists(output)) throw std::runtime_error("Output directory already exists");
    std::unique_ptr<octomap::AbstractOcTree> raw(octomap::AbstractOcTree::read(argv[1]));
    auto *tree=dynamic_cast<octomap::OcTree *>(raw.get());
    if (!tree || tree->size()==0) throw std::runtime_error("Expected non-empty full OcTree");
    const double res=tree->getResolution();
    if (std::abs(res-.05)>1.e-8) throw std::runtime_error("Current VoxRoom checkpoint requires 0.05 m voxels");
    double minx,miny,minz,maxx,maxy,maxz;
    tree->getMetricMin(minx,miny,minz); tree->getMetricMax(maxx,maxy,maxz);
    // Metric bounds include each leaf's extent. Integer XY alignment avoids resampling XY.
    int x0=std::llround(minx/res),y0=std::llround(miny/res);
    int x1=std::llround(maxx/res),y1=std::llround(maxy/res);
    if (argc==8) {
      std::array<int,4> limits;
      for (int i=0;i<4;++i) {
        const double cells=std::stod(argv[i+4])/res;
        if (!std::isfinite(cells) || std::abs(cells)>1000000 || std::abs(cells-std::round(cells))>1.e-6)
          throw std::runtime_error("Fixed bounds must be finite and voxel aligned");
        limits[i]=std::llround(cells);
      }
      if (limits[0]>x0 || limits[1]>y0 || limits[2]<x1 || limits[3]<y1)
        throw std::runtime_error("Fixed replay bounds must contain the complete source XY map");
      x0=limits[0];y0=limits[1];x1=limits[2];y1=limits[3];
    }
    const size_t w=x1-x0,h=y1-y0,nz=std::llround((zmax-zmin)/res);
    if (!w || !h || w>10000 || h>10000 || nz*h*w>150000000)
      throw std::runtime_error("Invalid or excessive dense map dimensions");
    std::vector<uint8_t> state(nz*h*w,0);
    std::vector<float> log_odds(state.size(),std::numeric_limits<float>::quiet_NaN());
    size_t pruned=0, source_free=0,source_occupied=0;
    auto zindex=[&](double source_z) {
      return std::clamp(static_cast<int>(std::ceil((source_z-floor-zmin)/res-.5-1.e-8)),0,static_cast<int>(nz));
    };
    for (auto it=tree->begin_leafs();it!=tree->end_leafs();++it) {
      const double size=it.getSize();
      const int count=std::llround(size/res);
      if (count>1) ++pruned;
      const bool occupied=tree->isNodeOccupied(*it);
      occupied ? ++source_occupied : ++source_free;
      const int xb=std::llround((it.getX()-size/2)/res)-x0;
      const int yb=std::llround((it.getY()-size/2)/res)-y0;
      const int zb=zindex(it.getZ()-size/2),ze=zindex(it.getZ()+size/2);
      for (int z=zb;z<ze;++z) for (int y=yb;y<yb+count;++y) {
        const size_t index=(static_cast<size_t>(z)*h+(h-1-y))*w+xb;
        std::fill(state.begin()+index,state.begin()+index+count,occupied ? 2:1);
        std::fill(log_odds.begin()+index,log_odds.begin()+index+count,it->getLogOdds());
      }
    }
    // Independent coordinate-query check catches wrong Y direction, pruned-leaf
    // expansion and fractional floor shifts. Includes both known and unknown cells.
    std::mt19937 rng(200);
    size_t checked_known=0,checked_unknown=0;
    for (size_t sample=0;sample<30000;++sample) {
      const size_t z=rng()%nz,row=rng()%h,col=rng()%w;
      const double x=(static_cast<double>(x0)+col+.5)*res;
      const double y=(static_cast<double>(y1)-row-.5)*res,zs=floor+zmin+(z+.5)*res;
      const auto *node=tree->search(x,y,zs);
      const uint8_t expected=node ? (tree->isNodeOccupied(node) ? 2:1):0;
      const size_t index=(z*h+row)*w+col;
      if (state[index]!=expected || (node && std::abs(log_odds[index]-node->getLogOdds())>1.e-7))
        throw std::runtime_error("Dense-grid coordinate validation failed");
      node ? ++checked_known : ++checked_unknown;
    }
    if (!checked_known || !checked_unknown) throw std::runtime_error("Validation must cover known and unknown space");
    std::filesystem::create_directories(output);
    write_binary(output/"state.u8",state); write_binary(output/"octomap_log_odds.f32",log_odds);
    std::ofstream meta(output/"grid.json");
    meta << std::setprecision(17)
         << "{\n  \"shape_zyx\": ["<<nz<<","<<h<<","<<w<<"],\n  \"resolution_m\": "<<res
         << ",\n  \"map_bounds_xyxy_m\": ["<<x0*res<<","<<y0*res<<","<<x1*res<<","<<y1*res<<"]"
         << ",\n  \"z_min_m\": "<<zmin<<",\n  \"z_max_m\": "<<zmax<<",\n  \"floor_z_in_room_map_m\": "<<floor
         << ",\n  \"source_z_bounds_m\": ["<<minz<<","<<maxz<<"]"
         << ",\n  \"source_free_leaves\": "<<source_free<<",\n  \"source_occupied_leaves\": "<<source_occupied
         << ",\n  \"source_pruned_leaves\": "<<pruned
         << ",\n  \"free_voxels\": "<<std::count(state.begin(),state.end(),1)
         << ",\n  \"occupied_voxels\": "<<std::count(state.begin(),state.end(),2)
         << ",\n  \"unknown_voxels\": "<<std::count(state.begin(),state.end(),0)
         << ",\n  \"validated_known_samples\": "<<checked_known<<",\n  \"validated_unknown_samples\": "<<checked_unknown
         << ",\n  \"array_order\": \"Z increasing; row from max Y to min Y; column from min X to max X\""
         << ",\n  \"height_sampling\": \"target voxel centers queried in source coordinates after floor translation\""
         << ",\n  \"state_encoding\": \"0 unknown; 1 free; 2 occupied\"\n}\n";
    if (!meta) throw std::runtime_error("Cannot write grid metadata");
    std::cout<<"Exported "<<nz<<" x "<<h<<" x "<<w<<" cells; 30000 coordinate queries verified\n";
  } catch (const std::exception &e) { std::cerr<<e.what()<<"\n"; return 1; }
}
