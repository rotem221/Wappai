// Signed-distance primitives used by the face renderer.
// Same math is mirrored in server/sim/face.js so the web simulator looks identical.
// Coordinates: y grows DOWN (screen space). Negative distance = inside.
#pragma once
#include <math.h>

struct V2 { float x, y; };
static inline V2 v2(float x, float y) { return {x, y}; }
static inline V2 operator+(V2 a, V2 b) { return {a.x + b.x, a.y + b.y}; }
static inline V2 operator-(V2 a, V2 b) { return {a.x - b.x, a.y - b.y}; }
static inline V2 operator*(V2 a, float s) { return {a.x * s, a.y * s}; }
static inline float dot(V2 a, V2 b) { return a.x * b.x + a.y * b.y; }
static inline float len(V2 a) { return sqrtf(a.x * a.x + a.y * a.y); }
static inline float clampf(float v, float a, float b) { return v < a ? a : (v > b ? b : v); }
static inline float mixf(float a, float b, float t) { return a + (b - a) * t; }
static inline float signf(float v) { return v < 0 ? -1.f : 1.f; }
static inline V2 rot(V2 p, float c, float s) { return {p.x * c - p.y * s, p.x * s + p.y * c}; }

// rounded box centred at origin, half size b, corner radius r
static inline float sdRoundBox(V2 p, V2 b, float r) {
    float qx = fabsf(p.x) - b.x + r, qy = fabsf(p.y) - b.y + r;
    float ox = qx > 0 ? qx : 0, oy = qy > 0 ? qy : 0;
    float m = qx > qy ? qx : qy;
    return sqrtf(ox * ox + oy * oy) + (m < 0 ? m : 0) - r;
}

static inline float sdCircle(V2 p, float r) { return len(p) - r; }

// ellipse (approximate, good for AA): radii a (x), b (y)
static inline float sdEllipse(V2 p, float a, float b) {
    float k0 = len(v2(p.x / a, p.y / b));
    if (k0 < 1e-4f) return -(a < b ? a : b);
    float k1 = len(v2(p.x / (a * a), p.y / (b * b)));
    return k0 * (k0 - 1.0f) / k1;
}

// capsule / thick segment from a to b, radius r
static inline float sdSegment(V2 p, V2 a, V2 b, float r) {
    V2 pa = p - a, ba = b - a;
    float h = clampf(dot(pa, ba) / dot(ba, ba), 0.f, 1.f);
    return len(pa - ba * h) - r;
}

// arc symmetric around the DOWN axis (+y), aperture half-angle given as (sin, cos), radius ra, thickness rb
static inline float sdArc(V2 p, float sa, float ca, float ra, float rb) {
    p.x = fabsf(p.x);
    float d = (ca * p.x > sa * p.y) ? len(p - v2(sa, ca) * ra) : fabsf(len(p) - ra);
    return d - rb;
}

// heart, size s, centred roughly on its middle (screen y down)
static inline float sdHeart(V2 q, float s) {
    V2 p = v2(fabsf(q.x) / s, -q.y / s + 0.55f);
    float d;
    if (p.y + p.x > 1.0f) {
        V2 t = p - v2(0.25f, 0.75f);
        d = len(t) - 0.35355339f;
    } else {
        V2 a = p - v2(0.f, 1.f);
        float m = 0.5f * fmaxf(p.x + p.y, 0.f);
        V2 b = p - v2(m, m);
        d = sqrtf(fminf(dot(a, a), dot(b, b))) * signf(p.x - p.y);
    }
    return d * s;
}

// 5-point star radius r, inner ratio rf (screen y down)
static inline float sdStar5(V2 q, float r, float rf) {
    const V2 k1 = {0.809016994f, -0.587785252f};
    const V2 k2 = {-k1.x, k1.y};
    V2 p = v2(fabsf(q.x), -q.y);
    float d1 = fmaxf(dot(k1, p), 0.f);
    p = p - k1 * (2.f * d1);
    float d2 = fmaxf(dot(k2, p), 0.f);
    p = p - k2 * (2.f * d2);
    p.x = fabsf(p.x);
    p.y -= r;
    V2 ba = v2(-k1.y, k1.x) * rf - v2(0, 1);
    float h = clampf(dot(p, ba) / dot(ba, ba), 0.f, r);
    V2 t = p - ba * h;
    return len(t) * signf(p.y * ba.x - p.x * ba.y);
}

// 4-point sparkle (concave star), size r
static inline float sdSparkle(V2 p, float r) {
    p = v2(fabsf(p.x), fabsf(p.y));
    // distance to curve x^(1/2)+y^(1/2)=r^(1/2) approximated by scaled implicit function
    float f = sqrtf(p.x + 1e-3f) + sqrtf(p.y + 1e-3f) - sqrtf(r);
    return f * sqrtf(r) * 1.2f;
}

// archimedean spiral, outer radius R, spacing sp, line half-width w, phase ph
static inline float sdSpiral(V2 p, float R, float sp, float w, float ph) {
    float r = len(p);
    float th = atan2f(p.y, p.x) + ph;
    float b = sp / 6.2831853f;
    float n = roundf((r / b - th) / 6.2831853f);
    float d = fabsf(r - b * (th + 6.2831853f * n)) - w;
    return fmaxf(d, r - R);
}

// tear drop: round bottom radius r, pointing up, total height h
static inline float sdDrop(V2 p, float r, float h) {
    // uneven capsule (iq) with r1=r at bottom, r2≈0 at top
    float r1 = r, r2 = 0.4f;
    V2 q = v2(fabsf(p.x), -p.y);   // y up, origin at bottom circle centre
    float b = (r1 - r2) / h, a = sqrtf(1.f - b * b);
    float k = dot(q, v2(-b, a));
    if (k < 0) return len(q) - r1;
    if (k > a * h) return len(q - v2(0, h)) - r2;
    return dot(q, v2(a, b)) - r1;
}

// polyline through n points (exact distance), thickness r
static inline float sdPolyline(V2 p, const V2 *pts, int n, float r) {
    float d = 1e9f;
    for (int i = 0; i + 1 < n; i++) {
        V2 pa = p - pts[i], ba = pts[i + 1] - pts[i];
        float h = clampf(dot(pa, ba) / dot(ba, ba), 0.f, 1.f);
        float e = len(pa - ba * h);
        if (e < d) d = e;
    }
    return d - r;
}

// coverage from distance (in screen pixels): 1 inside, 0 outside, smooth 1px edge
static inline float cover(float dpx) { return clampf(0.5f - dpx, 0.f, 1.f); }
