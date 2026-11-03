#include "shake_detector.h"
#include <cassert>
#include <limits>
#include <iostream>
int main(){
 ShakeDetector d;uint32_t t=100;
 auto pulse=[&](bool enabled=true){t+=120;bool fired=d.sample(2.3f,t,enabled);d.sample(1.f,t+40,enabled);return fired;};
 for(int i=0;i<100;i++)assert(!d.sample(1.03f,i,true));
 assert(!pulse());assert(!pulse());assert(pulse());
 for(int i=0;i<10;i++)assert(!pulse()); // cooldown
 t+=8001;for(int i=0;i<20;i++)assert(!d.sample(2.4f,t+i*40,true)); // sustained acceleration is one peak
 d.sample(1,t+900,true);t+=1000;assert(!pulse(false));assert(!pulse(false));assert(!pulse(false));
 assert(!pulse());assert(!pulse());assert(pulse());
 ShakeDetector slow;assert(!slow.sample(2.5,0,true));slow.sample(1,50,true);assert(!slow.sample(2.5,2000,true));
 assert(!slow.sample(std::numeric_limits<float>::quiet_NaN(),2050,true));
 ShakeDetector wrap;wrap.fired=true;wrap.lastFire=0xfffffff0U;assert(!wrap.sample(2.3,100,true));
 std::cout<<"Shake: impulses, sustained motion, cooldown, disabled/lock gate, sparse events and wraparound passed\n";
}
