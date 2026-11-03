#include "recording_store.h"
#if WAPPAI_SD_ENABLED
#include <SD_MMC.h>
#include <esp_system.h>
#if !defined(WAPPAI_SD_CLK) || !defined(WAPPAI_SD_CMD) || !defined(WAPPAI_SD_D0)
#error "An SD-enabled BSP must supply verified CLK/CMD/D0 pins"
#endif
static SemaphoreHandle_t lock_;
static File file_;
static bool present_=false,active_=false;
static size_t written_=0,read_=0;
static String failure_="not_mounted";
static uint32_t lastFlush_=0;
static void header(){
  uint8_t h[44]={};memcpy(h,"RIFF",4);memcpy(h+8,"WAVEfmt ",8);memcpy(h+36,"data",4);
  auto put=[&](int at,uint32_t n){memcpy(h+at,&n,4);};
  put(4,36+written_);put(16,16);h[20]=1;h[22]=1;put(24,16000);put(28,32000);h[32]=2;h[34]=16;put(40,written_);
  file_.seek(0);file_.write(h,44);file_.flush();
}
void recordingStoreBegin(){
  if(!lock_)lock_=xSemaphoreCreateMutex();
  present_=SD_MMC.setPins(WAPPAI_SD_CLK,WAPPAI_SD_CMD,WAPPAI_SD_D0) && SD_MMC.begin("/sdcard",true,false,20000) && SD_MMC.cardType()!=CARD_NONE;
  failure_=present_?"ready":"missing_or_unreadable";
  if(present_)SD_MMC.mkdir("/wappai-recordings");
}
bool recordingStoreStart(){
  recordingStoreClose();if(!present_)recordingStoreBegin();if(!present_)return false;
  if(SD_MMC.totalBytes()-SD_MMC.usedBytes()<4*1024*1024){failure_="full";return false;}
  char path[80];snprintf(path,sizeof path,"/wappai-recordings/%08lx-%08lx.wav",(unsigned long)time(nullptr),(unsigned long)esp_random());
  file_=SD_MMC.open(path,"w+");if(!file_){failure_="write_failed";return false;}
  written_=read_=0;active_=true;header();return true;
}
bool recordingStoreActive(){return active_;}
bool recordingStoreWrite(const uint8_t *data,size_t length){
  if(!active_||!file_)return false;
  if(xSemaphoreTake(lock_,pdMS_TO_TICKS(100))!=pdTRUE){failure_="busy";return false;}
  bool ok=SD_MMC.totalBytes()-SD_MMC.usedBytes()>1024*1024 && file_.seek(44+written_) && file_.write(data,length)==length;
  if(ok){written_+=length;if(millis()-lastFlush_>2000){header();lastFlush_=millis();}}
  else failure_="removed_or_full";
  xSemaphoreGive(lock_);return ok;
}
size_t recordingStoreRead(uint8_t *data,size_t length){
  if(!file_||xSemaphoreTake(lock_,pdMS_TO_TICKS(100))!=pdTRUE)return 0;
  size_t n=min(length,written_-read_);if(!file_.seek(44+read_))n=0;else n=file_.read(data,n);read_+=n;xSemaphoreGive(lock_);return n;
}
size_t recordingStoreQueued(){return written_>=read_?written_-read_:0;}
void recordingStoreStopCapture(){if(file_&&xSemaphoreTake(lock_,pdMS_TO_TICKS(200))==pdTRUE){header();xSemaphoreGive(lock_);}}
void recordingStoreClose(){if(file_){recordingStoreStopCapture();file_.close();}active_=false;}
String recordingStoreStatus(){return String("{\"sd_supported\":true,\"sd_present\":")+(present_?"true":"false")+",\"status\":\""+failure_+"\",\"available_bytes\":"+String(present_?SD_MMC.totalBytes()-SD_MMC.usedBytes():0)+"}";}
#else
void recordingStoreBegin(){}
bool recordingStoreStart(){return false;}
bool recordingStoreActive(){return false;}
bool recordingStoreWrite(const uint8_t*,size_t){return false;}
size_t recordingStoreRead(uint8_t*,size_t){return 0;}
size_t recordingStoreQueued(){return 0;}
void recordingStoreStopCapture(){}
void recordingStoreClose(){}
String recordingStoreStatus(){return "{\"sd_supported\":false,\"sd_present\":false,\"status\":\"no_slot\",\"offline_capacity_seconds\":98}";}
#endif
