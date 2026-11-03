#include "pip_asset.h"
#include "face.h"
#include <vector>
#include <fstream>
#include <cassert>
#include <iostream>
int main(int argc,char **argv){
 assert(argc==2);std::ifstream file(argv[1],std::ios::binary);std::vector<uint8_t> data((std::istreambuf_iterator<char>(file)),{});assert(data.size()>756);
 auto check=[](const std::vector<uint8_t>&d){PipAsset a;auto *buf=(uint16_t*)malloc(PipAsset::count*2);bool ok=a.decode(d.data(),d.size(),buf);if(!ok)free(buf);return ok;};
 assert(check(data));
 for(size_t n=0;n<data.size();n+=73){auto truncated=data;truncated.resize(n);assert(!check(truncated));}
 for(size_t i=0;i<data.size();i+=97){auto corrupt=data;corrupt[i]^=0x80;assert(!check(corrupt));}
 auto checksum=[](std::vector<uint8_t>&d){uint32_t c=PipAsset::crc(d.data(),d.size()-4);for(int j=0;j<4;j++)d[d.size()-4+j]=c>>(8*j);};
 auto bad=data;bad[752]=0;checksum(bad);assert(!check(bad));
 bad=data;bad[144]=95;bad[146]=1;checksum(bad);assert(!check(bad));
 bad=data;bad[240]=1;checksum(bad);assert(!check(bad));
 PipAsset asset;assert(asset.decode(data.data(),data.size(),(uint16_t*)malloc(PipAsset::count*2)));
 Face face;face.begin();face.setAsset(&asset);face.setPip(3);std::vector<uint16_t> pixels(466*466);Canvas canvas{pixels.data(),466,466,false};
 for(int e=0;e<Face::count();e++){face.setEmotionIndex(e);for(int i=0;i<90;i++){face.update(1.f/30);face.render(canvas,233,240);}}
 face.setAsset(nullptr);face.render(canvas,233,240);
 std::cout<<"Pack validation, corruption rejection and all custom-character emotions passed\n";
}
