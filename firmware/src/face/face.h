// Face engine: a parametric, vector (SDF) character rendered straight into an RGB565 buffer.
//
//  - Every emotion is a set of numbers (FaceP) generated from character/creature.json.
//  - Emotions blend with critically-damped springs; discrete parts (eye shape, mouth shape)
//    switch behind a quick blink so changes never "pop".
//  - A "life" layer adds blinking, saccades, breathing, idle body motion, talking mouth,
//    gaze, head tilt from the IMU and one-shot gestures.
//
// Platform-free: used by the firmware (LovyanGFX sprite buffer) and by tools/face_preview (PNG).
#pragma once
#include <stdint.h>
#include "pixel_catalog.gen.h"
#include "pip_asset.h"

enum EyeShape : uint8_t { EYE_ROUND, EYE_ARC_UP, EYE_ARC_DOWN, EYE_HEART, EYE_STAR, EYE_SPIRAL, EYE_X, EYE_SQUINT, EYE_LINE, EYE_SHAPES };
enum MouthShape : uint8_t { M_CURVE, M_O, M_WAVE, M_CAT, M_NONE, M_SHAPES };
enum BodyAnim : uint8_t { A_NONE, A_SWAY, A_BOUNCE, A_TREMBLE, A_FLOAT, A_WOBBLE, A_LEAN, A_ANIMS };
enum FxBit : uint16_t {
    FX_HEARTS = 1 << 0, FX_TEARS = 1 << 1, FX_SWEAT = 1 << 2, FX_ZZZ = 1 << 3, FX_SPARKLES = 1 << 4,
    FX_QUESTION = 1 << 5, FX_EXCLAIM = 1 << 6, FX_ANGER = 1 << 7, FX_NOTES = 1 << 8, FX_STEAM = 1 << 9,
    FX_DOTS = 1 << 10, FX_BLUSH = 1 << 11, FX_COUNT = 12
};

// All continuous values are floats so the whole struct can be blended as an array.
struct EyeP { float dx, y, w, h, r, rot, lidT, lidTA, lidB, hl, shape; };
struct BrowP { float a, y, dx, w, th, ang, curve; };
struct FaceP {
    EyeP eye[2];            // [0] = left on screen, [1] = right on screen
    BrowP brow[2];
    float mdx, my, mw, mcurve, mopen, mth, mrot, mshape;
    float cheek;
    float dy, scale, rot;   // whole face
    float cr, cg, cb;       // main colour 0..1
    float glow;             // halo strength 0..1
    float anim, animAmp;    // continuous body motion
    float fx;               // FxBit mask (discrete)
};

struct Emotion { const char *name; FaceP p; };

struct Canvas {
    uint16_t *px;    // RGB565
    int w, h;
    bool swapped;    // true = byte-swapped (LovyanGFX sprite memory)
};

struct Rect { int x0, y0, x1, y1; bool empty() const { return x1 <= x0 || y1 <= y0; } };

struct PipPose {float eyeOpen=1,smile=.6f,mouthOpen=0,gazeX=0,gazeY=0,tilt=0,leftArm=0,rightArm=0,bounce=.04f,speed=1,wink=0,brow=0,mouthPulse=0,armWave=0;char motion[24]={};};

class Face {
public:
    void begin(uint32_t seed = 1);
    void setExpression(const PipPose &pose);
    bool customExpression() const {return custom_;}
    void setPip(uint8_t kind, uint32_t color = 0) { pip_ = kind < PIXEL_RIG_COUNT || (kind == PIXEL_RIG_COUNT && asset_) ? kind : 0; color_ = color; }
    void setAsset(const PipAsset *asset) {asset_=asset;if(!asset_ && pip_==PIXEL_RIG_COUNT)pip_=0;}
    void setReducedMotion(bool on) { reduced_ = on; }
    bool setEmotion(const char *name);         // false if unknown
    void setEmotionIndex(int i);
    int emotionIndex() const { return emo_; }
    const char *emotionName() const;
    void gesture(const char *name);            // nod shake jump pop tilt_left tilt_right blink wiggle look_left look_right
    void lookAt(float x, float y, uint32_t holdMs);   // -1..1 (x right, y down)
    void setTalk(float level) { talk_ = level; }      // 0..1, mouth follows it
    void setTilt(float deg) { tilt_ = deg; }          // device roll from IMU
    void setAttention(bool on) { attention_ = on; }   // listening: steady gaze, slightly bigger
    // idle life: while nothing else happens the character does small things on its own (glance around, hop,
    // curious tilt, wiggle, content slow blink). The app turns it off while listening / talking / recording.
    void setIdle(bool on) { idle_ = on; }
    void update(float dt);
    // Draws the face; clears what it drew last frame. Returns the screen area that changed.
    Rect render(Canvas &c, int cx, int cy, float pixelScale = 1.f);
    // lift (and optionally shrink) the whole face, e.g. while subtitles show; both ease in smoothly
    void setCenterOffset(float dy, float scale = 1.f) { centerDy_ = dy; zoom_ = scale; }

    static int count();
    static const char *name(int i);

private:
    const PipAsset *asset_=nullptr;
    bool custom_=false;
    PipPose pixelPose_;
    float armL_=0,armR_=0,armLT_=0,armRT_=0,poseSpeed_=1,posePulse_=0,poseWave_=0;
    uint8_t pip_ = 0;
    uint32_t color_ = 0;
    bool reduced_ = false;
    FaceP cur_, vel_, tgt_;
    int emo_ = 0;
    float t_ = 0;
    // discrete parts
    uint8_t eyeShape_[2] = {0, 0}, eyeShapeTgt_[2] = {0, 0};
    float eyeSwap_[2] = {1, 1};           // 0..1 progress of a shape change (closing then opening)
    uint8_t mouthShape_ = 0, mouthShapeTgt_ = 0;
    float mouthSwap_ = 1;
    uint8_t anim_ = 0;
    float fxA_[FX_COUNT] = {};            // fade per effect
    uint16_t fxTgt_ = 0;
    // life
    float blink_ = 0, blinkT_ = 0, nextBlink_ = 2.f;
    bool doubleBlink_ = false;
    float lookX_ = 0, lookY_ = 0, lookVX_ = 0, lookVY_ = 0, lookTX_ = 0, lookTY_ = 0;
    float lookHold_ = 0, nextSaccade_ = 1.f;
    float talk_ = 0, talkS_ = 0;
    float tilt_ = 0, tiltS_ = 0;
    bool attention_ = false;
    bool idle_ = false;
    float nextIdle_ = 6.f, slowBlink_ = 0;
    float attS_ = 0;
    // gesture
    uint8_t gest_ = 0;
    float gestT_ = 0, gestDur_ = 0;
    float centerDy_ = 0, centerDyS_ = 0, zoom_ = 1, zoomS_ = 1;
    uint32_t rng_ = 1;
    // damage tracking
    Rect prev_[32];
    int nPrev_ = 0;
    Rect cur_rects_[32];
    int nCur_ = 0;

    float rnd();
    void step(float dt);

public:
    void addRect(int x0, int y0, int x1, int y1);   // internal: damage tracking
};
