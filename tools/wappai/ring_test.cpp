// Exercise the cached rasterizer against the original floating-point reference.
#include "../../firmware/src/ui/ring.cpp"
#include <vector>
#include <cassert>
#include <cstdio>
#include <cmath>
int main(){
 for(auto wh:{std::pair<int,int>{466,466},{368,448},{480,480},{233,233},{17,23}}){
  int W=wh.first,H=wh.second;size_t N=W*H;
  std::vector<uint16_t> actual(N+64,0xdead),reference(N,0);
  auto *px=actual.data()+32;
  for(bool swapped:{false,true})for(auto mode:{RS_FULL,RS_COMET,RS_PROGRESS})for(int frame=0;frame<16;frame++){
   std::fill(px,px+N,0);std::fill(reference.begin(),reference.end(),0);
   RingStyle s;s.contour=RC_CIRCLE;s.mode=mode;s.head=frame*6.2831853f/16;s.progress=frame/15.f;s.thickness=5+frame%10;s.glow=frame/15.f;
   ringDraw(px,W,H,swapped,s);ringDrawFallback(reference.data(),W,H,swapped,s);
   double error=0;int pixels=0;
   for(size_t i=0;i<N;i++){
    unsigned a=px[i],b=reference[i];if(swapped){a=((a>>8)|(a<<8))&65535;b=((b>>8)|(b<<8))&65535;}
    if(a || b){error+=abs(int((a>>11)&31)-int((b>>11)&31))+abs(int((a>>5)&63)-int((b>>5)&63))+abs(int(a&31)-int(b&31));pixels++;}
   }
   // Polar quantization <=1/16 pixel and 1/2 angular bin; AA differences only.
   if(error/(pixels?pixels:1)>=1.4){fprintf(stderr,"W=%d H=%d mode=%d frame=%d error=%f\n",W,H,mode,frame,error/(pixels?pixels:1));return 1;}
   for(int i=0;i<32;i++)assert(actual[i]==0xdead && actual[N+32+i]==0xdead);
   s.mode=RS_OFF;ringDraw(px,W,H,swapped,s);
   for(size_t i=0;i<N;i++)assert(px[i]==0);
  }
 }
 // Incremental frames must exactly match complete cached renders, including
 // wraparound, style changes and a damaged annulus that forces full repair.
 std::vector<uint16_t> incremental(466*466),complete(466*466);
 for(int frame=0;frame<120;frame++){
  RingStyle st;st.mode=RS_COMET;st.head=fmodf(frame*.09f,6.2831853f);
  if(frame>60)st.thickness=12;
  bool repair=frame%17==0;
  if(repair)std::fill(incremental.begin(),incremental.end(),0);
  // Full render first restores the shared previous frame cache; then initialize
  // incremental from last frame, so use saved prior arcs/style for its pass.
  auto prior=painted;bool valid=paintedValid;uint8_t old[ANGLES];memcpy(old,previousArcs,sizeof old);
  ringDraw(complete.data(),466,466,false,st);
  painted=prior;paintedValid=valid;memcpy(previousArcs,old,sizeof old);
  ringDraw(incremental.data(),466,466,false,st,!repair);
  assert(incremental==complete);
 }
 for(auto wh:{std::pair<int,int>{368,448},{480,480}}){
  int W=wh.first,H=wh.second;std::vector<uint16_t> buffer(W*H+64,0xdead);auto px=buffer.data()+32;
  std::fill(px,px+W*H,0);RingStyle s;s.mode=RS_FULL;s.track=0;s.thickness=8;
  ringDraw(px,W,H,false,s);
  // A rectangular frame reaches all four side midpoints, with rounded corners.
  int inset=(int)(fminf(W,H)*.035f);
  assert(px[inset*W+W/2] && px[(H/2)*W+inset]);
  assert(px[(H-1-inset)*W+W/2] && px[(H/2)*W+W-1-inset]);
  assert(!px[(H/2)*W+W/2] && !px[inset*W+inset]);
  for(auto mode:{RS_COMET,RS_PROGRESS})for(int frame=0;frame<60;frame++){s.mode=mode;s.head=frame*.2f;s.progress=frame/59.f;ringDraw(px,W,H,true,s);}
  s.mode=RS_OFF;ringDraw(px,W,H,true,s);for(int i=0;i<W*H;i++)assert(px[i]==0);
  for(int i=0;i<32;i++)assert(buffer[i]==0xdead && buffer[W*H+32+i]==0xdead);
 }
 puts("Circle and rounded-rectangle frames: reference, bounds, four edges, animation and clearing passed");
}
