#pragma once
#include <Arduino.h>
// The shipping 1.75C has no TF slot. SD-enabled BSPs must provide verified pins;
// never probe the bare-board pin map on 1.75C (it overlaps LCD reset/touch/PWR).
#ifndef WAPPAI_SD_ENABLED
#define WAPPAI_SD_ENABLED 0
#endif
void recordingStoreBegin();
bool recordingStoreStart();
bool recordingStoreActive();
bool recordingStoreWrite(const uint8_t *data,size_t length);
size_t recordingStoreRead(uint8_t *data,size_t length);
size_t recordingStoreQueued();
void recordingStoreStopCapture();
void recordingStoreClose();
String recordingStoreStatus();
