// On-device Wi-Fi setup for the round screen: pick a network from a scanned list, type the password on a
// 4x4 paged keyboard (a-o / p-z / 123 / symbols, shift, backspace), connect. Draws the whole screen.
//
// Talks to the network task only through the shared Model (scanReq / aps / wifiErr) and netSetWifi().
#pragma once
#include <LovyanGFX.hpp>

class WifiSetup {
public:
    void begin(bool canCancel);                 // canCancel: Wi-Fi works and the user opened it (show a close button)
    bool active() const { return active_; }
    bool canCancel() const { return canCancel_; }
    void close() { active_ = false; }
    // Feed the touch state every frame (down = finger on the glass).
    void touch(bool down, int x, int y, uint32_t now);
    void tap(int x, int y, uint32_t now);       // synthetic tap (serial tests)
    void render(LGFX_Sprite &s, uint32_t now);

private:
    enum State { LIST, KEYS, CONNECTING } st_ = LIST;
    bool active_ = false, canCancel_ = false;
    // list
    int scroll_ = 0, scrollStart_ = 0;
    uint32_t seenSeq_ = 0;
    struct Ap { char ssid[33]; int8_t rssi; bool open; } aps_[24];
    int nAps_ = 0;
    bool scanning_ = false;
    uint32_t scanT0_ = 0, lastScanDone_ = 0;
    uint32_t seenAt_[24] = {};
    // keyboard
    char ssid_[33] = "";
    bool open_ = false;
    char pass_[65] = "";
    int page_ = 0;
    bool shift_ = false, show_ = false;
    int pressedKey_ = -1;
    uint32_t pressedUntil_ = 0;
    char msg_[80] = "";
    uint32_t connectAt_ = 0;
    // touch tracking
    bool down_ = false, dragging_ = false;
    int x0_ = 0, y0_ = 0, x_ = 0, y_ = 0;

    void requestScan(uint32_t now);
    void onTap(int x, int y, uint32_t now);
    void pressKey(int k, uint32_t now);
    void drawList(LGFX_Sprite &s, uint32_t now);
    void drawKeys(LGFX_Sprite &s, uint32_t now);
};
