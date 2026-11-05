#pragma once
#include <stdint.h>
#include <string.h>
#include <algorithm>
// remaining = +/-width at the start, zero at rest. Works on a clipped DMA band.
inline void slideRow(uint16_t *out,const uint16_t *old,const uint16_t *next,int width,int left,int count,int remaining){
    remaining=std::max(-width,std::min(width,remaining));
    if(!remaining){memcpy(out,next+left,count*2);return;}
    int split=remaining>0?width-remaining:-remaining;
    int first=std::max(0,std::min(count,split-left));
    const uint16_t *a=remaining>0?next+remaining:old+width-split;
    if(first)memcpy(out,a+left,first*2);
    if(first<count){int x=left+first;const uint16_t *b=remaining>0?old:next;memcpy(out+first,b+x-split,(count-first)*2);}
}
inline float slideEase(float t){t=std::max(0.f,std::min(1.f,t));return 1-(1-t)*(1-t)*(1-t);}
