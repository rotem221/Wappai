#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <vector>
struct DizzyEye {float x,y,rx,ry;};
struct DizzyEyes {DizzyEye eye[2];};
// Analyze a pack once, never in the animation loop. Find a similarly sized
// horizontal eye pair; support dark pupils and bright robot eyes. Legacy packs
// need no binary migration. Unusual artwork gets bounded proportional anchors.
inline DizzyEyes locateDizzyEyes(const uint16_t *pixels,const uint8_t *bounds){
    float w=bounds[2]-bounds[0],h=bounds[3]-bounds[1],cx=(bounds[0]+bounds[2])*.5f;
    float rx=std::max(4.f,std::min(8.f,w*.08f));
    DizzyEyes result={{{cx-w*.16f,bounds[1]+h*.38f,rx,rx*1.3f},{cx+w*.16f,bounds[1]+h*.38f,rx,rx*1.3f}}};
    struct Box {int l,t,r,b,area;};float best=-1e9f;
    int l=bounds[0]+int(w*.10f),r=bounds[2]-int(w*.10f),top=bounds[1]+int(h*.12f),bottom=bounds[1]+int(h*.66f);
    std::vector<uint8_t> seen(96*96);std::vector<int> stack;stack.reserve(512);
    for(int bright=0;bright<2;bright++){
        std::fill(seen.begin(),seen.end(),0);std::vector<Box> boxes;
        auto eligible=[&](int p){auto c=pixels[p];if(!c)return false;int red=(c>>11)*255/31,green=((c>>5)&63)*255/63,blue=(c&31)*255/31;return bright?std::min(red,std::min(green,blue))>=170:std::max(red,std::max(green,blue))<135;};
        for(int y=top;y<bottom;y++)for(int x=l;x<r;x++){
            int at=y*96+x;if(seen[at] || !eligible(at))continue;
            Box b{x,y,x+1,y+1,0};stack.clear();stack.push_back(at);seen[at]=1;
            while(!stack.empty()){
                int p=stack.back();stack.pop_back();int px=p%96,py=p/96;b.l=std::min(b.l,px);b.r=std::max(b.r,px+1);b.t=std::min(b.t,py);b.b=std::max(b.b,py+1);b.area++;
                for(int d:{-1,1,-96,96}){int q=p+d,qx=q%96,qy=q/96;if(qx<l||qx>=r||qy<top||qy>=bottom||seen[q]||!eligible(q))continue;seen[q]=1;stack.push_back(q);}
            }
            int bw=b.r-b.l,bh=b.b-b.t;
            if(bw>=3&&bw<=18&&bh>=4&&bh<=22&&b.area>=10&&b.area<=220&&bw<=bh*2&&bh<=bw*3&&boxes.size()<96)boxes.push_back(b);
        }
        for(auto a:boxes)for(auto b:boxes){
            float ax=(a.l+a.r)*.5f,bx=(b.l+b.r)*.5f,ay=(a.t+a.b)*.5f,by=(b.t+b.b)*.5f;
            if(bx-ax<10||bx-ax>38||std::fabs(ay-by)>5||a.area>b.area*2.2f||b.area>a.area*2.2f||std::fabs((ax+bx)*.5f-cx)>w*.2f)continue;
            float score=a.area+b.area-8*std::fabs(ay-by)-2*std::fabs((ax+bx)*.5f-cx)-std::fabs((ay+by)*.5f-(bounds[1]+h*.36f));
            if(score<=best)continue;best=score;
            result={{{ax,ay,std::min(10.f,(a.r-a.l)*.5f+1.5f),std::min(12.f,(a.b-a.t)*.5f+1.5f)},{bx,by,std::min(10.f,(b.r-b.l)*.5f+1.5f),std::min(12.f,(b.b-b.t)*.5f+1.5f)}}};
        }
    }
    return result;
}
// Repaint only the small eye regions on a disposable 96px texture. Body, pose,
// recolour, transform and nearest-neighbour sampling stay in the shared renderer.
inline void paintDizzyEyes(uint16_t *pixels,const DizzyEyes &eyes,float time){
    constexpr uint16_t rim=0x10c7,cream=0xffdc;
    struct Point {float x,y;};
    static const auto curve=[](){std::array<Point,49> points{};for(int j=0;j<=48;j++){float k=j/48.f,angle=k*10.053096f,rad=.04f+.69f*k;points[j]={rad*cosf(angle),rad*sinf(angle)};}return points;}();
    for(int i=0;i<2;i++){
        auto e=eyes.eye[i];int l=std::max(0,int(std::floor(e.x-e.rx))),r=std::min(95,int(std::ceil(e.x+e.rx)));
        int t=std::max(0,int(std::floor(e.y-e.ry))),b=std::min(95,int(std::ceil(e.y+e.ry)));
        for(int y=t;y<=b;y++)for(int x=l;x<=r;x++){float dx=(x+.5f-e.x)/e.rx,dy=(y+.5f-e.y)/e.ry,q=dx*dx+dy*dy;if(q<=1)pixels[y*96+x]=q>.78f?rim:cream;}
        float phase=time*4.4f*(i? -1:1),c=cosf(phase),s=sinf(phase);
        // 48 bounded samples produce a readable 1.6-turn spiral; its whole
        // curve rotates rather than moving a pupil around an ordinary eye.
        int lastX=-1,lastY=-1;
        for(int j=0;j<=48;j++){
            float u=curve[j].x,v=curve[j].y;
            int x=int(std::floor(e.x+(u*c-v*s)*e.rx)),y=int(std::floor(e.y+(u*s+v*c)*e.ry));
            if(lastX>=0){int dx=std::abs(x-lastX),sx=lastX<x?1:-1,dy=-std::abs(y-lastY),sy=lastY<y?1:-1,err=dx+dy;
                for(int n=0;n<32;n++){if((unsigned)lastX<96&&(unsigned)lastY<96)pixels[lastY*96+lastX]=rim;if(lastX==x&&lastY==y)break;int twice=err*2;if(twice>=dy){err+=dy;lastX+=sx;}if(twice<=dx){err+=dx;lastY+=sy;}}}
            lastX=x;lastY=y;
        }
    }
}
