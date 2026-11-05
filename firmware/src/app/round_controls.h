#pragma once
#include <stdint.h>
#include <stdlib.h>
namespace roundControls {
inline int clamp(int n,int lo,int hi){return n<lo?lo:n>hi?hi:n;}
struct EdgeSwipe {
    enum Kind { NONE, VOLUME, BRIGHTNESS } kind=NONE;
    int x0=0,y0=0,initial=0,value=0;bool active=false;
    void begin(int x,int y,int brightness,int volume){
        active=false;x0=x;y0=y;kind=y>=90 && y<=376?(x<=90?VOLUME:x>=376?BRIGHTNESS:NONE):NONE;
        value=initial=kind==BRIGHTNESS?brightness:volume;
    }
    bool move(int x,int y){
        if(kind==NONE)return false;
        int dx=abs(x-x0),dy=abs(y-y0);
        if(!active){if(dx>20 && dx>=dy){kind=NONE;return false;}if(dy<16 || dy*10<dx*14)return false;active=true;}
        value=clamp(initial+(y0-y)*(kind==BRIGHTNESS?235:100)/240,kind==BRIGHTNESS?20:0,kind==BRIGHTNESS?255:100);
        return true;
    }
    void reset(){kind=NONE;active=false;}
};
struct TimerPicker {
    int hours=0,minutes=5,seconds=0;
    void change(int field,int delta){int *v=field==0?&hours:field==1?&minutes:&seconds;*v=clamp(*v+delta,0,field==0?23:59);}
    uint32_t total()const{return hours*3600+minutes*60+seconds;}
};
}
