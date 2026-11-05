#include "wifi_setup.h"
#include "theme.h"
#include <string.h>
#include "app/model.h"
#include "config.h"
#include "net/net.h"
#include "text_he.h"

// ---- layout (466 x 466 round screen)
static const int CX = SCREEN_W / 2;
static const int LIST_TOP = 104, LIST_BOT = 392, ROW_H = 56, ROW_W = 320;
static const int KW = 68, KH = 50, KG = 6;                 // keyboard keys
static const int KX0 = CX - (4 * KW + 3 * KG) / 2, KY0 = 134;
static const int BY = 360, BH = 48;                          // bottom row: shift | page | connect
static const int PW_Y = 86, PW_H = 38;

static const uint32_t C_BG = 0x000000, C_KEY = uiTheme::surface, C_KEY_HI = uiTheme::raised, C_TXT = uiTheme::text, C_MUTED = uiTheme::muted,
                      C_ACC = uiTheme::accent, C_ACC_INK = uiTheme::ink, C_BAD = 0xFF6A4D;

static const char *PAGES[4] = {"abcdefghijklmno", "pqrstuvwxyz.-_@", "1234567890!#$%&", "*+=/?:;,'\"()~^ "};
static const char *PAGE_NAME[4] = {"a-o", "p-z", "123", "#+="};

static uint16_t col(LGFX_Sprite &s, uint32_t rgb) { return s.color565(rgb >> 16, (rgb >> 8) & 255, rgb & 255); }

static void bidi(LGFX_Sprite &s, const char *t, int y, uint32_t c, float size = 1.f, int cx = CX) {
    s.setTextSize(size);
    drawBidiText(s, t, cx, SCREEN_H / 2, SCREEN_W / 2, y, 30, 1, c);
    s.setTextSize(1.f);
}

static void bars(LGFX_Sprite &s, int x, int y, int rssi, uint32_t c) {        // 4 signal bars, bottom-left at x,y
    int n = rssi > -56 ? 4 : rssi > -66 ? 3 : rssi > -76 ? 2 : 1;
    for (int i = 0; i < 4; i++) {
        int h = 5 + i * 4;
        s.fillRoundRect(x + i * 6, y - h, 4, h, 1, col(s, i < n ? c : 0x33424B));
    }
}

static void lock(LGFX_Sprite &s, int x, int y, uint32_t c) {                 // small padlock, centre x,y
    s.drawRoundRect(x - 4, y - 9, 8, 9, 3, col(s, c));
    s.fillRoundRect(x - 6, y - 3, 12, 9, 2, col(s, c));
}

void WifiSetup::begin(bool canCancel) {
    active_ = true;
    canCancel_ = canCancel;
    st_ = LIST;
    scroll_ = 0;
    nAps_ = 0;
    lastScanDone_ = millis();
    msg_[0] = 0;
    modelLock();
    if (model.wifiErr[0]) strlcpy(msg_, model.wifiErr, sizeof msg_);
    modelUnlock();
    requestScan(millis());
}

void WifiSetup::requestScan(uint32_t now) {
    modelLock();
    model.scanReq = true;
    modelUnlock();
    scanning_ = true;
    scanT0_ = now;
}

// ------------------------------------------------------------------ input
void WifiSetup::touch(bool down, int x, int y, uint32_t now) {
    if (down && !down_) { down_ = true; dragging_ = false; x0_ = x_ = x; y0_ = y_ = y; scrollStart_ = scroll_; }
    if (down) {
        x_ = x; y_ = y;
        if (st_ == LIST && abs(y_ - y0_) > 12) {
            dragging_ = true;
            int maxScroll = max(0, nAps_ * ROW_H - (LIST_BOT - LIST_TOP));
            scroll_ = constrain(scrollStart_ - (y_ - y0_), 0, maxScroll);
        }
    }
    if (!down && down_) {
        down_ = false;
        if (!dragging_ && abs(x_ - x0_) < 22 && abs(y_ - y0_) < 22) onTap(x0_, y0_, now);
    }
}

void WifiSetup::tap(int x, int y, uint32_t now) { onTap(x, y, now); }

