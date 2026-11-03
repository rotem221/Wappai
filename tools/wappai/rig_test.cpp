#include "face.h"
#include <vector>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <algorithm>
int main(){
 for(int rig=0;rig<3;rig++)for(auto wh: {std::pair<int,int>{466,466},{368,448},{480,480},{233,233}}){
  int w=wh.first,h=wh.second;std::vector<uint16_t> memory(w*h+64,0xdead);
  Canvas c{memory.data()+32,w,h,false};Face f;f.begin(19);f.setPip(rig);
  for(int e=0;e<Face::count();e++){
   f.setEmotionIndex(e);
   for(int n=0;n<8;n++){
    f.setTalk(n%2 ? .9f:0);f.setTilt(n%2 ? 8:-8);f.update(n==0?8.f:1/30.f);
    auto r=f.render(c,w/2,h/2,w==233?.5f:1.f);assert(r.x0>=0 && r.y0>=0 && r.x1<=w && r.y1<=h);
    for(int g=0;g<32;g++)assert(memory[g]==0xdead && memory[w*h+32+g]==0xdead);
   }
  }
  for(int k=0;k<16;k++) {
   PipPose p;p.leftArm=k&1 ? 2.4f:0;p.rightArm=k&2 ? 2.4f:0;p.tilt=k&4 ? .35f:-.35f;p.eyeOpen=k&8 ? .04f:1.4f;
   p.mouthOpen=1;p.bounce=.2f;p.speed=2;p.gazeX=1;p.gazeY=-1;
   f.setExpression(p);f.update(.25f);auto r=f.render(c,w/2,h/2,w==233?.5f:1.f);
   assert(r.x0>=0 && r.y0>=0 && r.x1<=w && r.y1<=h);
   for(int g=0;g<32;g++)assert(memory[g]==0xdead && memory[w*h+32+g]==0xdead);
  }
 }
 // Dizzy feedback stays visible during its spoken complaint; old tracked
 // star bounds are cleared when returning to idle, including clipped edges.
 for(bool swapped:{false,true})for(bool reduced:{false,true})for(int cy:{18,233}){
  std::vector<uint16_t> pixels(466*466);Canvas c{pixels.data(),466,466,swapped};Face f;f.begin(3);f.setReducedMotion(reduced);
  f.setEmotion("dizzy");f.setTalk(1);f.update(.3f);f.render(c,233,cy);
  uint16_t gold=swapped?0x20ff:0xff20;if(cy==233)assert(std::count(pixels.begin(),pixels.end(),gold)>5);
  f.setEmotion("idle");f.setTalk(0);f.update(.2f);f.render(c,233,cy);assert(std::count(pixels.begin(),pixels.end(),gold)==0);
 }
 puts("3 rigs x 39 states x 3 display geometries + half-resolution raster: memory bounds, custom pose extremes and long-pause transitions passed");
}
