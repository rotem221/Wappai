#include "app/pip_storage.h"
#include <mbedtls/sha256.h>
// Network task (core 0): Wi-Fi (on-device setup screen when unknown), WebSocket to the brain over
// TLS (Tailscale Funnel) or plain ws on the LAN, the protocol (docs/PROTOCOL.md), mic upload and OTA.
// Every WebSocket call happens in this task: the library is not thread-safe.
#include "net.h"
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <HTTPUpdate.h>
#include <NetworkClientSecure.h>
#include <Preferences.h>
#include <WebSocketsClient.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <sys/time.h>
#include "app/model.h"
#include "audio/audio.h"
#include "board.h"
#include "ca_certs.h"
#include "config.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

static WebSocketsClient ws;
static QueueHandle_t outQ;
static Preferences prefs;
static String url, token, host, path;
static String assetRequest;
static void assetReply(const String &id,const char *status){JsonDocument d;d["type"]="command.result";d["id"]=id;d["status"]=status;String out;serializeJson(d,out);netSend(out);}
static uint16_t port = 0;
static bool tls = false;
static volatile bool micMeeting = false, adpcmReset = false;
static volatile bool micActive = false, micStopPending = false, shutdownReq = false, restartReq = false;
static String otaUrl;
static String curUtt;
static volatile int batPct = -1, batMv = 0;
static volatile bool batChg = false, batUsb = false;
static uint32_t lastStatus = 0;

void netSend(const String &json) {
    String *s = new String(json);
    if (xQueueSend(outQ, &s, 0) != pdTRUE) delete s;
}

void netMicStart(bool meeting) {
    curUtt="";
    micMeeting = meeting;
    adpcmReset = true;
    if (meeting) { modelLock(); model.meetingId[0] = 0; model.meetingTitle[0] = 0; modelUnlock(); }
    netSend(meeting ? "{\"type\":\"ptt_start\",\"id\":\"mic\",\"mode\":\"meeting\",\"sample_rate\":16000,\"codec\":\"adpcm\"}"
                    : "{\"type\":\"ptt_start\",\"id\":\"mic\",\"sample_rate\":16000}");
    audioMic(true);
    micActive = true;
}

void netMicStop() {
    micActive = false;
    micStopPending = true;
}

void netSetBattery(int pct, int mv, bool charging, bool usb) { batPct = pct; batMv = mv; batChg = charging; batUsb = usb; }
void netShutdown() { shutdownReq = true; delay(300); }

// ---- IMA ADPCM (meetings): block = int16 predictor (LE), uint8 step index, 0, then 2 samples per byte (low nibble first)
static const int ADPCM_BLOCK = 2048;
static const int16_t ADPCM_STEP[89] = {7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80,
    88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963,
    1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132,
    7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767};
static const int8_t ADPCM_IDX[16] = {-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8};
static int adpcmPred = 0, adpcmIdx = 0;          // carried between blocks (each block still states it)

static size_t adpcmEncode(const int16_t *x, size_t n, uint8_t *out) {
    if (adpcmReset) { adpcmReset = false; adpcmPred = 0; adpcmIdx = 0; }
    out[0] = adpcmPred & 255; out[1] = (adpcmPred >> 8) & 255; out[2] = adpcmIdx; out[3] = 0;
    size_t o = 4;
    for (size_t i = 0; i < n; i++) {
        int step = ADPCM_STEP[adpcmIdx], diff = x[i] - adpcmPred, code = 0;
        if (diff < 0) { code = 8; diff = -diff; }
        int delta = step >> 3;
        if (diff >= step) { code |= 4; diff -= step; delta += step; }
        step >>= 1;
        if (diff >= step) { code |= 2; diff -= step; delta += step; }
        step >>= 1;
        if (diff >= step) { code |= 1; delta += step; }
        adpcmPred += (code & 8) ? -delta : delta;
        if (adpcmPred > 32767) adpcmPred = 32767; else if (adpcmPred < -32768) adpcmPred = -32768;
        adpcmIdx += ADPCM_IDX[code];
        if (adpcmIdx < 0) adpcmIdx = 0; else if (adpcmIdx > 88) adpcmIdx = 88;
        if (i & 1) out[o++] |= code << 4;
        else out[o] = code;
    }
    if (n & 1) o++;
    return o;
}

static void parseUrl(const String &u) {
    tls = u.startsWith("wss://");
    String rest = u.substring(u.indexOf("://") + 3);
    int slash = rest.indexOf('/');
    String hp = slash >= 0 ? rest.substring(0, slash) : rest;
    path = slash >= 0 ? rest.substring(slash) : "/ws";
    int colon = hp.indexOf(':');
    host = colon >= 0 ? hp.substring(0, colon) : hp;
    port = colon >= 0 ? hp.substring(colon + 1).toInt() : (tls ? 443 : 80);
}

static String batteryJson() {
    char b[96];
    snprintf(b, sizeof b, "{\"pct\":%d,\"mv\":%d,\"charging\":%s,\"usb\":%s}", batPct, batMv, batChg ? "true" : "false", batUsb ? "true" : "false");
    return b;
}

static void sendHello() {
    modelLock();String custom=model.customPip?model.customPip->pip:"";modelUnlock();
    String m = "{\"type\":\"hello\",\"device_id\":\"" + WiFi.macAddress() + "\",\"fw_version\":\"" FW_VERSION
               "\",\"name\":\"" DEVICE_NAME "\",\"board\":\"ws-s3-175c\",\"screen\":[466,466],\"has_mic\":true,\"has_speaker\":true,\"battery\":" +
               batteryJson() + ",\"custom_pip_id\":\""+custom+"\"}";
    ws.sendTXT(m);
}

