#pragma once
#include <algorithm>
#include <cmath>

struct DisplaySpan {int left,right;};
struct DisplaySpans {DisplaySpan spans[3];int count=0;};
// Even-aligned transfer regions covering the changed rectangle and optional ring.
// The board is a circular 466px panel; bounds are exclusive and already clipped.
inline DisplaySpans displaySpans(int x,int x1,int y,int y1,int yy,int bh,bool edgeBand) {
    constexpr int W=466,H=466;
    float dy=yy+bh<=H/2 ? H/2.f-(yy+bh-.5f):yy>=H/2 ? yy+.5f-H/2.f:0;
    int extent=(int)ceilf(sqrtf(W*W*.25f-dy*dy))+1;
    int outerLeft=std::max(0,(W/2-extent)&~1),outerRight=std::min(W,(W/2+extent+1)&~1);
    DisplaySpan input[3];int count=0;
    if(edgeBand){
        float far=fmaxf(fabsf(yy+.5f-H*.5f),fabsf(yy+bh-.5f-H*.5f));
        int hole=far<212 ? std::max(0,(int)sqrtf(212.f*212.f-far*far)-2):0;
        input[count++]={outerLeft,std::min(outerRight,(W/2-hole+1)&~1)};
        input[count++]={std::max(outerLeft,(W/2+hole)&~1),outerRight};
    }
    if(yy<y1 && yy+bh>y)input[count++]={std::max(outerLeft,x),std::min(outerRight,x1)};
    for(int i=1;i<count;i++)for(int j=i;j>0 && input[j].left<input[j-1].left;j--)std::swap(input[j],input[j-1]);
    DisplaySpans result;
    for(int i=0;i<count;i++){
        auto s=input[i];if(s.right<=s.left)continue;
        if(result.count && s.left<=result.spans[result.count-1].right)result.spans[result.count-1].right=std::max(result.spans[result.count-1].right,s.right);
        else result.spans[result.count++]=s;
    }
    return result;
}
