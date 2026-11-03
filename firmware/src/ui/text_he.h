// Minimal bidi for short Hebrew/English subtitles on the round screen.
#pragma once
#include <LovyanGFX.hpp>

// Draws `utf8` centred around cx, starting at line centre y0, with per-line widths that follow
// the circle (radius R, centre cy). Long text is split into pages of `maxLines` lines: `page` selects which
// one is drawn (clamped to the last). Returns the number of pages.
int drawBidiText(LGFX_Sprite &s, const char *utf8, int cx, int cy, int R, int y0, int lineH, int maxLines, uint32_t color,
                 int page = 0);
