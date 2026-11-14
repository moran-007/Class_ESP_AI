#include "device_core.h"
#include "fake_hardware.h"

#include <chrono>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>

namespace {

// Optional argv[1] is a test-owned state file, never a real device configuration.
// No serial ports, network or physical hardware are touched by this executable.
class FileHardware final : public FakeHardware {
 public:
  explicit FileHardware(std::string path) : path_(std::move(path)) {}

  std::string loadState() override {
    if (path_.empty()) return state;
    std::ifstream file(path_, std::ios::binary);
    if (!file) return "";
    state.assign(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
    return state;
  }

  bool saveState(const std::string& value) override {
    if (path_.empty()) return FakeHardware::saveState(value);
    // Simulator persistence does not prove ESP32 NVS power-loss behavior.
    std::ofstream file(path_, std::ios::binary | std::ios::trunc);
    if (!file || !(file << value)) return false;
    file.close();
    if (!file) return false;
    return FakeHardware::saveState(value);
  }
  std::string loadPageSlot(int slot) override {
    if (path_.empty()) return FakeHardware::loadPageSlot(slot);
    std::ifstream file(path_ + ".page" + std::to_string(slot), std::ios::binary);
    if (!file) return "";
    return std::string(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
  }
  bool savePageSlot(int slot, const std::string& value) override {
    if (path_.empty()) return FakeHardware::savePageSlot(slot, value);
    std::ofstream file(path_ + ".page" + std::to_string(slot), std::ios::binary | std::ios::trunc);
    if (!file || !(file << value)) return false;
    file.close(); return static_cast<bool>(file);
  }
  bool erasePageSlot(int slot) override {
    if (path_.empty()) return FakeHardware::erasePageSlot(slot);
    const auto name = path_ + ".page" + std::to_string(slot);
    std::ifstream existing(name, std::ios::binary);
    if (!existing) return true;
    existing.close(); return std::remove(name.c_str()) == 0;
  }

 private:
  std::string path_;
};

}  // namespace

int main(int argc, char** argv) {
  if (argc > 2) {
    std::cerr << "usage: ai_maker_native [test-state-file]\n";
    return 2;
  }
  FileHardware hardware(argc == 2 ? argv[1] : "");
  ai_maker::DeviceCore core(hardware);
  core.begin();
  const auto started = std::chrono::steady_clock::now();
  std::string line;
  while (std::getline(std::cin, line)) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - started).count();
    std::cout << core.process(line, static_cast<uint32_t>(elapsed)) << '\n' << std::flush;
  }
  return 0;
}