void WifiSetup::onTap(int x, int y, uint32_t now) {
    if (st_ == CONNECTING) return;
    if (canCancel_ && y < 58 && abs(x - CX) < 40) { active_ = false; return; }            // close (top)
    if (st_ == LIST) {
        if (y > LIST_BOT + 6 && abs(x - CX) < 90) { requestScan(now); return; }           // rescan
        if (y >= LIST_TOP && y < LIST_BOT && abs(x - CX) < ROW_W / 2) {
            int i = (y - LIST_TOP + scroll_) / ROW_H;
            if (i >= 0 && i < nAps_) {
                strlcpy(ssid_, aps_[i].ssid, sizeof ssid_);
                open_ = aps_[i].open;
                pass_[0] = 0;
                msg_[0] = 0;
                if (open_) { st_ = CONNECTING; connectAt_ = now + 600; }
                else { st_ = KEYS; page_ = 0; shift_ = false; show_ = false; }
            }
        }
        return;
    }
    // keyboard
    if (y < PW_Y - 4) { st_ = LIST; msg_[0] = 0; return; }                                // tap the network name = back
    if (y < PW_Y + PW_H + 4) { show_ = !show_; return; }                                   // tap the field = show / hide
    for (int r = 0; r < 4; r++)
        for (int c = 0; c < 4; c++) {
            int kx = KX0 + c * (KW + KG), ky = KY0 + r * (KH + KG);
            if (x >= kx - KG / 2 && x < kx + KW + KG / 2 && y >= ky - KG / 2 && y < ky + KH + KG / 2) {
                pressKey(r * 4 + c, now);
                return;
            }
        }
    if (y >= BY && y < BY + BH) {
        int w0 = 80, w1 = 80, w2 = 110, gx = CX - (w0 + w1 + w2 + 2 * KG) / 2;
        if (x < gx + w0) pressKey(16, now);
        else if (x < gx + w0 + KG + w1) pressKey(17, now);
        else pressKey(18, now);
    }
}

void WifiSetup::pressKey(int k, uint32_t now) {
    pressedKey_ = k;
    pressedUntil_ = now + 140;
    size_t n = strlen(pass_);
    if (k == 15) { if (n) pass_[n - 1] = 0; return; }                                       // backspace
    if (k < 15) {
        char ch = PAGES[page_][k];
        if (shift_ && ch >= 'a' && ch <= 'z') ch -= 32;
        if (n + 1 < sizeof pass_) { pass_[n] = ch; pass_[n + 1] = 0; }
        msg_[0] = 0;
        return;
    }
    if (k == 16) { shift_ = !shift_; return; }
    if (k == 17) { page_ = (page_ + 1) % 4; return; }
    if (k == 18) {
        if (strlen(pass_) < 8) { strlcpy(msg_, "הסיסמה קצרה מדי (לפחות 8 תווים)", sizeof msg_); return; }
        st_ = CONNECTING;
        connectAt_ = now + 600;                       // draw "connecting" first, then save + restart
    }
}

// ------------------------------------------------------------------ drawing
void WifiSetup::render(LGFX_Sprite &s, uint32_t now) {
    // new scan results?
    modelLock();
    if (model.scanSeq != seenSeq_) {
        seenSeq_ = model.scanSeq;
        // merge with what earlier scans found: a weak network that one scan missed stays in the list for 2 minutes
        for (int j = 0; j < model.nAps; j++) {
            int k = -1;
            for (int i = 0; i < nAps_; i++) if (!strcmp(aps_[i].ssid, model.aps[j].ssid)) k = i;
            if (k < 0 && nAps_ < 24) k = nAps_++;
            if (k < 0) continue;
            strlcpy(aps_[k].ssid, model.aps[j].ssid, sizeof aps_[k].ssid);
            aps_[k].rssi = model.aps[j].rssi;
            aps_[k].open = model.aps[j].open;
            seenAt_[k] = now;
        }
        int w = 0;
        for (int i = 0; i < nAps_; i++)
            if (now - seenAt_[i] < 120000) { aps_[w] = aps_[i]; seenAt_[w] = seenAt_[i]; w++; }
        nAps_ = w;
        for (int a = 1; a < nAps_; a++)                                   // strongest first
            for (int b = a; b > 0 && aps_[b].rssi > aps_[b - 1].rssi; b--) {
                auto t = aps_[b]; aps_[b] = aps_[b - 1]; aps_[b - 1] = t;
                uint32_t u = seenAt_[b]; seenAt_[b] = seenAt_[b - 1]; seenAt_[b - 1] = u;
            }
        scanning_ = false;
        lastScanDone_ = now;
    }
    modelUnlock();
    if (scanning_ && now - scanT0_ > 15000) scanning_ = false;
    if (st_ == LIST && !scanning_ && !down_ && now - lastScanDone_ > 15000 && now - scanT0_ > 15000) requestScan(now);   // keep looking

    s.fillScreen(0);
    if (canCancel_ && st_ != CONNECTING) {                                               // close button
        s.drawLine(CX - 9, 31, CX + 9, 49, col(s, C_MUTED));
        s.drawLine(CX + 9, 31, CX - 9, 49, col(s, C_MUTED));
    }
    if (st_ == LIST) drawList(s, now);
    else if (st_ == KEYS) drawKeys(s, now);
    else {
        bidi(s, "מתחבר ל-", 190, C_MUTED);
        s.setTextDatum(lgfx::middle_center);
        s.setTextColor(col(s, C_TXT));
        bidi(s, ssid_, 228, C_TXT);
        for (int i = 0; i < 3; i++) {                                                   // dots
            float a = 0.5f + 0.5f * sinf(now / 180.f - i * 0.9f);
            s.fillCircle(CX - 24 + i * 24, 280, 6, col(s, a > 0.6f ? C_ACC : 0x2B4A55));
        }
        bidi(s, "המכשיר יופעל מחדש ויתחבר", 330, C_MUTED, 0.75f);
        if (connectAt_ && (int32_t)(now - connectAt_) >= 0) {
            connectAt_ = 0;
            modelLock();
            model.wifiErr[0] = 0;
            modelUnlock();
            netSetWifi(ssid_, open_ ? "" : pass_);          // saves to NVS and restarts
        }
    }
}

