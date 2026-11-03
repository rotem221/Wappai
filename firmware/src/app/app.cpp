#include "pip_storage.h"
#include "shake_detector.h"
// The creature's "body": input (buttons, touch, IMU), power states, timers and drawing.
// Runs on core 1 from loop(); the network task (core 0) talks to it through `model`.
#include "app.h"
#include <WiFi.h>
#include <esp_sleep.h>
#include <driver/rtc_io.h>
#include <time.h>
#include <Preferences.h>
#include "audio/audio.h"
#include "board.h"
#include "board/pmu.h"
#include "config.h"
#include "face/face.h"
#include "ui/wifi_setup.h"
#include "model.h"
#include "provision/ble.h"
#include "net/net.h"
#include "ui/ring.h"
#include "ui/screens.h"
#include "ui/text_he.h"

static LGFX lcd;
static LGFX_Sprite scr(&lcd);
static Face face;
static Battery bat;

enum Power { P_ACTIVE, P_DIM, P_OFF };
static Power power = P_ACTIVE;
static uint32_t offSince = 0;
// Pocket mode: the screen is off and the device is not facing up (in a pocket or bag, face down). Then the touch
// screen and motion can't wake it (no pocket dials), speech plays with the screen off, and it deep-sleeps sooner.
static bool pocket = false;
static bool lowPower = false;
static bool manualLocked=false,bootUnlockConsumed=false,pwrWakeConsumed=false,bootHoldStarted=false;
static ShakeDetector shakeDetector;
static int pwrSim=-1;
static bool readPowerButton(){return pwrSim<0?pwrButtonDown():pwrSim==1;}
static bool imuPower = true;           // serial 'imupower 0': motion never turns the screen off / on (desk tests)          // CPU 80 MHz + Wi-Fi max modem sleep while the screen is off
static int rssiCache = 0;

// interaction
static bool bootDown = false, recording = false, touchPtt = false;
static bool gallery = false, galleryHold = false;
static uint8_t galleryPip = 0;
static int pipCount(){return PIXEL_RIG_COUNT+(model.customPip?1:0);}
static const char *pipName(int i){return i==PIXEL_RIG_COUNT && model.customPip?model.customPip->name:PIXEL_RIG_NAMES[i];}
static bool meeting = false;                 // continuous recording for transcription
static uint32_t meetingT0 = 0, lastBootTap = 0;
static uint32_t bootT0 = 0, recT0 = 0;
static bool touchDown = false;
static int tx0 = 0, ty0 = 0, tx = 0, ty = 0;
static uint32_t touchT0 = 0;
static bool pwrDown = false;
static WifiSetup wsetup;
static volatile int bootSimReq = -2;               // on-device Wi-Fi setup screen (no Wi-Fi, or PWR held 2 s)

// side pages (swipe: clock, timer, home, settings) and cards the server shows (time, weather, camera...)
using namespace screens;
static int page = FACE;
static uint32_t pageActiveT = 0;               // last touch on a page: back to the face after a minute
static bool cardOn = false;
static uint32_t cardUntil = 0, cardImgBase = 0, drawnImg = 0;
static Model::HaItem deviceBadge{};
static bool badgePending=false,badgeDrawn=false;
static uint32_t badgeUntil=0;
static char livePartial[320]="";
static const Rect BADGE_RECT={90,78,376,112};
static bool screenDirty = true;                // pages / cards: redraw now
static bool faceNeedsClear = false;            // back to the face: wipe what the page left
static int haScroll = 0;
static uint32_t seenInfo = 0, seenHa = 0, seenImg = 0;
static char toast[96] = "";
static uint32_t toastUntil = 0;
static Preferences uiPrefs;

// presentation
static char sub[320] = "";
static uint32_t subUntil = 0;
static bool subDrawn = false;
static uint32_t statusUntil = 0;
static bool statusDrawn = false;
static RingMode ringMode = RING_NONE;
static uint32_t ringT0 = 0;
static bool ringDrawn = false;
static uint32_t emotionHoldUntil = 0;     // when to fall back to the "home" emotion
static char serverEmotion[24] = "idle";
static uint32_t lastServerOk = 0;
static bool wasServer = false;

// timer / alarm
static bool alarmOn = false;
static uint32_t alarmT0 = 0, lastAlarmBeep = 0;
static char alarmLabel[64] = "";

static const int SUB_Y0 = 365, SUB_LH = 30, SUB_LINES = 2;
static const Rect SUB_RECT = {75, 348, 391, 413};
static const Rect STATUS_RECT = {100, 38, 366, 78};

// Time since t, never negative: several timestamps (recT0, ringT0, meetingT0...) are taken with millis() inside a loop
// iteration that already captured `now`, so a plain `now - t` wraps to ~49 days and fires every timeout at once.
static inline uint32_t since(uint32_t now, uint32_t t) {
    int32_t d = (int32_t)(now - t);
    return d < 0 ? 0 : (uint32_t)d;
}

void markActivity() {
    modelLock();
    model.lastActivity = millis();
    modelUnlock();
}

static void setBrightness(uint8_t v) { lcd.panelBrightness(v); }

static void setLowPower(bool on) {
    if (on == lowPower) return;
    lowPower = on;
    setCpuFrequencyMhz(on ? 80 : 240);
    WiFi.setSleep(on ? WIFI_PS_MAX_MODEM : WIFI_PS_MIN_MODEM);   // longer radio naps; replies arrive ~0.3 s later
}

// Battery saver: on battery below 20 % the screen is never brighter than 90.
static uint8_t activeBrightness() {
    uint8_t b = model.brightness;
    if (bat.present && !bat.usb && bat.pct >= 0 && bat.pct < 20 && b > 90) b = 90;
    return b;
}

// user = a person did something (button, lift, touch). Without it (server speech, timer) a device in the pocket
// stays dark: the sound plays, the screen doesn't light up inside the pocket.
static void wake(bool user = false) {
    if(manualLocked)return;
    if (user && pocket) { pocket = false; Serial.println("pocket: off"); }
    markActivity();
    if (pocket) return;
    setLowPower(false);
    if (power == P_OFF) {
        lcd.panelSleep(false);
        ringDrawn = true;                 // force full redraw
    }
    if (power != P_ACTIVE) setBrightness(activeBrightness());
    power = P_ACTIVE;
}

static void showFace();

static void screenOff(uint32_t now) {
    if (power == P_OFF) return;
    showFace();
    power = P_OFF;
    offSince = now;
    lcd.panelSleep(true);
    setLowPower(!meeting);                // the mic stream of a meeting keeps full speed
}

static void showStatus(uint32_t ms = 4000) { statusUntil = millis() + ms; }

// While Piko speaks the face (with subtitles) is shown; a card waits and appears when the speech ends.
static bool cardSpoke = false;                 // speech played while this card was up: restart its time after it
static uint16_t cardTtlS = 12;
static bool cardHeld() { return cardOn && (audioPlaying() || recording); }
static bool onScreens() { return meeting || (cardOn && !cardHeld()) || page != FACE; }

static void setPage(int p) {
    if (meeting) return;                                   // the meeting screen stays until it ends
    p = (p + NPAGES) % NPAGES;
    if (p == page && !cardOn) return;
    if (p == FACE) faceNeedsClear = true;
    page = p;
    cardOn = false;
    screenDirty = true;
    haScroll = 0;
    pageActiveT = millis();
}

static void showFace() { if (cardOn || page != FACE) setPage(FACE); }

static void homeEmotion() {
    const char *e = "idle";
    if (!model.server && millis() - lastServerOk > 20000) e = "curious";
    else if (bat.present && bat.pct >= 0 && bat.pct < 15 && !bat.usb) e = "low_battery";
    else {
        time_t now = time(nullptr);
        struct tm lt;
        localtime_r(&now, &lt);
        uint32_t idle = millis() - model.lastActivity;
        if (now > 1700000000 && (lt.tm_hour >= 23 || lt.tm_hour < 6) && idle > 60000) e = "sleepy";
        else if (idle > 5 * 60000) e = "bored";
    }
    if (face.customExpression() || strcmp(face.emotionName(), e)) face.setEmotion(e);
}

// Explicit locking is independent of automatic dim/sleep and pocket detection.
static void setManualLock(bool locked){
    manualLocked=locked;uiPrefs.putBool("locked",locked);
    if(locked){audioStop();netSend("{\"type\":\"interrupt\"}");screenOff(millis());}
    else wake(true);
    Serial.printf("lock: %d\n",locked);
}
static bool shakeAllowed(){return model.shakeReaction && !manualLocked && !pocket && power!=P_OFF && !recording && !meeting && !alarmOn && !audioPlaying() && !model.assetBusy && ringMode==RING_NONE;}
static void reactToShake(){
    if(!shakeAllowed())return;
    face.setEmotion("dizzy");face.gesture("shake");emotionHoldUntil=millis()+3500;
    strlcpy(sub,"די לנער אותי!",sizeof sub);subUntil=millis()+3500;
    if(model.characterSounds)audioShakeComplaint();
    Serial.println("shake: reaction");
}

