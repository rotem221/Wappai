#pragma once
#include <Arduino.h>

void netBegin();
void netSend(const String &json);          // queue a JSON message to the server
void netMicStart(bool meeting = false);    // push-to-talk (or meeting): start streaming the mic
void netMicStop();
void netSetBattery(int pct, int mv, bool charging, bool usb);
void netShutdown();                        // before deep sleep
void netConfigure(const String &url, const String &token);   // persists; applied after restart
void netSetWifi(const String &ssid, const String &pass);   // saved in NVS, then restart
void netResetWifi();
String netSavedSsid();

void netRetryWifi();
