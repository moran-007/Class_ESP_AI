#include <Arduino.h>
#include <driver/gpio.h>

#ifndef AI_MAKER_RGB_PIN
#define AI_MAKER_RGB_PIN 48
#endif

namespace {
int selected_pin = AI_MAKER_RGB_PIN;
enum class Mode { High, Rgb, Off };
Mode mode = Mode::Off;
bool driver_ok = false;
const char* driver_error = "none";
bool cleanup_ok = true;
const char* cleanup_error = "none";
bool rmt_owned = false;
bool rmt_fault = false;
String command;
uint32_t next_report = 0;

bool writePixel(uint8_t value) {
  if (rmt_fault) { driver_error = "rmt_fault_restart_required"; return false; }
  if (rmt_owned) {
    if (!rmtDeinit(selected_pin)) { driver_error = "rmt_release_failed"; return false; }
    rmt_owned = false;
  }
  gpio_config_t reset{};
  reset.pin_bit_mask = 1ULL << selected_pin;
  reset.mode = GPIO_MODE_OUTPUT;
  if (gpio_config(&reset) != ESP_OK || gpio_set_level(static_cast<gpio_num_t>(selected_pin), 0) != ESP_OK) {
    driver_error = "pixel_reset_gpio_failed";
    return false;
  }
  delay(1);  // Known LOW reset before a frame, including HIGH-to-RGB transitions.
  // Same 10MHz / 0.4us / 0.8us timing as Arduino's rgbLedWrite, but retain errors.
  if (!rmtInit(selected_pin, RMT_TX_MODE, RMT_MEM_NUM_BLOCKS_1, 10000000)) {
    driver_error = "rmt_init_failed";
    return false;
  }
  rmt_owned = true;
  // A timed-out RMT transaction may still own the buffer: keep it alive and
  // prohibit reuse after a fault until reset, even if abort itself fails.
  static rmt_data_t symbols[24]{};
  for (int index = 0; index < 24; ++index) {
    const bool one = (value & (1 << (7 - index % 8))) != 0;
    symbols[index].level0 = 1;
    symbols[index].duration0 = one ? 8 : 4;
    symbols[index].level1 = 0;
    symbols[index].duration1 = one ? 4 : 8;
  }
  if (!rmtWrite(selected_pin, symbols, 24, 1000)) {
    driver_error = "rmt_write_failed";
    rmt_fault = true;
    if (rmtDeinit(selected_pin)) rmt_owned = false;
    return false;
  }
  delay(1);  // Pixel reset/latch interval after the complete data frame.
  return true;
}

bool releasePrevious() {
  cleanup_ok = true;
  cleanup_error = "none";
  if (mode == Mode::Rgb) {
    if (!writePixel(0)) { cleanup_ok = false; cleanup_error = driver_error; }
    delay(2);
  }
  if (rmt_owned) {
    if (!rmtDeinit(selected_pin)) { cleanup_ok = false; cleanup_error = "rmt_release_failed"; }
    else rmt_owned = false;
  }
  if (gpio_reset_pin(static_cast<gpio_num_t>(selected_pin)) != ESP_OK) {
    cleanup_ok = false;
    cleanup_error = "gpio_release_failed";
  }
  return cleanup_ok;
}

void applyMode(int pin, Mode next) {
  if (pin != 38 && pin != 48) return;
  if (!releasePrevious()) {
    mode = Mode::Off;
    driver_ok = false;
    driver_error = "previous_release_failed";
    return;
  }
  selected_pin = pin;
  mode = next;
  driver_error = "none";
  if (mode == Mode::Rgb) {
    driver_ok = writePixel(24);  // All GRB channels identical: fixed white.
  } else {
    gpio_config_t config{};
    config.pin_bit_mask = 1ULL << selected_pin;
    config.mode = GPIO_MODE_INPUT_OUTPUT;
    config.pull_up_en = GPIO_PULLUP_DISABLE;
    config.pull_down_en = GPIO_PULLDOWN_DISABLE;
    config.intr_type = GPIO_INTR_DISABLE;
    driver_ok = gpio_config(&config) == ESP_OK;
    if (driver_ok) driver_ok = gpio_set_level(static_cast<gpio_num_t>(selected_pin), mode == Mode::High ? 1 : 0) == ESP_OK;
    if (!driver_ok) driver_error = "gpio_config_or_level_failed";
  }
}

void report() {
  const char* name = mode == Mode::High ? "gpio_high" : mode == Mode::Rgb ? "rgb_solid" : "off";
  Serial.printf("{\"firmware_family\":\"ai-maker-led-diagnostic\",\"mode\":\"%s\",\"pin\":%d,\"commanded_level\":%d,\"read_level\":%d,\"driver_ok\":%s,\"driver_error\":\"%s\",\"cleanup_ok\":%s,\"previous_release_error\":\"%s\",\"physical_verified\":false}\n",
      name, selected_pin, mode == Mode::High ? 1 : 0,
      gpio_get_level(static_cast<gpio_num_t>(selected_pin)), driver_ok ? "true" : "false", driver_error,
      cleanup_ok ? "true" : "false", cleanup_error);
}
}

void setup() {
  Serial.begin(115200);
  command.reserve(32);
  applyMode(selected_pin, Mode::Rgb);  // Confirmed board: fixed white immediately at boot.
  report();
}

void loop() {
  size_t budget = 64;
  while (budget-- && Serial.available()) {
    const char next = static_cast<char>(Serial.read());
    if (next == '\n') {
      command.trim();
      if (command == "HIGH 38") applyMode(38, Mode::High);
      else if (command == "HIGH 48") applyMode(48, Mode::High);
      else if (command == "RGB 38") applyMode(38, Mode::Rgb);
      else if (command == "RGB 48") applyMode(48, Mode::Rgb);
      else if (command == "OFF") applyMode(selected_pin, Mode::Off);
      command = "";
      report();
    } else if (command.length() < 31) command += next;
    else command = "INVALID";
  }
  if (static_cast<int32_t>(millis() - next_report) >= 0) {
    next_report = millis() + 1000;
    report();
  }
  delay(1);
}
