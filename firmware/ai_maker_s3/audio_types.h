#pragma once
#include <cstddef>
#include <cstdint>
#include <string>

namespace ai_maker {
constexpr uint32_t kAudioSampleRate = 16000;
constexpr size_t kAudioChunkBytes = 768;
#if defined(ARDUINO_USB_CDC_ON_BOOT)
constexpr bool kAudioTransportSupported = ARDUINO_USB_CDC_ON_BOOT != 0;
#else
constexpr bool kAudioTransportSupported = true;  // Production-core native tests.
#endif
struct AudioSpec {
  bool enabled = false;
  int bclk = 42, ws = 41, din = 21, dout = 40, sd = 39;
  bool mic_right = false;
  int volume = 20;
};
}  // namespace ai_maker
