// Physical, world-axis weapon presentation. No simulation or target inference here.
#pragma once
#include "emissive.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <vector>

namespace armada::flight {
using Point = std::array<float, 3>;
using Colour = std::array<float, 4>;
struct Vertex { Point position; Colour colour; };
inline Point add(Point a, Point b, float s = 1.f) {
  return {a[0]+b[0]*s, a[1]+b[1]*s, a[2]+b[2]*s};
}
inline float dot(Point a, Point b) { return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; }
inline Point cross(Point a, Point b) {
  return {a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]};
}
inline Point unit(Point v) {
  const float n=std::hypot(v[0],v[1],v[2]);
  return n>1e-9f ? Point{v[0]/n,v[1]/n,v[2]/n} : Point{0,0,0};
}

// A soft four-triangle lozenge. Centre is hot, the perimeter fades to zero. Every long-axis
// point is on the WORLD trajectory, so perspective foreshortening/off-centre headings are real.
inline void kite(std::vector<Vertex>& out, Point head, Point axis, Point side,
                 float length, float width, Colour colour, float hot = .25f) {
  const Point centre=add(head,axis,-length*hot);
  const Point rim[4]={head,add(centre,side,width),add(head,axis,-length),add(centre,side,-width)};
  Colour edge=colour; edge[3]=0.f;
  for(int i=0;i<4;++i) {
    out.push_back({centre,colour});
    out.push_back({rim[i],edge});
    out.push_back({rim[(i+1)%4],edge});
  }
}

// Soft-sided streak with a readable body and a tapered final quarter. Unlike a single hot
// point with zero-alpha tips, the body does not disappear into MSAA at tactical distance.
inline void streak(std::vector<Vertex>& out, Point head, Point axis, Point side,
                   float length, float width, Colour colour) {
  const float t[3]={0.f,.72f,1.f}, w[3]={1.f,.65f,0.f}, a[3]={1.f,.65f,0.f};
  for(int i=0;i<2;++i) {
    Point c0=add(head,axis,-length*t[i]), c1=add(head,axis,-length*t[i+1]);
    Colour k0=colour,k1=colour,edge=colour;
    k0[3]*=a[i]; k1[3]*=a[i+1]; edge[3]=0.f;
    for(float sign : {-1.f,1.f}) {
      Point e0=add(c0,side,sign*width*w[i]), e1=add(c1,side,sign*width*w[i+1]);
      out.push_back({c0,k0}); out.push_back({e0,edge}); out.push_back({c1,k1});
      out.push_back({e0,edge}); out.push_back({e1,edge}); out.push_back({c1,k1});
    }
  }
}

inline void append(const emissive::Primitive& p, Point eye, Point right, Point up,
                   float pxPerWorld, std::vector<Vertex>& out) {
  const Point axis=unit(p.b);
  if(dot(axis,axis)<.5f || p.radius<=0.f || p.width<=0.f) return;
  const Point view=unit(add(eye,p.a,-1.f));
  Point side=unit(cross(axis,view));
  const float width=std::max(p.width,.6f/std::max(pxPerWorld,1e-6f));
  Colour tint={p.colour[0]/255.f,p.colour[1]/255.f,p.colour[2]/255.f,p.colour[3]/255.f};
  Colour core={.65f+.35f*tint[0],.65f+.35f*tint[1],.65f+.35f*tint[2],tint[3]};
  if(dot(side,side)<.5f) {
    // End-on: a small luminous head, never an arbitrary horizontal streak.
    kite(out,add(p.a,up,width),up,right,width*2.f,width,core,.5f);
    return;
  }
  const float length=2.f*p.radius;
  if(p.shape==emissive::kFlightLaser) {
    Colour halo=tint; halo[3]*=.32f;
    streak(out,p.a,axis,side,length,width*3.f,halo);
    streak(out,p.a,axis,side,length,width,core);
  } else {
    const bool torpedo=p.shape==emissive::kFlightTorpedo;
    const Point engine=add(p.a,axis,-length*.85f);
    // A tapered local exhaust, NOT a made-up past trajectory: it turns with the current velocity.
    // Torpedoes are heavier and have a longer, cooler plume than rockets.
    Colour exhaust=torpedo ? Colour{.3f,.65f,1.f,tint[3]*.7f}
                           : Colour{1.f,.48f,.12f,tint[3]*.7f};
    streak(out,engine,axis,side,length*(torpedo?4.5f:3.5f),width*1.8f,exhaust);
    Colour engineCore={1.f,.9f,.65f,tint[3]};
    kite(out,engine,axis,side,length*.7f,width,engineCore,.12f);
    // Directional pointed body, subtly lit rather than another coloured screen square.
    core[3]*=.8f;
    kite(out,p.a,axis,side,length,width,core,.38f);
  }
}
} // namespace armada::flight
