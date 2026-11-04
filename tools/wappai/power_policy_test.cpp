#include "../../firmware/src/app/power_policy.h"
#include <cassert>
int main(){
 assert(powerDeepDelay(300000,false,false,80)==300000);
 assert(powerDeepDelay(300000,true,false,80)==60000);
 assert(powerDeepDelay(300000,false,true,80)==90000);
 assert(powerDeepDelay(300000,false,false,19)==60000);
 assert(powerDeepDelay(300000,false,false,-1)==300000);
 assert(powerDeepDelay(300000,false,false,20)==300000);
 assert(powerDeepDelay(45000,true,true,5)==45000);
 assert(powerDeepDelay(60000,false,true,80)==60000);
}
