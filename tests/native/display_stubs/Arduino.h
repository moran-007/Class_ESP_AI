#pragma once
#include <cstddef>
#include <cstdint>
constexpr int INPUT = 1;
constexpr int OUTPUT = 2;
constexpr int FSPI = 0;
void pinMode(int, int);
bool ledcAttachChannel(uint8_t, uint32_t, uint8_t, uint8_t);
bool ledcWrite(uint8_t, uint32_t);
bool ledcDetach(uint8_t);
