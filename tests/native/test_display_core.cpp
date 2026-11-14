#include "device_core.h"
#include "fake_hardware.h"
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
void require(bool yes, const std::string& message) {
  if (!yes) throw std::runtime_error(message);
}
std::string json(JsonVariantConst value) {
  std::string output; serializeJson(value, output); return output;
}
class DisplayHardware final : public FakeHardware {
 public:
  bool begin_ok = true, render_ok = true, release_ok = true;
  bool display_active = false;
  int starts = 0, stops = 0, renders = 0, brightness = -1;
  uint16_t color = 0;
  std::string words;
  std::vector<uint16_t> pixels;
  ai_maker::DisplaySpec spec;
  bool beginDisplay(const ai_maker::DisplaySpec& value) override {
    ++starts; spec = value; display_active = begin_ok; brightness = value.brightness; return begin_ok;
  }
  bool fillDisplay(uint16_t value) override { ++renders; color = value; return display_active && render_ok; }
  bool textDisplay(int, int, const std::string& value, uint16_t ink) override {
    ++renders; words = value; color = ink; return display_active && render_ok;
  }
  bool rectDisplay(int, int, int, int, uint16_t ink, bool) override {
    ++renders; color = ink; return display_active && render_ok;
  }
  bool lineDisplay(int, int, int, int, uint16_t ink) override {
    ++renders; color = ink; return display_active && render_ok;
  }
  bool bitmapDisplay(int, int, int width, int height, const uint16_t* values) override {
    ++renders; pixels.assign(values, values + width * height); return display_active && render_ok;
  }
  bool brightnessDisplay(int value) override { brightness = value; return display_active && render_ok; }
  bool releaseDisplay() override {
    ++stops; if (release_ok) display_active = false; return release_ok;
  }
};