static void setClock(time_t t) {
    if (t < 1700000000) return;
    struct timeval tv = {t, 0};
    settimeofday(&tv, nullptr);
    struct tm lt;
    localtime_r(&t, &lt);
    static time_t lastRtc = 0;
    if (t - lastRtc > 3600) { rtcWrite(&lt); lastRtc = t; }
}

// strlcpy that never leaves half a UTF-8 letter at the end (Hebrew names longer than the field)
static void copyUtf8(char *dst, const char *src, size_t n) {
    strlcpy(dst, src ? src : "", n);
    size_t len = strlen(dst);
    if (len + 1 < n || !len) return;                             // not truncated
    size_t i = len;
    while (i > 0 && (dst[i - 1] & 0xC0) == 0x80) i--;            // start of the last letter
    if (i > 0) {
        uint8_t lead = dst[i - 1];
        size_t need = lead >= 0xF0 ? 4 : lead >= 0xE0 ? 3 : lead >= 0xC0 ? 2 : 1;
        if (len - (i - 1) < need) dst[i - 1] = 0;
    }
}

static void readWeather(JsonVariantConst w, Model::Weather &o) {
    o.ok = w["t"].is<int>() || w["t"].is<float>();
    if (!o.ok) return;
    o.t = w["t"] | 0; o.feels = w["feels"] | o.t; o.mn = w["min"] | 0; o.mx = w["max"] | 0;
    o.rain = w["rain"] | 0; o.hum = w["hum"] | 0;
    copyUtf8(o.text, w["text"] | "", sizeof o.text);
    strlcpy(o.icon, w["icon"] | "", sizeof o.icon);
    copyUtf8(o.city, w["city"] | "", sizeof o.city);
    o.tmn = w["tmin"] | 0; o.tmx = w["tmax"] | 0; o.train = w["train"] | 0;
    copyUtf8(o.ttext, w["ttext"] | "", sizeof o.ttext);
    strlcpy(o.ticon, w["ticon"] | "", sizeof o.ticon);
}

static void readHa(JsonVariantConst v, Model::HaItem &o) {
    strlcpy(o.id, v["id"] | "", sizeof o.id);
    copyUtf8(o.name, v["name"] | "", sizeof o.name);
    strlcpy(o.kind, v["kind"] | "", sizeof o.kind);
    copyUtf8(o.state, v["state"] | "", sizeof o.state);
    o.on = v["on"] | false;
    o.avail = v["available"] | true;
}

