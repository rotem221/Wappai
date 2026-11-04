#pragma once
#include <stdint.h>
// Respect a shorter user setting; after explicit lock or low battery, stop
// spending five minutes in radio standby. Active recording is guarded by caller.
inline uint32_t powerDeepDelay(uint32_t configured,bool locked,bool pocket,int batteryPercent){
    uint32_t cap=locked || (batteryPercent>=0 && batteryPercent<20) ? 60000u:pocket ? 90000u:configured;
    return configured<cap?configured:cap;
}
