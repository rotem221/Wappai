#include "ring.h"
#include <math.h>
#include <string.h>
#include <stdlib.h>
#ifdef ARDUINO
#include <esp_heap_caps.h>
#endif

static inline float clampf(float v, float a, float b) { return v < a ? a : (v > b ? b : v); }

// fast atan2 (max error ~0.005 rad), result in [-pi, pi]
static inline float fatan2(float y, float x) {
    float ax = fabsf(x), ay = fabsf(y);
    float mn = ax < ay ? ax : ay, mx = ax < ay ? ay : ax;
    float a = mn / (mx + 1e-9f), s = a * a;
    float r = ((-0.0464964749f * s + 0.15931422f) * s - 0.327622764f) * s * a + a;
    if (ay > ax) r = 1.57079637f - r;
    if (x < 0) r = 3.14159274f - r;
    if (y < 0) r = -r;
    return r;
}

static inline uint16_t pack(float r, float g, float b, bool swap) {
    uint16_t v = (uint16_t)(((int)(clampf(r, 0, 1) * 31 + .5f) << 11) | ((int)(clampf(g, 0, 1) * 63 + .5f) << 5) | (int)(clampf(b, 0, 1) * 31 + .5f));
    return swap ? (uint16_t)((v >> 8) | (v << 8)) : v;
}

