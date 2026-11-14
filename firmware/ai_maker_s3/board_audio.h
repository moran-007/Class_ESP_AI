#pragma once
#include "audio_types.h"
#include <array>
#include <driver/i2s_std.h>

namespace ai_maker {

// One shared-clock standard-I2S bus. This driver never allocates a whole clip.
// Read/write methods exchange mono signed16 little-endian bytes with DeviceCore.
class BoardAudio {
 public:
  BoardAudio() = default;
  ~BoardAudio() { release(); }
  BoardAudio(const BoardAudio&) = delete;
  BoardAudio& operator=(const BoardAudio&) = delete;

  bool begin(const AudioSpec& spec);
  bool startCapture();
  size_t read(uint8_t* pcm, size_t bytes);
  bool startPlayback();
  size_t write(const uint8_t* pcm, size_t bytes);
  bool finishPlayback();
  bool stopIO();
  bool release();

 private:
  struct StereoFrame { int32_t left, right; };
  AudioSpec spec_;
  i2s_chan_handle_t tx_ = nullptr, rx_ = nullptr;
  bool tx_enabled_ = false, rx_enabled_ = false;
  bool active_ = false, capturing_ = false, playing_ = false;
  // Retain ownership until GPIO reset succeeds; failed cleanup can be retried.
  std::array<int,5> owned_pins_{{-1,-1,-1,-1,-1}};
  bool amplifier(bool enabled);
  bool drainSilence();
  static bool validSpec(const AudioSpec& spec);
};

}  // namespace ai_maker