// ------------------------------------------------------------------ push-to-talk
static void startRecording() {
    if (manualLocked || recording || model.assetBusy) return;
    wake(true);
    showFace();
    audioStop();
    audioChirp(true);
    // The listening indicator is local; capture starts without a blocking chirp delay.
    recording = true;
    recT0 = millis();
    ringMode = RING_REC;
    ringT0 = recT0;
    face.setEmotion("listening");
    face.setAttention(true);
    subUntil = 0;sub[0]=0;livePartial[0]=0;badgeUntil=0;
    modelLock(); model.recording = true; model.subNew = false; modelUnlock();
    Serial.printf("ptt: start (%s)\n", touchPtt ? "touch" : "boot");
    netMicStart();
}

static void stopRecording() {
    if (!recording) return;
    recording = false;livePartial[0]=0;
    Serial.printf("ptt: stop after %lu ms at %lu\n", (unsigned long)(millis() - recT0), (unsigned long)millis());
    netMicStop();
    audioChirp(false);
    face.setAttention(false);
    face.setEmotion("thinking");
    ringMode = RING_THINK;
    ringT0 = millis();
    emotionHoldUntil = millis() + 20000;
    strlcpy(sub,"חושב…",sizeof sub);subUntil=emotionHoldUntil;
    modelLock(); model.recording = false; modelUnlock();
}

static void startMeeting() {
    if(!netMeetingReady()){strlcpy(sub,"אין די זיכרון להקלטת פגישה",sizeof sub);subUntil=millis()+6000;return;}
    if (manualLocked || meeting || recording || netRecordingPending() || !model.server) return;
    wake(true);
    showFace();
    audioStop();
    audioChirp(true);
    delay(120);
    meeting = true;
    meetingT0 = millis();
    screenDirty = true;
    face.setEmotion("listening");
    face.setAttention(true);
    modelLock(); model.recording = true; modelUnlock();
    netMicStart(true);
}

static void stopMeeting() {
    if (!meeting) return;
    meeting = false;
    faceNeedsClear = true;
    netMicStop();
    wake();
    audioChirp(false);
    face.setAttention(false);
    face.setEmotion("working");
    ringMode = RING_THINK;
    ringT0 = millis();
    emotionHoldUntil = millis() + 60000;
    snprintf(sub, sizeof sub, "שומר את ההקלטה…");
    subUntil = millis() + 8000;
    modelLock(); model.recording = false; modelUnlock();
}

// ------------------------------------------------------------------ inputs
// Short BOOT press: silence the alarm first (its beeps also count as "playing"), else hush speech, else show status.
static void bootTap() {
    if (alarmOn) { alarmOn = false; audioStop(); }
    else if (audioPlaying()) { audioStop(); netSend("{\"type\":\"interrupt\"}"); }
    else showStatus();
}

// ------------------------------------------------------------------ pages and cards: buttons
static void sendSetting(const char *key, int v) {
    char m[64];
    snprintf(m, sizeof m, "{\"type\":\"setting\",\"%s\":%d}", key, v);
    netSend(m);
}

static void doButton(int id, uint32_t now) {
    if (id >= B_TIMER_PRESET && id < B_TIMER_PRESET + 100) {
        uint32_t ms = (id - B_TIMER_PRESET) * 60000UL;
        modelLock();
        model.timerOn = true; model.timerTotal = ms; model.timerEnd = now + ms; model.timerLabel[0] = 0;
        modelUnlock();
        char m[80];
        snprintf(m, sizeof m, "{\"type\":\"event\",\"name\":\"timer_set\",\"seconds\":%u}", (unsigned)(ms / 1000));
        netSend(m);
        audioBeep();
    } else if (id == B_TIMER_ADD) {
        modelLock(); if (model.timerOn) { model.timerEnd += 60000; model.timerTotal += 60000; } modelUnlock();
    } else if (id == B_TIMER_CANCEL) {
        modelLock(); model.timerOn = false; modelUnlock();
        netSend("{\"type\":\"event\",\"name\":\"timer_cancel\"}");
    } else if (id >= B_HA && id < B_HA + 12) {
        int i = id - B_HA;
        char m[96] = "";
        modelLock();
        if (i < model.nHa) snprintf(m, sizeof m, "{\"type\":\"ha_toggle\",\"id\":\"%s\"}", model.ha[i].id);
        modelUnlock();
        if (m[0]) { netSend(m); haPending(i, now); }
    } else if (id == B_BRIGHT_DN || id == B_BRIGHT_UP) {
        int b = constrain((int)model.brightness + (id == B_BRIGHT_UP ? 25 : -25), 20, 255);
        model.brightness = b;
        setBrightness(activeBrightness());
        uiPrefs.putUChar("bright", b);
        sendSetting("brightness", b);
    } else if (id == B_VOL_DN || id == B_VOL_UP) {
        int v = constrain((int)model.volume + (id == B_VOL_UP ? 10 : -10), 0, 100);
        model.volume = v;
        audioSetVolume(v);
        audioBeep();                                 // hear the new level
        uiPrefs.putUChar("vol", v);
        sendSetting("volume", v);
    } else if (id == B_WIFI) {
        setPage(FACE);
        wsetup.begin(true);
    } else if (id == B_SCREEN_OFF) {
        screenOff(now);
    }
}

static void screenTap(int dx, int dy, uint32_t now) {
    pageActiveT = now;
    if (meeting) {
        if (abs(dx) < 25 && abs(dy) < 25 && hit(tx, ty) == B_MEET_END) { pressed(B_MEET_END, now); stopMeeting(); }
        return;
    }
    if (cardOn && dy > 70) { showFace(); return; }                  // swipe down closes a card
    if (page == HOME && !cardOn && abs(dy) > 50) {                  // more devices: scroll by a row
        int n;
        modelLock(); n = model.nHa; modelUnlock();
        int maxScroll = n > 6 ? (n - 5) / 2 : 0;
        haScroll = constrain(haScroll + (dy < 0 ? 1 : -1), 0, maxScroll);
        screenDirty = true;
        return;
    }
    if (abs(dx) > 25 || abs(dy) > 25) return;
    int id = hit(tx, ty);
    if (cardOn) {
        if (id == B_CARD_DEVICE) {
            char m[96];
            modelLock(); snprintf(m, sizeof m, "{\"type\":\"ha_toggle\",\"id\":\"%s\"}", model.cardDev.id); modelUnlock();
            netSend(m);
            pressed(id, now);
            cardUntil = now + 8000;
            screenDirty = true;
        } else showFace();                                          // a tap anywhere else closes the card
        return;
    }
    if (id == B_NONE) return;
    pressed(id, now);
    screenDirty = true;
    doButton(id, now);
}

