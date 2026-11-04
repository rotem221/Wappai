// Audio: ES8311 (speaker) + ES7210 (mics) over I2S at 16 kHz. Adapted from Pana (MIT).
#include "audio.h"
#include "storage/recording_store.h"
#include "board.h"
#include <ESP_I2S.h>
#include <freertos/ringbuf.h>
#include <esp_rom_gpio.h>
#include <soc/gpio_sig_map.h>

static I2SClass i2s;
static const int RATE = 16000;
static bool ready = false;
static volatile bool micReceiverActive = true;
bool audioMicReceiverActive(){return micReceiverActive;}

// reproducción: ring buffer de muestras mono en PSRAM (20 s)
static const size_t PLAY_CAP = RATE * 20;
static int16_t *playBuf = nullptr;
static volatile size_t rd = 0, wr = 0;
static volatile bool open_ = false, playing = false;
static volatile float mouth = 0;
static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

// micrófono
// Mic ring in PSRAM: ~96 s of audio, so a meeting survives a Wi-Fi drop (the net task stops draining it while the
// server is unreachable and catches up after reconnecting).
static const size_t MIC_RING_BYTES = 3 * 1024 * 1024;
static RingbufHandle_t micRing = nullptr;
static volatile bool micOn = false;
static volatile size_t micDropped=0;
static volatile bool micCapacityStop=false;
static volatile int micCh = 0;          // 0 = left (MIC1), 1 = right (MIC2), 2 = average of both
static volatile float micLvl = 0;

static bool wr8(uint8_t reg, uint8_t v) {
    return lgfx::i2c::writeRegister8(I2C_PORT, 0x18, reg, v, 0, 400000).has_value();
}

static size_t avail() { return (wr + PLAY_CAP - rd) % PLAY_CAP; }

// Misma secuencia que el YT Gadget (esp_codec_dev, MCLK = 256 x 16 kHz) con el ADC activo.
static bool codecInit() {
    bool ok = wr8(0x0D, 0xFA);
    wr8(0x44, 0x08); ok &= wr8(0x44, 0x08);
    ok &= wr8(0x01, 0x30) && wr8(0x02, 0x00) && wr8(0x03, 0x10) && wr8(0x16, 0x24)
       && wr8(0x04, 0x10) && wr8(0x05, 0x00) && wr8(0x0B, 0x00) && wr8(0x0C, 0x00)
       && wr8(0x10, 0x1F) && wr8(0x11, 0x7F) && wr8(0x00, 0x80) && wr8(0x01, 0x3F)
       && wr8(0x06, 0x00) && wr8(0x13, 0x10) && wr8(0x1B, 0x0A) && wr8(0x1C, 0x6A)
       && wr8(0x44, 0x58);
    ok &= wr8(0x09, 0x0C) && wr8(0x0A, 0x0C);
    ok &= wr8(0x02, 0x00) && wr8(0x05, 0x00) && wr8(0x03, 0x10) && wr8(0x04, 0x20)
       && wr8(0x07, 0x00) && wr8(0x08, 0xFF) && wr8(0x06, 0x03);
    // ADC: PGA al máximo (0x14) y +8 dB digitales (0x17); el servidor normaliza el resto
    ok &= wr8(0x17, 0xCF) && wr8(0x0E, 0x02) && wr8(0x12, 0x00) && wr8(0x14, 0x1A)
       && wr8(0x0D, 0x01) && wr8(0x15, 0x40) && wr8(0x37, 0x08) && wr8(0x45, 0x00);
    ok &= wr8(0x32, 0xBF) && wr8(0x31, 0x00);
    return ok;
}

