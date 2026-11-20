#pragma once
#include "device_core.h"
#include "board_rgb.h"
#include "board_display.h"
#include "board_audio.h"
#include <Arduino.h>
#include <Preferences.h>

namespace ai_maker {

class EspHardware final : public Hardware {
 public:
  void begin();
  std::string bootId() const override { return boot_id_; }
  std::string loadState() override;
  bool saveState(const std::string& state) override;
  std::string loadProgramState() override;
  bool saveProgramState(const std::string& state) override;
  std::string loadPageSlot(int slot) override;
  bool savePageSlot(int slot, const std::string& data) override;
  bool erasePageSlot(int slot) override;
  bool configurePin(int pin, PinMode mode) override;
  void releasePin(int pin) override;
  bool writeDigital(int pin, int value) override;
  int readDigital(int pin) override;
  int readAdc(int pin) override;
  bool writePwm(int pin, int duty) override;
  bool writeServo(int pin, int pulse_us) override;
  bool writeLed(int red, int green, int blue) override;
  bool beginDisplay(const DisplaySpec& spec) override { return display_.begin(spec); }
  bool fillDisplay(uint16_t color) override { return display_.fill(color); }
  bool textDisplay(int x, int y, const std::string& value, uint16_t color) override { return display_.text(x, y, value, color); }
  bool rectDisplay(int x, int y, int w, int h, uint16_t color, bool filled) override { return display_.rect(x, y, w, h, color, filled); }
  bool lineDisplay(int x0, int y0, int x1, int y1, uint16_t color) override { return display_.line(x0, y0, x1, y1, color); }
  bool bitmapDisplay(int x, int y, int width, int height, const uint16_t* pixels) override { return display_.image(x, y, width, height, pixels); }
  bool brightnessDisplay(int percent) override { return display_.brightness(percent); }
  bool releaseDisplay() override { return display_.release(); }
  bool beginAudio(const AudioSpec& spec) override { return audio_.begin(spec); }
  bool startAudioCapture() override { return audio_.startCapture(); }
  size_t readAudio(uint8_t* data, size_t bytes) override { return audio_.read(data, bytes); }
  bool startAudioPlayback() override { return audio_.startPlayback(); }
  size_t writeAudio(const uint8_t* data, size_t bytes) override { return audio_.write(data, bytes); }
  bool finishAudioPlayback() override { return audio_.finishPlayback(); }
  bool stopAudioIO() override { return audio_.stopIO(); }
  bool releaseAudio() override { return audio_.release(); }
  bool wifiAvailable() const override { return true; }
  bool loadWifi(std::string& profile) override;
  bool saveWifi(const std::string& profile) override;
  bool stopWifi() override;
  bool startWifi(const std::string& ssid, const std::string& password) override;
  std::string wifiIp(const std::string& ssid) override;

 private:
  Preferences preferences_;
  bool storage_ready_ = false;
  std::string boot_id_;
  BoardRgb rgb_{kBuiltinRgbPin};
  BoardDisplay display_;
  BoardAudio audio_;
  std::array<int, 8> channels_{{-1, -1, -1, -1, -1, -1, -1, -1}};
  bool attach(int pin, bool servo);
};
}  // namespace ai_maker