void WifiSetup::drawList(LGFX_Sprite &s, uint32_t now) {
    bidi(s, "בחר רשת Wi-Fi", msg_[0] ? 66 : 76, C_TXT);
    if (msg_[0]) bidi(s, msg_, 94, C_BAD, 0.58f);                    // under the title: the rescan button stays
    if (scanning_ && nAps_ == 0) {
        bidi(s, "מחפש רשתות…", 233, C_MUTED);
        float a = now / 160.f;
        for (int i = 0; i < 8; i++) {
            float t = a - i * 0.6f;
            s.fillCircle(CX + 30 * cosf(i * 0.785f), 290 + 30 * sinf(i * 0.785f), 4,
                         col(s, (int)(t) % 8 == 0 ? C_ACC : 0x22313A));
        }
        return;
    }
    if (nAps_ == 0) { bidi(s, "לא נמצאו רשתות", 233, C_MUTED); }
    s.setClipRect(0, LIST_TOP, SCREEN_W, LIST_BOT - LIST_TOP);
    for (int i = 0; i < nAps_; i++) {
        int y = LIST_TOP + i * ROW_H - scroll_;
        if (y + ROW_H < LIST_TOP || y > LIST_BOT) continue;
        int x = CX - ROW_W / 2;
        uiTheme::button(s,x,y+3,ROW_W,ROW_H-6,14,C_KEY);
        int cy = y + ROW_H / 2;
        bars(s, x + 16, cy + 9, aps_[i].rssi, C_ACC);                 // left: signal
        if (!aps_[i].open) lock(s, x + 52, cy + 2, C_MUTED);
        s.setTextSize(0.8f);
        s.setTextColor(col(s, C_TXT));
        s.setTextDatum(lgfx::middle_right);
        // SSIDs are mostly Latin: right-aligned plain text, clipped to the row
        s.setClipRect(x + 66, max(LIST_TOP, y), ROW_W - 80, ROW_H);
        s.drawString(aps_[i].ssid, x + ROW_W - 16, cy + 1);
        s.setClipRect(0, LIST_TOP, SCREEN_W, LIST_BOT - LIST_TOP);
        s.setTextSize(1.f);
    }
    s.clearClipRect();
    // scroll hint + rescan
    if (nAps_ * ROW_H > LIST_BOT - LIST_TOP) {
        int total = nAps_ * ROW_H, vis = LIST_BOT - LIST_TOP;
        int h = vis * vis / total, y = LIST_TOP + (vis - h) * scroll_ / max(1, total - vis);
        s.fillRoundRect(CX + ROW_W / 2 + 8, y, 4, h, 2, col(s, 0x33424B));
    }
    uiTheme::button(s,CX-80,400,160,38,19,scanning_?uiTheme::raised:C_KEY);
    bidi(s, scanning_ ? "סורק…" : "סריקה מחדש", 420, scanning_ ? C_MUTED : C_ACC, 0.75f);
}

