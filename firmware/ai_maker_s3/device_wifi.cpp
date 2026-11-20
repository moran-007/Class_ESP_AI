#include "device_core.h"
#include <cstring>

namespace ai_maker {
namespace {
constexpr uint32_t kWifiTimeout = 20000;
constexpr uint32_t kWifiRetryDelay = 10000;
constexpr uint32_t kWifiSampleInterval = 100;

bool credentials(JsonObjectConst args, std::string& ssid, std::string& password) {
  if (args.size() != 2 || !args["ssid"].is<const char*>() || !args["password"].is<const char*>()) return false;
  const auto name = args["ssid"].as<JsonString>();
  const auto pass = args["password"].as<JsonString>();
  if (!name.size() || name.size() > 32 || std::strlen(name.c_str()) != name.size() ||
      pass.size() > 63 || (pass.size() && pass.size() < 8) || std::strlen(pass.c_str()) != pass.size()) return false;
  const std::string next_name(name.c_str(), name.size());
  if (!validPageText(next_name)) return false;
  for (unsigned char character : next_name) if (character < 32 || character == 127) return false;
  const std::string next_pass(pass.c_str(), pass.size());
  for (unsigned char character : next_pass) if (character < 32 || character > 126) return false;
  ssid = next_name;
  password = next_pass;
  return true;
}

void reject(JsonDocument& response, const char* code, const char* message) {
  response["ok"] = false;
  response["code"] = code;
  response["message"] = message;
  response.remove("data");
}
}

void DeviceCore::loadWifi() {
  std::string stored;
  if (!hardware_.loadWifi(stored)) {
    wifi_error_ = "storage_error";
    wifi_state_ = "error";
    return;
  }
  if (stored.empty()) return;
  JsonDocument document;
  if (deserializeJson(document, stored) ||
      !credentials(document.as<JsonObjectConst>(), wifi_saved_.ssid, wifi_saved_.password)) {
    wifi_error_ = "storage_error";
    wifi_state_ = "error";
    return;
  }
  wifi_retry_ = true;
  wifi_since_ = 0U - kWifiRetryDelay;
  wifi_state_ = "connecting";
}

void DeviceCore::startWifi(const WifiProfile& profile, uint32_t now_ms) {
  wifi_ip_.clear();
  wifi_since_ = now_ms;
  wifi_last_sample_ = now_ms - kWifiSampleInterval;
  wifi_retry_ = false;
  wifi_state_ = "connecting";
  wifi_connecting_ = hardware_.startWifi(profile.ssid, profile.password);
  if (!wifi_connecting_) failWifi("start_failed", now_ms);
}

void DeviceCore::failWifi(const char* error, uint32_t now_ms) {
  if (!wifi_candidate_.ssid.empty()) {
    wifi_candidate_ = {};
    wifi_provisioning_ = "failed";
    wifi_error_ = error;
  } else if (std::strcmp(wifi_provisioning_, "failed") != 0) wifi_error_ = error;
  const bool stopped = hardware_.stopWifi();
  wifi_ip_.clear();
  wifi_connecting_ = false;
  wifi_state_ = stopped ? "disconnected" : "error";
  wifi_since_ = now_ms;
  wifi_retry_ = !wifi_saved_.ssid.empty();
}

void DeviceCore::tickWifi(uint32_t now_ms) {
  if (wifi_retry_ && now_ms - wifi_since_ >= kWifiRetryDelay) {
    startWifi(wifi_saved_, now_ms);
    return;
  }
  if (!wifi_connecting_ && wifi_ip_.empty()) return;
  if (now_ms - wifi_last_sample_ < kWifiSampleInterval) return;
  wifi_last_sample_ = now_ms;
  const bool testing = !wifi_candidate_.ssid.empty();
  const auto& profile = testing ? wifi_candidate_ : wifi_saved_;
  const auto ip = hardware_.wifiIp(profile.ssid);
  if (ip.empty()) {
    if (wifi_connecting_) {
      if (now_ms - wifi_since_ >= kWifiTimeout) failWifi("connect_timeout", now_ms);
    } else failWifi("link_lost", now_ms);
    return;
  }
  if (testing) {
    if (wifi_saved_.ssid != profile.ssid || wifi_saved_.password != profile.password) {
      JsonDocument record;
      record["ssid"] = profile.ssid;
      record["password"] = profile.password;
      std::string stored;
      serializeJson(record, stored);
      if (!hardware_.saveWifi(stored)) return failWifi("storage_error", now_ms);
      wifi_saved_ = wifi_candidate_;
    }
    wifi_candidate_ = {};
    wifi_provisioning_ = "saved";
  }
  wifi_ip_ = ip;
  wifi_state_ = "connected";
  wifi_connecting_ = false;
  if (std::strcmp(wifi_provisioning_, "failed") != 0) wifi_error_ = "";
}

void DeviceCore::dispatchWifi(const std::string& op, JsonObjectConst args,
                              JsonDocument& response, uint32_t now_ms) {
  if (!hardware_.wifiAvailable()) return reject(response, "UNSUPPORTED_CAPABILITY", "Wi-Fi provisioning unavailable");
  if (op == "wifi.connect") {
    if (!wifi_candidate_.ssid.empty()) return reject(response, "DEVICE_BUSY", "A Wi-Fi test is already running");
    if (!credentials(args, wifi_candidate_.ssid, wifi_candidate_.password))
      return reject(response, "INVALID_ARGUMENT", "Expected UTF-8 SSID (1-32 bytes) and password (empty or 8-63 printable ASCII bytes)");
    wifi_provisioning_ = "connecting";
    wifi_error_ = "";
    startWifi(wifi_candidate_, now_ms);
  } else {
    if (args.size()) return reject(response, "INVALID_ARGUMENT", "This Wi-Fi operation takes no arguments");
    if (op == "wifi.clear") {
      if (!hardware_.saveWifi("")) return reject(response, "STORAGE_ERROR", "Wi-Fi profile could not be cleared");
      wifi_saved_ = {};
      wifi_candidate_ = {};
      wifi_connecting_ = wifi_retry_ = false;
      wifi_ip_.clear();
      wifi_provisioning_ = "idle";
      const bool stopped = hardware_.stopWifi();
      wifi_state_ = stopped ? "unconfigured" : "error";
      wifi_error_ = stopped ? "" : "stop_failed";
    }
  }
  auto data = response["data"].as<JsonObject>();
  data["state"] = wifi_state_;
  data["provisioning"] = wifi_provisioning_;
  data["ssid"] = wifi_candidate_.ssid.empty() ? wifi_saved_.ssid : wifi_candidate_.ssid;
  data["ip"] = wifi_ip_;
  data["saved"] = !wifi_saved_.ssid.empty();
  data["error"] = wifi_error_;
}
}