#ifdef HAS_ES7210
// En las redondas los micros van por un ES7210 (0x40) en esclavo: MIC1 y MIC2 en I2S de 16 bits,
// MIC1 en el canal izquierdo, que es el que se queda micTask. Secuencia de esp_codec_dev
// (es7210_open + mic_select + start) con 30 dB de PGA, como el BSP de Waveshare.
static bool w7210(uint8_t reg, uint8_t v) {
    return lgfx::i2c::writeRegister8(I2C_PORT, 0x40, reg, v, 0, 400000).has_value();
}
static uint8_t r7210(uint8_t reg) {
    auto r = lgfx::i2c::readRegister8(I2C_PORT, 0x40, reg, 400000);
    return r.has_value() ? r.value() : 0;
}
static bool micInit() {
    bool ok = w7210(0x00, 0xFF) && w7210(0x00, 0x41) && w7210(0x01, 0x3F) && w7210(0x09, 0x30)
           && w7210(0x0A, 0x30) && w7210(0x23, 0x2A) && w7210(0x22, 0x0A) && w7210(0x20, 0x0A)
           && w7210(0x21, 0x2A);
    ok &= w7210(0x08, r7210(0x08) & ~0x01);                     // esclavo
    ok &= w7210(0x40, 0x43) && w7210(0x41, 0x70) && w7210(0x42, 0x70) && w7210(0x07, 0x20)
       && w7210(0x02, 0xC1);
    for (int i = 0; i < 4; i++) ok &= w7210(0x43 + i, r7210(0x43 + i) & ~0x10);
    ok &= w7210(0x4B, 0xFF) && w7210(0x4C, 0xFF);
    ok &= w7210(0x01, r7210(0x01) & ~0x0B) && w7210(0x4B, 0x00);   // MIC1 y MIC2
    ok &= w7210(0x43, (r7210(0x43) & 0xE0) | 0x10 | 0x0A);         // 0x0A = 30 dB
    ok &= w7210(0x44, (r7210(0x44) & 0xE0) | 0x10 | 0x0A);
    ok &= w7210(0x12, 0x00);                                       // sin TDM
    ok &= w7210(0x11, (r7210(0x11) & 0x1C) | 0x60);                // I2S normal, 16 bits
    uint8_t off = r7210(0x01);
    ok &= w7210(0x01, off) && w7210(0x06, 0x00) && w7210(0x40, 0x43) && w7210(0x47, 0x08)
       && w7210(0x48, 0x08) && w7210(0x49, 0x08) && w7210(0x4A, 0x08) && w7210(0x40, 0x43)
       && w7210(0x00, 0x71) && w7210(0x00, 0x41);
    return ok;
}
#endif

static float levelOf(const int16_t *x, int n) {
    double acc = 0;
    for (int i = 0; i < n; i++) acc += (double)x[i] * x[i];
    float rms = sqrt(acc / n) / 32768.0f;
    float db = 20 * log10f(max(rms, 1e-5f));
    return constrain((db + 42.f) / 26.f, 0.f, 1.f);   // -42 dBFS -> 0, -16 dBFS -> 1
}

static void playTask(void *) {
    static int16_t mono[256], st[512];
    for (;;) {
        // arranca cuando hay 250 ms en cola (o ya se cerró el say): así no tartamudea
        if (!playing) {
            if (avail() > RATE / 4 || (!open_ && avail() > 0)) {
                playing = true;
                Serial.printf("spk: on %lu\n", (unsigned long)millis());   // for latency measurements
                digitalWrite(PIN_PA, HIGH);
                vTaskDelay(pdMS_TO_TICKS(20));
            } else {
                mouth = 0;
                vTaskDelay(pdMS_TO_TICKS(10));
                continue;
            }
        }
        size_t n = min((size_t)256, avail());
        if (n == 0) {
            if (!open_) {                     // se acabó: silencio para vaciar el DMA y apagar
                memset(st, 0, sizeof(st));
                for (int k = 0; k < 4; k++) i2s.write((uint8_t *)st, sizeof(st));
                digitalWrite(PIN_PA, !HIGH);
                playing = false;
                mouth = 0;
            } else {
                vTaskDelay(pdMS_TO_TICKS(5)); // esperando más red
            }
            continue;
        }
        for (size_t i = 0; i < n; i++) {
            mono[i] = playBuf[rd];
            rd = (rd + 1) % PLAY_CAP;
            st[2 * i] = st[2 * i + 1] = mono[i];
        }
        mouth = levelOf(mono, n);
        i2s.write((uint8_t *)st, n * 4);      // bloquea al ritmo del DAC
    }
}

