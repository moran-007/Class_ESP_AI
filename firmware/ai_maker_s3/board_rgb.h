#pragma once
#include <Arduino.h>
#include <array>

namespace ai_maker {
// Owned by the static hardware adapter for the entire firmware lifetime.
class BoardRgb {
 public:
  explicit BoardRgb(int pin) : pin_(pin) {}
  bool write(uint8_t red, uint8_t green, uint8_t blue);

 private:
  int pin_;
  bool owned_ = false;
  bool fault_ = false;
  // A timed-out RMT transfer may still refer to this memory. Never reuse it
  // after a timeout, even when deinitialization also fails.
  std::array<rmt_data_t, 24> symbols_{};
};
}  // namespace ai_maker
