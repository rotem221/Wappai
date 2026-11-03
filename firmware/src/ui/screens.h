// Information screens drawn instead of the face:
//  - cards the server pushes for a few seconds (time, weather, timer, text, camera image, device)
//  - side pages reached by swiping: clock, timer, home (Home Assistant), settings
// Everything is drawn into the full-screen sprite; the caller flushes. Taps are resolved with hit().
#pragma once
#include <LovyanGFX.hpp>
#include "app/model.h"

namespace screens {

enum Page { FACE = 0, CLOCK, TIMER, HOME, SETTINGS, NPAGES };

// Button ids returned by hit()
enum : int {
    B_NONE = -1,
    B_TIMER_PRESET = 100,    // + minutes
    B_TIMER_ADD = 201, B_TIMER_CANCEL = 202,
    B_HA = 300,              // + index
    B_BRIGHT_DN = 401, B_BRIGHT_UP, B_VOL_DN, B_VOL_UP, B_WIFI, B_SCREEN_OFF,
    B_CARD_DEVICE = 500, B_CARD_CLOSE = 501, B_MEET_END = 510,
};

// What the screens show, copied from the model under its lock (so drawing never holds it)
struct Snap {
    // clock
    char date[48];
    Model::Weather weather;
    // timer
    bool timerOn;
    uint32_t timerLeft, timerTotal;
    char timerLabel[64];
    // home
    bool haOk;
    uint8_t nHa;
    Model::HaItem ha[12];
    // settings
    uint8_t brightness, volume;
    bool wifi, server;
    int rssi;
    char ip[16];
    // card
    char cardKind[8];
    char cardTitle[64];
    char cardBody[300];
    Model::Weather cardW;
    Model::HaItem cardDev;
    bool imgReady;
};

void begin();                                    // fonts
void useText(LGFX_Sprite &s);                     // back to the Hebrew text font (subtitles)
void drawPage(LGFX_Sprite &s, int page, const Snap &d, uint32_t now, int haScroll);
void drawCard(LGFX_Sprite &s, const Snap &d, uint32_t now);
// meeting transcription screen: title (once known), elapsed time, mic level, offline note, end button
void drawMeeting(LGFX_Sprite &s, const char *title, uint32_t elapsedMs, float level, bool online, size_t bufferedBytes, uint32_t now);
void drawToast(LGFX_Sprite &s, const char *text);
void drawDots(LGFX_Sprite &s, int page);
int hit(int x, int y);                           // button under (x, y) from the last drawn screen, or B_NONE
void pressed(int id, uint32_t now);              // highlight a button for a moment
void haPending(int idx, uint32_t now);           // a device was toggled: show "…" until the next list
void haListChanged();
// big clock string for the status bar while a timer runs
void fmtLeft(char *out, size_t n, uint32_t ms);
void drawTimerBadge(LGFX_Sprite &s, int cx, int cy, uint32_t ms, float k);

}  // namespace screens