static void onText(const char *txt, size_t len) {
    JsonDocument d;
    if (len > 16384 || deserializeJson(d, txt, len)) return;
    const char *t = d["type"] | "";
    if (!strcmp(t, "ping")) {
        setClock((time_t)(d["t"] | 0));
        char r[48];
        snprintf(r, sizeof r, "{\"type\":\"pong\",\"t\":%ld}", (long)(d["t"] | 0));
        ws.sendTXT(r);
        return;
    }
    if (!strcmp(t, "say")) {
        if (micActive) return;
        const char *id = d["id"] | "";
        int seq = d["seq"] | 0;
        bool newUtt = curUtt != id || seq == 0;
        curUtt = id;
        if (d["audio"] | false) audioOpen(newUtt);
    } else if (!strcmp(t, "audio_end")) {
        if (d["final"] | true) audioClose();
    } else if (!strcmp(t, "ota")) {
        otaUrl = d["url"] | "";
        return;
    }
    modelLock();
    Model &m = model;
    if (!strcmp(t, "state")) {
        if (d["emotion"].is<const char *>()) { strlcpy(m.emotion, d["emotion"], sizeof m.emotion); m.emotionNew = true; }
        if (d["gesture"].is<const char *>()) { strlcpy(m.gesture, d["gesture"], sizeof m.gesture); m.gestureNew = true; }
        if (d["ring"].is<const char *>()) {
            const char *r = d["ring"];
            m.ring = !strcmp(r, "think") ? RING_THINK : RING_NONE;
        }
    } else if (!strcmp(t,"transcript.partial")) {
        copyUtf8(m.partial,m.liveTranscription && m.recording ? (d["text"]|""):"",sizeof m.partial);m.partialNew=true;
    } else if (!strcmp(t,"interaction")) {
        m.clearCard=d["clear_card"]|false;
        copyUtf8(m.sub,d["text"]|"",sizeof m.sub);m.subNew=true;
        strlcpy(m.emotion,"thinking",sizeof m.emotion);m.emotionNew=true;m.ring=RING_THINK;
    } else if (!strcmp(t,"device.badge")) {
        readHa(d["dev"],m.badge);m.badgePending=d["pending"]|false;
        m.badgeTtl=constrain((int)(d["ttl"]|12),0,60);m.badgeNew=true;
    } else if (!strcmp(t, "say")) {
        copyUtf8(m.sub, d["text"] | "", sizeof m.sub);
        m.subNew = true;
        if (d["emotion"].is<const char *>()) { strlcpy(m.emotion, d["emotion"], sizeof m.emotion); m.emotionNew = true; }
        m.lastActivity = millis();
    } else if (!strcmp(t, "timer")) {
        const char *id=d["id"]|"";
        if(strlen(id)<1 || strlen(id)>48 || strspn(id,"0123456789abcdefABCDEF-")!=strlen(id)) { modelUnlock(); return; }
        Preferences saved; saved.begin("wappai-timers",false);
        if(saved.getString("id","")==id) { saved.end(); modelUnlock(); ws.sendTXT(String("{\"type\":\"command.result\",\"status\":\"applied\",\"id\":\"")+id+"\"}"); return; }
        uint32_t s = d["seconds"] | 0;
        if (s>86400) { saved.end(); modelUnlock(); return; }
        m.timerOn = s > 0;
        m.timerTotal = s * 1000;
        m.timerEnd = millis() + s * 1000;
        strlcpy(m.timerLabel, d["label"] | "", sizeof m.timerLabel);
        saved.putString("id",id); saved.putULong64("deadline",(uint64_t)time(nullptr)+s);
        saved.putUInt("total",s); saved.putString("label",m.timerLabel); saved.putBool("active",s>0); saved.end();
        JsonDocument ack;ack["type"]="command.result";ack["id"]=id;ack["status"]="applied";String msg;serializeJson(ack,msg);netSend(msg);
    } else if (!strcmp(t, "timer_cancel")) {
        m.timerOn = false;
        Preferences saved;saved.begin("wappai-timers",false);saved.putBool("active",false);saved.end();
    } else if (!strcmp(t, "stop")) {
        m.stopAudio = true;
    } else if (!strcmp(t, "record")) {
        m.meetingReq = 1;
    } else if (!strcmp(t, "record_stop")) {
        m.meetingReq = 2;
    } else if (!strcmp(t,"pip.expression")) {
        int rig=d["rig"]|-1;
        if(rig>=0 && rig<PIXEL_RIG_COUNT+(m.customPip?1:0) && d["pose"].is<JsonObject>()) {
            const char *id=d["id"]|"";
            if(strlen(id)!=32 || strspn(id,"0123456789abcdef")!=32){modelUnlock();return;}
            strlcpy(m.expressionId,id,sizeof m.expressionId);m.expressionRig=rig;m.expressionColor=d["color"]|0U;
            JsonObject p=d["pose"];
            auto bounded=[&](const char *key,float fallback,float lo,float hi){float v=p[key]|fallback;return isfinite(v)?constrain(v,lo,hi):fallback;};
            m.expression.eyeOpen=bounded("eyeOpen",1,.04f,1.4f);m.expression.smile=bounded("smile",.6f,-1,1);
            m.expression.mouthOpen=bounded("mouthOpen",0,0,1);m.expression.gazeX=bounded("gazeX",0,-1,1);m.expression.gazeY=bounded("gazeY",0,-1,1);
            m.expression.tilt=bounded("tilt",0,-.35f,.35f);m.expression.leftArm=bounded("leftArm",0,0,2.4f);m.expression.rightArm=bounded("rightArm",0,0,2.4f);
            m.expression.bounce=bounded("bounce",.04f,0,.2f);m.expression.speed=bounded("speed",1,.3f,2);
            m.expression.wink=bounded("wink",0,-1,1);m.expression.brow=bounded("brow",0,-1,1);m.expression.mouthPulse=bounded("mouthPulse",0,0,1);m.expression.armWave=bounded("armWave",0,0,1);
            strlcpy(m.expression.motion,p["motion"]|"",sizeof m.expression.motion);
            strlcpy(m.cue,p["cue"]|"none",sizeof m.cue);m.expressionNew=true;m.lastActivity=millis();
        }
    } else if (!strcmp(t,"pip.install") || !strcmp(t,"pip.remove")) {
        const char *id=d["command_id"]|"";
        if(strlen(id)==32 && strspn(id,"0123456789abcdef")==32){
            if(m.assetBusy || m.recording || audioPlaying())assetReply(id,"busy");
            else{serializeJson(d,assetRequest);m.assetBusy=true;m.lastActivity=millis();}
        }
    } else if (!strcmp(t, "pip.activate")) {
        if (d["rig"].is<int>() && (int)d["rig"]>=0 && (int)d["rig"]<PIXEL_RIG_COUNT) {
            strlcpy(m.pipCommand,d["command_id"]|"",sizeof m.pipCommand);
            m.pip=d["rig"]; m.pipColor=d["color"]|0U; m.pipNew=true;
        }
    } else if (!strcmp(t, "config")) {
        if(d["live_transcription"].is<bool>())m.liveTranscription=d["live_transcription"];
        if(d["shake_reaction"].is<bool>())m.shakeReaction=d["shake_reaction"];
        if(d["character_sounds"].is<bool>())m.characterSounds=d["character_sounds"];
        if (d["hold_to_talk"].is<bool>()) m.holdToTalk=d["hold_to_talk"];
        if (d["reduced_motion"].is<bool>()) { m.reducedMotion=d["reduced_motion"]; m.pipNew=true; }
        if (d["dim_seconds"].is<int>()) m.dimMs=constrain((int)d["dim_seconds"],5,300)*1000;
        if (d["sleep_seconds"].is<int>()) m.deepMs=constrain((int)d["sleep_seconds"],60,3600)*1000;
        if (d["brightness"].is<int>()) m.brightness = d["brightness"];
        if (d["volume"].is<int>()) m.volume = constrain((int)d["volume"], 0, 100);
        m.configNew = true;
    } else if (!strcmp(t, "card")) {
        strlcpy(m.cardKind, d["kind"] | "", sizeof m.cardKind);
        m.cardTtl = constrain((int)(d["ttl"] | 12), 3, 120);
        copyUtf8(m.cardTitle, d["title"] | "", sizeof m.cardTitle);
        copyUtf8(m.cardBody, d["body"] | (d["date"] | ""), sizeof m.cardBody);
        if (!strcmp(m.cardKind, "weather")) readWeather(d.as<JsonVariantConst>(), m.cardW);
        if (!strcmp(m.cardKind, "device")) readHa(d["dev"], m.cardDev);
        if (!strcmp(m.cardKind, "image")) { strlcpy(m.imgUrl, d["url"] | "", sizeof m.imgUrl); m.imgReq = true; }
        if (d["date"].is<const char *>()) strlcpy(m.date, d["date"], sizeof m.date);
        m.cardNew = true;
    } else if (!strcmp(t, "info")) {
        if (d["date"].is<const char *>()) strlcpy(m.date, d["date"], sizeof m.date);
        readWeather(d["weather"], m.weather);
        m.infoSeq++;
    } else if (!strcmp(t, "ha_list")) {
        JsonArrayConst a = d["items"];
        int k = 0;
        for (JsonVariantConst v : a) { if (k >= 12) break; readHa(v, m.ha[k++]); }
        m.nHa = k;
        m.haOk = true;
        m.haSeq++;
    } else if (!strcmp(t, "ha_state")) {                      // one device changed (after a toggle)
        Model::HaItem it;
        readHa(d["item"], it);
        for (int i = 0; i < m.nHa; i++) if (!strcmp(m.ha[i].id, it.id)) m.ha[i] = it;
        if (!strcmp(m.cardDev.id, it.id)) { m.cardDev = it; m.infoSeq++; }
        m.haSeq++;
    } else if (!strcmp(t, "meeting")) {
        if (d["id"].is<const char *>()) strlcpy(m.meetingId, d["id"], sizeof m.meetingId);
        if (d["title"].is<const char *>()) copyUtf8(m.meetingTitle, d["title"], sizeof m.meetingTitle);
        m.meetingNew = true;
    } else if (!strcmp(t, "toast")) {
        copyUtf8(m.toast, d["text"] | "", sizeof m.toast);
        m.toastNew = true;
    }
    if (!strcmp(t, "config") && d["server_url"].is<const char *>()) {     // e.g. move from LAN to the Funnel URL
        String nu = d["server_url"].as<const char *>();
        if (nu.startsWith("ws") && nu != url) { prefs.putString("url", nu); Serial.printf("server url -> %s (reboot)\n", nu.c_str()); restartReq = true; }
    }
    modelUnlock();
}

