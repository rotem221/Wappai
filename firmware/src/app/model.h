// Shared state between the network task (core 0) and the UI loop (core 1). Guarded by modelLock().
#pragma once
#include <Arduino.h>
#include "face/face.h"

enum RingMode : uint8_t { RING_NONE, RING_REC, RING_THINK, RING_SPEAK };

struct Model {
    PipAsset *customPip=nullptr,*pendingPip=nullptr;bool assetSwap=false,assetRemove=false,assetBusy=false;
    char pipCommand[33]="";
    uint8_t pip = 0; uint32_t pipColor = 0; bool pipNew = false;
    PipPose expression;bool expressionNew=false;uint8_t expressionRig=0;uint32_t expressionColor=0;char expressionId[33]="";char cue[12]="none";bool characterSounds=true;
    bool shakeReaction=true;
    bool liveTranscription=false,partialNew=false,clearCard=false;
    char partial[320]="";
    bool holdToTalk = true, reducedMotion = false;
    uint32_t dimMs = 15000, offMs = 30000, deepMs = 300000;
    // from the server
    char emotion[24] = "idle";
    bool emotionNew = false;
    char gesture[16] = "";
    bool gestureNew = false;
    RingMode ring = RING_NONE;
    char sub[320] = "";
    bool subNew = false;
    uint32_t subUntil = 0;
    bool stopAudio = false;
    uint8_t meetingReq = 0;        // 1 = start meeting recording, 2 = stop
    // timer (runs on the device)
    bool timerOn = false;
    uint32_t timerEnd = 0, timerTotal = 0;
    char timerLabel[64] = "";
    // connection
    bool wifi = false, server = false;
    char ip[16] = "";
    // set by UI, read by net
    bool recording = false;
    uint32_t lastActivity = 0;     // millis of last interaction or server speech
    // on-device Wi-Fi setup: net task <-> setup screen
    bool wifiSetup = false;        // net -> UI: not connected, show the setup screen
    char wifiErr[64] = "";         // why the last attempt failed (Hebrew, shown on the setup screen)
    bool scanReq = false;          // UI -> net: scan for networks
    bool scanBusy = false;
    uint32_t scanSeq = 0;          // incremented when a new list is ready
    struct Ap { char ssid[33]; int8_t rssi; bool open; } aps[24];
    uint8_t nAps = 0;
    // config pushed by the server
    uint8_t brightness = 170;
    uint8_t volume = 80;           // 0..100
    bool configNew = false;

    // ---- information screens (cards + side pages), filled by the net task
    struct Weather { bool ok = false; int t = 0, feels = 0, mn = 0, mx = 0, rain = 0, hum = 0; char text[40] = ""; char icon[8] = "";
                     char city[32] = ""; int tmn = 0, tmx = 0, train = 0; char ttext[40] = ""; char ticon[8] = ""; };
    struct HaItem { char id[64]; char name[64]; char kind[14]; char state[32]; bool on, avail; };
    HaItem badge{};bool badgeNew=false,badgePending=false;uint16_t badgeTtl=12;
    // card: shown instead of the face for `ttl` seconds (time, weather, timer, text, image, device)
    char cardKind[8] = "";
    bool cardNew = false;
    uint16_t cardTtl = 12;
    char cardTitle[64] = "";
    char cardBody[300] = "";
    Weather cardW;
    HaItem cardDev{};
    // image card: the net task downloads the JPEG into PSRAM, the UI draws it
    char imgUrl[96] = "";
    bool imgReq = false;
    uint8_t *img = nullptr;
    size_t imgLen = 0;
    uint32_t imgSeq = 0;
    // clock page
    char date[48] = "";
    Weather weather;
    uint32_t infoSeq = 0;
    // home page (Home Assistant favourites)
    HaItem ha[12];
    uint8_t nHa = 0;
    bool haOk = false;             // the server has Home Assistant
    uint32_t haSeq = 0;
    // meeting transcription (server -> board): id for resuming after a Wi-Fi drop, title once the topic is known
    char meetingId[24] = "";
    char meetingTitle[96] = "";
    bool meetingNew = false;
    // short message at the bottom ("couldn't change the device")
    char toast[96] = "";
    bool toastNew = false;
};

extern Model model;
void modelLock();
void modelUnlock();
void markActivity();
