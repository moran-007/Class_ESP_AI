#pragma once
#include "fake_display_api.h"
extern const uint8_t u8g2_font_wqy12_t_gb2312[];
class U8G2_FOR_ADAFRUIT_GFX {
 public:
  void begin(Adafruit_ST77xx&) {}
  void setFont(const uint8_t*) {}
  void setFontMode(uint8_t) {}
  void setFontDirection(uint8_t) {}
  void setForegroundColor(uint16_t color) { display_api.foreground=color; }
  int drawUTF8(int x, int y, const char* text) { display_api.text.emplace_back(x,y,text); return 0; }
};