static void pollInputs(uint32_t now) {
    // BOOT: hold to talk, short press = stop speaking / show status
    // debounced: a change counts only after it has been stable for 30 ms (contact bounce, light presses)
    static bool bRaw = false, bStable = false;
    static uint32_t bChange = 0;
    static int bootSim = -1;                     // serial 'bootsim 1|0|-1' presses BOOT for tests
    if (bootSimReq != -2) { bootSim = bootSimReq; bootSimReq = -2; }
    bool raw = bootSim >= 0 ? bootSim == 1 : digitalRead(PIN_BOOT) == LOW;
    if (raw != bRaw) {
        bRaw = raw; bChange = now;
        Serial.printf("boot: raw %s\n", raw ? "down" : "up");
        netSend(raw ? "{\"type\":\"event\",\"name\":\"boot_down\"}" : "{\"type\":\"event\",\"name\":\"boot_up\"}");   // visible in the server log
    }
    if (now - bChange >= 30) bStable = bRaw;
    bool b = bStable;
    if(!raw && !b && !bootDown)bootUnlockConsumed=false;
    if (b && !bootDown) { bootDown = true; bootHoldStarted=false; bootT0 = now; if(manualLocked){setManualLock(false);bootUnlockConsumed=true;}else wake(true); }
    if (model.holdToTalk && !bootHoldStarted && !bootUnlockConsumed && !provisioningPrompt() && !gallery && b && bootDown && !recording && !meeting && since(now, bootT0) > PTT_HOLD_MS) {startRecording();bootHoldStarted=recording;}
    if (b && bootDown && meeting) bootT0 = now;               // no push-to-talk while a meeting records
    if (!b && bootDown) {
        bootDown = false;
        if (bootUnlockConsumed) {bootUnlockConsumed=false;}
        else if (provisioningConfirm(true)) { faceNeedsClear = true; }
        else if (gallery) { gallery = false; faceNeedsClear = true; face.setPip(model.pip, model.pipColor); }
        else if (meeting) stopMeeting();
        else if (model.holdToTalk) { if (recording) stopRecording(); else bootTap(); }
        else if (recording) stopRecording();
        else { netSend("{\"type\":\"interrupt\"}"); startRecording(); }
    }
    if (recording && since(now, recT0) > MAX_REC_MS) stopRecording();
    if (meeting && (since(now, meetingT0) > MAX_MEETING_MS || audioMicCapacityStop())) {
        if(audioMicCapacityStop()){
            netSend(String("{\"type\":\"event\",\"name\":\"recording_gap\",\"bytes\":")+String(audioMicDropped())+"}");
        }
        stopMeeting();
        if(audioMicCapacityStop()){strlcpy(sub,"הזיכרון מלא. ההקלטה נשמרה",sizeof sub);subUntil=millis()+15000;}
    }

    // touch
    lgfx::touch_point_t tp;
    bool t = lcd.getTouch(&tp);
    // Locked while the screen is off or the device is in a pocket: touches can't wake it or start anything.
    // (An ongoing touch push-to-talk keeps working until the finger lifts.)
    if ((manualLocked || power == P_OFF || pocket) && !touchPtt) { t = false; touchDown = false; }
    // The touch controller drops single reports while a finger is held: count it as lifted only after 200 ms
    static uint32_t touchLost = 0;
    if (!t && touchDown) {
        if (!touchLost) touchLost = now;
        if (now - touchLost < 200) { t = true; tp.x = tx; tp.y = ty; }
    } else touchLost = 0;
    if (t && !touchDown) { touchDown = true; touchT0 = now; tx0 = tx = tp.x; ty0 = ty = tp.y; wake(true); }
    if (t) { tx = tp.x; ty = tp.y; }
    if (touchDown && t && !recording && !meeting && page == FACE && since(now, touchT0) > TOUCH_PTT_MS && abs(tx - tx0) < 30 && abs(ty - ty0) < 30) {
        if (!galleryHold) { gallery = true; galleryHold = true; galleryPip = model.pip; faceNeedsClear = true; }
    }
    if (touchDown && !t) {
        touchDown = false;
        int dx = tx - tx0, dy = ty - ty0;
        if (gallery) {
            if (abs(dx) > 55) { galleryPip = (galleryPip + (dx > 0 ? 1 : pipCount()-1)) % pipCount(); face.setPip(galleryPip); faceNeedsClear = true; }
            else if (!galleryHold && abs(dx) < 20 && abs(dy) < 20) {
                model.pip = galleryPip; model.pipColor = 0;
                uiPrefs.putUChar("pip", model.pip); uiPrefs.putUInt("pipColor",0);
                face.setPip(model.pip); gallery = false; faceNeedsClear = true;
                netSend(String("{\"type\":\"pip.selected\",\"pip\":") + model.pip + ",\"pip_id\":\"" + (model.pip==PIXEL_RIG_COUNT && model.customPip?model.customPip->pip: model.pip==0?"pip":model.pip==1?"nori":"orbit") + "\"}");
            }
            galleryHold = false;
        }
        else if (touchPtt) { touchPtt = false; stopRecording(); }
        else if (alarmOn) { alarmOn = false; audioStop(); }
        else if (abs(dx) > 70 && abs(dx) > abs(dy) * 1.4f) {    // side swipe: next / previous page (round robin)
            setPage(page + (dx > 0 ? 1 : -1));
            Serial.printf("page: %d\n", page);
        }
        else if (onScreens()) screenTap(dx, dy, now);
        else if (dy > 70 && abs(dx) < 80) {                     // swipe down: hush
            audioStop();
            netSend("{\"type\":\"interrupt\"}");
        } else if (abs(dx) < 20 && abs(dy) < 20) {               // tap = pet
            face.gesture("pop");
            face.lookAt((tx - SCREEN_W / 2) / (float)(SCREEN_W / 2), (ty - SCREEN_H / 2) / (float)(SCREEN_H / 2), 1500);
            if (!audioPlaying()) { face.setEmotion("happy"); emotionHoldUntil = now + 2500; }
            showStatus(2500);
            char m[96];
            snprintf(m, sizeof m, "{\"type\":\"touch\",\"gesture\":\"tap\",\"x\":%d,\"y\":%d}", tx, ty);
            netSend(m);
        }
    }

    // PWR key (through the expander): short press toggles the screen
    static uint32_t lastPwrPoll = 0;
    if (now - lastPwrPoll > 60) {
        lastPwrPoll = now;
        // PWR: short press toggles the screen; hold 2 s = Wi-Fi setup screen
        static uint32_t pwrT0 = 0;
        static bool pwrLong = false;
        bool p = readPowerButton();
        if(!p && !pwrDown)pwrWakeConsumed=false;
        if (p && !pwrDown) { pwrDown = true; pwrT0 = now; pwrLong = false; netSend("{\"type\":\"event\",\"name\":\"pwr\"}"); }
        if (p && pwrDown && !pwrLong && !pwrWakeConsumed && !manualLocked && since(now, pwrT0) > 2000) { pwrLong = true; wake(true); wsetup.begin(true); }
        if (!p && pwrDown) {
            pwrDown = false;
            if(pwrWakeConsumed){pwrWakeConsumed=false;}
            else if (!pwrLong) {
                if(manualLocked)setManualLock(false);
                else if(power==P_OFF || pocket)wake(true);
                else if(!recording && !meeting)setManualLock(true);
            }
        }
    }
}

// IMU: tilt follows gravity, shake = dizzy, face-down = sleep, pick-up = wake
static void pollImu(uint32_t now) {
    static uint32_t last = 0, downSince = 0;
    static Accel prev{0, 0, 0, false};
    uint32_t every = power == P_OFF ? 250 : 40;
    if (now - last < every) return;
    last = now;
    Accel a = imuRead();
    if (!a.ok) return;
    // self-calibrating scale: at rest the magnitude must be 1 g
    static float gAvg = 1.f;
    float raw = sqrtf(a.x * a.x + a.y * a.y + a.z * a.z);
    if (prev.ok && fabsf(raw - gAvg * sqrtf(prev.x * prev.x + prev.y * prev.y + prev.z * prev.z)) < 0.03f && raw > 0.2f)
        gAvg = gAvg * 0.95f + raw * 0.05f;
    a.x /= gAvg; a.y /= gAvg; a.z /= gAvg;
    float mag = raw / gAvg;
    if (prev.ok) {
        float d = fabsf(a.x - prev.x) + fabsf(a.y - prev.y) + fabsf(a.z - prev.z);
        if (power == P_OFF && d > 0.35f && a.z > 0.45f) wake(true);    // lifted / picked up, screen towards you
        if(shakeDetector.sample(mag,now,shakeAllowed()))reactToShake();
    }
    prev = a;
    if (!imuPower) { downSince = 0; pocket = false; return; }
    if (fabsf(a.z) < 0.75f) face.setTilt(atan2f(a.x, a.y) * 57.2958f);
    else face.setTilt(0);
    if (a.z < -0.85f) {                                       // screen facing down
        if (!downSince) downSince = now;
        if (since(now, downSince) > 1500 && power != P_OFF && !recording) screenOff(now);
    } else downSince = 0;
    // pocket: screen off and not facing up for 5 s (walking in a pocket never shows the screen to the sky)
    static uint32_t notUpSince = 0;
    if (power == P_OFF && a.z < 0.45f) {
        if (!notUpSince) notUpSince = now;
        if (!pocket && since(now, notUpSince) > 5000) { pocket = true; Serial.println("pocket: on"); }
    } else notUpSince = 0;
}

