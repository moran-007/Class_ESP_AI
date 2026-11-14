#pragma once
#include "device_core.h"
#include "audio_types.h"
#include <array>
#include <string>
#include <vector>

class FakeHardware : public ai_maker::Hardware {
 public:
  std::string state;
  std::array<std::string, 2> page_slots;
  bool page_save_ok = true, page_erase_ok = true;
  bool save_ok = true;
  bool output_ok = true;
  size_t saves = 0;
  size_t releases = 0;
  size_t servo_writes = 0;
  size_t digital_writes = 0;
  size_t led_writes = 0;
  int adc_value = 1234;
  std::array<int, 3> led{};
  std::array<int, 49> digital{};
  std::array<int, 49> pwm{};
  std::array<int, 49> pulse{};
  std::array<ai_maker::PinMode, 49> modes{};
  bool display_active = false;
  ai_maker::DisplaySpec display;
  int display_brightness = 100;
  size_t display_writes = 0;
  bool audio_begin_ok = true, audio_capture_ok = true, audio_play_ok = true;
  bool audio_read_ok = true, audio_write_ok = true, audio_finish_ok = true;
  bool audio_stop_ok = true, audio_release_ok = true;
  bool audio_read_partial = false, audio_write_partial = false;
  bool audio_active = false, audio_capturing = false, audio_playing = false;
  size_t audio_begins = 0, audio_capture_starts = 0, audio_play_starts = 0;
  size_t audio_reads = 0, audio_writes = 0, audio_finishes = 0;
  size_t audio_stops = 0, audio_releases = 0, audio_sample_index = 0;
  ai_maker::AudioSpec audio_spec;
  std::vector<uint8_t> audio_written;
  std::string bootId() const override { return "native-test-boot"; }
  std::string loadState() override { return state; }
  bool saveState(const std::string& value) override {
    ++saves;
    if (!save_ok) return false;
    state = value;
    return true;
  }
  std::string loadPageSlot(int slot) override { return page_slots.at(slot); }
  bool savePageSlot(int slot, const std::string& value) override {
    if (!page_save_ok) return false;
    page_slots.at(slot) = value; return true;
  }
  bool erasePageSlot(int slot) override {
    if (!page_erase_ok) return false;
    page_slots.at(slot).clear(); return true;
  }
  bool configurePin(int pin, ai_maker::PinMode mode) override {
    if (!output_ok) return false;
    modes[pin] = mode;
    return true;
  }
  void releasePin(int pin) override {
    ++releases;
    modes[pin] = ai_maker::PinMode::Unset;
    digital[pin] = pwm[pin] = pulse[pin] = 0;
  }
  bool writeDigital(int pin, int value) override {
    ++digital_writes;
    if (!output_ok) return false;
    digital[pin] = value;
    return true;
  }
  int readDigital(int pin) override { return digital[pin]; }
  int readAdc(int) override { return adc_value; }
  bool writePwm(int pin, int duty) override {
    if (!output_ok) return false;
    pwm[pin] = duty;
    return true;
  }
  bool writeServo(int pin, int pulse_us) override {
    ++servo_writes;
    if (!output_ok) return false;
    pulse[pin] = pulse_us;
    return true;
  }
  bool writeLed(int red, int green, int blue) override {
    ++led_writes;
    if (!output_ok) return false;
    led = {red, green, blue};
    return true;
  }
  bool beginDisplay(const ai_maker::DisplaySpec& value) override {
    if (!output_ok) return false;
    display = value; display_active = true; display_brightness = value.brightness; return true;
  }
  bool fillDisplay(uint16_t) override { ++display_writes; return output_ok && display_active; }
  bool textDisplay(int, int, const std::string&, uint16_t) override { ++display_writes; return output_ok && display_active; }
  bool rectDisplay(int, int, int, int, uint16_t, bool) override { ++display_writes; return output_ok && display_active; }
  bool lineDisplay(int, int, int, int, uint16_t) override { ++display_writes; return output_ok && display_active; }
  bool bitmapDisplay(int, int, int, int, const uint16_t*) override { ++display_writes; return output_ok && display_active; }
  bool brightnessDisplay(int percent) override {
    if (!output_ok || !display_active) return false;
    display_brightness = percent; return true;
  }
  bool releaseDisplay() override { display_active = false; return true; }
  bool beginAudio(const ai_maker::AudioSpec& value) override {
    ++audio_begins;
    if (!output_ok || !audio_begin_ok) return false;
    audio_spec = value; audio_active = true;
    audio_capturing = audio_playing = false;
    return true;
  }
  bool startAudioCapture() override {
    ++audio_capture_starts;
    if (!output_ok || !audio_active || !audio_capture_ok) return false;
    audio_capturing = true; audio_sample_index = 0; return true;
  }
  size_t readAudio(uint8_t* data, size_t bytes) override {
    ++audio_reads;
    if (!output_ok || !audio_active || !audio_capturing || !audio_read_ok) return 0;
    const size_t count = audio_read_partial ? bytes - 2 : bytes;
    for (size_t i = 0; i < count; i += 2) {
      const auto sample = static_cast<int16_t>(static_cast<int>(audio_sample_index++ % 512) * 41 - 10000);
      const auto bits = static_cast<uint16_t>(sample);
      data[i] = static_cast<uint8_t>(bits & 255);
      data[i + 1] = static_cast<uint8_t>(bits >> 8);
    }
    return count;
  }
  bool startAudioPlayback() override {
    ++audio_play_starts;
    if (!output_ok || !audio_active || !audio_play_ok) return false;
    audio_playing = true; audio_written.clear(); return true;
  }
  size_t writeAudio(const uint8_t* data, size_t bytes) override {
    ++audio_writes;
    if (!output_ok || !audio_active || !audio_playing || !audio_write_ok) return 0;
    const size_t count = audio_write_partial ? bytes - 2 : bytes;
    audio_written.insert(audio_written.end(), data, data + count); return count;
  }
  bool finishAudioPlayback() override {
    ++audio_finishes;
    if (!output_ok || !audio_active || !audio_finish_ok) return false;
    audio_playing = false; return true;
  }
  bool stopAudioIO() override {
    ++audio_stops;
    if (!output_ok || !audio_stop_ok) return false;
    audio_capturing = audio_playing = false; return true;
  }
  bool releaseAudio() override {
    ++audio_releases;
    if (!output_ok || !audio_release_ok) return false;
    audio_active = audio_capturing = audio_playing = false; return true;
  }
};