namespace {
struct EdgePixel {uint32_t offset;uint16_t phase,distance;};
static EdgePixel *edgePixels=nullptr;
static int edgeW=0,edgeH=0;
static size_t edgeCount=0;
// Rounded rectangle parameterized by distance, starting at the top midpoint.
// Constant speed through corners; geometry is cached, never recomputed per frame.
static void edgeGeometry(float x,float y,int W,int H,float &distance,float &phase) {
    float inset=fminf(W,H)*.035f,r=fminf(W,H)*.12f;
    float hx=W*.5f-inset,hy=H*.5f-inset;
    r=fminf(r,fminf(hx,hy));
    float dx=fabsf(x-W*.5f),dy=fabsf(y-H*.5f),qx=dx-(hx-r),qy=dy-(hy-r);
    distance=fabsf(hypotf(fmaxf(qx,0),fmaxf(qy,0))+fminf(fmaxf(qx,qy),0)-r);
    float A=hx-r,B=hy-r,Q=A+B+1.570796327f*r,u;
    if(qx>0 && qy>0)u=A+r*atan2f(qx,qy);
    else if(qx>qy)u=Q-dy;
    else u=dx;
    float s=y<H*.5f ? (x>=W*.5f ? u:4*Q-u):(x>=W*.5f ? 2*Q-u:2*Q+u);
    phase=s/(4*Q);
}
static void drawRectangle(uint16_t *px,int W,int H,bool swapped,const RingStyle &st) {
    if(edgeW!=W || edgeH!=H) {
        free(edgePixels);edgePixels=nullptr;edgeCount=0;edgeW=W;edgeH=H;
        for(int y=0;y<H;y++)for(int x=0;x<W;x++){float d,p;edgeGeometry(x+.5f,y+.5f,W,H,d,p);if(d<=20)edgeCount++;}
#ifdef ARDUINO
        edgePixels=(EdgePixel*)heap_caps_malloc(edgeCount*sizeof(EdgePixel),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
#else
        edgePixels=(EdgePixel*)malloc(edgeCount*sizeof(EdgePixel));
#endif
        if(edgePixels){size_t n=0;for(int y=0;y<H;y++)for(int x=0;x<W;x++){
            float d,p;edgeGeometry(x+.5f,y+.5f,W,H,d,p);if(d<=20)edgePixels[n++]={(uint32_t)(y*W+x),(uint16_t)(p*65535),(uint16_t)(d*256+.5f)};
        }}
    }
    float head=fmodf(st.head/6.2831853f,1);if(head<0)head+=1;
    uint16_t colors[256];for(int i=0;i<256;i++)colors[i]=pack(st.r*i/255.f,st.g*i/255.f,st.b*i/255.f,swapped);
    auto paint=[&](uint32_t offset,float phase,float distance){
        float arc=1,half=st.thickness*.5f;
        if(st.mode==RS_PROGRESS)arc=st.progress>0 && phase<=clampf(st.progress,0,1) ? 1:0;
        if(st.mode==RS_COMET){float delta=head-phase;if(delta<0)delta+=1;arc=clampf(1-delta/(2.2f/6.2831853f),0,1);arc*=arc;}
        float band=clampf(half+.5f-distance,0,1),glow=clampf(st.glow,0,1)*clampf(1-(distance-half)/7,0,1)*.35f*arc;
        float alpha=st.mode==RS_OFF ? 0:fmaxf(band*fmaxf(arc,st.track)*st.alpha,glow);
        px[offset]=colors[(int)(clampf(alpha,0,1)*255+.5f)];
    };
    if(edgePixels){for(size_t i=0;i<edgeCount;i++){auto &p=edgePixels[i];paint(p.offset,p.phase/65535.f,p.distance/256.f);}}
    else for(int y=0;y<H;y++)for(int x=0;x<W;x++){float d,p;edgeGeometry(x+.5f,y+.5f,W,H,d,p);if(d<=20)paint(y*W+x,p,d);}
}
}

// Paints every pixel of the band [R0, R1] (so it also erases the previous frame).
static void ringDrawFallback(uint16_t *px, int W, int H, bool swapped, const RingStyle &st) {
    const float cx = W * 0.5f, cy = H * 0.5f;
    const float R0 = 212.f, R1 = 233.f;
    const float rc = st.radius, half = st.thickness * 0.5f;
    const float TWO_PI = 6.2831853f;
    for (int y = 0; y < H; y++) {
        float dy = y + 0.5f - cy;
        if (fabsf(dy) > R1) continue;
        float xo = sqrtf(R1 * R1 - dy * dy);
        float xi = fabsf(dy) < R0 ? sqrtf(R0 * R0 - dy * dy) : 0.f;
        int spans[2][2] = {{(int)(cx - xo) - 1, (int)(cx - xi) + 1}, {(int)(cx + xi) - 1, (int)(cx + xo) + 1}};
        for (auto &sp : spans) {
            int x0 = sp[0] < 0 ? 0 : sp[0], x1 = sp[1] > W ? W : sp[1];
            for (int x = x0; x < x1; x++) {
                float dx = x + 0.5f - cx;
                float r = sqrtf(dx * dx + dy * dy);
                if (r < R0 || r > R1) continue;
                // angle clockwise from 12 o'clock, 0..2pi
                float ang = fatan2(dx, -dy);
                if (ang < 0) ang += TWO_PI;
                float a = 0;
                if (st.mode != RS_OFF) {
                    float band = clampf(half + 0.5f - fabsf(r - rc), 0, 1);
                    float glowA = st.glow > 0 ? st.glow * clampf(1.f - (fabsf(r - rc) - half) / 7.f, 0, 1) * 0.35f : 0;
                    float track = st.track;
                    float arc = 0;
                    if (st.mode == RS_PROGRESS) {
                        float end = st.progress * TWO_PI;
                        // inside the arc, or rounded cap at the head
                        if (ang <= end) arc = 1;
                        else {
                            float hx = cx + sinf(end) * rc, hy = cy - cosf(end) * rc;
                            float dd = sqrtf((x + .5f - hx) * (x + .5f - hx) + (y + .5f - hy) * (y + .5f - hy));
                            arc = clampf(half + 0.5f - dd, 0, 1) / fmaxf(band, 1e-3f);
                            if (arc > 1) arc = 1;
                        }
                    } else if (st.mode == RS_COMET) {
                        float d = st.head - ang;
                        while (d < 0) d += TWO_PI;
                        while (d >= TWO_PI) d -= TWO_PI;
                        float L = 2.2f;
                        arc = d < L ? (1.f - d / L) : 0;
                        arc *= arc;
                    } else if (st.mode == RS_FULL) {
                        arc = 1;
                    }
                    float k = arc > track ? arc : track;
                    a = band * k * st.alpha;
                    if (arc > 0.05f && glowA > a) a = glowA * arc;
                }
                px[y * W + x] = a > 0.003f ? pack(st.r * a, st.g * a, st.b * a, swapped) : 0;
            }
        }
    }
}

// Geometry is invariant: store polar coordinates in PSRAM once, then shade from
// tiny lookup tables. No per-pixel atan/sqrt or RGB conversion in the comet loop.
namespace {
constexpr int ANGLES=1020, RADII=169;
// Only one quadrant is cached: its reflections share radius and angle.
// ~15 KB instead of ~235 KB keeps framebuffer writes from evicting the geometry.
static uint16_t *geometry=nullptr;
static int cachedW=0,cachedH=0;
static uint16_t startX[256],endX[256];
static uint8_t coverage[RADII],halo[RADII],arcs[ANGLES];
static uint16_t palette[256];
static RingStyle painted;
static bool paintedValid=false,paintedSwapped=false;
static uint8_t previousArcs[ANGLES];
static bool prepare(int W,int H) {
    if((W&1)||(H&1)||W>512||H>512)return false;
    if(geometry && W==cachedW && H==cachedH)return true;
    free(geometry);geometry=nullptr;paintedValid=false;
    size_t count=0;
    for(int y=0;y<H/2;y++) {
        startX[y]=endX[y]=0;
        for(int x=0;x<W/2;x++){
            float r2=(x+.5f)*(x+.5f)+(y+.5f)*(y+.5f);
            if(r2>=212.f*212.f && r2<=233.f*233.f){if(endX[y]==0)startX[y]=x;endX[y]=x+1;count++;}
        }
    }
    if(!count)return false;
#ifdef ARDUINO
    geometry=(uint16_t*)heap_caps_malloc(count*sizeof(uint16_t),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
#else
    geometry=(uint16_t*)malloc(count*sizeof(uint16_t));
#endif
    if(!geometry)return false;
    size_t n=0;
    for(int y=0;y<H/2;y++)for(int x=startX[y];x<endX[y];x++) {
        float dx=x+.5f,dy=y+.5f;
        unsigned angle=(unsigned)(atan2f(dx,dy)*ANGLES/6.2831853f+.5f);
        unsigned radius=(unsigned)((sqrtf(dx*dx+dy*dy)-212.f)*8+.5f);
        geometry[n++]=(radius<<8)|angle;
    }
    cachedW=W;cachedH=H;return true;
}
static inline int multiplyAlpha(int a,int b){int n=a*b+128;return (n+(n>>8))>>8;}
}

#if defined(__GNUC__) && !defined(__clang__)
__attribute__((optimize("O3")))
#endif
void ringDraw(uint16_t *px,int W,int H,bool swapped,const RingStyle &st,bool allowIncremental) {
    if(!px || W<=0 || H<=0)return;
    if(st.contour==RC_ROUNDED_RECT || (st.contour==RC_AUTO && (W!=466 || H!=466))) {
        paintedValid=false;drawRectangle(px,W,H,swapped,st);return;
    }
    if(!prepare(W,H)){paintedValid=false;ringDrawFallback(px,W,H,swapped,st);return;}

    const float tau=6.2831853f,half=st.thickness*.5f,end=clampf(st.progress,0,1)*tau;
    float head=fmodf(st.head,tau);if(head<0)head+=tau;
    const int track=(int)(clampf(st.track,0,1)*255+.5f);
    for(int i=0;i<256;i++)palette[i]=pack(st.r*i/255.f,st.g*i/255.f,st.b*i/255.f,swapped);
    for(int r=0;r<RADII;r++) {
        float distance=fabsf(212.f+r/8.f-st.radius);
        coverage[r]=(uint8_t)(clampf(half+.5f-distance,0,1)*clampf(st.alpha,0,1)*255+.5f);
        halo[r]=(uint8_t)(clampf(st.glow,0,1)*clampf(1-(distance-half)/7.f,0,1)*.35f*255+.5f);
    }
    for(int a=0;a<ANGLES;a++) {
        float angle=a*tau/ANGLES,arc=1;
        if(st.mode==RS_COMET){float d=head-angle;if(d<0)d+=tau;arc=clampf(1-d/2.2f,0,1);arc*=arc;}
        else if(st.mode==RS_PROGRESS)arc=angle<=end ? 1:0;
        arcs[a]=(uint8_t)(arc*255+.5f);
    }
    auto shade=[&](int angle,int radius)->uint16_t {
        if(st.mode==RS_OFF)return 0;
        int arc=arcs[angle];
        int a=multiplyAlpha(coverage[radius],arc>track?arc:track);
        if(st.mode==RS_PROGRESS && !arc) {
            float d=angle*tau/ANGLES-end;
            if(d<(half+1)/fmaxf(st.radius,1.f)) {
                float r=212.f+radius/8.f;
                float dist=sqrtf(fmaxf(0,r*r+st.radius*st.radius-2*r*st.radius*cosf(d)));
                int cap=(int)(clampf(half+.5f-dist,0,1)*clampf(st.alpha,0,1)*255);
                if(cap>a)a=cap;
            }
        }
        if(arc>13 && halo[radius]>a)a=multiplyAlpha(halo[radius],arc);
        return palette[a];
    };
    // A steady comet only changes its bright tail. The caller permits this
    // when no other drawing touches the annulus; layout/state changes repaint it.
    bool incremental=allowIncremental && paintedValid && paintedSwapped==swapped && st.mode==RS_COMET && painted.mode==RS_COMET && st.glow==0 && painted.glow==0
        && st.radius==painted.radius && st.thickness==painted.thickness && st.alpha==painted.alpha && st.track==painted.track
        && st.r==painted.r && st.g==painted.g && st.b==painted.b;
    auto write=[&](int offset,int angle,int radius){
        if(incremental && (coverage[radius]==0 || arcs[angle]==previousArcs[angle] || (arcs[angle]<=track && previousArcs[angle]<=track)))return;
        px[offset]=shade(angle,radius);
    };
    const uint16_t *g=geometry;
    for(int y=0;y<H/2;y++) {
        int top=(H/2-1-y)*W,bottom=(H/2+y)*W;
        for(int x=startX[y];x<endX[y];x++) {
            uint16_t polar=*g++;int angle=polar&255,radius=polar>>8;
            int left=W/2-1-x,right=W/2+x;
            write(top+right,angle,radius);
            write(bottom+right,510-angle,radius);
            write(bottom+left,510+angle,radius);
            write(top+left,angle ? 1020-angle:0,radius);
        }
    }
    painted=st;paintedValid=true;paintedSwapped=swapped;memcpy(previousArcs,arcs,sizeof arcs);
}