// ------------------------------------------------------------------ server -> body
static void applyModel(uint32_t now) {
    char pipCue[12]="none",expressionAck[33]="";bool expressionApplied=false;
    bool wakeReq = false;
    modelLock();
    if(model.assetSwap || model.assetRemove){
        PipAsset *old=model.customPip;model.customPip=model.assetRemove?nullptr:model.pendingPip;model.pendingPip=nullptr;
        face.setAsset(model.customPip);delete old;
        if(!model.assetRemove){model.pip=PIXEL_RIG_COUNT;model.pipColor=0;}
        else if(model.pip>=PIXEL_RIG_COUNT){model.pip=0;model.pipColor=0;}
        model.assetSwap=model.assetRemove=false;model.pipNew=true;gallery=false;wakeReq=true;
    }
    char pipAck[33]="";
    if (model.pipNew) {
        strlcpy(pipAck,model.pipCommand,sizeof pipAck);model.pipCommand[0]=0;if(pipAck[0])model.assetBusy=false;
        model.pipNew = false; model.pip = model.pip % pipCount();
        face.setPip(model.pip, model.pipColor); face.setReducedMotion(model.reducedMotion);
        uiPrefs.putUChar("pip", model.pip); uiPrefs.putUInt("pipColor", model.pipColor);
        faceNeedsClear = true;
    }
    if(model.expressionNew) {
        model.expressionNew=false;
        strlcpy(expressionAck,model.expressionId,sizeof expressionAck);
        if(!recording && !audioPlaying() && !meeting && !alarmOn) {
            model.pip=model.expressionRig;model.pipColor=model.expressionColor;model.pipNew=true;
            face.setPip(model.pip,model.pipColor);face.setExpression(model.expression);showFace();
            emotionHoldUntil=now+10000;wakeReq=true;expressionApplied=true;strlcpy(pipCue,model.cue,sizeof pipCue);
        }
    }
    if (model.emotionNew) {
        model.emotionNew = false;
        strncpy(serverEmotion, model.emotion, sizeof serverEmotion - 1);
        if (!recording) { face.setEmotion(serverEmotion); emotionHoldUntil = now + 8000; }
    }
    if (model.gestureNew) { model.gestureNew = false; face.gesture(model.gesture); }
    if(model.clearCard){model.clearCard=false;cardOn=false;page=FACE;faceNeedsClear=true;badgeUntil=0;}
    if(model.partialNew){model.partialNew=false;strlcpy(livePartial,model.liveTranscription && recording?model.partial:"",sizeof livePartial);}
    if(model.badgeNew){model.badgeNew=false;deviceBadge=model.badge;badgePending=model.badgePending;badgeUntil=now+model.badgeTtl*1000UL;}
    bool cardReq = false, cfgReq = false, toastReq = false;
    uint16_t cardTtl = 12;
    if (model.cardNew) { model.cardNew = false; cardReq = true; cardTtl = model.cardTtl; cardImgBase = model.imgSeq; }
    if (model.configNew) { model.configNew = false; cfgReq = true; }
    if (model.toastNew) { model.toastNew = false; toastReq = true; strlcpy(toast, model.toast, sizeof toast); }
    if (model.infoSeq != seenInfo) { seenInfo = model.infoSeq; screenDirty = true; }
    if (model.haSeq != seenHa) { seenHa = model.haSeq; haListChanged(); screenDirty = true; }
    if (model.imgSeq != seenImg) { seenImg = model.imgSeq; screenDirty = true; }
    if (model.meetingNew) { model.meetingNew = false; screenDirty = true; }
    if (model.subNew) {
        if (page != FACE) setPage(FACE);                       // it speaks: show the face (a card stays)
        model.subNew = false;
        strncpy(sub, model.sub, sizeof sub - 1);
        sub[sizeof sub - 1] = 0;
        subUntil = now + 3000 + strlen(sub) * 40;          // bytes: ~80 ms per Hebrew letter
        wakeReq = power != P_ACTIVE;
        if (ringMode == RING_THINK) ringMode = RING_NONE;
        emotionHoldUntil = now + 8000;
    }
    if (model.ring != RING_NONE || ringMode == RING_THINK) {
        if (model.ring == RING_THINK && ringMode != RING_THINK && !recording) { ringMode = RING_THINK; ringT0 = now;strlcpy(pipCue,"think",sizeof pipCue); }
        model.ring = RING_NONE;
    }
    if (model.stopAudio) { model.stopAudio = false; audioStop(); }
    uint8_t mreq = model.meetingReq;
    model.meetingReq = 0;
    bool timerDone = model.timerOn && (int32_t)(now - model.timerEnd) >= 0;
    if (timerDone) {
        model.timerOn = false;
        Preferences saved;saved.begin("wappai-timers",false);saved.putBool("active",false);saved.end();
        alarmOn = true;
        alarmT0 = now;
        lastAlarmBeep = 0;
        strncpy(alarmLabel, model.timerLabel, sizeof alarmLabel - 1);
    }
    bool server = model.server;
    bool wifiOk = model.wifi;
    modelUnlock();
    if(pipAck[0])netSend(String("{\"type\":\"command.result\",\"id\":\"")+pipAck+"\",\"status\":\"applied\"}");
    if(expressionApplied)wake(true);else if(wakeReq)wake();
    if(expressionAck[0])netSend(String("{\"type\":\"command.result\",\"id\":\"")+expressionAck+"\",\"status\":\""+(expressionApplied?"applied":"busy")+"\"}");
    if(model.characterSounds && !recording && !meeting && !alarmOn && !audioPlaying())audioPipCue(model.pip,pipCue);
    if (cardReq && !recording) {
        wake();
        page = FACE;
        cardOn = true;
        cardTtlS = cardTtl;
        cardSpoke = false;
        cardUntil = now + cardTtl * 1000UL;
        drawnImg = 0;
        screenDirty = true;
    }
    if (cfgReq) {
        uiPrefs.putBool("pipSounds",model.characterSounds);
        uiPrefs.putBool("shake",model.shakeReaction);
        uiPrefs.putBool("liveText",model.liveTranscription);if(!model.liveTranscription)livePartial[0]=0;
        audioSetVolume(model.volume);
        if (power == P_ACTIVE) setBrightness(activeBrightness());
        uiPrefs.putUChar("bright", model.brightness);
        uiPrefs.putUChar("vol", model.volume);
        uiPrefs.putBool("hold",model.holdToTalk);uiPrefs.putBool("reduced",model.reducedMotion);
        uiPrefs.putUInt("dim",model.dimMs);uiPrefs.putUInt("deep",model.deepMs);
        screenDirty = true;
    }
    if (toastReq) {
        if (onScreens()) { toastUntil = now + 3500; screenDirty = true; }
        else { strlcpy(sub, toast, sizeof sub); subUntil = now + 3500; }
    }
    if (cardOn && audioPlaying()) cardSpoke = true;
    if (cardOn && cardSpoke && !audioPlaying()) { cardSpoke = false; cardUntil = now + cardTtlS * 1000UL; screenDirty = true; }
    if (cardOn && (int32_t)(now - cardUntil) > 0 && !audioPlaying()) showFace();
    if (page != FACE && !cardOn && since(now, pageActiveT) > 60000) {
        bool keep = page == CLOCK || (page == TIMER && model.timerOn);   // a desk clock / a running timer may stay
        if (!keep) setPage(FACE);
    }
    if (mreq == 1) startMeeting();
    if (mreq == 2) stopMeeting();
    if (!wifiOk && sub[0] && strstr(sub, "Piko-Setup")) subUntil = now + 2000;   // keep setup hint visible
    if (timerDone) {
        wake();
        showFace();
        face.setEmotion("surprised");
        face.gesture("jump");
        if (alarmLabel[0]) snprintf(sub, sizeof sub, "הטיימר הסתיים: %s", alarmLabel);
        else snprintf(sub, sizeof sub, "הטיימר הסתיים!");
        subUntil = now + 30000;
        netTimerDone();
    }
    if (alarmOn) {
        if (since(now, lastAlarmBeep) > 2000) { lastAlarmBeep = now; audioAlarm(); }
        if (since(now, alarmT0) > 30000) alarmOn = false;
        markActivity();
    }
    if (server) lastServerOk = now;
    if (server && !wasServer) { face.setEmotion("happy"); face.gesture("jump"); emotionHoldUntil = now + 2500; }
    wasServer = server;
    if (ringMode == RING_THINK && since(now, ringT0) > 25000) ringMode = RING_NONE;
    if (!recording && !meeting && !audioPlaying() && !alarmOn && (int32_t)(now - emotionHoldUntil) > 0) homeEmotion();
}

// ------------------------------------------------------------------ power
static void enterDeepSleep(bool bootOnly = false) {
    Serial.printf("deep sleep (pocket=%d)\n", pocket);
    netShutdown();
    audioStop();
    digitalWrite(PIN_PA, LOW);
    imuSleep();
    lcd.panelSleep(true);
    rtc_gpio_pullup_en(GPIO_NUM_11);
    rtc_gpio_pulldown_dis(GPIO_NUM_11);
    // in a pocket only BOOT wakes it (a touch through the fabric must not); otherwise BOOT or a tap
    uint64_t pins = (1ULL << PIN_BOOT) | ((manualLocked || pocket || bootOnly) ? 0 : (1ULL << PIN_TP_INT));
    esp_sleep_enable_ext1_wakeup(pins, ESP_EXT1_WAKEUP_ANY_LOW);
    // Physical PWR is active-high GPIO3; BOOT/touch use active-low EXT1.
    esp_sleep_enable_ext0_wakeup((gpio_num_t)PIN_PWR_SENSE,1);
    modelLock();
    bool t = model.timerOn;
    uint32_t left = model.timerEnd - millis();
    modelUnlock();
    if (t) esp_sleep_enable_timer_wakeup((uint64_t)left * 1000ULL);
    delay(50);
    esp_deep_sleep_start();
}

static void render(uint32_t now);

