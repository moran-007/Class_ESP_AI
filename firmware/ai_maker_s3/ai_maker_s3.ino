#include <Arduino.h>
#include "device_core.h"
#include "esp_hardware.h"

namespace {
ai_maker::EspHardware hardware;
ai_maker::DeviceCore device(hardware);
std::string incoming;
bool discard_line = false;
}

void setup() {
  // Both UART and native HWCDC must accept a complete 4096-byte JSONL frame.
  // HWCDC otherwise defaults to 256 bytes and drops longer bursts in its ISR.
  Serial.setRxBufferSize(8192);
  Serial.begin(115200);
  incoming.reserve(ai_maker::kMaxLine + 1);
  hardware.begin();
  device.begin();
}

void loop() {
  device.tick(millis());
  // Bound RX work so continuous malformed input cannot starve lease expiry.
  size_t budget = 256;
  while (budget-- && Serial.available()) {
    const char next = static_cast<char>(Serial.read());
    if (next == '\n') {
      if (!incoming.empty() && incoming.back() == '\r') incoming.pop_back();
      if (discard_line) {
        const auto response = device.process(std::string(ai_maker::kMaxLine + 1, 'x'), millis());
        Serial.println(response.c_str());
      } else if (!incoming.empty()) {
        const auto response = device.process(incoming, millis());
        Serial.println(response.c_str());
      }
      incoming.clear();
      discard_line = false;
    } else if (!discard_line) {
      if (incoming.size() >= ai_maker::kMaxLine + 1) {
        incoming.clear();
        discard_line = true;
      } else incoming.push_back(next);
    }
  }
  delay(1);
}
