#include "screens.h"
#include <WiFi.h>
#include <string.h>
#include <time.h>
#include "config.h"
#include "fonts/he27.h"
#include "fonts/num104.h"
#include "fonts/num52.h"
#include "text_he.h"

namespace screens {

static const int CX = SCREEN_W / 2, CY = SCREEN_H / 2;
// RGB888 colours (uint32_t: LovyanGFX reads them as 24-bit)
static const uint32_t C_TXT = 0xE6EEF2, C_MUTED = 0x8AA0AD, C_DIM = 0x4E5F69, C_ACC = 0x62F2DF, C_AMBER = 0xFFB13B,
                      C_TILE = 0x14212A, C_TILE_HI = 0x24414D, C_BAD = 0xFF6A4D, C_SUN = 0xFFC94A, C_CLOUD = 0xC9D6DE,
                      C_RAIN = 0x5DB7FF, C_ON = 0xFFC56B, C_ON_INK = 0x2A1A00;

static lgfx::PointerWrapper wHe, w104, w52;
static lgfx::VLWfont fHe, f104, f52;

void begin() {
    wHe.set(he27, sizeof he27);
    w104.set(num104, sizeof num104);
    w52.set(num52, sizeof num52);
    fHe.loadFont(&wHe);
    f104.loadFont(&w104);
    f52.loadFont(&w52);
}

void useText(LGFX_Sprite &s) { s.setFont(&fHe); s.setTextSize(1.f); }

static uint32_t mix(uint32_t a, uint32_t b, float t) {
    auto ch = [&](int sh) { return (uint32_t)(((a >> sh) & 255) * (1 - t) + ((b >> sh) & 255) * t) << sh; };
    return ch(16) | ch(8) | ch(0);
}

// ---------------------------------------------------------------- buttons of the last drawn screen
struct Btn { int x0, y0, x1, y1, id; };
static Btn btns[24];
static int nBtns = 0;
static int pressId = B_NONE;
static uint32_t pressUntil = 0, nowMs = 0;

static void addBtn(int x, int y, int w, int h, int id) {
    if (nBtns < 24) btns[nBtns++] = {x, y, x + w, y + h, id};
}
int hit(int x, int y) {
    for (int i = 0; i < nBtns; i++)
        if (x >= btns[i].x0 - 6 && x < btns[i].x1 + 6 && y >= btns[i].y0 - 6 && y < btns[i].y1 + 6) return btns[i].id;
    return B_NONE;
}
void pressed(int id, uint32_t now) { pressId = id; pressUntil = now + 180; }
static bool isPressed(int id) { return id == pressId && (int32_t)(pressUntil - nowMs) > 0; }

static int pendingIdx = -1;
static uint32_t pendingUntil = 0;
void haPending(int idx, uint32_t now) { pendingIdx = idx; pendingUntil = now + 4000; }
void haListChanged() { pendingIdx = -1; }

// ---------------------------------------------------------------- text helpers
static void he(LGFX_Sprite &s, const char *t, int y, uint32_t c, float size = 1.f, int cx = CX, int lines = 1, int lh = 32) {
    s.setFont(&fHe);
    s.setTextSize(size);
    drawBidiText(s, t, cx, CY, SCREEN_W / 2, y, lh, lines, c);
    s.setTextSize(1.f);
}

// Shorten `t` (UTF-8) with "…" until it is at most maxW pixels wide at this text size.
static const char *fit(LGFX_Sprite &s, const char *t, int maxW, float size) {
    static char b[96];
    s.setFont(&fHe);
    s.setTextSize(size);
    strlcpy(b, t, sizeof b);
    if (s.textWidth(b) <= maxW) { s.setTextSize(1.f); return b; }
    size_t n = strlen(b);
    while (n > 0) {
        do n--; while (n > 0 && (b[n] & 0xC0) == 0x80);      // drop one UTF-8 character
        b[n] = 0;
        char tmp[100];
        snprintf(tmp, sizeof tmp, "%s…", b);
        if (s.textWidth(tmp) <= maxW) { strlcpy(b, tmp, sizeof b); break; }
    }
    s.setTextSize(1.f);
    return b;
}

static void num(LGFX_Sprite &s, const char *t, int x, int y, uint32_t c, bool big, float size = 1.f,
                lgfx::textdatum_t datum = lgfx::middle_center) {
    s.setFont(big ? &f104 : &f52);
    s.setTextSize(size);
    s.setTextDatum(datum);
    s.setTextColor(c);
    s.drawString(t, x, y);
    s.setTextSize(1.f);
    s.setFont(&fHe);
}

void fmtLeft(char *out, size_t n, uint32_t ms) {
    uint32_t sec = (ms + 999) / 1000;
    if (sec >= 3600) snprintf(out, n, "%u:%02u:%02u", (unsigned)(sec / 3600), (unsigned)(sec / 60 % 60), (unsigned)(sec % 60));
    else snprintf(out, n, "%02u:%02u", (unsigned)(sec / 60), (unsigned)(sec % 60));
}

void drawTimerBadge(LGFX_Sprite &s, int cx, int cy, uint32_t ms, float k) {
    char b[12];
    fmtLeft(b, sizeof b, ms);
    num(s, b, cx, cy, mix(0, C_AMBER, k), false, 0.62f);
}

// ---------------------------------------------------------------- icons
static void cloud(LGFX_Sprite &s, int x, int y, float r, uint32_t c) {
    s.fillSmoothCircle(x - r * 0.55f, y + r * 0.12f, r * 0.42f, c);
    s.fillSmoothCircle(x + r * 0.05f, y - r * 0.18f, r * 0.58f, c);
    s.fillSmoothCircle(x + r * 0.62f, y + r * 0.15f, r * 0.38f, c);
    s.fillSmoothRoundRect(x - r * 0.95f, y + r * 0.05f, r * 1.95f, r * 0.5f, r * 0.25f, c);
}

static void sun(LGFX_Sprite &s, int x, int y, float r, uint32_t c) {
    for (int i = 0; i < 8; i++) {
        float a = i * 0.785398f;
        s.drawWideLine(x + cosf(a) * r * 0.72f, y + sinf(a) * r * 0.72f, x + cosf(a) * r * 0.98f, y + sinf(a) * r * 0.98f, r * 0.07f, c);
    }
    s.fillSmoothCircle(x, y, r * 0.5f, c);
}

static void moon(LGFX_Sprite &s, int x, int y, float r, uint32_t c) {
    s.fillSmoothCircle(x, y, r * 0.6f, c);
    s.fillSmoothCircle(x + r * 0.3f, y - r * 0.22f, r * 0.5f, (uint32_t)0);
}

static bool night() {
    time_t t = time(nullptr);
    struct tm lt;
    localtime_r(&t, &lt);
    return t > 1700000000 && (lt.tm_hour >= 19 || lt.tm_hour < 6);
}

static void weatherIcon(LGFX_Sprite &s, int x, int y, float r, const char *icon) {
    bool n = night();
    if (!strcmp(icon, "sun")) { n ? moon(s, x, y, r, 0xE9E3C8) : sun(s, x, y, r, C_SUN); return; }
    if (!strcmp(icon, "partly")) {
        n ? moon(s, x + r * 0.3f, y - r * 0.3f, r * 0.8f, 0xE9E3C8) : sun(s, x + r * 0.3f, y - r * 0.3f, r * 0.8f, C_SUN);
        cloud(s, x - r * 0.1f, y + r * 0.2f, r * 0.8f, C_CLOUD);
        return;
    }
    if (!strcmp(icon, "fog")) {
        for (int i = 0; i < 4; i++) s.drawWideLine(x - r * 0.8f + (i & 1) * r * 0.2f, y - r * 0.45f + i * r * 0.3f, x + r * 0.8f - (i & 1) * r * 0.2f,
                                                   y - r * 0.45f + i * r * 0.3f, r * 0.07f, C_CLOUD);
        return;
    }
    cloud(s, x, y - r * 0.2f, r, C_CLOUD);
    if (!strcmp(icon, "rain"))
        for (int i = 0; i < 3; i++) s.drawWideLine(x - r * 0.45f + i * r * 0.42f, y + r * 0.5f, x - r * 0.6f + i * r * 0.42f, y + r * 0.85f, r * 0.06f, C_RAIN);
    if (!strcmp(icon, "snow"))
        for (int i = 0; i < 3; i++) s.fillSmoothCircle(x - r * 0.45f + i * r * 0.45f, y + r * 0.62f + (i & 1) * r * 0.18f, r * 0.08f, 0xFFFFFF);
    if (!strcmp(icon, "storm")) {
        s.fillTriangle(x + r * 0.05f, y + r * 0.3f, x - r * 0.25f, y + r * 0.7f, x, y + r * 0.66f, C_AMBER);
        s.fillTriangle(x - r * 0.05f, y + r * 1.0f, x + r * 0.25f, y + r * 0.55f, x, y + r * 0.6f, C_AMBER);
    }
}

// power / device glyph
static void powerGlyph(LGFX_Sprite &s, int x, int y, float r, uint32_t c) {
    s.drawArc(x, y, r, r - r * 0.22f, -50, 230, c);
    s.drawWideLine(x, y - r * 1.05f, x, y - r * 0.25f, r * 0.11f, c);
}

static void bulb(LGFX_Sprite &s, int x, int y, float r, uint32_t c) {
    s.fillSmoothCircle(x, y - r * 0.2f, r * 0.62f, c);
    s.fillSmoothRoundRect(x - r * 0.3f, y + r * 0.3f, r * 0.6f, r * 0.5f, r * 0.12f, c);
}

static void deviceIcon(LGFX_Sprite &s, int x, int y, float r, const char *kind, uint32_t c) {
    if (!strcmp(kind, "light")) bulb(s, x, y, r, c);
    else if (!strcmp(kind, "lock")) {
        s.drawArc(x, y - r * 0.25f, r * 0.42f, r * 0.28f, 180, 360, c);
        s.fillSmoothRoundRect(x - r * 0.6f, y - r * 0.25f, r * 1.2f, r * 0.9f, r * 0.15f, c);
    } else if (!strcmp(kind, "cover")) {
        for (int i = 0; i < 4; i++) s.fillRect(x - r * 0.65f, y - r * 0.6f + i * r * 0.32f, r * 1.3f, r * 0.2f, c);
    } else powerGlyph(s, x, y, r * 0.7f, c);
}

// ---------------------------------------------------------------- shared pieces
static void pill(LGFX_Sprite &s, int x, int y, int w, int h, uint32_t bg, const char *label, uint32_t fg, int id, float size = 0.85f) {
    s.fillSmoothRoundRect(x, y, w, h, h / 2, isPressed(id) ? mix(bg, 0xFFFFFF, 0.25f) : bg);
    he(s, label, y + h / 2, fg, size, x + w / 2);
    addBtn(x, y, w, h, id);
}

static void bigClock(LGFX_Sprite &s, int y) {
    time_t t = time(nullptr);
    struct tm lt;
    localtime_r(&t, &lt);
    char b[8] = "--:--";
    if (t > 1700000000) snprintf(b, sizeof b, "%02d:%02d", lt.tm_hour, lt.tm_min);
    num(s, b, CX, y, C_TXT, true);
}

static void title(LGFX_Sprite &s, const char *t) { he(s, t, 96, C_MUTED, 0.85f); }

void drawDots(LGFX_Sprite &s, int page) {
    for (int i = 0; i < NPAGES; i++) {
        int x = CX - (i - (NPAGES - 1) / 2.f) * 16;           // right to left: the face is the rightmost dot
        if (i == page) s.fillSmoothRoundRect(x - 7, 437, 14, 7, 3, C_ACC);
        else s.fillSmoothCircle(x, 440, 3, C_DIM);
    }
}

void drawToast(LGFX_Sprite &s, const char *text) {
    s.fillSmoothRoundRect(73, 382, 320, 44, 22, (uint32_t)0x3A1D18);
    he(s, text, 404, 0xFFD2C8, 0.75f);
}

// ---------------------------------------------------------------- pages
static void weatherRow(LGFX_Sprite &s, const Model::Weather &w, int y) {
    if (!w.ok) { he(s, "אין עדיין נתוני מזג אוויר", y, C_DIM, 0.75f); return; }
    char t[12];
    snprintf(t, sizeof t, "%d°", w.t);
    weatherIcon(s, CX + 62, y, 30, w.icon);
    num(s, t, CX - 30, y + 2, C_TXT, false);
    char line[80];
    snprintf(line, sizeof line, "%s · %d°-%d°", w.text, w.mn, w.mx);
    he(s, line, y + 54, C_MUTED, 0.75f);
}

static void pageClock(LGFX_Sprite &s, const Snap &d) {
    he(s, d.date[0] ? d.date : "", 112, C_MUTED, 0.85f);
    bigClock(s, 196);
    weatherRow(s, d.weather, 300);
    if (d.weather.ok && d.weather.city[0]) he(s, d.weather.city, 392, C_DIM, 0.65f);
}

static const int PRESETS[6] = {1, 3, 5, 10, 15, 30};

static void timerRunning(LGFX_Sprite &s, const Snap &d, bool buttons) {
    he(s, d.timerLabel[0] ? d.timerLabel : "טיימר", 128, C_MUTED, 0.85f);
    char b[12];
    fmtLeft(b, sizeof b, d.timerLeft);
    num(s, b, CX, 214, C_AMBER, true, strlen(b) > 5 ? 0.72f : 1.f);
    if (buttons) {
        pill(s, CX + 8, 300, 120, 52, C_TILE_HI, "עוד דקה", C_TXT, B_TIMER_ADD);
        pill(s, CX - 128, 300, 120, 52, (uint32_t)0x3A1D18, "ביטול", 0xFFB3A5, B_TIMER_CANCEL);
    }
}

static void pageTimer(LGFX_Sprite &s, const Snap &d) {
    if (d.timerOn) { timerRunning(s, d, true); return; }
    title(s, "טיימר");
    const int W = 104, H = 70, G = 12;
    int x0 = CX - (3 * W + 2 * G) / 2, y0 = 140;
    for (int i = 0; i < 6; i++) {
        int c = 2 - i % 3, r = i / 3;            // right to left
        int x = x0 + c * (W + G), y = y0 + r * (H + G);
        int id = B_TIMER_PRESET + PRESETS[i];
        s.fillSmoothRoundRect(x, y, W, H, 18, isPressed(id) ? C_TILE_HI : C_TILE);
        char n[4];
        snprintf(n, sizeof n, "%d", PRESETS[i]);
        num(s, n, x + W / 2, y + H / 2 - 9, C_TXT, false, 0.7f);
        he(s, "דקות", y + H / 2 + 20, C_MUTED, 0.55f, x + W / 2);
        addBtn(x, y, W, H, id);
    }
    he(s, "או פשוט לבקש: \"טיימר לעשר דקות\"", 336, C_DIM, 0.62f);
}

static void pageHome(LGFX_Sprite &s, const Snap &d, int scroll) {
    title(s, "הבית");
    if (!d.haOk) {
        he(s, "Home Assistant לא מחובר", 220, C_MUTED, 0.85f);
        he(s, "מחברים בפאנל הניהול", 262, C_DIM, 0.7f);
        return;
    }
    if (!d.nHa) { he(s, "לא נבחרו מכשירים", 230, C_MUTED, 0.85f); return; }
    const int W = 160, H = 74, G = 10;
    int x0 = CX - W - G / 2, y0 = 126;
    for (int k = 0; k < 6; k++) {
        int i = scroll * 2 + k;
        if (i >= d.nHa) break;
        const Model::HaItem &it = d.ha[i];
        int col = 1 - k % 2, row = k / 2;        // right column first
        int x = x0 + col * (W + G), y = y0 + row * (H + G);
        bool on = it.on && it.avail;
        uint32_t bg = !it.avail ? (uint32_t)0x111417 : on ? (uint32_t)0x4A3610 : C_TILE;
        if (isPressed(B_HA + i)) bg = mix(bg, 0xFFFFFF, 0.2f);
        s.fillSmoothRoundRect(x, y, W, H, 20, bg);
        deviceIcon(s, x + W - 28, y + H / 2, 17, it.kind, on ? C_ON : C_MUTED);
        // name (right aligned next to the icon) and state
        he(s, fit(s, it.name, W - 56, 0.62f), y + 26, it.avail ? C_TXT : C_DIM, 0.62f, x + (W - 46) / 2 + 4);
        const char *st = (pendingIdx == i && (int32_t)(pendingUntil - nowMs) > 0) ? "…" : it.state;
        he(s, fit(s, st, W - 56, 0.55f), y + 52, on ? C_ON : C_MUTED, 0.55f, x + (W - 46) / 2 + 4);
        addBtn(x, y, W, H, B_HA + i);
    }
    if (d.nHa > 6) he(s, "החלקה למעלה ולמטה לעוד", 392, C_DIM, 0.55f);
}

static void bar(LGFX_Sprite &s, int y, float v, uint32_t c) {
    const int W = 150;
    s.fillSmoothRoundRect(CX - W / 2, y - 5, W, 10, 5, (uint32_t)0x22313A);
    int w = max(10, (int)(W * v));
    s.fillSmoothRoundRect(CX + W / 2 - w, y - 5, w, 10, 5, c);       // fills from the right (RTL)
}

static void stepper(LGFX_Sprite &s, int y, const char *label, float v, int idDn, int idUp) {
    he(s, label, y - 26, C_MUTED, 0.65f);
    bar(s, y + 8, v, C_ACC);
    // + on the right, - on the left
    s.fillSmoothCircle(CX + 120, y + 8, 26, isPressed(idUp) ? C_TILE_HI : C_TILE);
    s.fillSmoothCircle(CX - 120, y + 8, 26, isPressed(idDn) ? C_TILE_HI : C_TILE);
    s.drawWideLine(CX + 110, y + 8, CX + 130, y + 8, 2.2f, C_TXT);
    s.drawWideLine(CX + 120, y - 2, CX + 120, y + 18, 2.2f, C_TXT);
    s.drawWideLine(CX - 130, y + 8, CX - 110, y + 8, 2.2f, C_TXT);
    addBtn(CX + 94, y - 18, 52, 52, idUp);
    addBtn(CX - 146, y - 18, 52, 52, idDn);
}

static void pageSettings(LGFX_Sprite &s, const Snap &d) {
    title(s, "הגדרות");
    stepper(s, 158, "בהירות", (d.brightness - 20) / 235.f, B_BRIGHT_DN, B_BRIGHT_UP);
    stepper(s, 250, "עוצמת קול", d.volume / 100.f, B_VOL_DN, B_VOL_UP);
    pill(s, CX + 8, 316, 128, 50, C_TILE, "Wi-Fi", C_TXT, B_WIFI);
    pill(s, CX - 136, 316, 128, 50, C_TILE, "כיבוי מסך", C_TXT, B_SCREEN_OFF);
    char info[64];
    snprintf(info, sizeof info, "Piko %s · %s", FW_VERSION, d.wifi ? d.ip : "ללא רשת");
    he(s, info, 398, C_DIM, 0.55f);
}

void drawPage(LGFX_Sprite &s, int page, const Snap &d, uint32_t now, int haScroll) {
    nowMs = now;
    nBtns = 0;
    s.fillScreen(0);
    switch (page) {
        case CLOCK: pageClock(s, d); break;
        case TIMER: pageTimer(s, d); break;
        case HOME: pageHome(s, d, haScroll); break;
        case SETTINGS: pageSettings(s, d); break;
        default: break;
    }
    drawDots(s, page);
    useText(s);
}

// ---------------------------------------------------------------- meeting
void drawMeeting(LGFX_Sprite &s, const char *title, uint32_t elapsedMs, float level, bool online, size_t buffered, uint32_t now, uint32_t limitSeconds) {
    nowMs = now;
    nBtns = 0;
    s.fillScreen(0);
    // "recording" with a blinking red dot
    bool blink = (now / 600) % 2;
    s.fillSmoothCircle(CX + 66, 92, 7, blink ? (uint32_t)0xFF4D5A : (uint32_t)0x5A1C22);
    he(s, "מתמלל פגישה", 92, 0xFF9AA2, 0.7f, CX - 8);
    if (title && title[0]) he(s, title, 146, C_TXT, 0.9f, CX, 2, 34);
    else he(s, "מזהה על מה הפגישה…", 150, C_DIM, 0.75f);
    uint32_t sec = elapsedMs / 1000;
    char t[16];
    snprintf(t, sizeof t, "%u:%02u:%02u", (unsigned)(sec / 3600), (unsigned)(sec / 60 % 60), (unsigned)(sec % 60));
    num(s, t, CX, 246, C_TXT, true, 0.72f);
    char budget[64];snprintf(budget,sizeof budget,"מתוך %u דקות לכל היותר",(unsigned)(limitSeconds/60));
    he(s,budget,288,C_DIM,0.55f);
    // listening: 9 bars from the mic level, the middle ones taller
    for (int i = 0; i < 9; i++) {
        float shape = 1.f - fabsf(i - 4) / 5.f;
        float wob = 0.55f + 0.45f * sinf(now / 90.f + i * 1.7f);
        int h = 6 + (int)(46 * level * shape * wob);
        uint32_t c = level > 0.05f ? C_ACC : C_DIM;
        s.fillSmoothRoundRect(CX - 4 * 16 - 3 + i * 16, 318 - h / 2, 7, h, 3, c);
    }
    if (!online) {
        char m[64];
        snprintf(m, sizeof m, "ללא רשת: %u שנ׳ במאגר זמני", (unsigned)(buffered / 32000));
        he(s, m, 356, C_AMBER, 0.6f);
    }
    pill(s, CX - 70, 376, 140, 52, (uint32_t)0x4A1820, "סיום", 0xFFC2C8, B_MEET_END, 0.9f);
    useText(s);
}

// ---------------------------------------------------------------- cards
void drawCard(LGFX_Sprite &s, const Snap &d, uint32_t now) {
    nowMs = now;
    nBtns = 0;
    const char *k = d.cardKind;
    if (!strcmp(k, "image")) {
        // the image itself is drawn by the caller (it lives in the model); here only the caption
        if (!d.imgReady) {
            s.fillScreen(0);
            he(s, "טוען תמונה…", CY, C_MUTED, 0.85f);
        }
        if (d.cardTitle[0]) {
            s.fillSmoothRoundRect(CX - 120, 392, 240, 40, 20, (uint32_t)0x0B1216);
            he(s, d.cardTitle, 412, C_TXT, 0.65f);
        }
        useText(s);
        return;
    }
    s.fillScreen(0);
    if (!strcmp(k, "time")) {
        he(s, d.cardBody[0] ? d.cardBody : d.date, 140, C_MUTED, 0.95f);
        bigClock(s, 240);
        if (d.weather.ok) {
            char t[64];
            snprintf(t, sizeof t, "%d° · %s", d.weather.t, d.weather.text);
            he(s, t, 336, C_DIM, 0.7f);
        }
    } else if (!strcmp(k, "weather")) {
        const Model::Weather &w = d.cardW.ok ? d.cardW : d.weather;
        if (w.city[0]) he(s, w.city, 100, C_MUTED, 0.8f);
        weatherIcon(s, CX, 168, 48, w.icon);
        char t[12];
        snprintf(t, sizeof t, "%d°", w.t);
        num(s, t, CX + 12, 262, C_TXT, true, 0.9f);
        char line[96];
        snprintf(line, sizeof line, "%s · מרגיש כמו %d°", w.text, w.feels);
        he(s, line, 334, C_MUTED, 0.75f);
        snprintf(line, sizeof line, "%d°-%d° · גשם %d%%", w.mn, w.mx, w.rain);
        he(s, line, 370, C_DIM, 0.7f);
        if (w.ttext[0]) {
            snprintf(line, sizeof line, "מחר: %s %d°-%d°", w.ttext, w.tmn, w.tmx);
            he(s, line, 404, C_DIM, 0.6f);
        }
    } else if (!strcmp(k, "timer")) {
        if (d.timerOn) timerRunning(s, d, false);
        else { he(s, "אין טיימר פעיל", CY, C_MUTED, 0.9f); }
    } else if (!strcmp(k, "device")) {
        const Model::HaItem &it = d.cardDev;
        bool on = it.on && it.avail;
        he(s, it.name, 130, C_TXT, 0.95f);
        s.fillSmoothCircle(CX, 238, 64, on ? (uint32_t)0x4A3610 : C_TILE);
        if (isPressed(B_CARD_DEVICE)) s.fillSmoothCircle(CX, 238, 64, C_TILE_HI);
        deviceIcon(s, CX, 238, 40, it.kind, on ? C_ON : C_MUTED);
        addBtn(CX - 64, 174, 128, 128, B_CARD_DEVICE);
        he(s, it.state, 336, on ? C_ON : C_MUTED, 0.85f);
        he(s, "נגיעה לשינוי", 380, C_DIM, 0.6f);
    } else {                                   // text
        if (d.cardTitle[0]) he(s, d.cardTitle, 110, C_ACC, 0.9f);
        he(s, d.cardBody, d.cardTitle[0] ? 160 : 140, C_TXT, 0.9f, CX, 7, 36);
    }
    useText(s);
}

}  // namespace screens
