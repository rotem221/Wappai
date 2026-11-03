// Native preview of the firmware face engine: renders every emotion (or a timeline) to raw RGB565 frames.
//   g++ -O2 -I../../firmware/src/face main.cpp ../../firmware/src/face/face.cpp -o preview
//   ./preview all out_dir        -> out_dir/<emotion>.rgb565 (after 1.2 s settle)
//   ./preview seq out_dir e1,e2.. -> out_dir/f%04d.rgb565 frames at 25 fps, 1.6 s per emotion
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <string>
#include <vector>
#include <algorithm>
#include "face.h"

static const int W = 466, H = 466;
static void save(const char *path, uint16_t *buf) { FILE *f = fopen(path, "wb"); fwrite(buf, 2, W * H, f); fclose(f); }

int main(int argc, char **argv) {
    std::string mode = argc > 1 ? argv[1] : "all", out = argc > 2 ? argv[2] : "out";
    std::vector<uint16_t> buf(W * H, 0);
    Canvas c{buf.data(), W, H, false};
    if (mode == "all") {
        for (int i = 0; i < Face::count(); i++) {
            std::fill(buf.begin(), buf.end(), 0);
            Face f; f.begin(7); if(getenv("PIP_RIG")) f.setPip(atoi(getenv("PIP_RIG")));
            if (getenv("PREVIEW_DY")) f.setCenterOffset(atof(getenv("PREVIEW_DY")), getenv("PREVIEW_SCALE") ? atof(getenv("PREVIEW_SCALE")) : 1.f);
            if (getenv("PREVIEW_TALK")) f.setTalk(atof(getenv("PREVIEW_TALK")));   // mouth open, as when speaking
            f.setEmotionIndex(i);
            for (int k = 0; k < 40; k++) { f.update(0.03f); f.render(c, W / 2, H / 2); }
            // freeze life: render settled frame at a moment with no blink
            std::string p = out + "/" + Face::name(i) + ".rgb565";
            save(p.c_str(), buf.data());
        }
    } else {
        std::vector<std::string> seq;
        std::string s = argc > 3 ? argv[3] : "idle,happy";
        size_t a = 0;
        while (a <= s.size()) { size_t b = s.find(',', a); if (b == std::string::npos) b = s.size(); seq.push_back(s.substr(a, b - a)); a = b + 1; }
        Face f; f.begin(3);
        int frame = 0;
        for (auto &e : seq) {
            if (e.rfind("talk:", 0) == 0) {   // talk:<seconds>
                float secs = atof(e.c_str() + 5);
                for (int k = 0; k < secs * 25; k++) {
                    float lvl = 0.5f + 0.5f * sinf(k * 0.9f) * sinf(k * 0.31f);
                    f.setTalk(lvl < 0 ? 0 : lvl);
                    f.update(0.04f); f.render(c, W / 2, H / 2);
                    char p[512]; snprintf(p, sizeof p, "%s/f%04d.rgb565", out.c_str(), frame++); save(p, buf.data());
                }
                f.setTalk(0);
                continue;
            }
            if (e.rfind("g:", 0) == 0) { f.gesture(e.c_str() + 2); continue; }
            f.setEmotion(e.c_str());
            for (int k = 0; k < 40; k++) {
                f.update(0.04f); f.render(c, W / 2, H / 2);
                char p[512]; snprintf(p, sizeof p, "%s/f%04d.rgb565", out.c_str(), frame++); save(p, buf.data());
            }
        }
    }
    return 0;
}
