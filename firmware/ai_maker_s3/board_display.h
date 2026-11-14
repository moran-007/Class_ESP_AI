#pragma once

#include "device_core.h"
#include <SPI.h>
#include <U8g2_for_Adafruit_GFX.h>

class Adafruit_ST7735;
class Adafruit_ST7789;
class Adafruit_ST77xx;

namespace ai_maker {
class BoardSt7735;
class BoardSt7789;

// Owns one SPI TFT. Configurations are validated by DeviceCore before begin().
// SPI TFT modules have no presence/optical feedback: true means commands sent.
class BoardDisplay {
 public:
  BoardDisplay() = default;
  ~BoardDisplay();
  BoardDisplay(const BoardDisplay&) = delete;
  BoardDisplay& operator=(const BoardDisplay&) = delete;

  bool begin(const DisplaySpec& spec);
  bool fill(uint16_t color);
  bool text(int x, int y, const std::string& value, uint16_t color);
  bool rect(int x, int y, int width, int height, uint16_t color, bool filled);
  bool line(int x0, int y0, int x1, int y1, uint16_t color);
  bool image(int x, int y, int width, int height, const uint16_t* pixels);
  bool brightness(int percent);
  bool release();

 private:
  SPIClass spi_{FSPI};
  DisplaySpec spec_;
  BoardSt7735* st7735_ = nullptr;
  BoardSt7789* st7789_ = nullptr;
  Adafruit_ST77xx* panel_ = nullptr;  // Non-owning; base destructor isn't virtual.
  U8G2_FOR_ADAFRUIT_GFX font_;
  bool owns_pins_ = false;
  bool panel_initialized_ = false;
  bool ready_ = false;
  bool backlight_attached_ = false;

  bool available();
};
}  // namespace ai_maker
