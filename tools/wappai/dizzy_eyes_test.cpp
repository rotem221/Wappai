#include "face.h"
#include "pip_asset.h"
#include "pixel_catalog.gen.h"
#include <cassert>
#include <fstream>
#include <iostream>
#include <vector>
#include <algorithm>

int main(int argc,char **argv){
 assert(argc==3); // Valid custom pack and existing output directory.
 std::ifstream file(argv[1],std::ios::binary);std::vector<uint8_t> data((std::istreambuf_iterator<char>(file)),{});
 PipAsset asset;assert(asset.decode(data.data(),data.size(),(uint16_t*)malloc(PipAsset::count*2)));
 for(auto eye:asset.dizzyEyes.eye)std::cout<<"Custom eye "<<eye.x<<","<<eye.y<<" radius "<<eye.rx<<","<<eye.ry<<"\n";
 auto original=std::vector<uint16_t>(asset.pixels,asset.pixels+PipAsset::count);
 // An eye-only phase change must alter each eye, preserve every other pixel,
 // and work at clipped edges. This catches a stationary spiral with moving stars.
 for(int rig=0;rig<4;rig++){
  DizzyEyes eyes=asset.dizzyEyes;
  if(rig<3)for(int i=0;i<2;i++){const float*e=PIXEL_DIZZY_EYES[rig][i];eyes.eye[i]={e[0],e[1],e[2],e[3]};}
  std::vector<uint16_t> a(9216,0x5555),b=a;paintDizzyEyes(a.data(),eyes,0);paintDizzyEyes(b.data(),eyes,.27f);
  for(auto e:eyes.eye){int changed=0;for(int y=0;y<96;y++)for(int x=0;x<96;x++)if(std::abs(x-e.x)<e.rx&&std::abs(y-e.y)<e.ry&&a[y*96+x]!=b[y*96+x])changed++;assert(changed>10);}
  for(int y=0;y<96;y++)for(int x=0;x<96;x++){bool inside=false;for(auto e:eyes.eye)inside|=std::abs(x+.5f-e.x)<=e.rx+1&&std::abs(y+.5f-e.y)<=e.ry+1;if(!inside)assert(a[y*96+x]==0x5555&&b[y*96+x]==0x5555);}
  for(bool reduced:{false,true})for(bool swapped:{false,true}){
   Face f;f.begin(7);f.setAsset(&asset);f.setPip(rig);f.setReducedMotion(reduced);f.setEmotion("dizzy");f.setTalk(.9f);f.lookAt(0,0,10000);
   std::vector<uint16_t> pixels(466*466);Canvas canvas{pixels.data(),466,466,swapped};
   for(int n=0;n<40;n++){f.update(.03f);f.render(canvas,233,233);}
   uint16_t cream=swapped?0xdcff:0xffdc;assert(std::count(pixels.begin(),pixels.end(),cream)>100);
   auto first=pixels;
   for(int n=0;n<9;n++){f.update(.03f);f.render(canvas,233,233);}
   if(reduced)assert(first==pixels);else assert(first!=pixels);
   if(!reduced&&!swapped){std::string path=std::string(argv[2])+"/rig"+std::to_string(rig)+".rgb565";std::ofstream out(path,std::ios::binary);out.write((char*)pixels.data(),pixels.size()*2);}
   f.setEmotion("idle");f.setTalk(0);for(int n=0;n<40;n++){f.update(.03f);f.render(canvas,233,233);}
   Face clean=f;std::vector<uint16_t> blank(pixels.size());Canvas cleanCanvas{blank.data(),466,466,swapped};clean.render(cleanCanvas,233,233);assert(blank==pixels);
  }
 }
 assert(std::equal(original.begin(),original.end(),asset.pixels));
 std::vector<uint16_t> pixels(9216);uint8_t bounds[]={0,0,96,96};auto fallback=locateDizzyEyes(pixels.data(),bounds);assert(fallback.eye[0].x<fallback.eye[1].x);
 for(int y=0;y<96;y++)for(int x=0;x<96;x++)pixels[y*96+x]=((x+y)%2)?0xffff:0x1082;
 auto noisy=locateDizzyEyes(pixels.data(),bounds);paintDizzyEyes(pixels.data(),noisy,1);
 DizzyEyes clipped={{{0,0,8,10},{95,95,8,10}}};paintDizzyEyes(pixels.data(),clipped,1);
 std::cout<<"Spiral rotation in both eyes; all rigs during speech; Reduce Motion; byte order; reset; immutable art; clipped/fallback/noisy custom art passed\n";
}