std::string display(const char* panel = "st7789_240x320", int rotation = 1, int backlight = -1) {
  return std::string(R"({"panel":")") + panel + R"(","sck":4,"mosi":5,"cs":15,"dc":7,"rst":6,"backlight":)" +
      std::to_string(backlight) + ",\"rotation\":" + std::to_string(rotation) +
      R"(,"invert":true,"brightness":)" + (backlight < 0 ? "100" : "60") + "}";
}
std::string servo(int pin = 14) {
  return std::string(R"([{"name":"head","pin":)") + std::to_string(pin) +
      R"(,"min_angle":30,"max_angle":150,"min_pulse_us":1000,"max_pulse_us":2000}])";
}
std::string config(const std::string& screen, const std::string& servos = "[]") {
  return R"({"schema_version":1,"servos":)" + servos + (screen.empty() ? "" : ",\"display\":" + screen) + "}";
}
std::string replace(std::string value, const std::string& from, const std::string& to) {
  const auto offset = value.find(from); require(offset != std::string::npos, "bad test replacement");
  value.replace(offset, from.size(), to); return value;
}

struct Fixture {
  DisplayHardware hardware;
  ai_maker::DeviceCore core{hardware};
  uint32_t now = 100;
  unsigned sequence = 0;
  explicit Fixture(const std::string& stored = "") { hardware.state = stored; core.begin(); }
  JsonDocument call(const std::string& op, const std::string& args = "{}", const std::string& session = "screen-owner") {
    JsonDocument request, reply;
    request["kind"] = "request"; request["protocol_version"] = 1;
    const auto id = "display-" + std::to_string(++sequence);
    request["request_id"] = id; request["session_id"] = session; request["op"] = op;
    std::string line; serializeJson(request, line); line.pop_back(); line += ",\"args\":" + args + "}";
    const auto result = core.process(line, now);
    require(!deserializeJson(reply, result), "non-JSON response: " + result);
    require(reply["request_id"] == id, "response must match request ID"); return reply;
  }
  JsonDocument ok(const std::string& op, const std::string& args = "{}") {
    auto result = call(op, args);
    require(result["ok"].as<bool>(), op + " failed: " + result["code"].as<std::string>()); return result;
  }
  void error(const std::string& op, const std::string& args, const char* code) {
    auto result = call(op, args);
    require(!result["ok"].as<bool>(), op + " unexpectedly succeeded");
    require(result["code"] == code, op + " expected " + code + ", got " + result["code"].as<std::string>());
  }
  void open() { ok("session.open"); }
  std::string applyArgs(const std::string& value) {
    auto current = ok("config.get");
    return "{\"expected_revision\":" + std::to_string(current["data"]["revision"].as<unsigned>()) + ",\"config\":" + value + "}";
  }
  void setup(const std::string& screen = display(), const std::string& servos = "[]") {
    open(); ok("maintenance.enter"); ok("config.apply", applyArgs(config(screen, servos)));
  }
  void start() { ok("maintenance.exit"); ok("display.begin"); }
};

void capability_and_configuration_reserve_runtime_pins() {
  Fixture f;
  const auto info = f.ok("device.info");
  require(info["data"]["capabilities"]["display"].as<bool>(), "display capability must be implemented");
  require(info["data"]["capabilities"]["configurable_display_pins"].as<bool>(), "display IO must be configurable");
  require(info["data"]["limits"]["display_text_bytes"] == 192, "text byte limit advertised");
  require(f.hardware.starts == 0, "boot must not initialize a screen");
  f.setup();
  require(f.hardware.starts == 0 && f.ok("device.status")["data"]["maintenance"].as<bool>(), "configuration does not drive screen");
  f.ok("maintenance.exit");
  f.error("gpio.setup", R"({"pin":4,"mode":"output"})", "RESOURCE_CONFLICT");
  const auto pins = f.ok("pins.list"); bool reserved = false;
  for (auto pin : pins["data"]["pins"].as<JsonArrayConst>()) if (pin["pin"] == 4) reserved = pin["owner"] == "display";
  require(reserved, "configured display pin must be owned before begin");
}

void display_configuration_survives_restart_without_motion() {
  Fixture f;
  f.setup(display("st7789_240x240", 2, 16), servo());
  const auto saved = f.ok("config.get");
  Fixture reboot(f.hardware.state);
  require(reboot.hardware.starts == 0 && reboot.hardware.servo_writes == 0, "restoring mapping cannot drive peripherals");
  require(reboot.ok("device.status")["data"]["maintenance"].as<bool>(), "maintenance persists");
  require(json(reboot.ok("config.get")["data"]["config"]) == json(saved["data"]["config"]), "saved display and servo mappings restore together");
  const std::string oldState = R"({"state_version":1,"revision":8,"maintenance":false,"config":{"schema_version":1,"servos":[]}})";
  Fixture legacy(oldState);
  auto status = legacy.ok("device.status");
  require(!status["data"]["storage_fault"].as<bool>() && !status["data"]["display"]["configured"].as<bool>(), "legacy no-display state remains valid");
}

void strict_display_configuration_is_transactional() {
  Fixture f; f.setup();
  const auto old = json(f.ok("config.get")["data"]);
  const auto source = display();
  const std::vector<std::string> invalid = {
      replace(source, "st7789_240x320", "unknown"),
      replace(source, "\"sck\":4", "\"sck\":19"),
      replace(source, "\"sck\":4", "\"sck\":5"),
      replace(source, "\"sck\":4", "\"sck\":true"),
      replace(source, "\"sck\":4", "\"sck\":4.0"),
      replace(source, "\"sck\":4", "\"sck\":\"4\""),
      replace(source, "\"backlight\":-1", "\"backlight\":4"),
      replace(source, "\"backlight\":-1", "\"backlight\":-2"),
      replace(source, "\"rotation\":1", "\"rotation\":4"),
      replace(source, "\"invert\":true", "\"invert\":1"),
      replace(source, "\"brightness\":100", "\"brightness\":60"),
      replace(source, "\"brightness\":100", "\"brightness\":101"),
      replace(source, "\"brightness\":100", "\"brightness\":true"),
      replace(source, "\"brightness\":100", "\"brightness\":100,\"typo\":0"),
      replace(source, "\"rst\":6,", ""), "true"};
  for (const auto& item : invalid) {
    f.error("config.apply", f.applyArgs(config(item)), "CONFIG_INVALID");
    require(json(f.ok("config.get")["data"]) == old, "bad mapping must not publish partial state");
  }
  f.error("config.apply", f.applyArgs(config(source, servo(4))), "CONFIG_INVALID");
  f.hardware.save_ok = false;
  f.error("config.apply", f.applyArgs(config(display("st7735s_128x160"))), "STORAGE_ERROR");
  require(json(f.ok("config.get")["data"]) == old, "failed save keeps full previous mapping");
}

void display_geometry_and_driver_selection() {
  struct Panel { const char* name; int width; int height; };
  for (const auto& panel : {Panel{"st7789_240x320", 240, 320}, Panel{"st7789_240x240", 240, 240}, Panel{"st7735s_128x160", 128, 160}}) {
    for (int rotation = 0; rotation < 4; ++rotation) {
      Fixture f; f.setup(display(panel.name, rotation)); f.ok("maintenance.exit");
      const auto started = f.ok("display.begin");
      require(f.hardware.starts == 1 && f.hardware.spec.panel == panel.name && f.hardware.spec.rotation == rotation, "panel configuration reaches hardware");
      const int width = rotation % 2 ? panel.height : panel.width;
      const int height = rotation % 2 ? panel.width : panel.height;
      require(started["data"]["width"] == width && started["data"]["height"] == height, "rotation geometry");
      auto status = f.ok("device.status");
      require(status["data"]["display"]["active"].as<bool>() && status["data"]["display"]["width"] == width, "active screen status");
    }
  }
}

void screen_drawing_is_explicit_and_reports_commanded_only() {
  Fixture f;
  f.error("display.begin", "{}", "SESSION_REQUIRED"); f.setup();
  f.error("display.begin", "{}", "MAINTENANCE_REQUIRED"); f.ok("maintenance.exit");
  f.error("display.fill", R"({"color":65535})", "INVALID_ARGUMENT");
  f.ok("display.begin");
  const int rendersBeforeCommands = f.hardware.renders;
  for (const auto& item : std::vector<std::pair<std::string, std::string>>{
      {"display.fill", R"({"color":63488})"},
      {"display.text", R"({"x":0,"y":0,"text":"AI\n\u4f60\u597d","color":65535})"},
      {"display.rect", R"({"x":10,"y":10,"width":20,"height":30,"color":2016,"filled":true})"},
      {"display.line", R"({"x0":0,"y0":0,"x1":319,"y1":239,"color":31})"}}) {
    const auto result = f.ok(item.first, item.second);
    require(result["data"]["state"] == "commanded" && result["data"]["physical_verified"].is<bool>() && !result["data"]["physical_verified"].as<bool>(), "no electrical/optical feedback claim");
  }
  require(f.hardware.renders == rendersBeforeCommands + 4 && f.hardware.words == "AI\n\xE4\xBD\xA0\xE5\xA5\xBD", "text and primitives reach adapter");
  const auto foreign = f.call("display.fill", R"({"color":31})", "foreign-owner");
  require(!foreign["ok"].as<bool>() && foreign["code"] == "SESSION_REQUIRED", "another session cannot draw");
}

void coordinates_types_and_utf8_are_checked_before_render() {
  Fixture f; f.setup(); f.start();
  const int calls = f.hardware.renders;
  for (const auto* value : {"-1", "65536", "true", "1.0", "\"1\""})
    f.error("display.fill", "{\"color\":" + std::string(value) + "}", "INVALID_ARGUMENT");
  for (const auto* value : {"-1", "320", "true", "1.0"})
    f.error("display.text", "{\"x\":" + std::string(value) + R"(,"y":0,"text":"A","color":1})", "INVALID_ARGUMENT");
  f.error("display.text", R"({"x":0,"y":240,"text":"A","color":1})", "INVALID_ARGUMENT");
  f.error("display.rect", R"({"x":310,"y":0,"width":11,"height":5,"color":1,"filled":false})", "INVALID_ARGUMENT");
  f.error("display.rect", R"({"x":0,"y":0,"width":0,"height":5,"color":1,"filled":false})", "INVALID_ARGUMENT");
  f.error("display.rect", R"({"x":0,"y":0,"width":10,"height":5,"color":1,"filled":1})", "INVALID_ARGUMENT");
  f.error("display.line", R"({"x0":0,"y0":0,"x1":320,"y1":0,"color":1})", "INVALID_ARGUMENT");
  for (const auto& words : {std::string(""), std::string(193, 'a'), std::string("bad\\u0000tail"), std::string("bad\\t"), std::string("bad\\u001b"), std::string("\xC0\xAF"), std::string("\xED\xA0\x80"), std::string("\xF4\x90\x80\x80")})
    f.error("display.text", R"({"x":0,"y":0,"text":")" + words + R"(","color":1})", "INVALID_ARGUMENT");
  require(f.hardware.renders == calls, "invalid input cannot reach renderer");
  f.ok("display.text", R"({"x":0,"y":0,"text":")" + std::string(192, 'x') + R"(","color":1})");
  f.ok("display.text", R"({"x":319,"y":239,"text":"x","color":65535})");
}

void backlight_has_explicit_support_and_budget() {
  Fixture noBacklight; noBacklight.setup(); noBacklight.start();
  noBacklight.error("display.brightness", R"({"percent":50})", "UNSUPPORTED_OPERATION");
  Fixture f; f.setup(display("st7789_240x320", 1, 16)); f.start();
  require(f.ok("device.info")["data"]["limits"]["pwm_channels"] == 3, "backlight consumes one general PWM channel");
  f.ok("display.brightness", R"({"percent":0})"); require(f.hardware.brightness == 0, "backlight fully off");
  f.ok("display.brightness", R"({"percent":100})"); require(f.hardware.brightness == 100, "backlight fully on");
  f.error("display.brightness", R"({"percent":101})", "INVALID_ARGUMENT");
  for (int pin : {8, 9, 10}) f.ok("gpio.setup", "{\"pin\":" + std::to_string(pin) + ",\"mode\":\"pwm\"}");
  f.error("gpio.setup", R"({"pin":11,"mode":"pwm"})", "RESOURCE_CONFLICT");
  std::string fourServos = "[";
  int index = 0;
  for (int pin : {12, 13, 14, 17}) {
    if (index) fourServos += ",";
    auto item = servo(pin);
    item = item.substr(1, item.size() - 2);
    fourServos += replace(item, "\"head\"", "\"servo" + std::to_string(++index) + "\"");
  }
  fourServos += "]";
  Fixture allChannels;
  allChannels.setup(display("st7789_240x320", 1, 16), fourServos); allChannels.start();
  for (int pin : {8, 9, 10}) allChannels.ok("gpio.setup", "{\"pin\":" + std::to_string(pin) + ",\"mode\":\"pwm\"}");
  for (int n = 1; n <= 4; ++n)
    allChannels.ok("servo.move", "{\"device\":\"servo" + std::to_string(n) + "\",\"angle\":90}");
  require(allChannels.hardware.servo_writes == 4, "backlight cannot consume any of the four servo channels");
}

void release_paths_keep_configuration_and_close_ownership() {
  for (const std::string action : {"display.release", "outputs.stop", "session.close", "maintenance.enter", "timeout"}) {
    Fixture f; f.setup(); f.start();
    const auto original = json(f.ok("config.get")["data"]["config"]);
    if (action == "timeout") { f.now += ai_maker::kLeaseMs; f.core.tick(f.now); }
    else f.ok(action);
    const auto status = f.ok("device.status");
    require(!f.hardware.display_active && !status["data"]["display"]["active"].as<bool>(), "release display on " + action);
    require(json(f.ok("config.get")["data"]["config"]) == original, "release retains mapping");
    if (action == "timeout" || action == "session.close") require(!status["data"]["session_active"].as<bool>(), "close ownership");
    if (action == "display.release") { f.ok("display.release"); f.ok("display.begin"); }
    if (action == "maintenance.enter") f.ok("display.release");
  }
}

void failed_driver_cannot_claim_a_working_screen() {
  Fixture f; f.setup(); f.ok("maintenance.exit"); f.hardware.begin_ok = false;
  f.error("display.begin", "{}", "HARDWARE_ERROR");
  auto status = f.ok("device.status");
  require(!status["data"]["display"]["driver_ok"].as<bool>() && !status["data"]["display"]["active"].as<bool>(), "failed begin leaves non-active fault status");
  require(f.hardware.stops > 0, "failed begin cleans partial hardware resources");
  Fixture render; render.setup(); render.start(); render.hardware.render_ok = false;
  render.error("display.fill", R"({"color":65535})", "HARDWARE_ERROR");
  require(!render.ok("device.status")["data"]["display"]["driver_ok"].as<bool>(), "draw failure cannot claim a working renderer");
  const int failedRenders = render.hardware.renders;
  render.error("display.fill", R"({"color":1})", "HARDWARE_ERROR");
  require(render.hardware.renders == failedRenders, "faulted drawing requires explicit release/reinitialization");
  render.hardware.render_ok = true; render.ok("display.release"); render.ok("display.begin");
  render.ok("display.fill", R"({"color":1})");
  Fixture running; running.setup(display(), servo()); running.start();
  running.ok("gpio.setup", R"({"pin":8,"mode":"output"})");
  running.ok("servo.move", R"({"device":"head","angle":90})");
  running.hardware.release_ok = false;
  running.error("session.close", "{}", "HARDWARE_ERROR");
  status = running.ok("device.status");
  require(!status["data"]["session_active"].as<bool>() && !status["data"]["display"]["driver_ok"].as<bool>(), "close ownership even when screen release fails");
  require(running.hardware.modes[8] == ai_maker::PinMode::Unset && running.hardware.pulse[14] == 0, "display cleanup fault cannot block GPIO or servo release");
}

void remapping_and_disable_release_old_pins() {
  Fixture f; f.setup(); f.start(); f.ok("maintenance.enter");
  const auto moved = replace(display(), "\"sck\":4", "\"sck\":18");
  f.ok("config.apply", f.applyArgs(config(moved))); f.ok("maintenance.exit");
  f.ok("gpio.setup", R"({"pin":4,"mode":"output"})");
  f.error("gpio.setup", R"({"pin":18,"mode":"output"})", "RESOURCE_CONFLICT");
  f.ok("maintenance.enter"); f.ok("config.apply", f.applyArgs(config("null"))); f.ok("maintenance.exit");
  f.ok("gpio.setup", R"({"pin":18,"mode":"output"})");
  require(!f.ok("device.status")["data"]["display"]["configured"].as<bool>(), "explicit null disables display");
}

void bitmap_streams_exact_bounded_big_endian_pixels() {
  Fixture f; f.setup(); f.start();
  require(f.ok("device.info")["data"]["capabilities"]["display_bitmap"].as<bool>(), "bitmap capability declared");
  const std::string bytes("\xF8\x00\x07\xE0\x00\x1F\xFF\xFF", 8);
  const std::string args = R"({"x":2,"y":3,"width":2,"height":2,"data":")" + ai_maker::encodePageBase64(bytes) + "\"}";
  const auto saved = f.hardware.state;
  auto result = f.ok("display.bitmap", args);
  require(f.hardware.pixels == std::vector<uint16_t>{0xF800,0x07E0,0x001F,0xFFFF}, "bitmap byte order converted to actual driver colors");
  require(!result["data"]["physical_verified"].as<bool>() && f.hardware.state == saved, "streaming is commanded only and never persists");
  for (const auto* bad : {R"({"x":0,"y":0,"width":2,"height":2,"data":"AA=="})",
                         R"({"x":0,"y":0,"width":2.0,"height":2,"data":"AAAAAAAAAAA="})",
                         R"({"x":319,"y":0,"width":2,"height":2,"data":"AAAAAAAAAAA="})",
                         R"({"x":0,"y":0,"width":2,"height":2,"data":"bad!"})"})
    f.error("display.bitmap", bad, "INVALID_ARGUMENT");
  const auto maximum = ai_maker::encodePageBase64(std::string(768, '\0'));
  f.ok("display.bitmap", R"({"x":0,"y":0,"width":192,"height":2,"data":")" + maximum + "\"}");
  require(f.hardware.pixels.size() == 384, "384-pixel bound inclusive");
  f.error("display.bitmap", R"({"x":0,"y":0,"width":193,"height":2,"data":")" + maximum + "\"}", "INVALID_ARGUMENT");
  f.hardware.render_ok = false;
  f.error("display.bitmap", args, "HARDWARE_ERROR");
}
}