static void onEvent(WStype_t type, uint8_t *payload, size_t len) {
    switch (type) {
        case WStype_CONNECTED:
            Serial.printf("ws: connected %s%s\n", host.c_str(), path.c_str());
            modelLock(); model.server = true; modelUnlock();
            sendHello();
            if (micActive && micMeeting) {                  // a meeting was recording: continue the same one
                char r[128];
                modelLock();
                snprintf(r, sizeof r, "{\"type\":\"ptt_start\",\"id\":\"mic\",\"mode\":\"meeting\",\"sample_rate\":16000,\"codec\":\"adpcm\",\"resume\":\"%s\"}", model.meetingId);
                modelUnlock();
                ws.sendTXT(r);
                Serial.printf("meeting: resume after reconnect, %u bytes buffered\n", (unsigned)audioMicQueued());
            }
            break;
        case WStype_DISCONNECTED:
            modelLock(); model.server = false; modelUnlock();
            break;
        case WStype_TEXT: onText((const char *)payload, len); break;
        case WStype_BIN: if (!micActive && !curUtt.isEmpty() && len<=4096) audioPush(payload, len); break;
        default: break;
    }
}

static void doOta() {
    String u = otaUrl;
    otaUrl = "";
    Serial.printf("ota: %s\n", u.c_str());
    modelLock(); strlcpy(model.sub, "מתעדכן…", sizeof model.sub); model.subNew = true;
    strlcpy(model.emotion, "working", sizeof model.emotion); model.emotionNew = true; modelUnlock();
    ws.disconnect();
    httpUpdate.rebootOnUpdate(true);
    t_httpUpdate_return r;
    if (u.startsWith("https://")) {
        NetworkClientSecure c;
        c.setCACert(CA_CERTS);
        r = httpUpdate.update(c, u);
    } else {
        NetworkClient c;
        r = httpUpdate.update(c, u);
    }
    Serial.printf("ota failed: %d %s\n", r, httpUpdate.getLastErrorString().c_str());
}

static volatile int discReasons[8], nDisc = 0;
static const char *authName(wifi_auth_mode_t a) {
    switch (a) {
        case WIFI_AUTH_OPEN: return "open"; case WIFI_AUTH_WEP: return "WEP"; case WIFI_AUTH_WPA_PSK: return "WPA";
        case WIFI_AUTH_WPA2_PSK: return "WPA2"; case WIFI_AUTH_WPA_WPA2_PSK: return "WPA/WPA2";
        case WIFI_AUTH_WPA3_PSK: return "WPA3"; case WIFI_AUTH_WPA2_WPA3_PSK: return "WPA2/WPA3";
        case WIFI_AUTH_WPA2_ENTERPRISE: return "WPA2-Enterprise"; default: return "other";
    }
}
// Arduino's WiFi.begin() zeroes the station config, which leaves WPA3-SAE on "hunt and peck" only.
// Routers in WPA2/WPA3 mode often require H2E, and then authentication fails (reason 202) even with the
// right password. Re-apply the ESP-IDF default (both methods) and reconnect.
static void fixSae() {
    wifi_config_t c;
    if (esp_wifi_get_config(WIFI_IF_STA, &c) != ESP_OK) return;
    if (c.sta.sae_pwe_h2e == WPA3_SAE_PWE_BOTH) return;
    c.sta.sae_pwe_h2e = WPA3_SAE_PWE_BOTH;
    c.sta.pmf_cfg.capable = true;
    c.sta.pmf_cfg.required = false;
    esp_wifi_disconnect();
    delay(50);
    esp_err_t e = esp_wifi_set_config(WIFI_IF_STA, &c);
    esp_wifi_connect();
    Serial.printf("wifi: SAE H2E+hunt&peck %s\n", e == ESP_OK ? "applied" : esp_err_to_name(e));
}