// diagnóstico (serie m): un segundo de micro, nivel de cada canal por separado
static volatile int testLeft = 0;
static double testSum[2];
static int32_t testPeak[2], testN = 0;

static void micTask(void *) {
    static int16_t st[1024 * 2], mono[1024];
    for (;;) {
        // This task alone owns RX enable/disable; TX keeps its shared clock for
        // chirps and speech. Do not keep capturing/discarding audio while idle.
        const bool needed=micOn || testLeft>0;
        if(needed!=micReceiverActive){
            esp_err_t result=needed ? i2s_channel_enable(i2s.rxChan()):i2s_channel_disable(i2s.rxChan());
            if(result==ESP_OK)micReceiverActive=needed;
        }
        if(!needed || !micReceiverActive){vTaskDelay(pdMS_TO_TICKS(20));continue;}
        size_t got = i2s.readBytes((char *)st, sizeof(st));
        int n = got / 4;
        if (testLeft > 0) {
            for (int i = 0; i < n; i++)
                for (int c = 0; c < 2; c++) {
                    int32_t v = st[2 * i + c];
                    testSum[c] += (double)v * v;
                    testPeak[c] = max(testPeak[c], abs(v));
                }
            testN += n;
            testLeft -= n;
        }
        if (!micOn || n == 0) continue;
        double acc = 0;
        for (int i = 0; i < n; i++) {
            mono[i] = micCh == 2 ? (int16_t)(((int32_t)st[2 * i] + st[2 * i + 1]) / 2) : st[2 * i + micCh];
            acc += (double)mono[i] * mono[i];
        }
        float rms = sqrt(acc / n) / 32768.0f;
        micLvl = min(1.0f, rms * 12.f);
        bool saved=recordingStoreActive()?recordingStoreWrite((uint8_t*)mono,n*2):xRingbufferSend(micRing,mono,n*2,0)==pdTRUE;
        if(!saved){micDropped+=n*2;micCapacityStop=true;micOn=false;}
        // Stop before exhausting the RAM buffer; preserve captured audio for reconnection.
        if(!recordingStoreActive() && xRingbufferGetCurFreeSize(micRing)<32000*4){micCapacityStop=true;micOn=false;}
    }
}

bool audioBegin() {
    recordingStoreBegin();
    pinMode(PIN_PA, OUTPUT);
    digitalWrite(PIN_PA, !HIGH);
    playBuf = (int16_t *)ps_malloc(PLAY_CAP * 2);
    micRing = xRingbufferCreateWithCaps(MIC_RING_BYTES, RINGBUF_TYPE_BYTEBUF, MALLOC_CAP_SPIRAM);
    i2s.setPins(PIN_I2S_BCLK, PIN_I2S_WS, PIN_I2S_DOUT, PIN_I2S_DIN, PIN_I2S_MCLK);
    if (!playBuf || !micRing || !i2s.begin(I2S_MODE_STD, RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO))
        return false;
    // 1.75C connects both codecs directly to GPIO16; no duplicate clock pin.
    delay(10);
    ready = codecInit();
#ifdef HAS_ES7210
    bool mic = micInit();
    if (!mic) Serial.println("ES7210: no responde");
    ready &= mic;
#endif
    xTaskCreatePinnedToCore(playTask, "play", 4096, nullptr, 5, nullptr, 0);
    xTaskCreatePinnedToCore(micTask, "mic", 4096, nullptr, 4, nullptr, 0);
    return ready;
}

void audioOpen(bool reset) {
    portENTER_CRITICAL(&mux);
    if (reset) rd = wr = 0;                   // a new utterance cuts whatever was playing
    open_ = true;
    portEXIT_CRITICAL(&mux);
}