int main() {
  const std::vector<std::pair<const char*, std::function<void()>>> tests = {
      {"capability_and_configuration_reserve_runtime_pins", capability_and_configuration_reserve_runtime_pins},
      {"display_configuration_survives_restart_without_motion", display_configuration_survives_restart_without_motion},
      {"strict_display_configuration_is_transactional", strict_display_configuration_is_transactional},
      {"display_geometry_and_driver_selection", display_geometry_and_driver_selection},
      {"screen_drawing_is_explicit_and_reports_commanded_only", screen_drawing_is_explicit_and_reports_commanded_only},
      {"coordinates_types_and_utf8_are_checked_before_render", coordinates_types_and_utf8_are_checked_before_render},
      {"backlight_has_explicit_support_and_budget", backlight_has_explicit_support_and_budget},
      {"release_paths_keep_configuration_and_close_ownership", release_paths_keep_configuration_and_close_ownership},
      {"failed_driver_cannot_claim_a_working_screen", failed_driver_cannot_claim_a_working_screen},
      {"remapping_and_disable_release_old_pins", remapping_and_disable_release_old_pins},
      {"bitmap_streams_exact_bounded_big_endian_pixels", bitmap_streams_exact_bounded_big_endian_pixels}};
  unsigned failures = 0;
  for (const auto& test : tests) {
    try { test.second(); std::cout << "PASS " << test.first << '\n'; }
    catch (const std::exception& error) { ++failures; std::cerr << "FAIL " << test.first << ": " << error.what() << '\n'; }
  }
  std::cout << tests.size() << " display tests, " << failures << " failures\n";
  return failures ? 1 : 0;
}
