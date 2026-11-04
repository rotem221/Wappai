#pragma once
// Board audio: ES8311 DAC + ES7210 mics over I2S, 16 kHz.
// Playback: network pushes PCM with audioPush(); a task plays it and computes the mouth level.
// Mic: audioMic(true) fills a ring buffer the network drains with audioMicPop().
#include <Arduino.h>

bool audioBegin();
bool audioMicReceiverActive(); // diagnostic: RX DMA only active during capture
void audioOpen(bool reset);                // start (reset=true) or continue (reset=false) an utterance
void audioPush(const uint8_t *pcm, size_t n);
void audioClose();                         // no more data for now: play the rest, then stop
void audioStop();                          // cut immediately
bool audioPlaying();
float audioMouth();                        // 0 / 0.5 / 1 from what is playing now
void audioMic(bool on);
float audioMicLevel();                     // 0..1 while recording
size_t audioMicPop(uint8_t *dst, size_t max);
size_t audioMicQueued();                   // bytes waiting (meeting buffer while offline)
void audioBeep();
void audioChirp(bool up);
void audioAlarm();
void audioMicTest();
void audioMicTone();                        // play a tone and measure both mic channels (diagnostics)
void audioMicGain(int g);                   // ES7210 PGA, 0..14 (10 = 30 dB)
void audioMicChannel(int c);                // 0 left, 1 right, 2 both
void audioSetVolume(int v);                // speaker 0..100 (DAC volume, 100 = 0 dB)

void audioPipCue(uint8_t rig,const char *cue); // short, rate-limited, never interrupts speech

void audioShakeComplaint(); // bundled Hebrew phrase, no network or model turn

size_t audioMicDropped();
bool audioMicCapacityStop();
