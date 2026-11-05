#pragma once
#include <stdint.h>
namespace uiTheme {
constexpr uint32_t surface=0x172536, raised=0x253B54, border=0x496783;
constexpr uint32_t accent=0xA4D2FF, text=0xE9F1FA, muted=0x91A6BC;
constexpr uint32_t ink=0x102337;
// Bordered surfaces use two fills: no blur, texture or extra framebuffer.
template<class Canvas> inline void button(Canvas &s,int x,int y,int w,int h,int radius,uint32_t fill,bool pressed=false){
 s.fillSmoothRoundRect(x,y,w,h,radius,pressed?accent:border);
 s.fillSmoothRoundRect(x+1,y+1,w-2,h-2,radius-1,fill);
}
}
