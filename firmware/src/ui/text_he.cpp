#include "text_he.h"
#include <math.h>
#include <string>
#include <vector>

static bool isHeb(uint32_t c) { return (c >= 0x0590 && c <= 0x05FF) || (c >= 0xFB1D && c <= 0xFB4F); }
static bool isLtrStrong(uint32_t c) { return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'); }

static std::vector<uint32_t> decode(const char *s) {
    std::vector<uint32_t> out;
    const uint8_t *p = (const uint8_t *)s;
    while (*p) {
        uint32_t c = *p++;
        int more = c >= 0xF0 ? 3 : c >= 0xE0 ? 2 : c >= 0xC0 ? 1 : 0;
        c &= more == 3 ? 7 : more == 2 ? 15 : more == 1 ? 31 : 0x7F;
        bool bad = false;
        for (int k = 0; k < more; k++) {                 // a string cut in the middle of a letter: stop at the NUL
            if ((*p & 0xC0) != 0x80) { bad = true; break; }
            c = (c << 6) | (*p++ & 0x3F);
        }
        if (bad) continue;
        out.push_back(c);
    }
    return out;
}

static std::string encode(const std::vector<uint32_t> &v) {
    std::string s;
    for (uint32_t c : v) {
        if (c < 0x80) s += (char)c;
        else if (c < 0x800) { s += (char)(0xC0 | (c >> 6)); s += (char)(0x80 | (c & 0x3F)); }
        else if (c < 0x10000) { s += (char)(0xE0 | (c >> 12)); s += (char)(0x80 | ((c >> 6) & 0x3F)); s += (char)(0x80 | (c & 0x3F)); }
        else { s += (char)(0xF0 | (c >> 18)); s += (char)(0x80 | ((c >> 12) & 0x3F)); s += (char)(0x80 | ((c >> 6) & 0x3F)); s += (char)(0x80 | (c & 0x3F)); }
    }
    return s;
}

static uint32_t mirror(uint32_t c) {
    switch (c) {
        case '(': return ')'; case ')': return '(';
        case '[': return ']'; case ']': return '[';
        case '<': return '>'; case '>': return '<';
        case '{': return '}'; case '}': return '{';
        default: return c;
    }
}

// One word in visual order. In an RTL context: Hebrew runs are reversed, digit/Latin runs keep their order,
// and the run order itself is reversed.
static std::vector<uint32_t> visualWord(const std::vector<uint32_t> &w, bool rtl) {
    if (!rtl) return w;
    const size_t n = w.size();
    std::vector<uint8_t> ltr(n);
    for (size_t i = 0; i < n; i++) {
        uint32_t c = w[i];
        bool l = isLtrStrong(c);
        bool sep = c == '.' || c == ':' || c == ',' || c == '/' || c == '-';
        if (!l && sep && i > 0 && i + 1 < n && ltr[i - 1] && isLtrStrong(w[i + 1])) l = true;   // 12:30, 3.5, 18°-27°
        if (!l && (c == '%' || c == 0xB0) && i > 0 && ltr[i - 1]) l = true;                        // 40%, 18°
        ltr[i] = l;
    }
    std::vector<uint32_t> out;
    // walk runs from the logical end: RTL runs are reversed (with bracket mirroring), LTR runs keep order
    size_t end = n;
    while (end > 0) {
        size_t beg = end - 1;
        while (beg > 0 && ltr[beg - 1] == ltr[end - 1]) beg--;
        if (ltr[end - 1]) out.insert(out.end(), w.begin() + beg, w.begin() + end);
        else for (size_t k = end; k > beg; k--) out.push_back(mirror(w[k - 1]));
        end = beg;
    }
    return out;
}

int drawBidiText(LGFX_Sprite &s, const char *utf8, int cx, int cy, int R, int y0, int lineH, int maxLines, uint32_t color,
                 int page) {
    auto cps = decode(utf8);
    bool rtl = false;
    for (uint32_t c : cps) {
        if (isHeb(c)) { rtl = true; break; }
        if (isLtrStrong(c) && !(c >= '0' && c <= '9')) break;
    }
    // words (logical order)
    std::vector<std::vector<uint32_t>> words;
    std::vector<uint32_t> w;
    for (uint32_t c : cps) {
        if (c == ' ' || c == '\n' || c == '\t') { if (!w.empty()) { words.push_back(w); w.clear(); } }
        else w.push_back(c);
    }
    if (!w.empty()) words.push_back(w);
    if (words.empty()) return 0;
    std::vector<std::string> vis;
    std::vector<int> wid;
    for (auto &ww : words) {
        vis.push_back(encode(visualWord(ww, rtl)));
        wid.push_back(s.textWidth(vis.back().c_str()));
    }
    const int space = s.textWidth(" ");
    auto lineWidth = [&](int li) {
        float dy = fabsf((y0 + li * lineH) - cy) + lineH * 0.5f;
        float half = dy < R ? sqrtf((float)R * R - dy * dy) : 0;
        return (int)(2 * half) - 36;
    };
    // greedy wrap into pages: line widths follow the circle and restart at the top of every page
    std::vector<std::vector<int>> lines;
    {
        std::vector<int> cur;
        int curW = 0;
        for (size_t i = 0; i < words.size(); i++) {
            int lw = lineWidth((int)lines.size() % maxLines);
            int add = wid[i] + (cur.empty() ? 0 : space);
            if (!cur.empty() && curW + add > lw) { lines.push_back(cur); cur.clear(); curW = 0; add = wid[i]; }
            cur.push_back((int)i);
            curW += add;
        }
        if (!cur.empty()) lines.push_back(cur);
    }
    const int pages = ((int)lines.size() + maxLines - 1) / maxLines;
    if (page >= pages) page = pages - 1;
    if (page < 0) page = 0;
    lines.erase(lines.begin(), lines.begin() + page * maxLines);
    s.setTextColor(color);
    s.setTextDatum(lgfx::middle_left);
    for (size_t li = 0; li < lines.size() && (int)li < maxLines; li++) {
        auto &L = lines[li];
        int total = 0;
        for (size_t k = 0; k < L.size(); k++) total += wid[L[k]] + (k ? space : 0);
        int y = y0 + (int)li * lineH;
        if (rtl) {
            int x = cx + total / 2;
            for (size_t k = 0; k < L.size(); k++) {
                x -= wid[L[k]];
                s.drawString(vis[L[k]].c_str(), x, y);
                x -= space;
            }
        } else {
            int x = cx - total / 2;
            for (size_t k = 0; k < L.size(); k++) {
                s.drawString(vis[L[k]].c_str(), x, y);
                x += wid[L[k]] + space;
            }
        }
    }
    return pages;
}