static void updatePower(uint32_t now) {
    bool busy = recording || audioPlaying() || alarmOn || touchDown || bootDown;
    if (busy) markActivity();
    int32_t idle = (int32_t)(now - model.lastActivity);   // signed: activity may be stamped after `now` was read
    if (idle < 0) idle = 0;
    if (power == P_ACTIVE && idle > (int32_t)model.dimMs) { power = P_DIM; setBrightness(BRIGHT_DIM); }
    if (power == P_DIM && idle < (int32_t)model.dimMs) { power = P_ACTIVE; setBrightness(activeBrightness()); }
    if (power == P_DIM && idle > (int32_t)model.offMs) screenOff(now);    // a long meeting records with the screen off
    uint32_t deepAfter = model.deepMs;
    if (power == P_OFF && !model.assetBusy && !bat.usb && !meeting && !netRecordingPending() && !audioPlaying() && since(now, offSince) > deepAfter) {
        modelLock();
        bool soon = model.timerOn && (int32_t)(model.timerEnd - now) < (int32_t)deepAfter;
        modelUnlock();
        if (!soon) enterDeepSleep();
    }
    // empty battery: protect the cell (and the user's data) - say so, then sleep until BOOT / charger
    if (bat.present && !bat.usb && bat.pct >= 0 && bat.pct <= BAT_CRITICAL_PCT && bat.mv > 0 && bat.mv < BAT_CRITICAL_MV
        && !recording && !meeting) {
        wake();
        face.setEmotion("low_battery");
        snprintf(sub, sizeof sub, "הסוללה כמעט ריקה. כדאי לחבר מטען");
        subUntil = now + 4000;
        for (uint32_t t0 = millis(); millis() - t0 < 3500;) { render(millis()); delay(30); }
        enterDeepSleep(true);
    }
}

// ------------------------------------------------------------------ drawing
static void clearRect(const Rect &r) {
    uint16_t *px = (uint16_t *)scr.getBuffer();
    for (int y = r.y0; y < r.y1; y++) memset(px + y * SCREEN_W + r.x0, 0, (r.x1 - r.x0) * 2);
}

static void unionRect(Rect &d, const Rect &r) {
    if (r.empty()) return;
    if (d.empty()) { d = r; return; }
    if (r.x0 < d.x0) d.x0 = r.x0; if (r.y0 < d.y0) d.y0 = r.y0;
    if (r.x1 > d.x1) d.x1 = r.x1; if (r.y1 > d.y1) d.y1 = r.y1;
}

// Top bar: Wi-Fi signal | clock | battery. Always shown while the screen is on; dim, brighter for a few seconds
// after a short press / tap ("status").
static uint16_t c565(uint32_t rgb, float k) {
    uint8_t r = ((rgb >> 16) & 255) * k, g = ((rgb >> 8) & 255) * k, b = (rgb & 255) * k;
    return lcd.color565(r, g, b);
}

static void drawStatus(bool bright) {
    const float k = bright ? 1.f : 0.55f;
    const int y = 52;
    // Familiar concentric Wi-Fi arcs, physically left of the centered clock.
    int bars = !model.wifi ? 0 : rssiCache > -60 ? 3 : rssiCache > -75 ? 2 : 1;
    uint32_t wc = !model.wifi ? 0x88959B : (!model.server ? 0xFFB13B : 0xE6EEF2);
    int wx = SCREEN_W / 2 - 69;
    scr.fillCircle(wx,y+6,2,c565(wc,k));
    for(int arc=1;arc<=3;arc++) {
        uint16_t color=c565(arc<=bars?wc:0x3A4650,k);
        for(int deg=225;deg<=315;deg+=4) {
            float angle=deg*PI/180.f;
            scr.fillCircle(wx+roundf(cosf(angle)*arc*6),y+7+roundf(sinf(angle)*arc*6),1,color);
        }
    }
    if(!model.wifi) scr.drawLine(wx-13,y-10,wx+13,y+8,c565(wc,k));
    // clock, or the time left while a timer runs
    if (model.timerOn) {
        int32_t left = (int32_t)(model.timerEnd - millis());
        drawTimerBadge(scr, SCREEN_W / 2, y + 1, left > 0 ? left : 0, 1.f);
    } else {
        time_t now = time(nullptr);
        struct tm lt;
        localtime_r(&now, &lt);
        char clock[8] = "--:--";
        if (now > 1700000000) snprintf(clock, sizeof clock, "%02d:%02d", lt.tm_hour, lt.tm_min);
        scr.setTextSize(0.7f);
        scr.setTextDatum(lgfx::middle_center);
        scr.setTextColor(c565(0xE6EEF2, k));
        scr.drawString(clock, SCREEN_W / 2, y + 1);
    }
    // Percentage stays inside the battery, with contrasting text over each part.
    int bx = SCREEN_W / 2 + 40, bw = 38, bh = 22;
    if (bat.present && bat.pct >= 0) {
        uint32_t fc = bat.charging ? 0x7CE38B : bat.pct < 15 ? 0xFF6A4D : 0xE6EEF2;
        scr.fillRoundRect(bx,y-bh/2,bw,bh,5,c565(0x3A4650,k));
        int fw=(bw-4)*constrain(bat.pct,0,100)/100;
        if(fw>0)scr.fillRoundRect(bx+2,y-bh/2+2,fw,bh-4,3,c565(fc,k));
        scr.drawRoundRect(bx,y-bh/2,bw,bh,5,c565(fc,k));
        scr.fillRoundRect(bx+bw+1,y-4,3,8,1,c565(fc,k));
        char p[4];snprintf(p,sizeof p,"%d",constrain(bat.pct,0,100));
        scr.setTextSize(0.56f);scr.setTextDatum(lgfx::middle_center);
        scr.setTextColor(c565(0xE6EEF2,k));scr.drawString(p,bx+bw/2,y+1);
        if(fw>0){scr.setClipRect(bx+2,y-bh/2+2,fw,bh-4);scr.setTextColor(0);scr.drawString(p,bx+bw/2,y+1);scr.clearClipRect();}
    } else {
        scr.setTextSize(0.55f);
        scr.setTextDatum(lgfx::middle_left);
        scr.drawString("USB", bx, y + 1);
    }
    scr.setTextSize(1.f);
}

// per-section render cost (µs, summed) for the 'ui:' log line
static uint32_t tUpd = 0, tFace = 0, tText = 0, tRing = 0, tFlush = 0, nDirtyPx = 0;

static RingStyle ringStyle(uint32_t now) {
    RingStyle rs;
    bool timerOn;
    uint32_t tEnd, tTotal;
    modelLock(); timerOn = model.timerOn; tEnd = model.timerEnd; tTotal = model.timerTotal; modelUnlock();
    if (meeting) {
        rs.mode = RS_FULL;
        rs.r = 1.f; rs.g = 0.27f; rs.b = 0.3f;
        rs.thickness = 6;
        rs.alpha = 0.45f + 0.35f * sinf(now / 600.f) + 0.3f * audioMicLevel();
        rs.track = 0;
    } else if (ringMode == RING_REC) {
        rs.mode = RS_PROGRESS;
        rs.progress = fminf(1.f, since(now, ringT0) / (float)MAX_REC_MS);
        rs.glow = audioMicLevel();
        rs.thickness = 9 + 5 * rs.glow;
    } else if (ringMode == RING_THINK) {
        rs.mode = RS_COMET;
        rs.head = fmodf(since(now, ringT0) / 1000.f * 4.2f, 6.2831853f);
        rs.r = 0.5f; rs.g = 0.77f; rs.b = 1.f;
        rs.track = 0.08f;
    } else if (alarmOn) {
        rs.mode = RS_FULL;
        rs.r = 1.f; rs.g = 0.7f; rs.b = 0.23f;
        rs.alpha = 0.65f + 0.35f * sinf(now / 120.f);       // pulses but never fades out (a screenshot caught it dark)
        rs.thickness = 13;
    } else if (timerOn && tTotal) {
        rs.mode = RS_PROGRESS;
        rs.progress = fmaxf(0.f, (int32_t)(tEnd - now) / (float)tTotal);
        rs.r = 1.f; rs.g = 0.7f; rs.b = 0.23f;
        rs.thickness = 5;
        rs.track = 0.1f;
    }
    return rs;
}

