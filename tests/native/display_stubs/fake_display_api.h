#pragma once
#include <Arduino.h>
#include <array>
#include <string>
#include <tuple>
#include <vector>

struct FakeDisplayApi {
  bool spi_begin_ok = true, geometry_ok = true;
  bool attach_ok = true, write_ok = true, detach_ok = true;
  int gpio_failure_pin = -1;
  int spi_starts = 0, spi_ends = 0, attaches = 0, detaches = 0;
  int sleep_commands = 0, off_commands = 0;
  int native_width = 0, native_height = 0, rotation = -1;
  uint32_t init_hz = 0, drawing_hz = 0;
  uint32_t duty = 0;
  uint16_t fill_color = 0, foreground = 0;
  std::array<int, 4> spi_pins{};
  std::array<int, 3> control_pins{};
  std::vector<int> input_pins;
  std::vector<std::tuple<int, int, std::string>> text;
  bool last_rect_filled = false;
  std::array<int, 4> shape{};
  std::vector<uint16_t> pixels;
};
extern FakeDisplayApi display_api;

class SPIClass;
class Adafruit_ST77xx {
 public:
  Adafruit_ST77xx(SPIClass*, int cs, int dc, int rst) { display_api.control_pins = {cs, dc, rst}; }
  virtual void begin(uint32_t hz = 0) { display_api.init_hz = hz; }
  virtual void setRotation(uint8_t rotation) { display_api.rotation = rotation; }
  void setSPISpeed(uint32_t hz) { display_api.drawing_hz = hz; }
  void invertDisplay(bool) {}
  int width() { return display_api.geometry_ok ? ((display_api.rotation & 1) ? display_api.native_height : display_api.native_width) : -1; }
  int height() { return (display_api.rotation & 1) ? display_api.native_width : display_api.native_height; }
  void fillScreen(uint16_t color) { display_api.fill_color = color; }
  void fillRect(int x, int y, int w, int h, uint16_t) { display_api.shape = {x,y,w,h}; display_api.last_rect_filled = true; }
  void drawRect(int x, int y, int w, int h, uint16_t) { display_api.shape = {x,y,w,h}; display_api.last_rect_filled = false; }
  void drawLine(int x0, int y0, int x1, int y1, uint16_t) { display_api.shape = {x0,y0,x1,y1}; }
  void drawRGBBitmap(int x, int y, const uint16_t* data, int w, int h) {
    display_api.shape = {x,y,w,h}; display_api.pixels.assign(data, data + w * h);
  }
  void enableDisplay(bool enabled) { if (!enabled) ++display_api.off_commands; }
  void enableSleep(bool enabled) { if (enabled) ++display_api.sleep_commands; }
};
class Adafruit_ST7735 : public Adafruit_ST77xx {
 public:
  using Adafruit_ST77xx::Adafruit_ST77xx;
  void initR(uint8_t) { begin(); display_api.native_width=128; display_api.native_height=160; }
};
class Adafruit_ST7789 : public Adafruit_ST77xx {
 public:
  using Adafruit_ST77xx::Adafruit_ST77xx;
  void init(int width, int height) { begin(); display_api.native_width=width; display_api.native_height=height; }
};
constexpr uint8_t INITR_BLACKTAB = 2;
constexpr uint16_t ST77XX_BLACK = 0;
