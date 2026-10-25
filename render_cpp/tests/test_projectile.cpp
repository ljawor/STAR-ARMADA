#include "projectile_effects.hpp"
#include <cstdio>
#include <limits>
namespace f=armada::flight;
namespace e=armada::emissive;
int failures=0;
void check(bool pass,const char* label) { if(!pass) { ++failures; std::printf("FAIL %s\n",label); } }
e::Primitive shot(unsigned subtype=0) {
  e::Primitive p; p.kind=e::kFlight; p.shape=uint8_t(subtype); p.flags=3;
  p.a={100.f,60.f,0.f}; p.b={0.f,300.f,900.f}; p.radius=12.f; p.width=.4f;
  p.colour={80,180,255,255}; return p;
}
std::vector<uint8_t> wire(const e::Primitive& p) {
  std::vector<uint8_t> b(64,0); std::memcpy(b.data(),e::kMagic,8); b[8]=1;b[10]=1;
  auto* r=b.data()+20; r[0]=p.kind;r[1]=p.shape;r[2]=uint8_t(p.flags);
  std::memcpy(r+4,p.colour.data(),4);std::memcpy(r+8,p.a.data(),12);
  std::memcpy(r+20,p.b.data(),12);std::memcpy(r+32,&p.radius,4);
  std::memcpy(r+36,&p.width,4);std::memcpy(r+40,&p.segments,2);
  uint32_t crc=e::crc32(r,44);std::memcpy(b.data()+16,&crc,4);return b;
}
bool accepted(e::Primitive p) {
  auto b=wire(p);
  try { return e::decode(b.data(),b.size()).size()==1; } catch(const e::EmissiveError&) { return false; }
}
int main() {
  for(unsigned shape=0;shape<3;++shape) {
    auto p=shot(shape);check(accepted(p),"native decoder accepts producer flight subtype");
    std::vector<f::Vertex> near,far;
    f::append(p,{0,0,400},{1,0,0},{0,1,0},2.f,near);
    f::append(p,{0,0,1600},{1,0,0},{0,1,0},.5f,far);
    check(near.size()==48 && far.size()==48,"bounded triangle count for each projectile");
    auto axis=f::unit(p.b);
    float minNear=0,minFar=0;
    for(const auto& pair : {std::make_pair(&near,&minNear),std::make_pair(&far,&minFar)})
      for(const auto& vertex:*pair.first) {
        const float along=f::dot(f::add(vertex.position,p.a,-1.f),axis);
        *pair.second=std::min(*pair.second,along);
        check(along<=1e-4f,"body and exhaust stay BEHIND actual physics head");
        for(float n:vertex.position) check(std::isfinite(n),"finite geometry");
        check(vertex.colour[3]>=0.f && vertex.colour[3]<=1.f,"bounded alpha");
      }
    check(std::abs(minNear-minFar)<1e-4f,"world length invariant under 4x zoom");
    const float factor=shape==0?1.f:(shape==1?4.35f:5.35f);
    check(std::abs(minNear+2.f*p.radius*factor)<1e-3f,"exact world body/exhaust length");
    check(p.a==shot(shape).a && p.b==shot(shape).b,"input head/velocity unchanged");
  }
  auto p=shot();p.a={0,0,0};p.b={0,0,900};
  std::vector<f::Vertex> endOn;
  f::append(p,{0,0,400},{1,0,0},{0,1,0},1.f,endOn);
  check(endOn.size()==12,"end-on shot is a small glow, not a horizontal streak");
  float extent=0;for(auto v:endOn) extent=std::max(extent,std::abs(v.position[0]));
  check(extent<=.601f,"end-on width limited to world width/readability floor");
  p.b={0,0,0};std::vector<f::Vertex> zero;
  f::append(p,{0,0,400},{1,0,0},{0,1,0},1.f,zero);
  check(zero.empty(),"zero velocity never invents an arbitrary direction");
  check(!accepted(p),"decoder refuses zero velocity");
  p=shot();p.shape=3;check(!accepted(p),"decoder refuses unknown subtype");
  p=shot();p.a[1]=std::numeric_limits<float>::infinity();check(!accepted(p),"decoder refuses infinite head");
  p=shot();p.b[0]=std::numeric_limits<float>::quiet_NaN();check(!accepted(p),"decoder refuses NaN velocity");
  p=shot();p.radius=0;check(!accepted(p),"decoder refuses empty length");
  p=shot();p.width=std::numeric_limits<float>::infinity();check(!accepted(p),"decoder refuses infinite width");
  p=shot();p.flags=2;check(!accepted(p),"decoder refuses through-hull flight");
  p=shot();p.segments=1;check(!accepted(p),"decoder refuses nonzero reserved flight segments");
  std::printf("Projectile geometry/protocol: %s\n",failures?"FAIL":"PASS");
  return failures?1:0;
}