static void snapshot(Snap &d, uint32_t now) {
    modelLock();
    strlcpy(d.date, model.date, sizeof d.date);
    d.weather = model.weather;
    d.timerOn = model.timerOn;
    int32_t left = (int32_t)(model.timerEnd - now);
    d.timerLeft = left > 0 ? left : 0;
    d.timerTotal = model.timerTotal;
    strlcpy(d.timerLabel, model.timerLabel, sizeof d.timerLabel);
    d.haOk = model.haOk;
    d.nHa = model.nHa;
    memcpy(d.ha, model.ha, sizeof(Model::HaItem) * model.nHa);
    d.brightness = model.brightness;
    d.volume = model.volume;
    d.wifi = model.wifi;
    d.server = model.server;
    strlcpy(d.cardKind, model.cardKind, sizeof d.cardKind);
    strlcpy(d.cardTitle, model.cardTitle, sizeof d.cardTitle);
    strlcpy(d.cardBody, model.cardBody, sizeof d.cardBody);
    d.cardW = model.cardW;
    d.cardDev = model.cardDev;
    d.imgReady = model.img && model.imgSeq > cardImgBase;
    modelUnlock();
    d.rssi = rssiCache;
    strlcpy(d.ip, model.wifi ? WiFi.localIP().toString().c_str() : "", sizeof d.ip);
}

// Pages and cards: redrawn when something changed (or every second / quarter second for a countdown),
// with the edge ring on top every frame while it animates.
static void renderScreens(uint32_t now) {
    static int lastPage = -1;
    static bool lastCard = false, lastToast = false;
    static uint32_t lastDraw = 0, pressT = 0;
    static Snap d;
    snapshot(d, now);
    bool timerShown = d.timerOn && ((page == TIMER && !cardOn) || (cardOn && !strcmp(d.cardKind, "timer")));
    bool toastOn = (int32_t)(toastUntil - now) > 0;
    bool need = screenDirty || page != lastPage || cardOn != lastCard || toastOn != lastToast ||
                since(now, lastDraw) >= (timerShown ? 250u : 1000u) || since(now, pressT) < 400;
    if (screenDirty) pressT = now;
    if (meeting) {
        static uint32_t lastM = 0;
        need = screenDirty || since(now, lastM) >= 200;
        if (need) {
            char title[96];
            modelLock(); strlcpy(title, model.meetingTitle, sizeof title); modelUnlock();
            drawMeeting(scr, title, since(now, meetingT0), audioMicLevel(), d.server, audioMicQueued(), now, model.meetingLimitSeconds);
            lastM = now;
        }
    } else if (need) {
        if (cardOn && !strcmp(d.cardKind, "image") && d.imgReady) {
            // the photo is decoded once (it is big); the caption is drawn over it
            if (drawnImg != seenImg || lastPage != page || !lastCard) {
                scr.fillScreen(0);
                modelLock();
                if (model.img) scr.drawJpg(model.img, model.imgLen, 25, 25, 416, 416);
                drawnImg = model.imgSeq;
                modelUnlock();
                uint16_t *px = (uint16_t *)scr.getBuffer();          // round photo: black outside r = 208
                for (int y = 25; y < 441; y++)
                    for (int x = 25; x < 441; x++) {
                        int dx = x - SCREEN_W / 2, dy = y - SCREEN_H / 2;
                        if (dx * dx + dy * dy > 208 * 208) px[y * SCREEN_W + x] = 0;
                    }
            }
            drawCard(scr, d, now);
        } else if (cardOn) drawCard(scr, d, now);
        else {
            uint32_t t0 = micros();
            drawPage(scr, page, d, now, haScroll);
            if (page != lastPage) {
                uint32_t nz = 0;
                const uint16_t *p = (const uint16_t *)scr.getBuffer();
                for (int i = 0; i < SCREEN_W * SCREEN_H; i += 7) nz += p[i] != 0;
                Serial.printf("screen: page %d drawn in %u us, lit~%u, ha=%d/%d\n", page, (unsigned)(micros() - t0), (unsigned)nz * 7, d.haOk, d.nHa);
            }
        }
        if (toastOn) drawToast(scr, toast);
        lastDraw = now;
    }
    RingStyle rs = ringStyle(now);
    bool ringOn = rs.mode != RS_OFF;
    if (ringOn || ringDrawn) ringDraw((uint16_t *)scr.getBuffer(), SCREEN_W, SCREEN_H, true, rs);
    if (need || ringOn || ringDrawn) { lcd.flush(scr, 0, 0, SCREEN_W, SCREEN_H); nDirtyPx += SCREEN_W * SCREEN_H; }
    ringDrawn = ringOn;
    lastPage = page;
    lastCard = cardOn;
    lastToast = toastOn;
    screenDirty = false;
    subDrawn = statusDrawn = false;
}

// Pixel art is drawn directly at native screen resolution. It needs no half-size
// framebuffer and no bilinear upscale; status and Hebrew captions remain native.
static Rect renderCharacter(){
    Canvas cv{(uint16_t*)scr.getBuffer(),SCREEN_W,SCREEN_H,true};
    return face.render(cv,SCREEN_W/2,SCREEN_H/2);
}

static void render(uint32_t now) {
    static bool wasScreens = false;
    bool scr_ = onScreens();
    if (scr_ != wasScreens) { if (scr_) { screenDirty = true; drawnImg = 0; } else faceNeedsClear = true; wasScreens = scr_; }
    if (provisioningPrompt()) {
        scr.fillScreen(0); scr.setTextDatum(lgfx::middle_center); scr.setTextColor(0x80F2CD);
        scr.setTextSize(1.f); scr.drawString("Wappai",233,130);
        drawBidiText(scr,"האייפון רוצה להתחבר",233,233,233,200,30,1,0xE6EEF2,0);
        drawBidiText(scr,"לחץ BOOT לאישור",233,233,233,255,32,1,0x80F2CD,0);
        drawBidiText(scr,"ללא אישור הבקשה תבוטל",233,233,233,310,27,1,0xA0B8B0,0);
        lcd.flush(scr,0,0,SCREEN_W,SCREEN_H); faceNeedsClear=true; return;
    }
    if (scr_) { renderScreens(now); return; }
    bool fullClear=faceNeedsClear;
    if (faceNeedsClear) {                                   // back from a page: start from a clean screen
        faceNeedsClear = false;
        scr.fillScreen(0);
        statusDrawn = false;
        ringDrawn = true;                                   // forces a full flush below
    }
    uint32_t q0 = micros();
    static uint32_t lastT = 0;
    float dt = lastT ? (now - lastT) / 1000.f : 0.03f;
    lastT = now;
    Rect dirty = {0, 0, 0, 0};

    bool liveOn=recording && model.liveTranscription && livePartial[0];
    bool subOn = sub[0] && (int32_t)(subUntil - now) > 0 && !recording;
    if (!subOn && (audioPlaying() || ringMode==RING_THINK) && sub[0] && !recording) subOn = true;
    bool statusOn = true;                                 // top bar always on (hidden while subtitles lift the face)
    bool statusBright = (int32_t)(statusUntil - now) > 0;
    static uint32_t lastRssi = 0;
    if (now - lastRssi > 2000) { lastRssi = now; rssiCache = model.wifi ? WiFi.RSSI() : 0; }
    if (subOn || subDrawn || liveOn) { clearRect(SUB_RECT); unionRect(dirty, SUB_RECT); }
    // Status changes at most once per second. Do not expand every face redraw
    // all the way up to the clock; redraw after a clear or a brightness change.
    static uint32_t statusSecond=UINT32_MAX;
    static bool previousBright=false;
    bool statusChanged=!statusDrawn || statusSecond!=now/1000 || previousBright!=statusBright;
    if(statusChanged){clearRect(STATUS_RECT);unionRect(dirty,STATUS_RECT);statusSecond=now/1000;previousBright=statusBright;}

    bool badgeOn=deviceBadge.id[0] && (int32_t)(badgeUntil-now)>0 && !recording && !gallery;
    if(badgeOn || badgeDrawn){clearRect(BADGE_RECT);unionRect(dirty,BADGE_RECT);}
    face.setTalk(audioPlaying() ? audioMouth() : 0.f);
    // idle life only when nothing is going on (not listening, talking, thinking, recording or ringing)
    face.setIdle(!recording && !meeting && !audioPlaying() && !alarmOn && ringMode == RING_NONE && (int32_t)(now - emotionHoldUntil) > 0);
    // with subtitles: lift and shrink the face so 3 lines fit under a wide-open mouth and nothing touches the edge
    // (-44 px, 80 %: checked for every emotion with tools/face_preview, talking and not)
    face.setCenterOffset(-16.f, 0.88f);
    face.update(dt);
    uint32_t q1 = micros(); tUpd += q1 - q0;
    Rect faceDirty=renderCharacter();unionRect(dirty,faceDirty);
    if(faceDirty.y0<STATUS_RECT.y1 && faceDirty.y1>STATUS_RECT.y0){statusChanged=true;unionRect(dirty,STATUS_RECT);}
    uint32_t q2 = micros(); tFace += q2 - q1;

    if(badgeOn){
        uint32_t color=badgePending?0xA6B5C4:!deviceBadge.avail?0x929292:deviceBadge.on?0x80F2CD:0xA6B5C4;
        scr.fillRoundRect(94,80,278,30,15,c565(0x102020,1.f));
        scr.drawCircle(112,95,7,c565(color,1.f));scr.fillRect(110,86,5,6,c565(0x102020,1.f));scr.drawLine(112,86,112,94,c565(color,1.f));
        scr.setTextSize(.75f);drawBidiText(scr,deviceBadge.name,246,95,125,95,24,1,color,0);scr.setTextSize(1.f);
    }
    badgeDrawn=badgeOn;
    if(liveOn){drawBidiText(scr,livePartial,SCREEN_W/2,SCREEN_H/2,SCREEN_W/2,SUB_Y0,SUB_LH,SUB_LINES,0xA7D9F5,10000);}
    if (subOn) {
        // long subtitles turn pages at roughly the speaking pace (~70 ms per character)
        static char shown[sizeof sub] = "";
        static uint32_t subT0 = 0;
        static int pages = 1, chars = 0;
        if (strcmp(shown, sub)) {
            strcpy(shown, sub);
            subT0 = now;
            chars = 0;
            for (const char *p = sub; *p; p++) chars += (*p & 0xC0) != 0x80;
        }
        uint32_t pageMs = max(2200, chars * 70 / max(pages, 1));
        int page = (int)(since(now, subT0) / pageMs);
        pages = drawBidiText(scr, sub, SCREEN_W / 2, SCREEN_H / 2, SCREEN_W / 2, SUB_Y0, SUB_LH, SUB_LINES, 0xE6EEF2, page);
    }
    if (gallery) {
        clearRect(SUB_RECT); unionRect(dirty, SUB_RECT);
        scr.setTextSize(0.8f); scr.setTextDatum(lgfx::middle_center); scr.setTextColor(0xFFFFFF);
        String caption=String("‹  ")+pipName(galleryPip)+"  ›";
        drawBidiText(scr,caption.c_str(),SCREEN_W/2,SCREEN_H/2,SCREEN_W/2,355,26,1,0xFFFFFF,0);
        scr.setTextSize(1.f);
        drawBidiText(scr, "החלקה לבחירה · נגיעה לאישור", SCREEN_W/2, SCREEN_H/2, SCREEN_W/2, 400, 26, 1, 0xA0B8B0, 0);
    }
    subDrawn = subOn || liveOn || gallery;
    if (statusOn && statusChanged) drawStatus(statusBright);
    statusDrawn = statusOn;

    uint32_t q3 = micros(); tText += q3 - q2;
    RingStyle rs = ringStyle(now);
    bool ringOn = rs.mode != RS_OFF;
    bool edgeChanged=ringOn || ringDrawn;
    if(edgeChanged){
        int dx=max(abs(dirty.x0-SCREEN_W/2),abs(dirty.x1-SCREEN_W/2));
        int dy=max(abs(dirty.y0-SCREEN_H/2),abs(dirty.y1-SCREEN_H/2));
        bool ringUntouched=!fullClear && dx*dx+dy*dy<212*212;
        ringDraw((uint16_t*)scr.getBuffer(),SCREEN_W,SCREEN_H,true,rs,ringUntouched);
    }
    if(fullClear)dirty={0,0,SCREEN_W,SCREEN_H};
    ringDrawn = ringOn;
    uint32_t q4 = micros(); tRing += q4 - q3;
    if (!dirty.empty()) { lcd.flush(scr, dirty.x0, dirty.y0, dirty.x1 - dirty.x0, dirty.y1 - dirty.y0,edgeChanged); nDirtyPx += (dirty.x1 - dirty.x0) * (dirty.y1 - dirty.y0); }
    tFlush += micros() - q4;
}

