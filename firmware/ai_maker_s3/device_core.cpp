#include "device_core.h"
#include <cstring>
#include <initializer_list>
#include <limits>
#include <vector>

namespace ai_maker {
namespace {
void fail(JsonDocument& reply, const char* code, const char* message) {
  reply["ok"] = false; reply["code"] = code; reply["message"] = message; reply.remove("data");
}
bool integer(JsonVariantConst value) { return value.is<int>() && !value.is<bool>(); }
bool text(JsonVariantConst value, size_t maximum) {
  if (!value.is<const char*>()) return false;
  const auto string = value.as<JsonString>();
  return string.size() > 0 && string.size() <= maximum && std::strlen(string.c_str()) == string.size();
}
bool onlyKeys(JsonObjectConst object, std::initializer_list<const char*> keys) {
  for (JsonPairConst pair : object) {
    bool found = false;
    for (const auto* key : keys) if (pair.key() == key) found = true;
    if (!found) return false;
  }
  return true;
}
bool validName(const std::string& name) {
  const auto letter = [](char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); };
  if (name.empty() || name.size() > 24 || !letter(name[0])) return false;
  for (char c : name) if (!letter(c) && !(c >= '0' && c <= '9') && c != '_') return false;
  return true;
}
bool space(char c) { return c == ' ' || c == '\t' || c == '\n' || c == '\r'; }
// Reject trailing objects/bytes: a JSONL frame must contain exactly one object.
bool singleObject(const std::string& line) {
  size_t start = 0;
  while (start < line.size() && space(line[start])) ++start;
  if (start == line.size() || line[start] != '{') return false;
  int depth = 0; bool quoted = false; bool escaped = false;
  for (size_t i = start; i < line.size(); ++i) {
    const char c = line[i];
    if (quoted) {
      if (escaped) escaped = false;
      else if (c == '\\') escaped = true;
      else if (c == '"') quoted = false;
    } else if (c == '"') quoted = true;
    else if (c == '{' || c == '[') ++depth;
    else if (c == '}' || c == ']') {
      if (--depth == 0) {
        for (++i; i < line.size(); ++i) if (!space(line[i])) return false;
        return true;
      }
      if (depth < 0) return false;
    }
  }
  return false;
}
const char* modeName(PinMode mode) {
  switch (mode) {
    case PinMode::Input: return "input";
    case PinMode::InputPullup: return "input_pullup";
    case PinMode::InputPulldown: return "input_pulldown";
    case PinMode::Output: return "output";
    case PinMode::Pwm: return "pwm";
    default: return "unset";
  }
}
std::array<int, 6> displayPins(const DisplaySpec& d) { return {{d.sck, d.mosi, d.cs, d.dc, d.rst, d.backlight}}; }
bool displayPin(const DisplaySpec& d, int pin) {
  if (!d.enabled || pin < 0) return false;
  for (int assigned : displayPins(d)) if (assigned == pin) return true;
  return false;
}
bool panelSize(const std::string& panel, int& width, int& height) {
  if (panel == "st7789_240x320") { width = 240; height = 320; }
  else if (panel == "st7789_240x240") { width = height = 240; }
  else if (panel == "st7735s_128x160") { width = 128; height = 160; }
  else return false;
  return true;
}
void displaySize(const DisplaySpec& d, int& width, int& height) {
  width = height = 0;
  if (!d.enabled || !panelSize(d.panel, width, height)) return;
  if (d.rotation % 2) { const int tmp = width; width = height; height = tmp; }
}
bool validDisplayText(const std::string& value) {
  if (value.empty() || value.size() > 192) return false;
  for (size_t i = 0; i < value.size();) {
    const auto lead = static_cast<uint8_t>(value[i++]);
    uint32_t cp = lead; int extra = 0;
    if (lead >= 0xc2 && lead <= 0xdf) { cp = lead & 0x1f; extra = 1; }
    else if (lead >= 0xe0 && lead <= 0xef) { cp = lead & 0x0f; extra = 2; }
    else if (lead >= 0xf0 && lead <= 0xf4) { cp = lead & 7; extra = 3; }
    else if (lead >= 0x80) return false;
    if (i + extra > value.size()) return false;
    for (int n = 0; n < extra; ++n) {
      const auto tail = static_cast<uint8_t>(value[i++]);
      if ((tail & 0xc0) != 0x80) return false;
      cp = (cp << 6) | (tail & 0x3f);
    }
    if ((extra == 1 && cp < 0x80) || (extra == 2 && cp < 0x800) || (extra == 3 && cp < 0x10000) ||
        cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff) ||
        (cp < 0x20 && cp != '\n') || (cp >= 0x7f && cp <= 0x9f)) return false;
  }
  return true;
}
void encodeConfig(JsonObject object, const std::array<ServoSpec, kMaxServos>& servos, size_t count,
                  const DisplaySpec& display) {
  object["schema_version"] = 1;
  auto array = object["servos"].to<JsonArray>();
  for (size_t i = 0; i < count; ++i) {
    const auto& s = servos[i]; auto item = array.add<JsonObject>();
    item["name"] = s.name; item["pin"] = s.pin;
    item["min_angle"] = s.min_angle; item["max_angle"] = s.max_angle;
    item["min_pulse_us"] = s.min_pulse_us; item["max_pulse_us"] = s.max_pulse_us;
  }
  if (display.enabled) {
    auto d = object["display"].to<JsonObject>();
    d["panel"] = display.panel; d["sck"] = display.sck; d["mosi"] = display.mosi;
    d["cs"] = display.cs; d["dc"] = display.dc; d["rst"] = display.rst;
    d["backlight"] = display.backlight; d["rotation"] = display.rotation;
    d["invert"] = display.invert; d["brightness"] = display.brightness;
  }
}
}  // namespace

