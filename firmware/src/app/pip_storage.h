#pragma once
#include "face/pip_asset.h"
#include <Arduino.h>
#include <SPIFFS.h>
#include <esp_partition.h>
#include <mbedtls/sha256.h>
inline PipAsset *pipDecode(const uint8_t *bytes,size_t n){
    auto *p=new PipAsset;auto *pixels=(uint16_t*)ps_malloc(PipAsset::count*2);
    if(!pixels || !p->decode(bytes,n,pixels)){free(pixels);delete p;return nullptr;}return p;
}
inline PipAsset *pipLoad(const char *path){
    auto f=SPIFFS.open(path,"r");if(!f || f.size()>160000)return nullptr;
    size_t n=f.size();auto *data=(uint8_t*)ps_malloc(n);if(!data)return nullptr;
    size_t got=f.read(data,n);f.close();auto *p=got==n?pipDecode(data,n):nullptr;free(data);return p;
}
// Initialize only erased flash or this board's verified empty factory SPIFFS.
// Unknown/corrupt filesystems are never formatted automatically.
inline bool pipKnownEmptyStorage(){
    const esp_partition_t *part=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,ESP_PARTITION_SUBTYPE_DATA_SPIFFS,nullptr);
    if(!part || part->size!=0x60000)return false;
    uint8_t block[1024],hash[32];bool erased=true;mbedtls_sha256_context context;mbedtls_sha256_init(&context);mbedtls_sha256_starts(&context,0);
    for(size_t offset=0;offset<part->size;offset+=sizeof block){
        if(esp_partition_read(part,offset,block,sizeof block)!=ESP_OK){mbedtls_sha256_free(&context);return false;}
        mbedtls_sha256_update(&context,block,sizeof block);for(uint8_t byte:block)if(byte!=255)erased=false;
    }
    mbedtls_sha256_finish(&context,hash);mbedtls_sha256_free(&context);char hex[65];for(int i=0;i<32;i++)sprintf(hex+i*2,"%02x",hash[i]);
    return erased || !strcmp(hex,"c1d47c9164b3c7ba8bb5793a4efba96cd0110d85fca395d72079ea7cc593bb79");
}
inline PipAsset *pipBoot(){
    if(!SPIFFS.begin(false)){
        if(!pipKnownEmptyStorage() || !SPIFFS.format() || !SPIFFS.begin(false)){Serial.println("Pip storage unavailable (unknown data preserved)");return nullptr;}
        Serial.println("Pip storage initialized from verified empty factory partition");
    }
    auto *p=pipLoad("/wappai.bin");if(p)return p;
    p=pipLoad("/wappai.old");if(p){SPIFFS.remove("/wappai.bin");SPIFFS.rename("/wappai.old","/wappai.bin");}return p;
}
inline void pipStorageInfo(){
    Serial.printf("Pip storage: used=%u total=%u\n",(unsigned)SPIFFS.usedBytes(),(unsigned)SPIFFS.totalBytes());
    for(const char *path:{"/wappai.bin","/wappai.old","/wappai.tmp"}){auto f=SPIFFS.open(path,"r");if(f)Serial.printf("  %s %u bytes\n",path,(unsigned)f.size());}
}
inline bool pipSave(const uint8_t *data,size_t n){
    // SPIFFS has a bounded garbage-collection budget per write. A single large
    // write can exhaust that budget after prior assets were deleted. Small
    // writes reclaim pages progressively while the previous asset stays intact.
    auto f=SPIFFS.open("/wappai.tmp","w");if(!f){Serial.println("Pip storage: open failed");pipStorageInfo();return false;}
    size_t written=0;
    while(written<n){size_t chunk=min((size_t)4096,n-written);size_t got=f.write(data+written,chunk);written+=got;if(got!=chunk)break;}
    f.flush();f.close();if(written!=n){Serial.printf("Pip storage: short write %u/%u\n",(unsigned)written,(unsigned)n);pipStorageInfo();SPIFFS.remove("/wappai.tmp");return false;}
    auto *check=pipLoad("/wappai.tmp");if(!check){Serial.println("Pip storage: readback invalid");SPIFFS.remove("/wappai.tmp");return false;}delete check;
    SPIFFS.remove("/wappai.old");bool had=SPIFFS.exists("/wappai.bin");
    if(had&&!SPIFFS.rename("/wappai.bin","/wappai.old"))return false;
    if(!SPIFFS.rename("/wappai.tmp","/wappai.bin")){if(had)SPIFFS.rename("/wappai.old","/wappai.bin");return false;}
    SPIFFS.remove("/wappai.old");return true;
}