// ------------------------------------------------------------------ public
void appBegin() {
    // ext1 deep-sleep wake turns these pins into RTC GPIOs, and that survives software resets (OTA, reboot):
    // the BOOT key then reads as "never pressed". Give them back to the digital GPIO matrix first.
    rtc_gpio_deinit(GPIO_NUM_0);
    rtc_gpio_deinit((gpio_num_t)PIN_PWR_SENSE);
    rtc_gpio_deinit((gpio_num_t)PIN_TP_INT);
    pinMode(PIN_BOOT, INPUT_PULLUP);
    pinMode(PIN_PA, OUTPUT);
    digitalWrite(PIN_PA, LOW);
    lcd.init();
    lcd.setRotation(0);
    scr.setPsram(true);
    scr.setColorDepth(16);
    scr.createSprite(SCREEN_W, SCREEN_H);
    scr.fillScreen(0);
    screens::begin();                    // fonts, loaded once (reloading per frame is slow)
    useText(scr);
    lcd.flush(scr, 0, 0, SCREEN_W, SCREEN_H);
    uiPrefs.begin("ui", false);
    model.brightness = uiPrefs.getUChar("bright", model.brightness);
    model.volume = uiPrefs.getUChar("vol", model.volume);
    model.liveTranscription=uiPrefs.getBool("liveText",false);
    model.holdToTalk=uiPrefs.getBool("hold",true);model.reducedMotion=uiPrefs.getBool("reduced",false);
    model.dimMs=uiPrefs.getUInt("dim",DIM_AFTER_MS);model.deepMs=uiPrefs.getUInt("deep",DEEP_AFTER_MS);
    setBrightness(model.brightness);
    imuBegin();
    pmuBegin(BATTERY_CARE);
    bat = pmuRead();
    // clock: RTC keeps local time between boots; the server corrects it on connect
    setenv("TZ", TZ_INFO, 1);
    tzset();
    struct tm t;
    if (rtcRead(&t)) {
        time_t e = mktime(&t);
        struct timeval tv = {e, 0};
        settimeofday(&tv, nullptr);
    }
    {
        Preferences saved;saved.begin("wappai-timers",false);
        if(saved.getBool("active",false)) {
            int64_t left=(int64_t)saved.getULong64("deadline",0)-(int64_t)time(nullptr);
            if(left>0 && left<=86400) { model.timerOn=true;model.timerEnd=millis()+left*1000;model.timerTotal=saved.getUInt("total",left)*1000;strlcpy(model.timerLabel,saved.getString("label","").c_str(),sizeof model.timerLabel); }
            else { saved.putBool("active",false); if(left<=0) {alarmOn=true;alarmT0=millis();} }
        }
        saved.end();
    }
    model.characterSounds=uiPrefs.getBool("pipSounds",true);
    model.shakeReaction=uiPrefs.getBool("shake",true);
    manualLocked=uiPrefs.getBool("locked",false);
    face.begin(esp_random());
    model.customPip=pipBoot();face.setAsset(model.customPip);
    model.pip = uiPrefs.getUChar("pip",0)%pipCount(); model.pipColor = uiPrefs.getUInt("pipColor",0);
    face.setPip(model.pip,model.pipColor);face.setReducedMotion(model.reducedMotion);
    markActivity();
    esp_sleep_wakeup_cause_t why = esp_sleep_get_wakeup_cause();
    if(why==ESP_SLEEP_WAKEUP_EXT0 || (why==ESP_SLEEP_WAKEUP_EXT1 && (esp_sleep_get_ext1_wakeup_status()&(1ULL<<PIN_BOOT)))){
        manualLocked=false;uiPrefs.putBool("locked",false);
        bootUnlockConsumed=(why==ESP_SLEEP_WAKEUP_EXT1);pwrWakeConsumed=(why==ESP_SLEEP_WAKEUP_EXT0);
    }
    if(manualLocked)screenOff(millis());
    if (why == ESP_SLEEP_WAKEUP_EXT1 && bat.present && !bat.usb && bat.pct >= 0 && bat.pct <= BAT_CRITICAL_PCT)
        Serial.println("app: woke with a critical battery");     // updatePower() shows the message and sleeps again
    face.setEmotion(why == ESP_SLEEP_WAKEUP_EXT1 ? "sleepy" : "happy");
    face.gesture(why == ESP_SLEEP_WAKEUP_EXT1 ? "blink" : "jump");
    emotionHoldUntil = millis() + 3000;
    showStatus(3000);
    Serial.printf("app: battery %s %d%% %dmV usb=%d charging=%d care=%d\n", bat.present ? "present" : "absent", bat.pct, bat.mv,
                  bat.usb, bat.charging, bat.care);
}

static void setupLoop(uint32_t now) {
    static uint32_t next = 0;
    lgfx::touch_point_t tp;
    bool t = lcd.getTouch(&tp);
    wsetup.touch(t, tp.x, tp.y, now);
    markActivity();                                  // keep the screen on while setting up
    if ((int32_t)(now - next) >= 0) {
        next = now + 40;
        scr.setTextSize(1.f);
        wsetup.render(scr, now);
        lcd.flush(scr, 0, 0, SCREEN_W, SCREEN_H);
    }
    if (!wsetup.active()) {                          // closed: back to the face, redraw everything
        scr.fillScreen(0);
        statusDrawn = false;
        ringDrawn = true;
        face.setEmotion("happy");
        face.gesture("jump");
        emotionHoldUntil = now + 2500;
    }
}

