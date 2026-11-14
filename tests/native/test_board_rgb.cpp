// Executes the production RMT driver with fault-injectable peripheral calls.
// This validates frames/lifetimes, not a real LED's optical output or waveform.
#include "board_rgb.h"
#include <driver/gpio.h>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
std::vector<rmt_data_t> frame;
std::vector<char> events;
bool init_ok = true, write_ok = true, deinit_ok = true, gpio_ok = true;
unsigned writes = 0;
void require(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
void reset() { frame.clear(); events.clear(); init_ok = write_ok = deinit_ok = gpio_ok = true; writes = 0; }
unsigned byte(size_t start) {
  unsigned value = 0;
  for (size_t bit = start; bit < start + 8; ++bit) {
    const auto& s = frame.at(bit);
    require(s.level0 == 1 && s.level1 == 0 && s.duration0 + s.duration1 == 12, "invalid pixel pulse");
    require(s.duration0 == 4 || s.duration0 == 8, "invalid bit timing");
    value = value * 2 + (s.duration0 == 8);
  }
  return value;
}
}
bool rmtInit(int pin, rmt_ch_dir_t dir, rmt_reserve_memsize_t, uint32_t hz) {
  require(pin == 48 && dir == RMT_TX_MODE && hz == 10000000, "wrong RMT configuration");
  events.push_back('I'); return init_ok;
}
bool rmtDeinit(int) { events.push_back('D'); return deinit_ok; }
bool rmtWrite(int, rmt_data_t* data, size_t count, uint32_t timeout) {
  require(count == 24 && timeout == 1000, "wrong RGB frame length or timeout");
  ++writes; events.push_back('W'); frame.assign(data, data + count); return write_ok;
}
void delay(uint32_t ms) { require(ms >= 1, "missing LOW latch interval"); events.push_back('L'); }
int gpio_config(const gpio_config_t* cfg) {
  require(cfg->pin_bit_mask == (1ULL << 48) && cfg->mode == GPIO_MODE_OUTPUT, "wrong reset pin");
  events.push_back('G'); return gpio_ok ? ESP_OK : -1;
}
int gpio_set_level(gpio_num_t pin, int level) { require(pin == 48 && level == 0, "reset must be LOW"); return ESP_OK; }

int main() {
  try {
    reset(); ai_maker::BoardRgb rgb(48);
    require(rgb.write(2, 5, 16), "frame failed");
    require(byte(0) == 5 && byte(8) == 2 && byte(16) == 16, "pixel must receive GRB, MSB first");
    require(events == std::vector<char>{'G','L','I','W','L'}, "reset/write/latch ordering");
    events.clear(); require(rgb.write(0, 0, 0), "off frame failed");
    require(events.front() == 'D' && byte(0) == 0 && byte(8) == 0 && byte(16) == 0, "old RMT owner must be released before off");
    deinit_ok = false; const auto previous = writes;
    require(!rgb.write(1, 1, 1) && writes == previous, "cleanup failure must not overwrite a live transfer");

    reset(); ai_maker::BoardRgb faulted(48); write_ok = false; deinit_ok = false;
    require(!faulted.write(3, 4, 5), "timeout must fail");
    write_ok = deinit_ok = true;
    require(!faulted.write(0, 0, 0) && writes == 1, "timed-out buffer must never be reused before reset");

    reset(); ai_maker::BoardRgb recoverable(48); init_ok = false;
    require(!recoverable.write(1, 0, 0) && writes == 0, "init failure must not claim a frame");
    init_ok = true; require(recoverable.write(1, 0, 0), "init failure without transfer can recover");
    reset(); ai_maker::BoardRgb bad_gpio(48); gpio_ok = false;
    require(!bad_gpio.write(1, 0, 0) && writes == 0, "reset GPIO failure must abort frame");
    std::cout << "PASS RGB GRB frame, reset ordering, off, cleanup, timeout and init faults\n";
    return 0;
  } catch (const std::exception& e) { std::cerr << "FAIL RGB driver: " << e.what() << '\n'; return 1; }
}