void WifiSetup::drawKeys(LGFX_Sprite &s, uint32_t now) {
    // network name (tap = back) and the password field (tap = show / hide)
    s.setTextSize(0.75f);
    s.setTextDatum(lgfx::middle_center);
    s.setTextColor(col(s, C_MUTED));
    char t[48];
    snprintf(t, sizeof t, "< %s", ssid_);
    s.drawString(t, CX, 62);
    s.drawRoundRect(CX - 150, PW_Y, 300, PW_H, 10, col(s, C_ACC));
    char shown[72];
    size_t n = strlen(pass_);
    if (show_) strlcpy(shown, pass_, sizeof shown);
    else { size_t m = min(n, sizeof shown - 1); memset(shown, '*', m); shown[m] = 0; }
    s.setTextSize(0.85f);
    s.setTextColor(col(s, n ? C_TXT : C_MUTED));
    s.setTextDatum(lgfx::middle_left);
    s.setClipRect(CX - 142, PW_Y + 2, 284, PW_H - 4);
    int w = s.textWidth(n ? shown : "סיסמה");
    int tx = w > 276 ? CX + 138 - w : CX - w / 2;            // keep the end (the caret) visible
    s.drawString(n ? shown : "", tx, PW_Y + PW_H / 2 + 1);
    if (!n) bidi(s, "סיסמה", PW_Y + PW_H / 2 + 1, C_MUTED, 0.8f);
    if ((now / 500) % 2) s.fillRect(n ? min(tx + w + 2, CX + 140) : CX + 30, PW_Y + 9, 2, PW_H - 18, col(s, C_ACC));
    s.clearClipRect();
    // grid
    for (int k = 0; k < 16; k++) {
        int r = k / 4, c = k % 4, kx = KX0 + c * (KW + KG), ky = KY0 + r * (KH + KG);
        bool hi = pressedKey_ == k && (int32_t)(pressedUntil_ - now) > 0;
        uiTheme::button(s,kx,ky,KW,KH,12,hi?C_KEY_HI:C_KEY,hi);
        int mx = kx + KW / 2, my = ky + KH / 2;
        if (k == 15) {                                         // backspace icon
            uint16_t ic = col(s, C_TXT);
            s.fillTriangle(mx - 16, my, mx - 7, my - 9, mx - 7, my + 9, ic);
            s.fillRect(mx - 7, my - 9, 22, 18, ic);
            s.drawLine(mx - 1, my - 4, mx + 8, my + 4, col(s, C_KEY));
            s.drawLine(mx + 8, my - 4, mx - 1, my + 4, col(s, C_KEY));
            continue;
        }
        char ch = PAGES[page_][k];
        if (shift_ && ch >= 'a' && ch <= 'z') ch -= 32;
        s.setTextColor(col(s, C_TXT));
        s.setTextDatum(lgfx::middle_center);
        if (ch == ' ') { bidi(s, "רווח", my, C_TXT, 0.6f, mx); continue; }
        char str[2] = {ch, 0};
        s.setTextSize(1.f);
        s.drawString(str, mx, my + 1);
    }
    // bottom row: shift | next page | connect
    int w0 = 80, w1 = 80, w2 = 110, gx = CX - (w0 + w1 + w2 + 2 * KG) / 2;
    bool hs = pressedKey_ == 16 && (int32_t)(pressedUntil_ - now) > 0;
    uiTheme::button(s,gx,BY,w0,BH,14,shift_?C_ACC:(hs?C_KEY_HI:C_KEY),hs);
    uint16_t sc = col(s, shift_ ? C_ACC_INK : C_TXT);
    int sx = gx + w0 / 2, sy = BY + BH / 2;
    s.fillTriangle(sx, sy - 12, sx - 11, sy + 1, sx + 11, sy + 1, sc);
    s.fillRect(sx - 5, sy + 1, 10, 9, sc);
    bool hp = pressedKey_ == 17 && (int32_t)(pressedUntil_ - now) > 0;
    uiTheme::button(s,gx+w0+KG,BY,w1,BH,14,hp?C_KEY_HI:C_KEY,hp);
    s.setTextSize(0.8f);
    s.setTextDatum(lgfx::middle_center);
    s.setTextColor(col(s, C_ACC));
    s.drawString(PAGE_NAME[(page_ + 1) % 4], gx + w0 + KG + w1 / 2, BY + BH / 2 + 1);
    int ox = gx + w0 + w1 + 2 * KG;
    uiTheme::button(s,ox,BY,w2,BH,14,C_ACC);
    s.setTextColor(col(s, C_ACC_INK));
    s.setTextDatum(lgfx::middle_center);
    s.setTextSize(0.8f);
    s.drawString("OK", ox + w2 / 2, BY + BH / 2 + 1);
    s.setTextSize(1.f);
    if (msg_[0]) bidi(s, msg_, 426, C_BAD, 0.6f);
    else {                                                     // page dots
        for (int i = 0; i < 4; i++) s.fillCircle(CX - 18 + i * 12, 424, 3, col(s, i == page_ ? C_ACC : 0x33424B));
    }
}
