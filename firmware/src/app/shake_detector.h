#pragma once
#include <cstdint>
#include <cmath>
// Three distinct impulses, not one sustained acceleration. No polling/task of its own.
struct ShakeDetector {
    uint32_t first=0,lastFire=0;unsigned peaks=0;bool high=false,fired=false;
    bool sample(float magnitude,uint32_t now,bool enabled){
        if(!enabled || !std::isfinite(magnitude)){peaks=0;high=false;return false;}
        float deviation=std::fabs(magnitude-1.f);
        if(deviation<.45f)high=false;
        if(deviation<.9f || high)return false;
        high=true;
        if(fired && uint32_t(now-lastFire)<8000)return false;
        if(!peaks || uint32_t(now-first)>1200){peaks=0;first=now;}
        if(++peaks<3)return false;
        peaks=0;lastFire=now;fired=true;return true;
    }
};
