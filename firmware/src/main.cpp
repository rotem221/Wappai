// Piko: a small AI creature living on a Waveshare ESP32-S3-Touch-AMOLED-1.75.
// Core 1: face, input, power (app/). Core 0: network (net/), audio playback and mic (audio/).
// Serial (115200): emo <name> · g <gesture> · list · sub <text> · ptt · imu · bat · sleep · info
//                  url <wss://…/ws> · token <t> (saved, applied after reboot) · wifi reset · reboot
#include <Arduino.h>
#include "app/app.h"
#include "app/model.h"
#include "audio/audio.h"
#include "config.h"
#include "net/net.h"
#include "provision/ble.h"
#include <WiFi.h>
#include <esp_task_wdt.h>
#include <esp_phy_init.h>
#include <esp_wifi.h>
#include <Preferences.h>
#include <mbedtls/platform.h>

static void *tlsCalloc(size_t count,size_t size) {
    // Arduino's prebuilt IDF selects INTERNAL_MEM_ALLOC. TLS needs two 16KB
    // records while BLE is resident; the board has 8MB external RAM available.
    void *p=heap_caps_calloc(count,size,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    return p ? p:heap_caps_calloc(count,size,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
}

Model model;
static SemaphoreHandle_t mtx;
// Recursive: a helper that locks (e.g. markActivity) may run inside a locked section without deadlocking.
void modelLock() { xSemaphoreTakeRecursive(mtx, portMAX_DELAY); }
void modelUnlock() { xSemaphoreGiveRecursive(mtx); }

static void serialCommands() {
    static String line;
    while (Serial.available()) {
        char c = Serial.read();
        if (c != '\n' && c != '\r') { line += c; continue; }
        if (!line.startsWith("wifiset ")) line.trim();
        if (line.isEmpty()) continue;
        if (line.startsWith("url ")) netConfigure(line.substring(4), "");
        else if (line.startsWith("token ")) netConfigure("", line.substring(6));
        else if (line == "wifi reset") netResetWifi();
        else if (line.startsWith("wifiset ")) {                 // wifiset <ssid>\t<password>
            String rest = line.substring(8);
            int tab = rest.indexOf('\t');
            if (tab > 0) netSetWifi(rest.substring(0, tab), rest.substring(tab + 1));
        }
        else if (line == "scan") {
            int n = WiFi.scanNetworks(false, true);
            String saved = netSavedSsid();
            Serial.printf("scan: %d networks (saved name: %d chars)\n", n, saved.length());
            for (int i = 0; i < n; i++)
                Serial.printf("  [%s] ch%d %ddBm %s%s\n", WiFi.SSID(i).c_str(), WiFi.channel(i), WiFi.RSSI(i),
                              WiFi.encryptionType(i) == WIFI_AUTH_OPEN ? "open" : "secured",
                              WiFi.SSID(i) == saved ? "  <== saved (exact)" : (WiFi.SSID(i).equalsIgnoreCase(saved) ? "  <== saved (case differs!)" : ""));
            WiFi.scanDelete();
        }
        else if (line == "net") Serial.printf("wifi %d ssid '%s' ip %s rssi %d\n", WiFi.status(), WiFi.SSID().c_str(), WiFi.localIP().toString().c_str(), WiFi.RSSI());
        else if (line == "bleoff") { provisioningEnd();Serial.printf("BLE stopped, heap %u largest %u\n",ESP.getFreeHeap(),ESP.getMaxAllocHeap()); }
        else if (line == "retrywifi") { WiFi.setSleep(false); netRetryWifi(); }
        else if (line == "radiotest") { Preferences p;p.begin("wappai-diag",false);p.putBool("radio",true);p.end();ESP.restart(); }
        else if (line == "reboot") ESP.restart();
        else if (line == "phycal") {                     // forget the radio calibration: a full one runs at the next boot
            esp_err_t e = esp_phy_erase_cal_data_in_nvs();
            Serial.printf("phycal: erase %s, restarting\n", esp_err_to_name(e));
            delay(200);
            ESP.restart();
        }
        else if (line == "radio") {
            int8_t p = 0; esp_wifi_get_max_tx_power(&p);
            wifi_country_t c = {}; esp_wifi_get_country(&c);
            wifi_ps_type_t ps; esp_wifi_get_ps(&ps);
            Serial.printf("radio: mode %d tx %.1f dBm country %.2s ch %d-%d ps %d heap %u\n", WiFi.getMode(), p / 4.f, c.cc, c.schan,
                          c.schan + c.nchan - 1, ps, ESP.getFreeHeap());
        }
        else if (line == "info") Serial.printf("fw %s · heap %u · psram %u · up %lus\n", FW_VERSION, ESP.getFreeHeap(), ESP.getFreePsram(), millis() / 1000);
        else appSerial(line);
        line = "";
    }
}

void setup() {
    Serial.setRxBufferSize(1024);                  // long serial commands (sub …, wifiset …)
    Serial.begin(115200);
    mtx = xSemaphoreCreateRecursiveMutex();
    // Reserve scarce internal radio memory before display/audio DMA allocations.
    heap_caps_malloc_extmem_enable(512);
    mbedtls_platform_set_calloc_free(tlsCalloc,heap_caps_free);
    WiFi.mode(WIFI_STA);
    esp_wifi_set_country_code("IL",true);
    { Preferences p;p.begin("wappai-diag",false);bool test=p.getBool("radio",false);p.remove("radio");p.end();
      if(test){
        delay(1500);WiFi.setAutoReconnect(false);WiFi.disconnect(false,false);WiFi.setSleep(false);
        for(bool passive:{false,true}){
          int n=WiFi.scanNetworks(false,true,passive,400);
          Serial.printf("isolated radio: %s scan %d networks, heap %u\n",passive?"passive":"active",n,ESP.getFreeHeap());
          for(int i=0;i<n;i++) Serial.printf("  channel %d RSSI %d\n",WiFi.channel(i),WiFi.RSSI(i));
          WiFi.scanDelete();
        }
      }
    }
    provisioningBegin();
    Serial.printf("radios: heap %u largest %u\n",ESP.getFreeHeap(),ESP.getMaxAllocHeap());
    appBegin();
    bool audio = audioBegin();
    {   // mic tuning saved with the serial commands micgain / micch
        Preferences p;
        p.begin("audio", true);
        if (p.isKey("gain")) audioMicGain(p.getInt("gain", 10));
        if (p.isKey("ch")) audioMicChannel(p.getInt("ch", 0));
        p.end();
    }
    audioSetVolume(model.volume);                  // saved on the device (settings page), updated by the server
    Serial.printf("\nWappai fw %s · audio %s · psram free %u\n", FW_VERSION, audio ? "ok" : "FAIL", ESP.getFreePsram());
    netBegin();
    // Watchdog on the UI loop: if it ever stalls for 20 s, reboot instead of freezing silently.
    esp_task_wdt_config_t wdt = {.timeout_ms = 20000, .idle_core_mask = 0, .trigger_panic = true};
    esp_task_wdt_reconfigure(&wdt);
    enableLoopWDT();
}

void loop() {
    serialCommands();
    provisioningLoop();
    appLoop();
}