void audioStop() {
    portENTER_CRITICAL(&mux);
    rd = wr = 0;
    open_ = false;
    portEXIT_CRITICAL(&mux);
}

float audioMicLevel() { return micOn ? micLvl : 0; }

// alarm: three rising beeps, repeated by the caller
void audioAlarm() {
    constexpr size_t bytes = (RATE * 3 / 4) * sizeof(int16_t);
    int16_t *buf = (int16_t *)ps_malloc(bytes);
    if (!buf) return;
    const int n = bytes / 2;
    for (int i = 0; i < n; i++) {
        int k = i / (RATE / 4), j = i % (RATE / 4);
        float f = 880 + k * 220, env = j < RATE / 8 ? sinf(PI * j / (RATE / 8)) : 0;
        buf[i] = sinf(2 * PI * f * i / RATE) * 9000 * env;
    }
    audioOpen(true);
    audioPush((uint8_t *)buf, bytes);
    audioClose();
    free(buf);
}

void audioPush(const uint8_t *pcm, size_t n) {
    if (!open_) return;                       // frame sin say abierto: se descarta
    const int16_t *x = (const int16_t *)pcm;
    for (size_t i = 0; i < n / 2; i++) {
        size_t next = (wr + 1) % PLAY_CAP;
        if (next == rd) break;                // lleno
        playBuf[wr] = x[i];
        wr = next;
    }
}

void audioClose() { open_ = false; }
bool audioPlaying() { return playing || open_; }
float audioMouth() { return mouth; }

void audioMic(bool on) {
    if (on) {
        micDropped=0;micCapacityStop=false;       // start a fresh capture
        size_t sz;
        void *it;
        while ((it = xRingbufferReceiveUpTo(micRing, &sz, 0, MIC_RING_BYTES))) vRingbufferReturnItem(micRing, it);
    }
    micOn = on;
}

size_t audioMicDropped(){return micDropped;}
bool audioMicCapacityStop(){return micCapacityStop;}
size_t audioMicQueued() {
    if(recordingStoreActive())return recordingStoreQueued();
    UBaseType_t freeB = xRingbufferGetCurFreeSize(micRing);
    return MIC_RING_BYTES > freeB ? MIC_RING_BYTES - freeB : 0;
}

size_t audioMicPop(uint8_t *dst, size_t max) {
    if(recordingStoreActive())return recordingStoreRead(dst,max);
    size_t sz = 0;
    void *it = xRingbufferReceiveUpTo(micRing, &sz, 0, max);
    if (!it) return 0;
    memcpy(dst, it, sz);
    vRingbufferReturnItem(micRing, it);
    return sz;
}

// barrido corto al abrir (sube) y cerrar (baja) el micro; corta lo que estuviera sonando
void audioChirp(bool up) {
    constexpr size_t bytes = (RATE / 10 * 2) * sizeof(uint8_t);
    uint8_t *buf = (uint8_t *)ps_malloc(bytes);
    if (!buf) return;
    int16_t *x = (int16_t *)buf;
    const int n = RATE / 10;
    float ph = 0;
    for (int i = 0; i < n; i++) {
        float t = (float)i / n, f = up ? 700 + 500 * t : 1200 - 500 * t;
        ph += 2 * PI * f / RATE;
        x[i] = sinf(ph) * 5000 * sinf(PI * t);
    }
    audioOpen(true);
    audioPush(buf, bytes);
    audioClose();
    free(buf);
}

void audioMicTest() {
    testSum[0] = testSum[1] = 0;
    testPeak[0] = testPeak[1] = 0;
    testN = 0;
    testLeft = RATE;
    while (testLeft > 0) delay(20);
    for (int c = 0; c < 2; c++) {
        float rms = testN ? sqrt(testSum[c] / testN) : 0;
        Serial.printf("micro %s: rms %.0f (%.1f dBFS) · pico %d\n", c ? "der" : "izq", rms,
                      20 * log10f(max(rms, 1.0f) / 32768.0f), (int)testPeak[c]);
    }
#ifdef HAS_ES7210
    Serial.print("es7210:");
    static const uint8_t regs[] = {0x00, 0x01, 0x02, 0x06, 0x07, 0x08, 0x11, 0x12, 0x40, 0x41, 0x43, 0x44, 0x47, 0x48, 0x4B, 0x4C};
    for (uint8_t r : regs) Serial.printf(" %02x=%02x", r, r7210(r));
    Serial.println();
#endif
}

