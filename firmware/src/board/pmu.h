#pragma once
#include <stdint.h>

struct Battery {
    bool present, usb, charging, full, care;
    int pct;      // 0..100, -1 unknown
    int mv;       // battery voltage
};

bool pmuBegin(bool batteryCare);   // batteryCare: charge to 4.1 V instead of 4.2 V
void pmuSetCare(bool care);
Battery pmuRead();
void pmuPowerOff();
