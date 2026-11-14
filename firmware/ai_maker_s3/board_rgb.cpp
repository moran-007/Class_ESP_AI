#include "board_rgb.h"
#include <driver/gpio.h>

namespace ai_maker {
bool BoardRgb::write(uint8_t red, uint8_t green, uint8_t blue) {
  if (fault_) return false;
  if (owned_) {
    if (!rmtDeinit(pin_)) return false;
    owned_ = false;
  }
  gpio_config_t reset{};
  reset.pin_bit_mask = 1ULL << pin_;
  reset.mode = GPIO_MODE_OUTPUT;
  if (gpio_config(&reset) != ESP_OK ||
      gpio_set_level(static_cast<gpio_num_t>(pin_), 0) != ESP_OK) return false;
  delay(1);  // Establish a LOW reset before the first frame, including boot.
  if (!rmtInit(pin_, RMT_TX_MODE, RMT_MEM_NUM_BLOCKS_1, 10000000)) return false;
  owned_ = true;
  const uint8_t grb[] = {green, red, blue};
  for (size_t bit = 0; bit < symbols_.size(); ++bit) {
    const bool one = (grb[bit / 8] & (1 << (7 - bit % 8))) != 0;
    auto& symbol = symbols_[bit];
    symbol.level0 = 1; symbol.duration0 = one ? 8 : 4;
    symbol.level1 = 0; symbol.duration1 = one ? 4 : 8;
  }
  if (!rmtWrite(pin_, symbols_.data(), symbols_.size(), 1000)) {
    fault_ = true;
    if (rmtDeinit(pin_)) owned_ = false;
    return false;
  }
  delay(1);  // Latch interval after all 24 GRB bits; do not cut the last bit.
  return true;
}
}  // namespace ai_maker