void audioBeep() {
    constexpr size_t bytes = (RATE / 5 * 2) * sizeof(uint8_t);
    uint8_t *buf = (uint8_t *)ps_malloc(bytes);
    if (!buf) return;
    int16_t *x = (int16_t *)buf;
    for (int i = 0; i < RATE / 5; i++) x[i] = sinf(2 * PI * 1100 * i / RATE) * 6000 * expf(-(float)i / RATE * 12);
    audioOpen(true);
    audioPush(buf, bytes);
    audioClose();
    free(buf);
}

// ---- mic diagnostics and tuning (serial: mic, mictone, micgain N, micch N)
void audioMicTone() {
    constexpr size_t bytes = (RATE * 6 / 5) * sizeof(int16_t);
    int16_t *buf = (int16_t *)ps_malloc(bytes);
    if (!buf) return;
    const int n = bytes / 2;
    for (int i = 0; i < n; i++) buf[i] = sinf(2 * PI * 1000 * i / RATE) * 4000;
    audioOpen(true);
    audioPush((uint8_t *)buf, bytes);
    audioClose();
    free(buf);
    delay(450);                               // measure while the speaker plays (mic should hear it loudly)
    audioMicTest();
}

void audioMicGain(int g) {
#ifdef HAS_ES7210
    g = constrain(g, 0, 14);                  // 0 = 0 dB ... 10 = 30 dB ... 14 = 37.5 dB
    w7210(0x43, (r7210(0x43) & 0xF0) | 0x10 | g);
    w7210(0x44, (r7210(0x44) & 0xF0) | 0x10 | g);
    Serial.printf("mic gain %d\n", g);
#endif
}

void audioMicChannel(int c) {
    micCh = constrain(c, 0, 2);
    Serial.printf("mic channel %d\n", micCh);
}

// Speaker volume 0..100 through the ES8311 DAC volume (0xBF = 0 dB, 0.5 dB steps): 100 = 0 dB, 50 = -20 dB, 0 = mute.
void audioSetVolume(int v) {
    v = constrain(v, 0, 100);
    int reg = v == 0 ? 0 : 0xBF - (100 - v) * 4 / 5;
    wr8(0x32, (uint8_t)reg);
}

void audioPipCue(uint8_t rig,const char *cue) {
    static uint32_t last=0;
    if(!strcmp(cue,"none") || audioPlaying() || millis()-last<4000)return;
    last=millis();
    const int n=RATE*42/100;uint8_t *buf=(uint8_t*)ps_malloc(n*2);if(!buf)return;
    float base=rig==1?680:rig==2?350:520,phase=0;
    float rise=!strcmp(cue,"joy")?1.5f:!strcmp(cue,"curious")?1.25f:!strcmp(cue,"hello")?1.15f:.85f;
    int16_t *pcm=(int16_t*)buf;
    for(int i=0;i<n;i++) {float u=(float)i/n,t=(float)i/RATE;phase+=2*PI*(base*(1+(rise-1)*u)+sinf(t*24)*12)/RATE;float env=sinf(PI*u);pcm[i]=(sinf(phase)+(rig==2?.16f*sinf(phase*2):.04f*sinf(phase*3)))*env*env*3800;}
    if(!audioPlaying()){audioOpen(true);audioPush(buf,n*2);audioClose();}free(buf);
}

#include "shake_voice.h"
void audioShakeComplaint(){
    if(audioPlaying())return;
    audioOpen(true);audioPush(SHAKE_VOICE,sizeof SHAKE_VOICE);audioClose();
}