// Scan and publish the visible networks to the setup screen: unique names, strongest first.
// A scan fails (-2) while the station is busy connecting / auto-reconnecting, and returns -1 while another scan runs.
// Then: stop the connection attempt (only when not connected), wait, and try again, so the list is never empty
// just because of timing.
static int scanRobust() {
    int n = -2;
    for (int attempt = 0; attempt < 4; attempt++) {
        if (WiFi.scanComplete() == WIFI_SCAN_RUNNING) {
            for (uint32_t t0 = millis(); WiFi.scanComplete() == WIFI_SCAN_RUNNING && millis() - t0 < 6000;) delay(50);
        }
        WiFi.scanDelete();
        n = WiFi.scanNetworks(false, true, false, 220);
        Serial.printf("wifi: scan try %d -> %d (status %d)\n", attempt + 1, n, WiFi.status());
        if (n > 0) return n;
        if (WiFi.status() != WL_CONNECTED) {
            WiFi.setAutoReconnect(false);
            WiFi.disconnect(false, false);
        }
        delay(400 + attempt * 400);
    }
    return n < 0 ? 0 : n;
}

static void scanToModel() {
    modelLock(); model.scanBusy = true; modelUnlock();
    int n = scanRobust();
    Model::Ap list[24];
    int k = 0;
    for (int i = 0; i < n && k < 24; i++) {
        String s = WiFi.SSID(i);
        if (!s.length()) continue;
        bool dup = false;
        for (int j = 0; j < k; j++) if (s == list[j].ssid) { dup = true; if (WiFi.RSSI(i) > list[j].rssi) list[j].rssi = WiFi.RSSI(i); }
        if (dup) continue;
        strlcpy(list[k].ssid, s.c_str(), sizeof list[k].ssid);
        list[k].rssi = WiFi.RSSI(i);
        list[k].open = WiFi.encryptionType(i) == WIFI_AUTH_OPEN;
        k++;
    }
    WiFi.scanDelete();
    for (int a = 1; a < k; a++)                                  // insertion sort by signal
        for (int b = a; b > 0 && list[b].rssi > list[b - 1].rssi; b--) { Model::Ap t = list[b]; list[b] = list[b - 1]; list[b - 1] = t; }
    modelLock();
    memcpy(model.aps, list, sizeof(Model::Ap) * k);
    model.nAps = k;
    model.scanSeq++;
    model.scanReq = false;
    model.scanBusy = false;
    modelUnlock();
    Serial.printf("wifi: scan -> %d networks\n", k);
}

