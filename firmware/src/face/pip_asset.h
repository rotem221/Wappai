#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include "dizzy_eyes.h"
struct PipAsset {
    uint16_t *pixels=nullptr;
    DizzyEyes dizzyEyes{};
    uint8_t bounds[24][4]{};
    char pip[33]{},asset[33]{},name[64]{};
    ~PipAsset(){free(pixels);}
    static constexpr size_t count=24*96*96;
    static uint32_t crc(const uint8_t *p,size_t n){uint32_t c=~0u;while(n--){c^=*p++;for(int i=0;i<8;i++)c=(c>>1)^(0xedb88320u&-(c&1));}return ~c;}
    static uint32_t u32(const uint8_t*p){return uint32_t(p[0])|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24;}
    bool decode(const uint8_t *p,size_t n,uint16_t *storage){
        if(n<756 || n>160000 || memcmp(p,"WPP1",4) || p[4]!=96 || p[5] || p[6]!=96 || p[7] || p[8]!=24 || p[9] || p[10] || p[11]!=1)return false;
        uint32_t len=u32(p+12);if(len!=n-756 || len%2 || crc(p,n-4)!=u32(p+n-4))return false;
        for(int i=16;i<80;i++)if(!((p[i]>='0'&&p[i]<='9')||(p[i]>='a'&&p[i]<='f')))return false;
        if(p[143]!=0)return false;
        for(int f=0;f<24;f++){const uint8_t*b=p+144+f*4;if(b[0]>=b[2]||b[1]>=b[3]||b[2]>96||b[3]>96)return false;}
        if(p[240] || p[241])return false;
        size_t pos=0;bool visible[24]={};
        for(size_t i=752;i<n-4;i+=2){unsigned run=p[i],idx=p[i+1];if(!run||pos+run>count)return false;uint16_t v=p[240+idx*2]|uint16_t(p[241+idx*2])<<8;
            while(run--){unsigned f=pos/(96*96),x=pos%96,y=(pos/96)%96;const uint8_t*b=p+144+f*4;
                if(v){if(x<b[0]||x>=b[2]||y<b[1]||y>=b[3])return false;visible[f]=true;}storage[pos++]=v;}}
        if(pos!=count)return false;for(bool v:visible)if(!v)return false;
        memcpy(bounds,p+144,96);memcpy(pip,p+16,32);memcpy(asset,p+48,32);memcpy(name,p+80,64);pixels=storage;dizzyEyes=locateDizzyEyes(storage+12*96*96,bounds[12]);return true;
    }
};
