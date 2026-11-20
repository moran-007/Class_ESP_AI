#include "esp_hardware.h"
#include <WiFi.h>
#include <esp_wifi.h>
#include <cstring>

namespace ai_maker {
bool EspHardware::loadWifi(std::string& profile) {
  if (!storage_ready_) return false;
  if (!preferences_.isKey("wifi")) return true;
  profile = preferences_.getString("wifi", "").c_str();
  return !profile.empty() && profile.size() <= 256;
}

bool EspHardware::saveWifi(const std::string& profile) {
  if (!storage_ready_) return false;
  if (profile.empty()) return !preferences_.isKey("wifi") || preferences_.remove("wifi");
  return profile.size() <= 256 && preferences_.putString("wifi", profile.c_str()) == profile.size();
}

bool EspHardware::stopWifi() {
  return WiFi.getMode() == WIFI_MODE_NULL || WiFi.mode(WIFI_MODE_NULL);
}

bool EspHardware::startWifi(const std::string& ssid, const std::string& password) {
  if (!stopWifi()) return false;
  WiFi.persistent(false);
  WiFi.setAutoReconnect(false);
  return WiFi.STA.begin(false) && WiFi.STA.connect(ssid.c_str(), password.c_str());
}

std::string EspHardware::wifiIp(const std::string& ssid) {
  if (!WiFi.STA.hasIP()) return "";
  wifi_ap_record_t ap{};
  if (esp_wifi_sta_get_ap_info(&ap) != ESP_OK ||
      ssid.size() != strnlen(reinterpret_cast<const char*>(ap.ssid), sizeof(ap.ssid)) ||
      std::memcmp(ap.ssid, ssid.data(), ssid.size()) != 0) return "";
  const auto ip = WiFi.localIP();
  return ip == IPAddress(0, 0, 0, 0) ? "" : ip.toString().c_str();
}
}
