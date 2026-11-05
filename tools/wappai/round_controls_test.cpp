#include "app/round_controls.h"
#include <cassert>
#include <iostream>
using namespace roundControls;
int main(){
 EdgeSwipe g;
 g.begin(400,233,170,80);assert(!g.move(401,240));assert(g.move(401,113));assert(g.value==255);assert(g.kind==EdgeSwipe::BRIGHTNESS);
 assert(g.move(400,465));assert(g.value==20);g.reset();assert(!g.active);
 g.begin(65,233,170,80);assert(g.move(65,353));assert(g.value==30);assert(g.kind==EdgeSwipe::VOLUME);assert(g.move(65,465));assert(g.value==0);
 for(int x=100;x<370;x+=30){g.begin(x,233,170,80);assert(!g.move(x,50));}
 for(int y:{0,50,400,465}){g.begin(400,y,170,80);assert(!g.move(400,233));}
 g.begin(400,230,170,80);assert(!g.move(320,240));assert(!g.move(320,60)); // horizontal intent never becomes volume
 g.begin(400,230,170,80);assert(g.move(400,200));int v=g.value;assert(g.move(400,200)&&g.value==v); // absolute, no accumulating drift
 g.begin(60,230,170,0);assert(g.move(60,100));assert(g.value==54);g.reset();assert(!g.move(60,20));
 TimerPicker p;assert(p.total()==300);p.change(0,999);p.change(1,999);p.change(2,999);assert(p.total()==86399);
 p.change(0,-999);p.change(1,-999);p.change(2,-999);assert(p.total()==0);p.change(2,30);assert(p.total()==30);
 std::cout<<"Edge direction, intent, bounds, jitter, release and timer limits passed\n";
}
