#pragma once
#include "pip_art.gen.h"
// Inverse mapping keeps transforms subpixel and clips before touching the framebuffer.
// Prelit torso/limbs share the native iOS sculpt; facial expressions remain procedural.
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((optimize("O3")))
#endif
static void drawPipPart(Canvas &cv,const Xf &xf,const PipRaster &art,Face *owner,
                        float pivotX=0,float pivotY=0,float angle=0,float dy=0,uint32_t tint=0,int rig=0) {
    constexpr float unit=330.f/256.f;
    const float ca=cosf(angle),sa=sinf(angle);
    float minx=1e9f,miny=1e9f,maxx=-1e9f,maxy=-1e9f;
    for(int k=0;k<4;k++) {
        float ax=((k&1?art.x+art.w:art.x)-128)*unit-pivotX;
        float ay=((k&2?art.y+art.h:art.y)-128)*unit-pivotY;
        float sx,sy;xf.toScreen(pivotX+ax*ca-ay*sa,pivotY+dy+ax*sa+ay*ca,sx,sy);
        minx=fminf(minx,sx);maxx=fmaxf(maxx,sx);miny=fminf(miny,sy);maxy=fmaxf(maxy,sy);
    }
    int x0=fmaxf(0,floorf(minx)-1),x1=fminf(cv.w,ceilf(maxx)+1),y0=fmaxf(0,floorf(miny)-1),y1=fminf(cv.h,ceilf(maxy)+1);
    if(x0>=x1 || y0>=y1)return;owner->addRect(x0,y0,x1,y1);
    const int bases[3]={0x69E8BC,0xFFAF80,0x84C5F1};
    int tr=256,tg=256,tb=256;
    if(tint) {tr=((tint>>16)&255)*256/((bases[rig]>>16)&255);tg=((tint>>8)&255)*256/((bases[rig]>>8)&255);tb=(tint&255)*256/(bases[rig]&255);}
    // Fixed-point inverse transform + integer bilinear RGB565. Floating point per
    // pixel cost ~80 ms on S3; only row origins use floats now.
    const float inv=65536.f/(xf.s*unit);
    const int du=(int)((xf.c*ca-xf.sn*sa)*inv),dv=(int)((-xf.c*sa-xf.sn*ca)*inv);
    for(int y=y0;y<y1;y++) {
        V2 origin=xf.toFace(x0+.5f,y+.5f);float ax=origin.x-pivotX,ay=origin.y-pivotY-dy;
        int uf=(int)(((pivotX+ax*ca+ay*sa)/unit+128-art.x-.5f)*65536.f);
        int vf=(int)(((pivotY-ax*sa+ay*ca)/unit+128-art.y-.5f)*65536.f);
        for(int x=x0;x<x1;x++,uf+=du,vf+=dv) {
            int ix=uf>>16,iy=vf>>16;if(ix<0 || iy<0 || ix>=art.w-1 || iy>=art.h-1)continue;
            unsigned fx=(uf>>8)&255,fy=(vf>>8)&255;
            unsigned weights[4]={(256-fx)*(256-fy),fx*(256-fy),(256-fx)*fy,fx*fy};
            const uint32_t *src=art.pixels+iy*art.w+ix;
            uint32_t q[4]={src[0],src[1],src[art.w],src[art.w+1]};
            unsigned a=255,r=0,g=0,b=0;
            if(((q[0]&q[1]&q[2]&q[3])&0xff0000)==0xff0000) {
                for(int k=0;k<4;k++){r+=((q[k]>>11)&31)*weights[k];g+=((q[k]>>5)&63)*weights[k];b+=(q[k]&31)*weights[k];}
                r=(r+32768)>>16;g=(g+32768)>>16;b=(b+32768)>>16;
            } else {
                unsigned alpha=0;
                for(int k=0;k<4;k++){unsigned w=weights[k]*((q[k]>>16)&255);alpha+=w;r+=((q[k]>>11)&31)*w;g+=((q[k]>>5)&63)*w;b+=(q[k]&31)*w;}
                a=alpha>>16;if(a<2)continue;r/=alpha;g/=alpha;b/=alpha;
            }
            if(tint){r=r*tr>>8;g=g*tg>>8;b=b*tb>>8;if(r>31)r=31;if(g>63)g=63;if(b>31)b=31;}
            uint16_t *dst=cv.px+y*cv.w+x;
            if(a<254){uint16_t bg=*dst;if(cv.swapped)bg=(bg>>8)|(bg<<8);r=(r*a+((bg>>11)&31)*(255-a)+127)/255;g=(g*a+((bg>>5)&63)*(255-a)+127)/255;b=(b*a+(bg&31)*(255-a)+127)/255;}
            uint16_t rgb=(r<<11)|(g<<5)|b;*dst=cv.swapped?(uint16_t)((rgb>>8)|(rgb<<8)):rgb;
        }
    }
}