void appLoop() {
    static bool pairingShown=false;
    bool pairing=provisioningPrompt();
    if(pairing && !pairingShown) wake(true);
    pairingShown=pairing;
    static uint32_t nextFrame = 0, lastBat = 0, frames = 0, renderUs = 0, lastStat = 0;
    uint32_t now = millis();
    {
        bool need;
        modelLock(); need = model.wifiSetup; modelUnlock();
        // Offline keeps the home/Pip available. PWR hold opens Wi-Fi setup; BLE can provision it.
        if (wsetup.active()) {
            if (!need && !wsetup.canCancel()) wsetup.close();      // the saved network came back by itself
            static uint32_t lastPwr = 0;
            if (now - lastPwr > 60) {                               // PWR still turns the screen on/off
                lastPwr = now;
                bool p = readPowerButton();
                if (p && !pwrDown) { pwrDown = true; setManualLock(!manualLocked); }
                if (!p) pwrDown = false;
            }
            if (power == P_OFF) { delay(20); return; }
            setupLoop(now);
            delay(1);
            return;
        }
    }
    pollInputs(now);
    pollImu(now);
    applyModel(now);
    if (now - lastBat > 5000) { lastBat = now; bat = pmuRead(); netSetBattery(bat.pct, bat.mv, bat.charging, bat.usb); }
    updatePower(now);
    if (power == P_OFF) { delay(20); return; }
    // Thinking, expressions and the live ring must retain active cadence even
    // without touches; these do not reset inactivity or postpone screen sleep.
    const bool animated = recording || meeting || audioPlaying() || alarmOn || ringMode != RING_NONE || gallery || (int32_t)(emotionHoldUntil-now)>0;
    uint32_t frameMs = power == P_DIM ? 66 : !animated && since(now,model.lastActivity)>5000 ? 42 : FRAME_MS;
    if ((int32_t)(now - nextFrame) >= 0) {
        // Keep a stable deadline, skipping missed slots instead of accumulating jitter.
        if(since(now,nextFrame)>frameMs)nextFrame=now;
        nextFrame += frameMs;
        uint32_t t0 = micros();
        render(now);
        renderUs += micros() - t0;
        frames++;
    }
    if (now - lastStat > 10000 && frames) {
        Serial.printf("ui: %u fps-ish, %u us/frame (upd %u face %u text %u ring %u flush %u, %u kpx), heap %u\n", (unsigned)(frames / 10),
                      (unsigned)(renderUs / frames), (unsigned)(tUpd / frames), (unsigned)(tFace / frames), (unsigned)(tText / frames),
                      (unsigned)(tRing / frames), (unsigned)(tFlush / frames), (unsigned)(nDirtyPx / frames / 1000), ESP.getFreeHeap());
        tUpd = tFace = tText = tRing = tFlush = nDirtyPx = 0;
        frames = 0; renderUs = 0; lastStat = now;
    }
    delay(1);
}

static Preferences &prefsAudio() {
    static Preferences p;
    static bool open = false;
    if (!open) { p.begin("audio", false); open = true; }
    return p;
}

void appSerial(const String &cmd) {
    if (cmd.startsWith("pip ")) { model.pip = constrain(cmd.substring(4).toInt(),0,pipCount()-1); model.pipNew = true; }
    else if (cmd == "ui comet") { wake(true); ringMode=RING_THINK; ringT0=millis(); }
    else if (cmd == "ui idle") { ringMode=RING_NONE; wake(true); }
    else if (cmd == "gallery") { gallery = true; galleryPip = model.pip; faceNeedsClear = true; }
    else if (cmd.startsWith("emo ")) { face.setEmotion(cmd.substring(4).c_str()); emotionHoldUntil = millis() + 10000; }
    else if (cmd.startsWith("g ")) face.gesture(cmd.substring(2).c_str());
    else if (cmd == "imu") { Accel a = imuRead(); Serial.printf("imu x=%.2f y=%.2f z=%.2f\n", a.x, a.y, a.z); }
    else if (cmd.startsWith("pwrsim ")) pwrSim=constrain(cmd.substring(7).toInt(),-1,1);
    else if (cmd == "lock") setManualLock(true);
    else if (cmd == "unlock") setManualLock(false);
    else if (cmd.startsWith("shakeacc ")) {if(shakeDetector.sample(cmd.substring(9).toFloat(),millis(),shakeAllowed()))reactToShake();}
    else if (cmd == "pipstore") pipStorageInfo();
    else if (cmd == "bat") { Battery b = pmuRead(); Serial.printf("bat present=%d %d%% %dmV usb=%d chg=%d full=%d care=%d\n", b.present, b.pct, b.mv, b.usb, b.charging, b.full, b.care); }
    else if (cmd.startsWith("sub ")) { strncpy(sub, cmd.substring(4).c_str(), sizeof sub - 1); subUntil = millis() + 8000; }
    else if (cmd == "btn") Serial.printf("btn: boot_gpio0=%d (0=pressed) pwr=%d bootDown=%d recording=%d\n", digitalRead(PIN_BOOT), pwrButtonDown(), bootDown, recording);
    else if (cmd.startsWith("bootsim ")) bootSimReq = cmd.substring(8).toInt();
    else if (cmd == "tap") bootTap();
    else if (cmd == "wifiui") { wake(true); wsetup.begin(true); }
    else if (cmd.startsWith("tapxy ")) {           // tapxy <x> <y>: a tap on the Wi-Fi setup screen (tests)
        int sp = cmd.indexOf(' ', 6);
        if (wsetup.active() && sp > 0) wsetup.tap(cmd.substring(6, sp).toInt(), cmd.substring(sp + 1).toInt(), millis());
    }
    else if (cmd.startsWith("imupower ")) { imuPower = cmd.substring(9).toInt() != 0; Serial.printf("imupower %d\n", imuPower); }
    else if (cmd.startsWith("page ")) { wake(true); setPage(cmd.substring(5).toInt()); }
    else if (cmd.startsWith("tapscreen ")) {        // tapscreen <x> <y>: a tap on a page / card (tests)
        int sp = cmd.indexOf(' ', 10);
        if (sp > 0) { tx = cmd.substring(10, sp).toInt(); ty = cmd.substring(sp + 1).toInt(); wake(true); if (onScreens()) screenTap(0, 0, millis()); }
    }
    else if (cmd.startsWith("swipe ")) { wake(true); setPage(page + (cmd.substring(6).toInt() > 0 ? 1 : -1)); }
    else if (cmd == "meet") { if (meeting) stopMeeting(); else startMeeting(); }
    else if (cmd == "mic") audioMicTest();
    else if (cmd == "mictone") audioMicTone();
    else if (cmd.startsWith("micgain ")) { int g = cmd.substring(8).toInt(); audioMicGain(g); prefsAudio().putInt("gain", g); }
    else if (cmd.startsWith("micch ")) { int c = cmd.substring(6).toInt(); audioMicChannel(c); prefsAudio().putInt("ch", c); }
    else if (cmd == "ptt") { if (recording) stopRecording(); else startRecording(); }
    else if (cmd == "sleep") enterDeepSleep();
    else if (cmd == "wake") wake();
    else if (cmd == "state") {
        uint32_t nz = 0;
        const uint16_t *p = (const uint16_t *)scr.getBuffer();
        for (int i = 0; i < SCREEN_W * SCREEN_H; i++) nz += p[i] != 0;
        Serial.printf("state: locked=%d power=%d emotion=%s sub='%.40s' server=%d wifi=%d alarm=%d playing=%d pocket=%d lowpower=%d cpu=%d lit_pixels=%u bright=%d page=%d card=%d vol=%d live=%d recording=%d partial=%u\n", manualLocked,power,
                      face.emotionName(), sub, model.server, model.wifi, alarmOn, audioPlaying(), pocket, lowPower, getCpuFrequencyMhz(), nz, model.brightness, page, cardOn, model.volume,model.liveTranscription,recording,(unsigned)strlen(livePartial));
    }
    else if (cmd == "shot") {          // raw screenshot over serial: header, 466*466*2 bytes (RGB565 big-endian), footer
        Serial.flush();
        Serial.printf("SHOT %d %d\n", SCREEN_W, SCREEN_H);
        const uint8_t *p = (const uint8_t *)scr.getBuffer();
        size_t n = SCREEN_W * SCREEN_H * 2;
        for (size_t i = 0; i < n; i += 4096) Serial.write(p + i, min((size_t)4096, n - i));
        Serial.flush();
        Serial.println("\nENDSHOT");
    }
    else if (cmd == "list") { for (int i = 0; i < Face::count(); i++) Serial.printf("%s ", Face::name(i)); Serial.println(); }
}
