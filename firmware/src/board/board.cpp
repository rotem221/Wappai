// Display, touch, IMU, RTC and expander for the Waveshare AMOLED 1.75 (see board.h).
#include <Arduino.h>
#include <time.h>
#include "board.h"
#include "display_spans.h"

static volatile bool touchIrq = false;
static void IRAM_ATTR onTouchIrq() { touchIrq = true; }

bool i2cWrite(uint8_t addr, uint8_t reg, uint8_t v) {
    return lgfx::i2c::writeRegister8(I2C_PORT, addr, reg, v, 0, 400000).has_value();
}
int i2cRead(uint8_t addr, uint8_t reg) {
    auto r = lgfx::i2c::readRegister8(I2C_PORT, addr, reg, 400000);
    return r.has_value() ? r.value() : -1;
}
bool i2cReadN(uint8_t addr, uint8_t reg, uint8_t *dst, size_t n) {
    return lgfx::i2c::transactionWriteRead(I2C_PORT, addr, &reg, 1, dst, n, 400000).has_value();
}

// AXP2101: make sure the panel rail (BLDO1 3.3 V) is on; the other rails keep their defaults.
static void pmuPanelOn() {
    int v = i2cRead(ADDR_PMU, 0x90);
    if (v < 0) { Serial.println("pmu: AXP2101 not responding"); return; }
    i2cWrite(ADDR_PMU, 0x96, 0x1C);                    // BLDO1 = 0.5 + 28*0.1 = 3.3 V
    i2cWrite(ADDR_PMU, 0x90, (v & 0x01) | 0x10);       // keep ALDO1, enable BLDO1
    delay(20);
}

bool LGFX::init() {
    lgfx::i2c::init(I2C_PORT, PIN_I2C_SDA, PIN_I2C_SCL);
    pmuPanelOn();
    bool ok = LGFX_Device::init();
    pinMode(PIN_TP_RST, OUTPUT);
    digitalWrite(PIN_TP_RST, LOW);
    delay(10);
    digitalWrite(PIN_TP_RST, HIGH);
    delay(100);
    pinMode(PIN_TP_INT, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(PIN_TP_INT), onTouchIrq, FALLING);
    _touchOk = true;
    Serial.printf("touch: %s\n", lgfx::i2c::transactionWrite(I2C_PORT, ADDR_TOUCH, nullptr, 0, 100000).has_value() ? "ok" : "no ACK (power-cycle fully if stuck)");
    return ok;
}

// CST9217 read by hand (only after an interrupt or while a finger is down: reading it idle can stall the bus)
bool LGFX::getTouch(lgfx::touch_point_t *tp) {
    if (!_touchOk) return false;
    static uint32_t lastPoll = 0;
    bool intLow = digitalRead(PIN_TP_INT) == LOW;
    if (!touchIrq && !_down && !(intLow && millis() - lastPoll > 50)) return false;
    lastPoll = millis();
    touchIrq = false;
    static const uint8_t cmd[2] = {0xD0, 0x00};
    uint8_t d[10] = {};
    if (!lgfx::i2c::transactionWriteRead(I2C_PORT, ADDR_TOUCH, cmd, 2, d, sizeof(d), 400000).has_value()) {
        _down = false;
        return false;
    }
    static const uint8_t ack[3] = {0xD0, 0x00, 0xAB};
    lgfx::i2c::transactionWrite(I2C_PORT, ADDR_TOUCH, ack, 3, 400000);
    int n = d[5] & 0x7F;
    if (d[6] != 0xAB || n == 0 || n > 2 || (d[0] & 0x0F) != 0x06) {
        _down = false;
        return false;
    }
    int x = (d[1] << 4) | (d[3] >> 4), y = (d[2] << 4) | (d[3] & 0x0F);
    tp->x = constrain(WIDTH - 1 - x, 0, WIDTH - 1);       // panel is rotated 180° vs touch
    tp->y = constrain(HEIGHT - 1 - y, 0, HEIGHT - 1);
    _down = true;
    return true;
}

// Tearing-free updates: start sending right after the panel's TE pulse (start of vertical blank).
// A full frame (434 KB over 80 MHz QSPI) takes ~11 ms, less than one ~16.7 ms scan, so it never overtakes the scan.
static void waitTE() {
    static bool init = false,available=false;
    if (!init) {
        pinMode(PIN_LCD_TE, INPUT);init=true;
        // Some panel revisions do not expose a running TE signal. Do not pay
        // a 20ms timeout on every frame when there is no edge to synchronize to.
        uint32_t start=micros();bool hi=false,lo=false;
        while(micros()-start<50000){if(digitalRead(PIN_LCD_TE))hi=true;else lo=true;if(hi&&lo)break;}
        available=hi&&lo;
        Serial.printf("display: TE %s\n",available?"active":"not present; bounded flush");
    }
    if(!available)return;
    uint32_t t0 = micros();
    while (digitalRead(PIN_LCD_TE) == HIGH && micros() - t0 < 20000) {}
    while (digitalRead(PIN_LCD_TE) == LOW && micros() - t0 < 20000) {}
}

