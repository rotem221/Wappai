#pragma once
#include <Arduino.h>
void provisioningBegin();
void provisioningLoop();
bool provisioningPrompt();
uint32_t provisioningCode();
bool provisioningConfirm(bool allow);

void provisioningEnd();
