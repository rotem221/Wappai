#include "../../firmware/include/display_spans.h"
#include <vector>
#include <cassert>
#include <cstdio>
int main(){
 for(bool ring:{false,true})for(int test=0;test<40;test++){
  int x=(test*37%232)*2,y=(test*29%232)*2;
  int x1=std::min(466,x+2+(test*13%233)*2),y1=std::min(466,y+2+(test*19%233)*2);
  std::vector<bool> sent(466*466);
  int begin=ring?0:y,end=ring?466:y1;
  for(int yy=begin;yy<end;yy+=12){
   int h=std::min(12,end-yy);auto spans=displaySpans(x,x1,y,y1,yy,h,ring);
   assert(spans.count<=3);
   for(int i=0;i<spans.count;i++){
    auto s=spans.spans[i];assert(s.left>=0 && s.right<=466 && s.left<s.right && !(s.left&1) && !(s.right&1));
    if(i)assert(spans.spans[i-1].right<s.left);
    for(int row=yy;row<yy+h;row++)for(int col=s.left;col<s.right;col++)sent[row*466+col]=true;
   }
  }
  for(int row=0;row<466;row++)for(int col=0;col<466;col++){
   float dx=col+.5f-233,dy=row+.5f-233,r2=dx*dx+dy*dy;
   bool visible=r2<=233.f*233.f;
   bool required=visible && ((col>=x && col<x1 && row>=y && row<y1)||(ring && r2>=212.f*212.f));
   if(required)assert(sent[row*466+col]);
  }
 }
 for(auto wh:{std::pair<int,int>{368,448},{480,480}}){
  int W=wh.first,H=wh.second;std::vector<bool> sent(W*H);
  for(int y=0;y<H;y+=12){int h=std::min(12,H-y);auto spans=displaySpans(0,2,0,2,y,h,true,W,H,false);
   for(int i=0;i<spans.count;i++){auto s=spans.spans[i];assert(s.left>=0 && s.right<=W && !(s.left&1) && !(s.right&1));
    for(int yy=y;yy<y+h;yy++)for(int x=s.left;x<s.right;x++)sent[yy*W+x]=true;
   }
  }
  int inset=(int)(std::min(W,H)*.035f);
  for(int x=inset;x<W-inset;x++){assert(sent[inset*W+x]);assert(sent[(H-inset-1)*W+x]);}
  for(int y=inset;y<H-inset;y++){assert(sent[y*W+inset]);assert(sent[y*W+W-inset-1]);}
  assert(!sent[(H/2)*W+W/2]);
 }
 puts("Round and rectangular display transfers: edge coverage, alignment, merging and bounds passed");
}