DeviceCore::DeviceCore(Hardware& hardware) : hardware_(hardware) {}
bool DeviceCore::validPin(int pin) { return (pin >= 0 && pin <= 21) || (pin >= 26 && pin <= 48); }
bool DeviceCore::reservedPin(int pin) {
  // Conservative N16R8 board profile; other boards require an explicit review.
  return pin == 0 || pin == 3 || pin == 19 || pin == 20 || (pin >= 26 && pin <= 37) ||
         pin == 43 || pin == 44 || pin == 45 || pin == 46 || pin == kBuiltinRgbPin;
}
bool DeviceCore::adcPin(int pin) { return pin >= 1 && pin <= 20 && !reservedPin(pin); }
void DeviceCore::begin() {
  // WS2812 latches can outlive an MCU reset or a diagnostic app replacement.
  led_driver_ok_ = hardware_.writeLed(0, 0, 0);
  const std::string state = hardware_.loadState();
  if (state.empty()) return;
  JsonDocument doc; std::array<ServoSpec, kMaxServos> next{}; DisplaySpec next_display;
  size_t count = 0; std::string error;
  const bool valid = state.size() <= kMaxLine && singleObject(state) &&
      !deserializeJson(doc, state, DeserializationOption::NestingLimit(8)) &&
      integer(doc["state_version"]) && (doc["state_version"].as<int>() == 1 || doc["state_version"].as<int>() == 2) &&
      doc["revision"].is<uint32_t>() && !doc["revision"].is<bool>() &&
      doc["maintenance"].is<bool>() && doc["config"].is<JsonObjectConst>() &&
      parseConfig(doc["config"].as<JsonObjectConst>(), next, count, next_display, error);
  if (!valid) { maintenance_ = storage_fault_ = true; return; }
  servos_ = next; servo_count_ = count;
  display_ = next_display; display_brightness_ = display_.brightness;
  revision_ = doc["revision"].as<uint32_t>(); maintenance_ = doc["maintenance"].as<bool>();
  if (!loadPagesState(doc.as<JsonObjectConst>(), doc["state_version"].as<int>())) {
    maintenance_ = storage_fault_ = true;
    return;
  }
  if (!maintenance_) resumeDefaultPage();
  // Restoring a mapping never attaches LEDC or moves a servo.
}
bool DeviceCore::stopOutputs() {
  const bool audio_stopped = releaseAudioDevice(false);
  bool display_stopped = true;
  if (display_active_ || !display_driver_ok_) {
    display_stopped = hardware_.releaseDisplay();
    display_driver_ok_ = display_stopped;
    if (display_stopped) display_active_ = false;
  }
  if (display_stopped) {
    standalone_active_ = false; shown_page_.clear(); page_text_overrides_.clear();
  }
  if (led_[0] || led_[1] || led_[2] || !led_driver_ok_) {
    led_driver_ok_ = hardware_.writeLed(0, 0, 0);
    if (led_driver_ok_) led_ = {{0, 0, 0}};
  }
  for (size_t pin = 0; pin < modes_.size(); ++pin) {
    if (modes_[pin] == PinMode::Unset) continue;
    hardware_.releasePin(static_cast<int>(pin)); modes_[pin] = PinMode::Unset; values_[pin] = 0;
  }
  for (size_t i = 0; i < servo_count_; ++i) {
    auto& servo = servos_[i];
    if (servo.active) hardware_.releasePin(servo.pin);
    servo.active = false;
  }
  return led_driver_ok_ && display_stopped && audio_stopped;
}
void DeviceCore::tick(uint32_t now_ms) {
  if (!session_.empty() && static_cast<uint32_t>(now_ms - last_seen_ms_) >= kLeaseMs) {
    const bool stopped = stopOutputs(); session_.clear(); clearPageUpload(); clearAudioSession();
    if (stopped) resumeDefaultPage();
  }
}
ServoSpec* DeviceCore::findServo(const std::string& name) {
  for (size_t i = 0; i < servo_count_; ++i) if (servos_[i].name == name) return &servos_[i];
  return nullptr;
}
const ServoSpec* DeviceCore::servoForPin(int pin) const {
  for (size_t i = 0; i < servo_count_; ++i) if (servos_[i].pin == pin) return &servos_[i];
  return nullptr;
}
bool DeviceCore::parseConfig(JsonObjectConst config, std::array<ServoSpec, kMaxServos>& out,
                            size_t& count, DisplaySpec& display, std::string& error) const {
  if (!onlyKeys(config, {"schema_version", "servos", "display"}) || !integer(config["schema_version"]) ||
      config["schema_version"].as<int>() != 1 || !config["servos"].is<JsonArrayConst>()) {
    error = "Expected schema_version 1 and a servos array without unknown fields"; return false;
  }
  auto array = config["servos"].as<JsonArrayConst>();
  if (array.size() > kMaxServos) { error = "At most four servos are supported"; return false; }
  count = 0;
  for (JsonVariantConst item : array) {
    if (!item.is<JsonObjectConst>() ||
        !onlyKeys(item.as<JsonObjectConst>(), {"name", "pin", "min_angle", "max_angle", "min_pulse_us", "max_pulse_us"}) ||
        !text(item["name"], 24) || !integer(item["pin"]) ||
        !integer(item["min_angle"]) || !integer(item["max_angle"]) ||
        !integer(item["min_pulse_us"]) || !integer(item["max_pulse_us"])) {
      error = "Servo configuration fields are missing or invalid"; return false;
    }
    ServoSpec next;
    next.name = item["name"].as<std::string>(); next.pin = item["pin"].as<int>();
    next.min_angle = item["min_angle"].as<int>(); next.max_angle = item["max_angle"].as<int>();
    next.min_pulse_us = item["min_pulse_us"].as<int>(); next.max_pulse_us = item["max_pulse_us"].as<int>();
    if (!validName(next.name) || !validPin(next.pin) || reservedPin(next.pin) ||
        next.min_angle < 0 || next.max_angle > 180 || next.min_angle >= next.max_angle ||
        next.min_pulse_us < 500 || next.max_pulse_us > 2500 || next.min_pulse_us >= next.max_pulse_us) {
      error = "Servo name, GPIO, angle limits or pulse calibration is invalid"; return false;
    }
    for (size_t i = 0; i < count; ++i) if (out[i].name == next.name || out[i].pin == next.pin) {
      error = "Servo names and pins must be unique"; return false;
    }
    out[count++] = next;
  }
  display = DisplaySpec{};
  if (!config["display"].isNull()) {
    const auto d = config["display"].as<JsonObjectConst>();
    if (d.isNull() || !onlyKeys(d, {"panel", "sck", "mosi", "cs", "dc", "rst", "backlight", "rotation", "invert", "brightness"}) ||
        !text(d["panel"], 32) || !d["invert"].is<bool>()) {
      error = "Display fields are missing or invalid"; return false;
    }
    for (const auto* name : {"sck", "mosi", "cs", "dc", "rst", "backlight", "rotation", "brightness"}) {
      if (!integer(d[name])) { error = "Display numeric fields must be integers"; return false; }
    }
    display.enabled = true; display.panel = d["panel"].as<std::string>();
    display.sck = d["sck"]; display.mosi = d["mosi"]; display.cs = d["cs"];
    display.dc = d["dc"]; display.rst = d["rst"]; display.backlight = d["backlight"];
    display.rotation = d["rotation"]; display.invert = d["invert"]; display.brightness = d["brightness"];
    int width, height;
    if (!panelSize(display.panel, width, height) || display.rotation < 0 || display.rotation > 3 ||
        display.backlight < -1 || display.brightness < 0 || display.brightness > 100 ||
        (display.backlight == -1 && display.brightness != 100)) {
      error = "Unsupported panel, rotation or backlight settings"; return false;
    }
    const auto pins = displayPins(display);
    for (size_t i = 0; i < pins.size(); ++i) {
      if (i == pins.size() - 1 && pins[i] == -1) continue;
      if (!validPin(pins[i]) || reservedPin(pins[i])) { error = "Display GPIO is invalid or reserved"; return false; }
      for (size_t j = 0; j < i; ++j) if (pins[i] == pins[j]) { error = "Display GPIOs must be unique"; return false; }
      for (size_t j = 0; j < count; ++j) if (pins[i] == out[j].pin) { error = "Display GPIO conflicts with servo"; return false; }
    }
  }
  if (audio_.enabled) {
    for (size_t i = 0; i < count; ++i) if (audioPin(out[i].pin)) {
      error = "Servo GPIO conflicts with this session's I2S audio"; return false;
    }
    if (display.enabled) for (int pin : displayPins(display)) if (audioPin(pin)) {
      error = "Display GPIO conflicts with this session's I2S audio"; return false;
    }
  }
  return true;
}
void DeviceCore::writeConfig(JsonObject target) const { encodeConfig(target, servos_, servo_count_, display_); }
std::string DeviceCore::stateBlob(bool maintenance, uint32_t revision,
    const std::array<ServoSpec, kMaxServos>& servos, size_t count, const DisplaySpec& display,
    const PageSettings* pages) const {
  JsonDocument state;
  const PageSettings& saved = pages ? *pages : page_settings_;
  state["state_version"] = saved.slot >= 0 ? 2 : 1;
  state["revision"] = revision; state["maintenance"] = maintenance;
  encodeConfig(state["config"].to<JsonObject>(), servos, count, display);
  if (saved.slot >= 0) {
    auto page = state["pages"].to<JsonObject>();
    page["slot"] = saved.slot; page["crc32"] = saved.crc32;
    page["startup_enabled"] = saved.startup_enabled; page["default_page"] = saved.default_page;
  }
  std::string text; serializeJson(state, text); return text;
}
std::string DeviceCore::process(const std::string& line, uint32_t now_ms) {
  tick(now_ms);
  JsonDocument request, response;
  response["kind"] = "response"; response["protocol_version"] = 1;
  response["request_id"] = ""; response["ok"] = true; response["code"] = "OK";
  if (line.size() > kMaxLine) fail(response, "LINE_TOO_LONG", "Control line exceeds 4096 bytes");
  else if (!singleObject(line) || deserializeJson(request, line, DeserializationOption::NestingLimit(8))) {
    fail(response, "INVALID_REQUEST", "Expected one complete JSON object");
  } else {
    const auto id = request["request_id"];
    if (text(id, 64)) response["request_id"] = id;
    if (!text(request["kind"], 16) || request["kind"] != "request" ||
        !text(id, 64) || !text(request["op"], 64) || !request["args"].is<JsonObjectConst>()) {
      fail(response, "INVALID_REQUEST", "kind, request_id, op and args are required");
    } else if (!integer(request["protocol_version"]) || request["protocol_version"].as<int>() != 1) {
      fail(response, "PROTOCOL_MISMATCH", "Only protocol version 1 is supported");
    } else dispatch(request.as<JsonObjectConst>(), response, now_ms);
  }
  std::string text; serializeJson(response, text); return text;
}
void DeviceCore::dispatch(JsonObjectConst request, JsonDocument& response, uint32_t now_ms) {
  const std::string op = request["op"].as<std::string>();
  const auto args = request["args"].as<JsonObjectConst>();
  auto data = response["data"].to<JsonObject>();
  if (op == "device.info") {
    data["firmware_family"] = "ai-maker-s3"; data["firmware_version"] = "0.5.0";
    data["protocol_version"] = 1; data["target"] = "esp32s3";
    data["board_profile"] = std::string("s3-n16r8-rgb") + std::to_string(kBuiltinRgbPin) + "-v1";
    data["boot_id"] = hardware_.bootId();
    auto caps = data["capabilities"].to<JsonObject>();
    for (const auto* name : {"gpio", "adc", "pwm", "servo", "configurable_servo_pins"}) caps[name] = true;
    caps["builtin_led"] = true;
    caps["display"] = true; caps["configurable_display_pins"] = true;
    caps["display_bitmap"] = true;
    caps["pages"] = true; caps["page_images"] = true; caps["page_startup"] = true;
    caps["audio_in"] = kAudioTransportSupported; caps["audio_out"] = kAudioTransportSupported;
    caps["i2s_audio"] = kAudioTransportSupported; caps["configurable_audio_pins"] = kAudioTransportSupported;
    caps["full_duplex_audio"] = false; data["audio_transport"] = "native-usb-required";
    caps["digital_input"] = true; caps["digital_output"] = true;
    caps["analog_input"] = true; caps["analog_output"] = false; caps["pwm_output"] = true;
    caps["pin_pagination"] = true;
    auto panels = data["display_panels"].to<JsonArray>();
    for (const auto* panel : {"st7789_240x320", "st7789_240x240", "st7735s_128x160"}) panels.add(panel);
    auto builtin = data["builtin_led"].to<JsonObject>();
    builtin["type"] = "ws2812"; builtin["pin"] = kBuiltinRgbPin; builtin["max_component"] = 32;
    builtin["physical_verified"] = false;
    for (const auto* name : {"sd", "student_web", "ai"}) caps[name] = false;
    auto limits = data["limits"].to<JsonObject>();
    limits["line_bytes"] = kMaxLine; limits["servos"] = kMaxServos;
    limits["pwm_channels"] = display_.enabled && display_.backlight >= 0 ? 3 : 4;
    limits["display_text_bytes"] = 192;
    limits["display_bitmap_pixels"] = 384;
    limits["audio_chunk_bytes"] = kAudioChunkBytes; limits["audio_stream_bytes"] = 1920000;
    limits["page_project_bytes"] = kMaxPageProjectBytes; limits["page_upload_chunk_bytes"] = 768;
    limits["page_count"] = 4; limits["page_widgets"] = 32; limits["page_images"] = 4; limits["page_image_edge"] = 48;
    limits["pwm_frequency_hz"] = 1000; limits["lease_ms"] = kLeaseMs; return;
  }
  if (op == "device.status") {
    data["session_active"] = !session_.empty(); data["maintenance"] = maintenance_;
    data["storage_fault"] = storage_fault_; data["config_revision"] = revision_;
    writeAudioInfo(data["audio"].to<JsonObject>());
    auto led = data["led"].to<JsonObject>();
    led["red"] = led_[0]; led["green"] = led_[1]; led["blue"] = led_[2];
    led["driver_ok"] = led_driver_ok_; led["physical_verified"] = false;
    auto display = data["display"].to<JsonObject>();
    display["configured"] = display_.enabled; display["active"] = display_active_;
    display["driver_ok"] = display_driver_ok_; display["panel"] = display_.enabled ? display_.panel : "";
    int width, height; displaySize(display_, width, height);
    display["width"] = width; display["height"] = height;
    display["brightness"] = display_.enabled ? display_brightness_ : 0;
    display["physical_verified"] = false;
    data["standalone_active"] = standalone_active_;
    writePagesInfo(data["pages"].to<JsonObject>());
    auto gpio = data["gpio"].to<JsonArray>();
    for (size_t pin = 0; pin < modes_.size(); ++pin) if (modes_[pin] != PinMode::Unset) {
      auto item = gpio.add<JsonObject>(); item["pin"] = pin;
      item["mode"] = modeName(modes_[pin]); item["value"] = values_[pin];
    }
    auto servos = data["servos"].to<JsonArray>();
    for (size_t i = 0; i < servo_count_; ++i) {
      auto item = servos.add<JsonObject>(); item["name"] = servos_[i].name; item["pin"] = servos_[i].pin;
      item["active"] = servos_[i].active;
      if (servos_[i].angle >= 0) item["angle"] = servos_[i].angle; else item["angle"] = nullptr;
      item["position_verified"] = false;
    }
    return;
  }
  if (op == "pins.list") {
    const bool paged = !args["offset"].isNull() || !args["limit"].isNull();
    int offset = 0, limit = 45;
    if (paged) {
      if (!onlyKeys(args, {"offset", "limit"}) || !integer(args["offset"]) || !integer(args["limit"]) ||
          args["offset"].as<int>() < 0 || args["offset"].as<int>() > 45 ||
          args["limit"].as<int>() < 1 || args["limit"].as<int>() > 12)
        return fail(response, "INVALID_ARGUMENT", "Pin pages require offset0..45 and limit1..12");
      offset = args["offset"]; limit = args["limit"];
      data["offset"] = offset; data["total"] = 45;
      if (offset + limit < 45) data["next_offset"] = offset + limit;
      else data["next_offset"] = nullptr;
    } else if (!onlyKeys(args, {})) return fail(response, "INVALID_ARGUMENT", "Unknown pins.list arguments");
    auto pins = data["pins"].to<JsonArray>();
    int index = 0;
    for (int pin = 0; pin <= 48; ++pin) {
      if (!validPin(pin)) continue;
      if (index++ < offset) continue;
      if (index > offset + limit) break;
      auto item = pins.add<JsonObject>(); const bool reserved = reservedPin(pin);
      item["pin"] = pin; item["input"] = true; item["output"] = true;
      item["adc"] = pin >= 1 && pin <= 20; item["reserved"] = reserved;
      if (paged) {
        item["digital_input"] = true; item["digital_output"] = true;
        item["analog_input"] = pin >= 1 && pin <= 20;
        item["analog_output"] = false; item["pwm_output"] = true;
      }
      const auto* servo = servoForPin(pin);
      if (reserved) item["owner"] = "system";
      else if (audioPin(pin)) item["owner"] = pin == audio_.din ? "audio:mic_in" : "audio:output";
      else if (displayPin(display_, pin)) item["owner"] = "display";
      else if (servo) item["owner"] = std::string("servo:") + servo->name;
      else if (modes_[pin] != PinMode::Unset) item["owner"] = "gpio";
      else item["owner"] = "";
    }
    return;
  }
  if (op == "config.get") { data["revision"] = revision_; writeConfig(data["config"].to<JsonObject>()); return; }
  if (op == "pages.info") return writePagesInfo(data);
  if (op == "audio.info") return writeAudioInfo(data);
  const auto sessionValue = request["session_id"];
  if (!text(sessionValue, 40)) {
    return fail(response, "SESSION_REQUIRED", "A session_id of 1 to 40 bytes is required");
  }
  const std::string session = sessionValue.as<std::string>();
  if (op == "session.open") {
    if (!session_.empty() && session_ != session) return fail(response, "DEVICE_BUSY", "Another session owns the device");
    if (session_.empty() && standalone_active_ && !stopOutputs())
      return fail(response, "HARDWARE_ERROR", "Default page cleanup failed before taking control");
    session_ = session; last_seen_ms_ = now_ms;
    data["session_id"] = session_; data["lease_ms"] = kLeaseMs; return;
  }
  if (session_.empty() || session != session_) return fail(response, "SESSION_REQUIRED", "Session is missing, expired or not the owner");
  last_seen_ms_ = now_ms;
  if (op == "session.heartbeat") { data["lease_ms"] = kLeaseMs; return; }
  if (op == "session.close") {
    const bool stopped = stopOutputs(); session_.clear(); clearPageUpload(); clearAudioSession();
    if (!stopped) return fail(response, "HARDWARE_ERROR", "Session closed; output cleanup failed, check device.status");
    if (!resumeDefaultPage()) return fail(response, "HARDWARE_ERROR", "Session closed; default page failed to resume");
    data["closed"] = true; return;
  }
  if (op == "outputs.stop") {
    if (!stopOutputs()) return fail(response, "HARDWARE_ERROR", "Output cleanup failed, check device.status");
    data["stopped"] = true; return;
  }
  if (op == "maintenance.enter") {
    const bool stopped = stopOutputs(); maintenance_ = true;
    if (!hardware_.saveState(stateBlob(true, revision_, servos_, servo_count_, display_))) {
      storage_fault_ = true;
      return fail(response, "STORAGE_ERROR", "Maintenance flag was not saved; do not rewire yet");
    }
    storage_fault_ = false;
    if (!stopped) return fail(response, "HARDWARE_ERROR", "Maintenance saved; output cleanup failed, check device.status");
    data["maintenance"] = true; return;
  }
  if (op == "config.apply") {
    if (!maintenance_) return fail(response, "MAINTENANCE_REQUIRED", "Enter maintenance before changing wiring");
    if (!args["expected_revision"].is<uint32_t>() || args["expected_revision"].is<bool>())
      return fail(response, "INVALID_ARGUMENT", "expected_revision must be an unsigned integer");
    if (args["expected_revision"].as<uint32_t>() != revision_)
      return fail(response, "CONFIG_REVISION_MISMATCH", "Read the latest configuration before applying changes");
    if (!args["config"].is<JsonObjectConst>()) return fail(response, "CONFIG_INVALID", "config must be an object");
    std::array<ServoSpec, kMaxServos> next{}; size_t count = 0; DisplaySpec next_display; std::string error;
    if (!parseConfig(args["config"].as<JsonObjectConst>(), next, count, next_display, error))
      return fail(response, "CONFIG_INVALID", error.c_str());
    if (revision_ == std::numeric_limits<uint32_t>::max()) return fail(response, "CONFIG_INVALID", "Configuration revision exhausted");
    const auto revision = revision_ + 1;
    if (!stopOutputs()) return fail(response, "HARDWARE_ERROR", "Release old outputs before changing mappings");
    PageSettings next_pages = page_settings_;
    if (next_pages.startup_enabled && !pageFitsDisplay(page_project_, next_display)) next_pages.startup_enabled = false;
    if (!hardware_.saveState(stateBlob(true, revision, next, count, next_display, &next_pages))) {
      storage_fault_ = true;
      return fail(response, "STORAGE_ERROR", "Configuration was not saved; previous mapping is retained");
    }
    servos_ = next; servo_count_ = count; display_ = next_display; display_brightness_ = display_.brightness;
    page_settings_ = next_pages;
    revision_ = revision; storage_fault_ = false;
    data["revision"] = revision_; writeConfig(data["config"].to<JsonObject>()); return;
  }
  if (op == "maintenance.exit") {
    if (storage_fault_) return fail(response, "STORAGE_ERROR", "Repair and save configuration before leaving maintenance");
    if (!hardware_.saveState(stateBlob(false, revision_, servos_, servo_count_, display_)))
      return fail(response, "STORAGE_ERROR", "Maintenance flag could not be cleared");
    maintenance_ = false; data["maintenance"] = false; return;
  }
  if (op.compare(0, 6, "pages.") == 0) return dispatchPages(op, args, response);
  if (op.compare(0, 6, "audio.") == 0) return dispatchAudio(op, args, response);
  if (op == "display.release") return dispatchDisplay(op, args, response);
  if (maintenance_) return fail(response, "MAINTENANCE_REQUIRED", "Hardware operations are disabled in maintenance");
  if (op.compare(0, 8, "display.") == 0) return dispatchDisplay(op, args, response);
  if (op == "led.set" || op == "led.off") {
    std::array<int, 3> next{};
    const char* colors[] = {"red", "green", "blue"};
    if (op == "led.set") for (size_t i = 0; i < 3; ++i) {
      if (!integer(args[colors[i]]) || args[colors[i]].as<int>() < 0 || args[colors[i]].as<int>() > 32)
        return fail(response, "INVALID_ARGUMENT", "RGB components must be integers from 0 to 32");
      next[i] = args[colors[i]].as<int>();
    }
    led_driver_ok_ = hardware_.writeLed(next[0], next[1], next[2]);
    if (!led_driver_ok_) return fail(response, "HARDWARE_ERROR", "RGB command failed; check LED status and reset board");
    led_ = next;
    data["red"] = led_[0]; data["green"] = led_[1]; data["blue"] = led_[2];
    data["state"] = "commanded"; data["physical_verified"] = false; return;
  }
  if (op == "servo.move" || op == "servo.release") {
    if (!args["device"].is<const char*>()) return fail(response, "INVALID_ARGUMENT", "device must be a servo name");
    auto* servo = findServo(args["device"].as<std::string>());
    if (!servo) return fail(response, "DEVICE_NOT_FOUND", "Configure the servo first");
    if (op == "servo.release") { hardware_.releasePin(servo->pin); servo->active = false; data["released"] = true; return; }
    if (!integer(args["angle"])) return fail(response, "INVALID_ARGUMENT", "angle must be an integer");
    const int angle = args["angle"].as<int>();
    if (angle < servo->min_angle || angle > servo->max_angle)
      return fail(response, "ANGLE_OUT_OF_RANGE", "Angle is outside calibrated limits");
    const int pulse = servo->min_pulse_us + ((servo->max_pulse_us - servo->min_pulse_us) * angle + 90) / 180;
    if (!hardware_.writeServo(servo->pin, pulse)) {
      hardware_.releasePin(servo->pin); servo->active = false;
      return fail(response, "HARDWARE_ERROR", "Servo PWM could not be written");
    }
    servo->active = true; servo->angle = angle;
    data["state"] = "commanded"; data["angle"] = angle; data["position_verified"] = false; return;
  }
  const bool pinOperation = op == "gpio.setup" || op == "gpio.read" || op == "gpio.write" ||
      op == "gpio.release" || op == "adc.read" || op == "pwm.write";
  if (!pinOperation) return fail(response, "UNSUPPORTED_OPERATION", "This firmware does not implement that operation");
  if (!integer(args["pin"])) return fail(response, "INVALID_ARGUMENT", "pin must be an integer");
  const int pin = args["pin"].as<int>();
  if (!validPin(pin)) return fail(response, "PIN_INVALID", "GPIO does not exist on ESP32-S3");
  if (reservedPin(pin)) return fail(response, "PIN_RESERVED", "GPIO is reserved by this board profile");
  if (servoForPin(pin)) return fail(response, "RESOURCE_CONFLICT", "GPIO is assigned to a configured servo");
  if (displayPin(display_, pin)) return fail(response, "RESOURCE_CONFLICT", "GPIO is assigned to display");
  if (audioPin(pin)) return fail(response, "RESOURCE_CONFLICT", "GPIO is assigned to I2S audio");
  if (op == "gpio.setup") {
    if (!args["mode"].is<const char*>()) return fail(response, "INVALID_ARGUMENT", "mode is required");
    const std::string mode = args["mode"].as<std::string>(); PinMode next = PinMode::Unset;
    if (mode == "input") next = PinMode::Input;
    else if (mode == "input_pullup") next = PinMode::InputPullup;
    else if (mode == "input_pulldown") next = PinMode::InputPulldown;
    else if (mode == "output") next = PinMode::Output;
    else if (mode == "pwm") next = PinMode::Pwm;
    else return fail(response, "INVALID_ARGUMENT", "Unsupported GPIO mode");
    if (next == PinMode::Pwm) {
      size_t count = 0;
      for (size_t p = 0; p < modes_.size(); ++p) if (p != static_cast<size_t>(pin) && modes_[p] == PinMode::Pwm) ++count;
      const size_t limit = display_.enabled && display_.backlight >= 0 ? 3 : 4;
      if (count >= limit) return fail(response, "RESOURCE_CONFLICT", "General PWM channels are exhausted; backlight reserves one channel");
    }
    if (modes_[pin] != PinMode::Unset) hardware_.releasePin(pin);
    modes_[pin] = PinMode::Unset; values_[pin] = 0;
    if (!hardware_.configurePin(pin, next)) {
      hardware_.releasePin(pin); return fail(response, "HARDWARE_ERROR", "GPIO could not be configured");
    }
    modes_[pin] = next; data["pin"] = pin; data["mode"] = mode; return;
  }
  if (op == "gpio.release") {
    hardware_.releasePin(pin); modes_[pin] = PinMode::Unset; values_[pin] = 0;
    data["pin"] = pin; data["released"] = true; return;
  }
  if (modes_[pin] == PinMode::Unset) return fail(response, "INVALID_ARGUMENT", "Call gpio.setup first");
  if (op == "adc.read") {
    if (!adcPin(pin)) return fail(response, "PIN_CAPABILITY_MISMATCH", "GPIO has no usable ADC channel");
    if (modes_[pin] != PinMode::Input) return fail(response, "INVALID_ARGUMENT", "ADC requires plain input without pulls");
    const int raw = hardware_.readAdc(pin);
    if (raw < 0 || raw > 4095) return fail(response, "HARDWARE_ERROR", "ADC reading failed");
    data["pin"] = pin; data["raw"] = raw; data["bits"] = 12; return;
  }
  if (op == "gpio.read") {
    if (modes_[pin] == PinMode::Pwm) return fail(response, "INVALID_ARGUMENT", "Read PWM duty from device.status");
    const bool commanded = modes_[pin] == PinMode::Output;
    const int value = commanded ? values_[pin] : hardware_.readDigital(pin);
    if (value != 0 && value != 1) return fail(response, "HARDWARE_ERROR", "Digital input read failed");
    data["pin"] = pin; data["value"] = value; data["source"] = commanded ? "commanded" : "input"; return;
  }
  if (op == "gpio.write") {
    if (modes_[pin] != PinMode::Output) return fail(response, "INVALID_ARGUMENT", "GPIO is not configured as output");
    if (!integer(args["value"]) || args["value"].as<int>() < 0 || args["value"].as<int>() > 1)
      return fail(response, "INVALID_ARGUMENT", "value must be integer 0 or 1");
    const int value = args["value"].as<int>();
    if (!hardware_.writeDigital(pin, value)) {
      hardware_.releasePin(pin); modes_[pin] = PinMode::Unset;
      return fail(response, "HARDWARE_ERROR", "Digital output failed");
    }
    values_[pin] = value; data["pin"] = pin; data["value"] = value; return;
  }
  if (modes_[pin] != PinMode::Pwm) return fail(response, "INVALID_ARGUMENT", "GPIO is not configured as PWM");
  if (!integer(args["duty"]) || args["duty"].as<int>() < 0 || args["duty"].as<int>() > 100)
    return fail(response, "INVALID_ARGUMENT", "duty must be integer 0 to 100");
  const int duty = args["duty"].as<int>();
  if (!hardware_.writePwm(pin, duty)) {
    hardware_.releasePin(pin); modes_[pin] = PinMode::Unset;
    return fail(response, "HARDWARE_ERROR", "PWM output failed");
  }
  values_[pin] = duty; data["pin"] = pin; data["duty"] = duty; data["frequency_hz"] = 1000;
}
void DeviceCore::dispatchDisplay(const std::string& op, JsonObjectConst args, JsonDocument& response) {
  auto data = response["data"].as<JsonObject>();
  const auto commanded = [&]() { data["state"] = "commanded"; data["physical_verified"] = false; };
  if (op == "display.release") {
    if (!onlyKeys(args, {})) return fail(response, "INVALID_ARGUMENT", "display.release takes no arguments");
    bool released = true;
    if (display_active_ || !display_driver_ok_) released = hardware_.releaseDisplay();
    display_driver_ok_ = released;
    if (!released) return fail(response, "HARDWARE_ERROR", "Display cleanup failed");
    display_active_ = false; data["released"] = true; return;
  }
  if (!display_.enabled) return fail(response, "DEVICE_NOT_FOUND", "Configure display in maintenance first");
  if (op == "display.begin") {
    if (!onlyKeys(args, {})) return fail(response, "INVALID_ARGUMENT", "display.begin takes no arguments");
    if (display_active_ || !display_driver_ok_) {
      if (!hardware_.releaseDisplay()) {
        display_driver_ok_ = false;
        return fail(response, "HARDWARE_ERROR", "Display cleanup failed before initialization");
      }
    }
    display_active_ = false;
    display_driver_ok_ = hardware_.beginDisplay(display_);
    if (!display_driver_ok_) {
      hardware_.releaseDisplay();
      return fail(response, "HARDWARE_ERROR", "Display driver initialization failed");
    }
    display_active_ = true; display_brightness_ = display_.brightness;
    int width, height; displaySize(display_, width, height);
    data["width"] = width; data["height"] = height; data["panel"] = display_.panel;
    commanded(); return;
  }
  if (!display_active_) return fail(response, "INVALID_ARGUMENT", "Call display.begin first");
  if (!display_driver_ok_) return fail(response, "HARDWARE_ERROR", "Release and reinitialize display after driver failure");
  int width, height; displaySize(display_, width, height);
  const auto coordinate = [&](const char* name, int bound) {
    return integer(args[name]) && args[name].as<int>() >= 0 && args[name].as<int>() < bound;
  };
  const auto color = [&]() { return integer(args["color"]) && args["color"].as<int>() >= 0 && args["color"].as<int>() <= 65535; };
  bool success = false;
  if (op == "display.fill") {
    if (!onlyKeys(args, {"color"}) || !color()) return fail(response, "INVALID_ARGUMENT", "color must be RGB565 integer 0 to 65535");
    success = hardware_.fillDisplay(args["color"].as<uint16_t>());
  } else if (op == "display.text") {
    if (!onlyKeys(args, {"x", "y", "text", "color"}) || !color() || !coordinate("x", width) || !coordinate("y", height) ||
        !text(args["text"], 192) || !validDisplayText(args["text"].as<std::string>()))
      return fail(response, "INVALID_ARGUMENT", "Text requires screen coordinates and 1 to 192 valid UTF8 bytes without controls except newline");
    success = hardware_.textDisplay(args["x"], args["y"], args["text"].as<std::string>(), args["color"].as<uint16_t>());
  } else if (op == "display.rect") {
    if (!onlyKeys(args, {"x", "y", "width", "height", "color", "filled"}) || !color() ||
        !coordinate("x", width) || !coordinate("y", height) || !integer(args["width"]) || !integer(args["height"]) ||
        !args["filled"].is<bool>() || args["width"].as<int>() <= 0 || args["height"].as<int>() <= 0 ||
        args["width"].as<int>() > width - args["x"].as<int>() || args["height"].as<int>() > height - args["y"].as<int>())
      return fail(response, "INVALID_ARGUMENT", "Rectangle must fit the visible screen");
    success = hardware_.rectDisplay(args["x"], args["y"], args["width"], args["height"], args["color"].as<uint16_t>(), args["filled"]);
  } else if (op == "display.line") {
    if (!onlyKeys(args, {"x0", "y0", "x1", "y1", "color"}) || !color() ||
        !coordinate("x0", width) || !coordinate("x1", width) || !coordinate("y0", height) || !coordinate("y1", height))
      return fail(response, "INVALID_ARGUMENT", "Line endpoints must be on screen");
    success = hardware_.lineDisplay(args["x0"], args["y0"], args["x1"], args["y1"], args["color"].as<uint16_t>());
  } else if (op == "display.bitmap") {
    if (!onlyKeys(args, {"x", "y", "width", "height", "data"}) ||
        !coordinate("x", width) || !coordinate("y", height) || !integer(args["width"]) || !integer(args["height"]) ||
        args["width"].as<int>() <= 0 || args["height"].as<int>() <= 0 ||
        args["width"].as<int>() > width - args["x"].as<int>() || args["height"].as<int>() > height - args["y"].as<int>() ||
        !text(args["data"], 1024)) return fail(response, "INVALID_ARGUMENT", "Bitmap rectangle must fit the display");
    const size_t pixels = args["width"].as<size_t>() * args["height"].as<size_t>();
    std::string decoded;
    if (pixels > 384 || !decodePageBase64(args["data"].as<std::string>(), decoded, 768) || decoded.size() != pixels * 2)
      return fail(response, "INVALID_ARGUMENT", "Bitmap needs at most 384 RGB565 big-endian pixels");
    std::vector<uint16_t> colors(pixels);
    for (size_t i = 0; i < pixels; ++i)
      colors[i] = (static_cast<uint8_t>(decoded[2 * i]) << 8) | static_cast<uint8_t>(decoded[2 * i + 1]);
    success = hardware_.bitmapDisplay(args["x"], args["y"], args["width"], args["height"], colors.data());
  } else if (op == "display.brightness") {
    if (!onlyKeys(args, {"percent"}) || !integer(args["percent"]) || args["percent"].as<int>() < 0 || args["percent"].as<int>() > 100)
      return fail(response, "INVALID_ARGUMENT", "Brightness must be an integer from 0 to 100");
    if (display_.backlight < 0) return fail(response, "UNSUPPORTED_OPERATION", "This display has no GPIO-controlled backlight");
    success = hardware_.brightnessDisplay(args["percent"]);
    if (success) { display_brightness_ = args["percent"]; data["brightness"] = display_brightness_; }
  } else return fail(response, "UNSUPPORTED_OPERATION", "Unknown display operation");
  display_driver_ok_ = success;
  if (!success) return fail(response, "HARDWARE_ERROR", "Display command failed");
  commanded();
}
}  // namespace ai_maker
