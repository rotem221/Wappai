#pragma once
#include "face/pip_asset.h"
#include <Arduino.h>
#include <SPIFFS.h>
#define MINIZ_NO_ZLIB_COMPATIBLE_NAMES
#include <miniz.h>
#include <esp_partition.h>
#include <mbedtls/sha256.h>
inline PipAsset *pipDecode(const uint8_t *bytes,size_t n){
    if(n>=8 && !memcmp(bytes,"WPC1",4)){
        size_t raw=PipAsset::u32(bytes+4);if(raw<756 || raw>160000 || n>160000)return nullptr;
        auto *unpacked=(uint8_t*)ps_malloc(raw);if(!unpacked)return nullptr;
        // ROM's mem_to_mem helper puts its ~11KB decoder on the 8KB network stack.
        // Keep the workspace in PSRAM instead, and require one complete bounded stream.
        auto *decoder=(tinfl_decompressor*)ps_malloc(sizeof(tinfl_decompressor));
        if(!decoder){free(unpacked);return nullptr;}tinfl_init(decoder);
        size_t input=n-8,got=raw;
        auto status=tinfl_decompress(decoder,bytes+8,&input,unpacked,unpacked,&got,TINFL_FLAG_PARSE_ZLIB_HEADER|TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF);
        free(decoder);
        PipAsset *result=status==TINFL_STATUS_DONE && input==n-8 && got==raw && !memcmp(unpacked,"WPP1",4)?pipDecode(unpacked,raw):nullptr;
        free(unpacked);return result;
    }
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
// One decoded atlas at a time. Compressed, checksummed packs stay in flash.
struct PipEntry {char pip[33]{},asset[33]{},name[64]{},path[32]{};};
inline void pipPath(char *out,const char *id){snprintf(out,32,"/%.24s.pp",id);}
inline bool pipMount(){
    if(SPIFFS.begin(false))return true;
    if(!pipKnownEmptyStorage() || !SPIFFS.format())return false;
    return SPIFFS.begin(false);
}
inline void pipRecover(){
    auto *old=pipLoad("/cache.old");
    if(old){char target[32];pipPath(target,old->pip);auto *current=pipLoad(target);
        if(!current){SPIFFS.remove(target);SPIFFS.rename("/cache.old",target);}delete current;delete old;}
}
inline unsigned pipScan(PipEntry *entries,unsigned capacity){
    unsigned count=0;auto root=SPIFFS.open("/");auto file=root.openNextFile();
    while(file){String path=file.path();file.close();
        if(path.endsWith(".pp") || path=="/wappai.bin"){
            auto *p=pipLoad(path.c_str());if(p){
                unsigned i=0;while(i<count && strcmp(entries[i].pip,p->pip))++i;
                if(i<capacity && (i==count || path.endsWith(".pp"))){
                    if(i==count)++count;
                    strlcpy(entries[i].pip,p->pip,33);strlcpy(entries[i].asset,p->asset,33);
                    strlcpy(entries[i].name,p->name,64);strlcpy(entries[i].path,path.c_str(),32);
                }delete p;
            }
        }file=root.openNextFile();
    }
    for(unsigned i=0;i<count;i++)for(unsigned j=i+1;j<count;j++)if(strcmp(entries[i].pip,entries[j].pip)>0){auto tmp=entries[i];entries[i]=entries[j];entries[j]=tmp;}
    return count;
}
inline PipAsset *pipCached(const char *pid){
    char path[32];pipPath(path,pid);auto *p=pipLoad(path);
    if(p && strcmp(p->pip,pid)){delete p;p=nullptr;}
    if(!p){p=pipLoad("/wappai.bin");if(p && strcmp(p->pip,pid)){delete p;p=nullptr;}}
    return p;
}
inline PipAsset *pipBoot(){
    if(!pipMount()){Serial.println("Pip storage unavailable; existing data preserved");return nullptr;}
    pipRecover();auto *p=pipLoad("/wappai.bin");if(p)return p;
    p=pipLoad("/wappai.old");if(p){SPIFFS.remove("/wappai.bin");SPIFFS.rename("/wappai.old","/wappai.bin");}return p;
}
inline void pipStorageInfo(){Serial.printf("Pip storage: used=%u total=%u\n",(unsigned)SPIFFS.usedBytes(),(unsigned)SPIFFS.totalBytes());}
inline bool pipSave(const uint8_t *data,size_t n){
    auto *valid=pipDecode(data,n);if(!valid)return false;
    char target[32];pipPath(target,valid->pip);
    auto *existing=pipLoad(target);
    if(existing && strcmp(existing->pip,valid->pip)){delete existing;delete valid;return false;} // truncated-name collision
    delete existing;
    // Reserve GC headroom, never evict another character or format on failure.
    SPIFFS.remove("/cache.tmp");
    if(SPIFFS.usedBytes()+n+8192>SPIFFS.totalBytes()*3/4){delete valid;return false;}
    auto f=SPIFFS.open("/cache.tmp","w");if(!f){delete valid;return false;}
    size_t written=0;while(written<n){size_t chunk=min((size_t)4096,n-written);size_t got=f.write(data+written,chunk);written+=got;if(got!=chunk)break;}
    f.flush();f.close();auto *check=written==n?pipLoad("/cache.tmp"):nullptr;
    bool verified=check && !strcmp(check->asset,valid->asset);delete check;
    if(!verified){SPIFFS.remove("/cache.tmp");delete valid;return false;}
    SPIFFS.remove("/cache.old");bool had=SPIFFS.exists(target);
    if(had && !SPIFFS.rename(target,"/cache.old")){delete valid;return false;}
    if(!SPIFFS.rename("/cache.tmp",target)){if(had)SPIFFS.rename("/cache.old",target);delete valid;return false;}
    SPIFFS.remove("/cache.old");
    auto *legacy=pipLoad("/wappai.bin");if(legacy && !strcmp(legacy->pip,valid->pip)){SPIFFS.remove("/wappai.bin");SPIFFS.remove("/wappai.old");}delete legacy;delete valid;return true;
}
inline bool pipRemove(const char *pid){
    char path[32];pipPath(path,pid);auto *p=pipLoad(path);
    bool ok=true;if(p && !strcmp(p->pip,pid))ok=SPIFFS.remove(path);delete p;
    p=pipLoad("/wappai.bin");if(p && !strcmp(p->pip,pid))ok=SPIFFS.remove("/wappai.bin")&&ok;delete p;return ok;
}
