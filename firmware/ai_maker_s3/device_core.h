#pragma once

#include <ArduinoJson.h>
#include <array>
#include <cstdint>
#include <string>
#include "page_model.h"
#include "audio_types.h"

namespace ai_maker {

constexpr uint32_t kLeaseMs = 6000;
constexpr size_t kMaxLine = 4096;
constexpr size_t kMaxStateBytes = 4096;
constexpr size_t kMaxServos = 4;
#ifndef AI_MAKER_RGB_PIN
#define AI_MAKER_RGB_PIN 48
#endif
constexpr int kBuiltinRgbPin = AI_MAKER_RGB_PIN;
static_assert(kBuiltinRgbPin == 38 || kBuiltinRgbPin == 48, "Select a verified RGB board variant");
enum class PinMode { Unset, Input, InputPullup, InputPulldown, Output, Pwm };

struct ServoSpec {
  std::string name;
  int pin = -1;
  int min_angle = 30;
  int max_angle = 150;
  int min_pulse_us = 500;
  int max_pulse_us = 2500;
  int angle = -1;
  bool active = false;
};

struct DisplaySpec {
  bool enabled = false;
  std::string panel = "st7789_240x320";
  int sck = 4, mosi = 5, cs = 15, dc = 7, rst = 6;
  int backlight = -1;
  int rotation = 1;
  bool invert = true;
  int brightness = 60;
};

class Hardware {
 public:
  virtual ~Hardware() = default;
  virtual std::string bootId() const = 0;
  virtual std::string loadState() = 0;
  virtual bool saveState(const std::string& state) = 0;
  virtual std::string loadPageSlot(int) { return ""; }
  virtual bool savePageSlot(int, const std::string&) { return false; }
  virtual bool erasePageSlot(int) { return false; }
  virtual bool configurePin(int pin, PinMode mode) = 0;
  virtual void releasePin(int pin) = 0;
  virtual bool writeDigital(int pin, int value) = 0;
  virtual int readDigital(int pin) = 0;
  virtual int readAdc(int pin) = 0;
  virtual bool writePwm(int pin, int duty) = 0;
  virtual bool writeServo(int pin, int pulse_us) = 0;
  virtual bool writeLed(int, int, int) { return false; }
  virtual bool beginDisplay(const DisplaySpec&) { return false; }
  virtual bool fillDisplay(uint16_t) { return false; }
  virtual bool textDisplay(int, int, const std::string&, uint16_t) { return false; }
  virtual bool rectDisplay(int, int, int, int, uint16_t, bool) { return false; }
  virtual bool lineDisplay(int, int, int, int, uint16_t) { return false; }
  virtual bool bitmapDisplay(int, int, int, int, const uint16_t*) { return false; }
  virtual bool brightnessDisplay(int) { return false; }
  virtual bool releaseDisplay() { return true; }
  virtual bool beginAudio(const AudioSpec&) { return false; }
  virtual bool startAudioCapture() { return false; }
  virtual size_t readAudio(uint8_t*, size_t) { return 0; }
  virtual bool startAudioPlayback() { return false; }
  virtual size_t writeAudio(const uint8_t*, size_t) { return 0; }
  virtual bool finishAudioPlayback() { return false; }
  virtual bool stopAudioIO() { return true; }
  virtual bool releaseAudio() { return true; }
};

class DeviceCore {
 public:
  explicit DeviceCore(Hardware& hardware);
  void begin();
  std::string process(const std::string& line, uint32_t now_ms);
  void tick(uint32_t now_ms);
  static bool validPin(int pin);
  static bool reservedPin(int pin);
  static bool adcPin(int pin);

 private:
  struct PageSettings {
    int slot = -1;
    std::string crc32;
    bool startup_enabled = false;
    std::string default_page;
  };
  Hardware& hardware_;
  std::array<PinMode, 49> modes_{};
  std::array<int, 49> values_{};
  std::array<ServoSpec, kMaxServos> servos_{};
  size_t servo_count_ = 0;
  uint32_t revision_ = 0;
  bool maintenance_ = false;
  bool storage_fault_ = false;
  std::string session_;
  uint32_t last_seen_ms_ = 0;
  std::array<int, 3> led_{};
  bool led_driver_ok_ = false;
  DisplaySpec display_;
  bool display_active_ = false;
  bool display_driver_ok_ = true;
  int display_brightness_ = 100;
  PageSettings page_settings_;
  PageProject page_project_;
  bool standalone_active_ = false;
  std::string shown_page_;
  std::map<std::string, std::string> page_text_overrides_;
  std::string page_error_;
  std::string upload_id_, upload_data_, aborted_upload_id_;
  size_t upload_expected_ = 0;
  uint32_t upload_crc_ = 0, upload_sequence_ = 0;
  AudioSpec audio_;
  bool audio_active_ = false, audio_driver_ok_ = true;
  bool audio_cleanup_fault_ = false;
  bool audio_recording_ = false, audio_playing_ = false;
  uint32_t audio_read_bytes_ = 0, audio_written_bytes_ = 0;

  void dispatch(JsonObjectConst request, JsonDocument& response, uint32_t now_ms);
  bool stopOutputs();
  ServoSpec* findServo(const std::string& name);
  const ServoSpec* servoForPin(int pin) const;
  bool parseConfig(JsonObjectConst config, std::array<ServoSpec, kMaxServos>& out,
                   size_t& count, DisplaySpec& display, std::string& error) const;
  void writeConfig(JsonObject target) const;
  std::string stateBlob(bool maintenance, uint32_t revision,
                        const std::array<ServoSpec, kMaxServos>& servos, size_t count,
                        const DisplaySpec& display, const PageSettings* pages = nullptr) const;
  void dispatchDisplay(const std::string& op, JsonObjectConst args, JsonDocument& response);
  void dispatchPages(const std::string& op, JsonObjectConst args, JsonDocument& response);
  void writePagesInfo(JsonObject target) const;
  bool loadPagesState(JsonObjectConst state, int version);
  bool pageFitsDisplay(const PageProject& project, const DisplaySpec& spec) const;
  bool showPage(const std::string& id, bool standalone);
  bool resumeDefaultPage();
  void clearPageUpload();
  void dispatchAudio(const std::string& op, JsonObjectConst args, JsonDocument& response);
  void writeAudioInfo(JsonObject target) const;
  bool audioPin(int pin) const;
  bool releaseAudioDevice(bool clear_config);
  void clearAudioSession();
};

}  // namespace ai_maker
