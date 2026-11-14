#include "board_display.h"

#include <Adafruit_ST7735.h>
#include <Adafruit_ST7789.h>
#include <driver/gpio.h>
#include <new>

namespace ai_maker {
namespace {
constexpr uint32_t kDrawingSpiHz = 8000000;
constexpr uint8_t kBacklightChannel = 3;
constexpr uint32_t kBacklightMax = 16383;
constexpr int kTextLineHeight = 16;

bool dimensions(const DisplaySpec& spec, int& width, int& height) {
  if (spec.panel == "st7735s_128x160") { width = 128; height = 160; }
  else if (spec.panel == "st7789_240x320") { width = 240; height = 320; }
  else if (spec.panel == "st7789_240x240") { width = height = 240; }
  else return false;
  if (spec.rotation & 1) { const int previous = width; width = height; height = previous; }
  return true;
}
}  // namespace

// Adafruit commonInit() calls virtual begin() with frequency=0, which otherwise
// selects 32MHz. Use the same conservative clock during init and drawing.
class BoardSt7735 final : public Adafruit_ST7735 {
 public:
  using Adafruit_ST7735::Adafruit_ST7735;
  void begin(uint32_t hz = 0) override { Adafruit_ST77xx::begin(hz ? hz : kDrawingSpiHz); }
};
class BoardSt7789 final : public Adafruit_ST7789 {
 public:
  using Adafruit_ST7789::Adafruit_ST7789;
  void begin(uint32_t hz = 0) override { Adafruit_ST77xx::begin(hz ? hz : kDrawingSpiHz); }
};

BoardDisplay::~BoardDisplay() { release(); }

bool BoardDisplay::available() { return ready_ && panel_ && spi_.bus(); }

bool BoardDisplay::begin(const DisplaySpec& spec) {
  // Never silently overwrite a previous owner whose cleanup failed.
  if (!release()) return false;
  int expected_width = 0, expected_height = 0;
  if (!spec.enabled || spec.rotation < 0 || spec.rotation > 3 ||
      !dimensions(spec, expected_width, expected_height) ||
      spec.brightness < 0 || spec.brightness > 100 ||
      (spec.backlight < 0 && spec.brightness != 100)) return false;

  spec_ = spec;
  owns_pins_ = true;  // Even partial SPI initialization needs cleanup.
  if (spec_.backlight >= 0) {
    // Keep the lamp dark until a valid controller has been initialized.
    if (gpio_set_level(static_cast<gpio_num_t>(spec_.backlight), 0) != ESP_OK) {
      release(); return false;
    }
    pinMode(spec_.backlight, OUTPUT);
  }
  if (!spi_.begin(spec_.sck, -1, spec_.mosi, spec_.cs)) {
    release(); return false;
  }

  if (spec_.panel == "st7735s_128x160") {
    st7735_ = new (std::nothrow) BoardSt7735(&spi_, spec_.cs, spec_.dc, spec_.rst);
    panel_ = st7735_;
    if (st7735_) st7735_->initR(INITR_BLACKTAB);
  } else {
    st7789_ = new (std::nothrow) BoardSt7789(&spi_, spec_.cs, spec_.dc, spec_.rst);
    panel_ = st7789_;
    if (st7789_) st7789_->init(240, spec_.panel == "st7789_240x240" ? 240 : 320);
  }
  if (!panel_) { release(); return false; }
  panel_initialized_ = true;
  panel_->setSPISpeed(kDrawingSpiHz);
  panel_->setRotation(spec_.rotation);
  panel_->invertDisplay(spec_.invert);
  if (!spi_.bus() || panel_->width() != expected_width || panel_->height() != expected_height) {
    release(); return false;
  }
  panel_->fillScreen(ST77XX_BLACK);
  font_.begin(*panel_);
  font_.setFont(u8g2_font_wqy12_t_gb2312);
  font_.setFontMode(1);
  font_.setFontDirection(0);

  if (spec_.backlight >= 0) {
    if (!ledcAttachChannel(spec_.backlight, 1000, 14, kBacklightChannel)) {
      release(); return false;
    }
    backlight_attached_ = true;
  }
  ready_ = true;
  if (spec_.backlight >= 0 && !brightness(spec_.brightness)) {
    release(); return false;
  }
  return true;
}

bool BoardDisplay::fill(uint16_t color) {
  if (!available()) return false;
  panel_->fillScreen(color);
  return true;
}

bool BoardDisplay::text(int x, int y, const std::string& value, uint16_t color) {
  if (!available()) return false;
  font_.setForegroundColor(color);
  // The API uses a top-left origin; the font renderer expects a baseline.
  // Handle newlines explicitly to retain the caller's x and a fixed 16px row.
  size_t start = 0;
  int top = y;
  while (start < value.size() && top < panel_->height()) {
    const size_t end = value.find('\n', start);
    const std::string row = value.substr(start, end == std::string::npos ? end : end - start);
    font_.drawUTF8(x, top + 12, row.c_str());
    if (end == std::string::npos) break;
    start = end + 1;
    top += kTextLineHeight;
  }
  return true;
}

bool BoardDisplay::rect(int x, int y, int width, int height, uint16_t color, bool filled) {
  if (!available()) return false;
  if (filled) panel_->fillRect(x, y, width, height, color);
  else panel_->drawRect(x, y, width, height, color);
  return true;
}

bool BoardDisplay::line(int x0, int y0, int x1, int y1, uint16_t color) {
  if (!available()) return false;
  panel_->drawLine(x0, y0, x1, y1, color);
  return true;
}

bool BoardDisplay::brightness(int percent) {
  if (!available() || !backlight_attached_ || percent < 0 || percent > 100) return false;
  const uint32_t duty = (static_cast<uint32_t>(percent) * kBacklightMax + 50) / 100;
  if (!ledcWrite(spec_.backlight, duty)) return false;
  spec_.brightness = percent;
  return true;
}

bool BoardDisplay::image(int x, int y, int width, int height, const uint16_t* pixels) {
  if (!available() || !pixels || x < 0 || y < 0 || width <= 0 || height <= 0 ||
      width > panel_->width() - x || height > panel_->height() - y) return false;
  panel_->drawRGBBitmap(x, y, pixels, width, height);
  return true;
}

bool BoardDisplay::release() {
  ready_ = false;
  bool ok = true;
  if (panel_ && panel_initialized_ && spi_.bus()) {
    panel_->enableDisplay(false);
    panel_->enableSleep(true);
  }
  panel_initialized_ = false;
  if (backlight_attached_) {
    if (!ledcWrite(spec_.backlight, 0)) ok = false;
    if (!ledcDetach(spec_.backlight)) ok = false;
    else backlight_attached_ = false;
  }
  // Delete concrete objects: Adafruit_SPITFT does not have a virtual destructor.
  panel_ = nullptr;
  delete st7735_; st7735_ = nullptr;
  delete st7789_; st7789_ = nullptr;
  spi_.end();  // Also cleans a partial begin() that allocated a bus then failed.

  if (owns_pins_) {
    const int pins[] = {spec_.sck, spec_.mosi, spec_.cs, spec_.dc, spec_.rst, spec_.backlight};
    for (const int pin : pins) {
      if (pin < 0) continue;
      // Retain an unsuccessfully detached LEDC handle for a later retry, while
      // electrically placing that pin into input mode with the IDF API.
      if (pin != spec_.backlight || !backlight_attached_) pinMode(pin, INPUT);
      gpio_config_t input{};
      input.pin_bit_mask = 1ULL << pin;
      input.mode = GPIO_MODE_INPUT;
      input.pull_up_en = GPIO_PULLUP_DISABLE;
      input.pull_down_en = GPIO_PULLDOWN_DISABLE;
      input.intr_type = GPIO_INTR_DISABLE;
      if (gpio_config(&input) != ESP_OK) ok = false;
    }
  }
  if (ok) owns_pins_ = false;
  return ok;
}
}  // namespace ai_maker