static volatile bool retryWifi=false;
void netRetryWifi(){retryWifi=true;}
static void connectWifi() {
    WiFi.onEvent([](arduino_event_id_t, arduino_event_info_t info) {
        if (nDisc < 8) discReasons[nDisc++] = info.wifi_sta_disconnected.reason;
        Serial.printf("wifi disconnect reason %u heap %u largest %u\n",info.wifi_sta_disconnected.reason,ESP.getFreeHeap(),ESP.getMaxAllocHeap());
    }, ARDUINO_EVENT_WIFI_STA_DISCONNECTED);
    WiFi.mode(WIFI_STA);
    WiFi.setHostname(DEVICE_NAME);
    WiFi.setScanMethod(WIFI_ALL_CHANNEL_SCAN);          // several APs share the SSID: pick the strongest
    WiFi.setSortMethod(WIFI_CONNECT_AP_BY_SIGNAL);
    String ss = prefs.getString("ssid", ""), pw = prefs.getString("pass", "");
    {
        // scan once at boot: lets the setup script offer a pick-list, and fixes a saved name that differs only in case
        int n = WiFi.scanNetworks(false, true);
        int best=-128; String chosen=ss, chosenPassword=pw;
        for (int i = 0; i < n; i++) {
            String visible=WiFi.SSID(i);
            if(visible==ss && WiFi.RSSI(i)+8>best) {best=WiFi.RSSI(i)+8;chosen=ss;chosenPassword=pw;}
            for(int slot=0;slot<8;slot++) {
                String key=String("ssid")+slot;
                if(!prefs.isKey(key.c_str()))continue;
                String saved=prefs.getString(key.c_str(),"");
                if(saved.length() && visible==saved && WiFi.RSSI(i)>best) {
                    best=WiFi.RSSI(i);chosen=saved;chosenPassword=prefs.getString((String("pass")+slot).c_str(),"");
                }
            }
        }
        ss=chosen;pw=chosenPassword;
        Serial.printf("wifi scan: %d networks, saved candidate %s\n",n,best>-128?"available":"not visible");
        WiFi.scanDelete();
    }
    if (ss.length()) {
        Serial.printf("wifi begin: ssid bytes %u password bytes %u result %d\n",ss.length(),pw.length(),WiFi.begin(ss.c_str(), pw.c_str()));
        fixSae();
    } else if (strlen(WIFI_SSID)) {
        WiFi.begin(WIFI_SSID, WIFI_PASS);
    } else {
        WiFi.begin();                                    // whatever the setup portal stored
    }
    uint32_t t0 = millis();
    uint32_t wait = (ss.length() || strlen(WIFI_SSID)) ? 20000 : 6000;   // nothing saved: go to the setup screen quickly
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < wait) delay(200);
    if (WiFi.status() != WL_CONNECTED) {
        Serial.printf("wifi: failed for '%.3s…' (%d chars), reasons:", ss.c_str(), ss.length());
        for (int i = 0; i < nDisc; i++) Serial.printf(" %d", discReasons[i]);
        Serial.println("   (15/204 = wrong password, 201 = not found, 202 = auth failed)");
        // No Wi-Fi: the setup screen on the device takes over (pick a network, type the password). Meanwhile the
        // saved network is retried every 90 s, so a router that was just off doesn't leave the board stuck here.
        bool wrongPw = nDisc && (discReasons[0] == 15 || discReasons[0] == 202 || discReasons[0] == 204);
        bool notFound = nDisc && discReasons[0] == 201;
        modelLock();
        model.wifiSetup = true;
        strlcpy(model.wifiErr, !ss.length() ? "" : wrongPw ? "הסיסמה של הרשת השמורה שגויה" : notFound ? "הרשת השמורה לא נמצאה" : "לא הצלחתי להתחבר לרשת השמורה",
                sizeof model.wifiErr);
        modelUnlock();
        WiFi.setAutoReconnect(false);                       // background reconnects would make every scan fail
        WiFi.disconnect(false, false);
        uint32_t lastTry = millis(),retryDelay=10000;
        while (WiFi.status() != WL_CONNECTED) {
            bool scan;
            modelLock(); scan = model.scanReq; modelUnlock();
            if (scan) scanToModel();
            if (ss.length() && (retryWifi || millis() - lastTry > retryDelay)) {
                retryWifi=false;
                lastTry = millis();
                WiFi.begin(ss.c_str(), pw.c_str());
                fixSae();
                for (uint32_t t0 = millis(); WiFi.status() != WL_CONNECTED && millis() - t0 < 12000;) {
                    modelLock(); scan = model.scanReq; modelUnlock();
                    if (scan) break;                                 // the user is looking at the list: let them
                    delay(200);
                }
                if (WiFi.status() != WL_CONNECTED) {WiFi.disconnect(false, false);retryDelay=min(90000UL,retryDelay*2);}
            }
            delay(50);
        }
        modelLock(); model.wifiSetup = false; model.wifiErr[0] = 0; modelUnlock();
        WiFi.setAutoReconnect(true);
    }
    WiFi.setSleep(true);                                     // modem sleep between beacons (saves power)
    modelLock(); model.subNew = false; model.sub[0] = 0; modelUnlock();
    Serial.printf("wifi: connected %s rssi %d ch %d\n", WiFi.localIP().toString().c_str(), WiFi.RSSI(), WiFi.channel());
}

// Several access points share the home SSID; the board sometimes ends up on a far one (-85 dBm: meetings stutter).
// When idle and weak, look for a clearly stronger AP with the same name and move to it.
static void roamCheck(bool force = false) {
    static uint32_t last = 0;
    if (!force && millis() - last < 5UL * 60UL * 1000UL) return;
    last = millis();
    int now = WiFi.RSSI();
    if (WiFi.status() != WL_CONNECTED || now > -72) return;
    String ss = WiFi.SSID();
    if (prefs.getString("ssid", "") != ss) return;          // only with the credentials saved on the board
    String pw = prefs.getString("pass", "");
    int n = WiFi.scanNetworks(false, false, false, 120);
    int best = -1, bestRssi = now;
    for (int i = 0; i < n; i++)
        if (WiFi.SSID(i) == ss && WiFi.RSSI(i) > bestRssi + 8 && memcmp(WiFi.BSSID(i), WiFi.BSSID(), 6)) { best = i; bestRssi = WiFi.RSSI(i); }
    if (best >= 0) {
        uint8_t bssid[6];
        memcpy(bssid, WiFi.BSSID(best), 6);
        int ch = WiFi.channel(best);
        Serial.printf("wifi: roaming %d dBm -> %d dBm (ch %d)\n", now, bestRssi, ch);
        WiFi.scanDelete();
        WiFi.begin(ss.c_str(), pw.length() ? pw.c_str() : nullptr, ch, bssid);
        fixSae();
        for (uint32_t t0 = millis(); WiFi.status() != WL_CONNECTED && millis() - t0 < 10000;) delay(100);
        if (WiFi.status() != WL_CONNECTED) {                    // that AP refused: back to normal
            WiFi.begin(ss.c_str(), pw.length() ? pw.c_str() : nullptr);
            fixSae();
            for (uint32_t t0 = millis(); WiFi.status() != WL_CONNECTED && millis() - t0 < 15000;) delay(100);
        }
        Serial.printf("wifi: now %d dBm ch %d\n", WiFi.RSSI(), WiFi.channel());
    } else {
        WiFi.scanDelete();
    }
}

