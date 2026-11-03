// AXP2101 power management: battery %, voltage, charging state and battery-care charge limits.
// Registers per XPowersLib (AXP2101Constants.h / XPowersAXP2101.tpp).
#include "pmu.h"
#include <Arduino.h>
#include "board.h"

static bool ok = false;

static void setBits(uint8_t reg, uint8_t mask, uint8_t val) {
    int v = i2cRead(ADDR_PMU, reg);
    if (v >= 0) i2cWrite(ADDR_PMU, reg, (v & ~mask) | (val & mask));
}

bool pmuBegin(bool batteryCare) {
    ok = i2cRead(ADDR_PMU, 0x03) >= 0;
    if (!ok) return false;
    setBits(0x30, 0x01, 0x01);        // ADC: battery voltage measurement on
    setBits(0x18, 0x08, 0x08);        // fuel gauge module on
    setBits(0xA2, 0x01, 0x01);        // fuel gauge enable
    pmuSetCare(batteryCare);
    setBits(0x62, 0x1F, 8);           // constant charge current 200 mA (gentle; capacity unknown)
    return true;
}

void pmuSetCare(bool care) {
    // CV target: 1=4.0V 2=4.1V 3=4.2V 4=4.35V 5=4.4V
    setBits(0x64, 0x07, care ? 2 : 3);
}

Battery pmuRead() {
    Battery b{};
    if (!ok) return b;
    int s1 = i2cRead(ADDR_PMU, 0x00), s2 = i2cRead(ADDR_PMU, 0x01);
    b.present = s1 >= 0 && (s1 & 0x08);
    b.usb = s1 >= 0 && (s1 & 0x20);
    b.charging = s2 >= 0 && ((s2 >> 5) & 0x03) == 1;
    b.full = s2 >= 0 && (s2 & 0x07) == 0x04;   // charger state "done"
    if (b.present) {
        int h = i2cRead(ADDR_PMU, 0x34), l = i2cRead(ADDR_PMU, 0x35);
        if (h >= 0 && l >= 0) b.mv = ((h & 0x3F) << 8) | l;
        int p = i2cRead(ADDR_PMU, 0xA4);
        b.pct = (p >= 0 && p <= 100) ? p : -1;
    } else {
        b.pct = -1;
    }
    int cv = i2cRead(ADDR_PMU, 0x64);
    b.care = cv >= 0 && (cv & 0x07) <= 2;
    return b;
}

void pmuPowerOff() {
    setBits(0x10, 0x01, 0x01);        // soft power-off; PWR key turns it back on
}
