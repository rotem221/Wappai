// The status ring along the screen edge: push-to-talk progress, "thinking" comet, timer, speaking pulse.
#pragma once
#include <stdint.h>

enum RingShape : uint8_t { RS_OFF, RS_PROGRESS, RS_COMET, RS_FULL };

struct RingStyle {
    RingShape mode = RS_OFF;
    float progress = 0;     // 0..1 for RS_PROGRESS (clockwise from 12 o'clock)
    float head = 0;         // radians for RS_COMET
    float r = 0.38f, g = 0.95f, b = 0.87f;
    float alpha = 1;
    float track = 0.15f;    // faint full ring under the arc
    float thickness = 9;
    float radius = 224;
    float glow = 0;         // 0..1 soft halo (mic level)
};

// Draws (and clears) the whole edge band of an RGB565 full-screen buffer.
void ringDraw(uint16_t *px, int W, int H, bool swapped, const RingStyle &st, bool allowIncremental=false);