// Two endpoints: the public Funnel URL (works anywhere) and the LAN URL (faster at home).
// The one that worked last on this Wi-Fi is tried first; after 12 s without a connection we switch.
static String urlPublic, urlLan, hdr;
static int using_ = 0;   // 0 = public, 1 = lan
static uint32_t tryStart = 0;

static void startWs(int which) {
    using_ = which;
    String u = which == 1 && urlLan.length() ? urlLan : urlPublic;
    ws.disconnect();
    parseUrl(u);
    ws.setExtraHeaders(hdr.c_str());
    if (tls) ws.beginSslWithCA(host.c_str(), port, path.c_str(), CA_CERTS);
    else ws.begin(host.c_str(), port, path.c_str());
    ws.onEvent(onEvent);
    ws.setReconnectInterval(3000);
    ws.enableHeartbeat(15000, 4000, 2);
    tryStart = millis();
    Serial.printf("ws: trying %s\n", u.c_str());
}

// Camera snapshot for an image card: GET <server>/img/<id>.jpg into PSRAM; the UI draws it.
static void fetchImage() {
    char rel[96];
    modelLock(); strlcpy(rel, model.imgUrl, sizeof rel); model.imgReq = false; modelUnlock();
    String u = String(tls ? "https://" : "http://") + host + ":" + port + rel;
    HTTPClient http;
    NetworkClientSecure sc;
    NetworkClient pc;
    bool ok = tls ? (sc.setCACert(CA_CERTS), http.begin(sc, u)) : http.begin(pc, u);
    if (!ok) return;
    http.addHeader("Authorization", "Bearer " + token);
    http.setTimeout(8000);
    int code = http.GET();
    int len = http.getSize();
    uint8_t *buf = nullptr;
    size_t got = 0;
    if (code == 200 && len > 0 && len < 300000 && (buf = (uint8_t *)ps_malloc(len))) {
        NetworkClient *st = http.getStreamPtr();
        uint32_t t0 = millis();
        while (got < (size_t)len && millis() - t0 < 8000) {
            int a = st->available();
            if (a > 0) got += st->readBytes(buf + got, min((size_t)a, len - got));
            else delay(5);
        }
    }
    http.end();
    Serial.printf("img: %s -> %d, %u/%d bytes\n", rel, code, (unsigned)got, len);
    if (buf && got != (size_t)len) { free(buf); buf = nullptr; }
    if (!buf) return;
    modelLock();
    uint8_t *old = model.img;
    model.img = buf;
    model.imgLen = got;
    model.imgSeq++;
    modelUnlock();
    free(old);
}


static void fetchPip() {
    JsonDocument d;deserializeJson(d,assetRequest);assetRequest="";
    String id=d["command_id"]|"",pid=d["pip_id"]|"",aid=d["asset_id"]|"";
    auto fail=[&](const char *why){modelLock();model.assetBusy=false;modelUnlock();assetReply(id,why);};
    if(pid.length()!=32 || strspn(pid.c_str(),"0123456789abcdef")!=32){fail("invalid");return;}
    modelLock();bool match=model.customPip && pid==model.customPip->pip;bool cached=match && aid==model.customPip->asset;modelUnlock();
    if(String(d["type"]|"")=="pip.remove"){
        if(!match){fail("applied");return;}
        if(SPIFFS.exists("/wappai.bin")&&!SPIFFS.remove("/wappai.bin")){fail("storage");return;}
        SPIFFS.remove("/wappai.old");SPIFFS.remove("/wappai.tmp");
        modelLock();model.assetRemove=true;strlcpy(model.pipCommand,id.c_str(),33);modelUnlock();return;
    }
    if(cached){modelLock();model.pip=PIXEL_RIG_COUNT;model.pipColor=0;model.pipNew=true;strlcpy(model.pipCommand,id.c_str(),33);modelUnlock();return;}
    int expected=d["bytes"]|0;String sha=d["sha256"]|"";
    if(aid.length()!=32 || strspn(aid.c_str(),"0123456789abcdef")!=32 || expected<756 || expected>160000 || sha.length()!=64){fail("invalid");return;}
    HTTPClient http;NetworkClientSecure sc;NetworkClient pc;
    String u=String(tls?"https://":"http://")+host+":"+port+"/v1/device/pips/"+aid+".bin";
    bool ok=tls?(sc.setCACert(CA_CERTS),http.begin(sc,u)):http.begin(pc,u);
    if(!ok){fail("network");return;}http.setTimeout(10000);http.addHeader("Authorization","Bearer "+token);
    int code=http.GET(),len=http.getSize();uint8_t *bytes=nullptr;size_t got=0;
    if(code==200 && len==expected && (bytes=(uint8_t*)ps_malloc(len))){
        auto *stream=http.getStreamPtr();uint32_t start=millis();
        while(got<(size_t)len && millis()-start<30000){int n=stream->available();if(n>0)got+=stream->readBytes(bytes+got,min((size_t)n,len-got));else delay(5);}
    }http.end();
    if(!bytes || got!=(size_t)expected){free(bytes);fail("download");return;}
    uint8_t hash[32];mbedtls_sha256(bytes,got,hash,0);char hex[65];for(int i=0;i<32;i++)sprintf(hex+i*2,"%02x",hash[i]);
    PipAsset *asset=sha==hex?pipDecode(bytes,got):nullptr;
    if(!asset || pid!=asset->pip || aid!=asset->asset){delete asset;free(bytes);fail("invalid");return;}
    if(!pipSave(bytes,got)){delete asset;free(bytes);fail("storage");return;}free(bytes);
    modelLock();model.pendingPip=asset;model.assetSwap=true;strlcpy(model.pipCommand,id.c_str(),33);model.lastActivity=millis();modelUnlock();
}

