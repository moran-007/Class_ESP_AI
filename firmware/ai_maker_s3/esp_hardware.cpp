#include "esp_hardware.h"
#include <esp_system.h>
#include <soc/soc_caps.h>
#include <driver/gpio.h>
#include <esp_adc/adc_oneshot.h>

#if !CONFIG_IDF_TARGET_ESP32S3
#error "This hardware adapter targets ESP32-S3 only"
#endif

static_assert(SOC_LEDC_CHANNEL_NUM >= 8, "Eight LEDC channels are required");

namespace ai_maker {
void EspHardware::begin() {
  char boot[24];
  snprintf(boot, sizeof(boot), "%08lx-%08lx", static_cast<unsigned long>(esp_random()),
           static_cast<unsigned long>(esp_random()));
  boot_id_ = boot;
  storage_ready_ = preferences_.begin("ai-maker-v1", false);
  analogReadResolution(12);
}

std::string EspHardware::loadState() {
  if (!storage_ready_) return "storage unavailable";  // Core enters maintenance.
  return preferences_.getString("state", "").c_str();
}

bool EspHardware::saveState(const std::string& state) {
  if (!storage_ready_ || state.empty() || state.size() > kMaxStateBytes) return false;
  // One NVS value contains mapping, revision and maintenance state together.
  return preferences_.putString("state", state.c_str()) == state.size();
}

std::string EspHardware::loadProgramState() {
  if (!storage_ready_) return "storage unavailable";
  return preferences_.getString("program", "").c_str();
}

bool EspHardware::saveProgramState(const std::string& state) {
  if (!storage_ready_ || state.empty() || state.size() > 3584) return false;
  // A single independent NVS value contains the program and its boot policy.
  // Never erase the namespace, existing mappings or saved screen pages.
  return preferences_.putString("program", state.c_str()) == state.size();
}

std::string EspHardware::loadPageSlot(int slot) {
  if (!storage_ready_ || slot < 0 || slot > 1) return "";
  const char* key = slot == 0 ? "page0" : "page1";
  const size_t length = preferences_.getBytesLength(key);
  if (!length || length > kMaxPageProjectBytes) return "";
  std::string result(length, '\0');
  return preferences_.getBytes(key, &result[0], length) == length ? result : "";
}

bool EspHardware::savePageSlot(int slot, const std::string& data) {
  if (!storage_ready_ || slot < 0 || slot > 1 || data.empty() || data.size() > kMaxPageProjectBytes) return false;
  // NVS strings are limited to 4000 bytes; page packages use bounded blobs.
  return preferences_.putBytes(slot == 0 ? "page0" : "page1", data.data(), data.size()) == data.size();
}

bool EspHardware::erasePageSlot(int slot) {
  if (!storage_ready_ || slot < 0 || slot > 1) return false;
  const char* key = slot == 0 ? "page0" : "page1";
  return !preferences_.isKey(key) || preferences_.remove(key);
}

bool EspHardware::attach(int pin, bool servo) {
  const int first = servo ? 4 : 0;
  const int end = servo ? 8 : 4;
  for (int channel = first; channel < end; ++channel) if (channels_[channel] == pin) return true;
  for (int channel = first; channel < end; ++channel) {
    if (channels_[channel] != -1) continue;
    if (!ledcAttachChannel(pin, servo ? 50 : 1000, 14, channel)) return false;
    channels_[channel] = pin;
    if (!ledcWrite(pin, 0)) { releasePin(pin); return false; }
    return true;
  }
  return false;
}

void EspHardware::releasePin(int pin) {
  for (auto& assigned : channels_) {
    if (assigned != pin) continue;
    ledcWrite(pin, 0);
    ledcDetach(pin);
    assigned = -1;
  }
  pinMode(pin, INPUT);  // Release signal; external servo power stays connected.
}

bool EspHardware::configurePin(int pin, PinMode mode) {
  switch (mode) {
    case PinMode::Input: pinMode(pin, INPUT); return true;
    case PinMode::InputPullup: pinMode(pin, INPUT_PULLUP); return true;
    case PinMode::InputPulldown: pinMode(pin, INPUT_PULLDOWN); return true;
    case PinMode::Output:
      if (gpio_set_level(static_cast<gpio_num_t>(pin), 0) != ESP_OK) return false;
      pinMode(pin, OUTPUT);
      return true;
    case PinMode::Pwm: return attach(pin, false);
    default: return false;
  }
}

bool EspHardware::writeDigital(int pin, int value) { digitalWrite(pin, value); return true; }
int EspHardware::readDigital(int pin) { return digitalRead(pin); }
int EspHardware::readAdc(int pin) {
  adc_unit_t unit;
  adc_channel_t channel;
  if (adc_oneshot_io_to_channel(pin, &unit, &channel) != ESP_OK) return -1;
  adc_oneshot_unit_handle_t handle = nullptr;
  adc_oneshot_unit_init_cfg_t unit_config{};
  unit_config.unit_id = unit;
  if (adc_oneshot_new_unit(&unit_config, &handle) != ESP_OK) return -1;
  adc_oneshot_chan_cfg_t channel_config{};
  channel_config.atten = ADC_ATTEN_DB_12;
  channel_config.bitwidth = ADC_BITWIDTH_12;
  int raw = -1;
  const bool configured = adc_oneshot_config_channel(handle, channel, &channel_config) == ESP_OK;
  const bool read = configured && adc_oneshot_read(handle, channel, &raw) == ESP_OK;
  const bool released = adc_oneshot_del_unit(handle) == ESP_OK;
  // ADC can disable the digital input path. Restore the Core's plain-input mode.
  pinMode(pin, INPUT);
  return read && released ? raw : -1;
}
bool EspHardware::writePwm(int pin, int duty) {
  return ledcWrite(pin, static_cast<uint32_t>(duty) * 16383U / 100U);
}
bool EspHardware::writeServo(int pin, int pulse_us) {
  if (!attach(pin, true)) return false;
  const uint32_t duty = (static_cast<uint32_t>(pulse_us) * 16383U + 10000U) / 20000U;
  return ledcWrite(pin, duty);
}
bool EspHardware::writeLed(int red, int green, int blue) {
  return rgb_.write(red, green, blue);  // Driver result, never optical feedback.
}
}  // namespace ai_maker
