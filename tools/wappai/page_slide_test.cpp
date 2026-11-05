#include "ui/page_slide.h"
#include <array>
#include <cassert>
#include <cmath>
#include <iostream>
int main(){
 constexpr int W=466;std::array<uint16_t,W> old,next;for(int x=0;x<W;x++){old[x]=1000+x;next[x]=2000+x;}
 for(int remain=-W;remain<=W;remain++)for(int left:{0,2,61,230,460}){
  int count=W-left;std::array<uint16_t,W+2> out{};out.front()=out.back()=65535;
  slideRow(out.data()+1,old.data(),next.data(),W,left,count,remain);
  for(int i=0;i<count;i++){int x=left+i;int expected=!remain?next[x]:remain>0?(x<W-remain?next[x+remain]:old[x-(W-remain)]):(x<-remain?old[x+W+remain]:next[x+remain]);assert(out[i+1]==expected);}
  assert(out.front()==65535 && out.back()==65535);
 }
 float last=0;for(int i=0;i<=100;i++){float e=slideEase(i/100.f);assert(e>=last && e<=1);last=e;}
 assert(slideEase(0)==0 && slideEase(1)==1);
 std::cout<<"Both slide directions, 933 offsets, clipped DMA spans and ease endpoints passed\n";
}
