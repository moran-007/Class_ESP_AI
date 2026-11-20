#include "device_core.h"
#include "fake_hardware.h"
#include <iostream>
#include <stdexcept>

namespace {
void check(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}

class WifiHardware : public FakeHardware {
 public:
  std::string stored, ssid, ip;
  size_t writes = 0;
  bool writable = true, start_ok = true, stop_ok = true;
  bool wifiAvailable() const override { return true; }
  bool loadWifi(std::string& value) override { value = stored; return true; }
  bool saveWifi(const std::string& value) override {
    if (!writable) return false;
    stored = value;
    ++writes;
    return true;
  }
  bool stopWifi() override { ssid.clear(); ip.clear(); return stop_ok; }
  bool startWifi(const std::string& name, const std::string&) override {
    ssid = name; ip.clear(); return start_ok;
  }
  std::string wifiIp(const std::string& name) override { return ssid == name ? ip : ""; }
};

JsonDocument request(ai_maker::DeviceCore& device, uint32_t now, const char* op,
                     const char* args = "{}", const char* session = "test") {
  const std::string input = std::string(R"({"kind":"request","protocol_version":1,"request_id":"wifi-test","session_id":")") +
      session + R"(","op":")" + op + R"(","args":)" + args + "}";
  const auto output = device.process(input, now);
  check(output.find("test-secret") == std::string::npos, "password must not appear in any reply");
  JsonDocument response;
  check(!deserializeJson(response, output), "valid response JSON");
  return response;
}
}

int main() {
  WifiHardware hardware;
  ai_maker::DeviceCore device(hardware);
  device.begin();
  auto response = request(device, 0, "device.info");
  check(response["data"]["capabilities"]["wifi_provisioning"] == true, "capability advertised");
  response = request(device, 0, "wifi.status", "{}", "");
  check(response["data"]["state"] == "unconfigured", "read-only without session");
  const char* chinese = R"({"ssid":"\u6559\u5ba4\u4e00","password":"test-secret"})";
  check(request(device, 0, "wifi.connect", chinese)["code"] == "SESSION_REQUIRED", "write requires session");
  check(request(device, 0, "session.open")["ok"] == true, "session opens");
  check(request(device, 1, "wifi.connect", R"({"ssid":"Bad","password":"test-secret\u0000"})")["code"] ==
      "INVALID_ARGUMENT", "embedded nul rejected");
  response = request(device, 2, "wifi.connect", chinese);
  check(response["data"]["provisioning"] == "connecting" && hardware.writes == 0, "no write before IPv4");
  check(hardware.ssid == "\xe6\x95\x99\xe5\xae\xa4\xe4\xb8\x80", "Chinese SSID reaches driver as UTF-8");
  check(request(device, 3, "wifi.connect", chinese)["code"] == "DEVICE_BUSY", "no overlapping attempts");
  check(request(device, 4, "session.close")["ok"] == true, "connection work does not hold USB session");
  hardware.ip = "192.0.2.4";
  response = request(device, 104, "wifi.status", "{}", "");
  check(response["data"]["provisioning"] == "saved" && response["data"]["ip"] == "192.0.2.4", "save after DHCP even after USB close");
  const auto original = hardware.stored;
  check(hardware.writes == 1, "saved exactly once");

  ai_maker::DeviceCore rebooted(hardware);
  rebooted.begin();
  check(request(rebooted, 0, "wifi.status")["data"]["state"] == "connecting", "auto starts on boot");
  hardware.ip = "192.0.2.5";
  check(request(rebooted, 1, "wifi.status")["data"]["ip"] == "192.0.2.5" && hardware.writes == 1, "reconnect does not rewrite profile");
  request(rebooted, 2, "session.open");
  const char* unavailable = R"({"ssid":"Missing","password":"test-secret"})";
  request(rebooted, 3, "wifi.connect", unavailable);
  response = request(rebooted, 20003, "wifi.status");
  check(response["data"]["provisioning"] == "failed" && response["data"]["error"] == "connect_timeout", "timeout signaled");
  check(hardware.stored == original && hardware.writes == 1, "failed trial preserves existing profile");
  request(rebooted, 30003, "wifi.status");
  hardware.ip = "192.0.2.6";
  response = request(rebooted, 30004, "wifi.status");
  check(response["data"]["ip"] == "192.0.2.6" && response["data"]["provisioning"] == "failed", "restore link without masking failure");

  request(rebooted, 30005, "session.open");
  request(rebooted, 30006, "wifi.connect", unavailable);
  hardware.ip = "192.0.2.7";
  hardware.writable = false;
  response = request(rebooted, 30007, "wifi.status");
  check(response["data"]["error"] == "storage_error" && hardware.stored == original, "storage failure retains old profile");
  check(request(rebooted, 30008, "wifi.clear")["code"] == "STORAGE_ERROR", "clear storage failure reported");
  hardware.writable = true;
  response = request(rebooted, 30009, "wifi.clear");
  check(response["data"]["state"] == "unconfigured" && hardware.stored.empty(), "clear stored credentials and link");
  request(rebooted, 60000, "wifi.status");
  check(hardware.ssid.empty(), "clear cancels automatic reconnect");
  std::cout << "Wi-Fi: UTF-8, lease, DHCP save, timeout rollback, boot, storage fault and clear passed\n";
}