void LGFX::flush(LGFX_Sprite &s, int x, int y, int w, int h, bool edgeBand) {
    int x1 = min(WIDTH, x + w), y1 = min(HEIGHT, y + h);
    x = max(0, x) & ~1;
    y = max(0, y) & ~1;
    x1 = min(WIDTH, (x1 + 1) & ~1);
    y1 = min(HEIGHT, (y1 + 1) & ~1);
    if (x1 <= x || y1 <= y) return;
    static uint16_t *band = nullptr;
    constexpr int rows=12;
    if (!band) band = (uint16_t *)heap_caps_malloc(WIDTH * rows * 2, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    if(!band)return;
    const uint16_t *src = (const uint16_t *)s.getBuffer();
    uint32_t t0=micros();waitTE();uint32_t t1=micros();
    startWrite();
    const int firstRow=edgeBand ? 0:y,lastRow=edgeBand ? HEIGHT:y1;
    for (int yy = firstRow; yy < lastRow; yy += rows) {
        int bh = min(rows, lastRow - yy);
        // One TE sync for the entire frame, up to three merged regions per band.
        auto regions=displaySpans(x,x1,y,y1,yy,bh,edgeBand,WIDTH,HEIGHT,WIDTH==466 && HEIGHT==466);
        for(int i=0;i<regions.count;i++){
            int left=regions.spans[i].left,bw=regions.spans[i].right-left;
            waitDMA();
            for(int r=0;r<bh;r++)memcpy(band+r*bw,src+(yy+r)*WIDTH+left,bw*2);
            pushImageDMA(left,yy,bw,bh,(const lgfx::swap565_t*)band);
        }
    }
    waitDMA();
    endWrite();
    static uint32_t samples=0,syncUs=0,transferUs=0;
    syncUs+=t1-t0;transferUs+=micros()-t1;
    if(++samples==200){Serial.printf("display: sync %u us, transfer %u us/frame\n",syncUs/samples,transferUs/samples);samples=syncUs=transferUs=0;}
}

void LGFX::panelBrightness(uint8_t v) { setBrightness(v); }

void LGFX::panelSleep(bool on) {
    if (on) {
        powerSave(true);     // 0x28 display off
        sleep();             // 0x10 sleep in
    } else {
        wakeup();            // 0x11 sleep out (needs ~120 ms before drawing)
        delay(130);
        powerSave(false);    // 0x29 display on
    }
}

// --- QMI8658 accelerometer --------------------------------------------------------------
static bool imuOk = false;
bool imuBegin() {
    if (i2cRead(ADDR_IMU, 0x00) != 0x05) { Serial.println("imu: QMI8658 not found"); return false; }
    i2cWrite(ADDR_IMU, 0x60, 0xB0);   // soft reset (the factory firmware may have left it in another mode)
    for (int i = 0; i < 20 && i2cRead(ADDR_IMU, 0x4D) != 0x80; i++) delay(5);   // RST_RESULT
    i2cWrite(ADDR_IMU, 0x02, 0x40);   // CTRL1: address auto-increment, little endian
    i2cWrite(ADDR_IMU, 0x03, 0x16);   // CTRL2: ±4 g, ~125 Hz
    i2cWrite(ADDR_IMU, 0x08, 0x01);   // CTRL7: accelerometer only
    imuOk = true;
    return true;
}

Accel imuRead() {
    Accel a{0, 0, 0, false};
    if (!imuOk) return a;
    uint8_t d[6];
    if (!i2cReadN(ADDR_IMU, 0x35, d, 6)) return a;
    int16_t r[3];
    for (int i = 0; i < 3; i++) r[i] = (int16_t)(d[2 * i] | d[2 * i + 1] << 8);
    // sensor -> screen frame (verified on device with the serial 'imu' command; adjust here if needed)
    a.x = -r[1] / 8192.f;
    a.y = -r[0] / 8192.f;
    a.z = r[2] / 8192.f;
    a.ok = true;
    return a;
}

void imuSleep() {
    if (imuOk) i2cWrite(ADDR_IMU, 0x08, 0x00);
}

// --- PCF85063 RTC (stores local time) ----------------------------------------------------
static uint8_t bcd(int v) { return ((v / 10) << 4) | (v % 10); }
static int unbcd(uint8_t v) { return (v >> 4) * 10 + (v & 0x0F); }

bool rtcRead(struct tm *t) {
    uint8_t d[7];
    if (!i2cReadN(ADDR_RTC, 0x04, d, 7)) return false;
    if (d[0] & 0x80) return false;                 // oscillator stopped: time not valid
    memset(t, 0, sizeof(*t));
    t->tm_sec = unbcd(d[0] & 0x7F);
    t->tm_min = unbcd(d[1] & 0x7F);
    t->tm_hour = unbcd(d[2] & 0x3F);
    t->tm_mday = unbcd(d[3] & 0x3F);
    t->tm_wday = d[4] & 0x07;
    t->tm_mon = unbcd(d[5] & 0x1F) - 1;
    t->tm_year = unbcd(d[6]) + 100;
    t->tm_isdst = -1;
    return t->tm_year > 120;
}

void rtcWrite(const struct tm *t) {
    i2cWrite(ADDR_RTC, 0x04, bcd(t->tm_sec));
    i2cWrite(ADDR_RTC, 0x05, bcd(t->tm_min));
    i2cWrite(ADDR_RTC, 0x06, bcd(t->tm_hour));
    i2cWrite(ADDR_RTC, 0x07, bcd(t->tm_mday));
    i2cWrite(ADDR_RTC, 0x08, t->tm_wday);
    i2cWrite(ADDR_RTC, 0x09, bcd(t->tm_mon + 1));
    i2cWrite(ADDR_RTC, 0x0A, bcd(t->tm_year % 100));
}

// --- TCA9554: PWR key level on EXIO4 ------------------------------------------------------
bool pwrButtonDown() {
    static bool initialized=false;
    if(!initialized){pinMode(PIN_PWR_SENSE,INPUT_PULLUP);initialized=true;}
    return digitalRead(PIN_PWR_SENSE)==HIGH;
}