static void netTask(void *) {
    connectWifi();
    roamCheck(true);
    hdr = "Authorization: Bearer " + token;
    bool lanFirst = urlLan.length() && prefs.getString("lan_ssid", "") == WiFi.SSID();
    startWs(lanFirst ? 1 : 0);
    static uint8_t buf[2048];
    for (;;) {
        if (shutdownReq) { ws.disconnect(); WiFi.disconnect(true); WiFi.mode(WIFI_OFF); vTaskDelay(portMAX_DELAY); }
        modelLock(); model.wifi = WiFi.status() == WL_CONNECTED; modelUnlock();
        ws.loop();
        bool up = model.server;
        if (up) {
            tryStart = millis();
            static bool saved = false;
            if (!saved) { saved = true; prefs.putString("lan_ssid", using_ == 1 ? WiFi.SSID() : String("")); }
        } else if (lanFirst && urlLan.length() && urlLan != urlPublic && millis() - tryStart > 12000) {
            startWs(using_ ^ 1);
        }
        if (restartReq) { delay(500); ESP.restart(); }
        if (model.scanReq && !model.scanBusy) scanToModel();
        if (!otaUrl.isEmpty()) doOta();
        if (!micActive && !micStopPending && !audioPlaying()) roamCheck();
        if(assetRequest.length())fetchPip();
        if (model.imgReq) fetchImage();
        // meeting offline: keep the audio in the mic ring (PSRAM) until the server is back
        bool hold = micMeeting && (!model.server || WiFi.status() != WL_CONNECTED);
        if ((micActive || micStopPending) && !hold) {
            size_t n = 0;
            int guard = 0;
            if (micMeeting) {
                // meetings: IMA ADPCM (4 bits/sample, 1/4 of the bandwidth), self-contained 2048-sample blocks.
                // A weak Wi-Fi link keeps up, and a block lost to a reconnect never breaks the decoding of the next.
                static int16_t blk[ADPCM_BLOCK];
                static size_t have = 0;
                while (guard++ < 6) {
                    n = audioMicPop((uint8_t *)blk + have, sizeof blk - have);
                    have += n;
                    if (have == sizeof blk || (n == 0 && micStopPending && have > 0)) {
                        uint8_t out[4 + ADPCM_BLOCK / 2];
                        size_t len = adpcmEncode(blk, have / 2, out);
                        ws.sendBIN(out, len);
                        have = 0;
                    }
                    if (n == 0) break;
                }
                n = (micStopPending && audioMicQueued() == 0 && have == 0) ? 0 : 1;   // 0 = all sent
            } else {
                while ((n = audioMicPop(buf, sizeof buf)) > 0 && guard++ < 8) ws.sendBIN(buf, n);
            }
            if (micStopPending && n == 0) {
                micStopPending = false;
                audioMic(false);
                ws.sendTXT("{\"type\":\"ptt_end\",\"id\":\"mic\"}");
                micMeeting = false;
            }
        }
        String *s;
        while (xQueueReceive(outQ, &s, 0) == pdTRUE) {
            ws.sendTXT(*s);
            delete s;
        }
        if (millis() - lastStatus > 60000 && model.server) {
            lastStatus = millis();
            String st = "{\"type\":\"status\",\"rssi\":" + String(WiFi.RSSI()) + ",\"heap\":" + String(ESP.getFreeHeap()) +
                        ",\"uptime\":" + String(millis() / 1000) + ",\"battery\":" + batteryJson() + "}";
            ws.sendTXT(st);
        }
        vTaskDelay(pdMS_TO_TICKS(micActive ? 2 : 5));
    }
}

void netBegin() {
    outQ = xQueueCreate(16, sizeof(String *));
    prefs.begin("net", false);
    url = prefs.getString("url", SERVER_URL);
    if (!url.startsWith("wss://")) url = SERVER_URL;     // a saved LAN address is handled by the fallback below
    urlPublic = url;
#ifdef SERVER_URL_LAN
    urlLan = SERVER_URL_LAN;
#endif
    token = prefs.getString("token", DEVICE_TOKEN);
    xTaskCreatePinnedToCore(netTask, "net", 8192, nullptr, 3, nullptr, 0);
}

void netConfigure(const String &newUrl, const String &newToken) {
    if (newUrl.length()) prefs.putString("url", newUrl);
    if (newToken.length()) prefs.putString("token", newToken);
}

void netSetWifi(const String &ssid, const String &pass) {
    String previous=prefs.getString("ssid","");
    if(previous.length() && previous!=ssid) {
        uint8_t slot=prefs.getUChar("slot",0)%8;
        prefs.putString((String("ssid")+slot).c_str(),previous);
        prefs.putString((String("pass")+slot).c_str(),prefs.getString("pass",""));
        prefs.putUChar("slot",(slot+1)%8);
    }
    prefs.putString("ssid", ssid);
    prefs.putString("pass", pass);
    Serial.printf("wifi saved for '%s', restarting\n", ssid.c_str());
    delay(300);
    ESP.restart();
}

String netSavedSsid() { return prefs.getString("ssid", ""); }

void netResetWifi() {
    prefs.remove("ssid");
    prefs.remove("pass");
    WiFi.disconnect(false, true);                      // also forget what the IDF stored
    ESP.restart();
}
