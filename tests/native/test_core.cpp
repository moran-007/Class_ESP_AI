#include "device_core.h"
#include "fake_hardware.h"
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
void require(bool value, const std::string& message) {
  if (!value) throw std::runtime_error(message);
}

struct Fixture {
  FakeHardware hardware;
  ai_maker::DeviceCore core{hardware};
  uint32_t now = 100;
  unsigned sequence = 0;
  std::string session = "native-session";
  Fixture() { core.begin(); }
  JsonDocument call(const std::string& op, const std::string& args = "{}",
                    const std::string& identity = "native-session") {
    JsonDocument request, arguments, reply;
    request["kind"] = "request";
    request["protocol_version"] = 1;
    const std::string id = "test-" + std::to_string(++sequence);
    request["request_id"] = id;
    request["session_id"] = identity;
    request["op"] = op;
    require(!deserializeJson(arguments, args), "test args must be JSON");
    std::string line;
    serializeJson(request, line);
    // Preserve the supplied JSON number spelling: reserializing an ArduinoJson
    // double such as 4.0 can produce 4 and invalidate strict-input tests.
    line.pop_back();
    line += ",\"args\":" + args + "}";
    const auto output = core.process(line, now);
    require(!deserializeJson(reply, output), "reply must be JSON: " + output);
    require(reply["kind"] == "response", "reply kind must be response");
    require(reply["protocol_version"] == 1, "reply protocol must be v1");
    require(reply["request_id"] == id, "reply must preserve request ID");
    return reply;
  }
  JsonDocument ok(const std::string& op, const std::string& args = "{}") {
    auto result = call(op, args, session);
    require(result["ok"].as<bool>(), op + " failed: " + result["code"].as<std::string>());
    return result;
  }
  void error(const std::string& op, const std::string& args, const char* code) {
    auto result = call(op, args, session);
    require(!result["ok"].as<bool>(), op + " unexpectedly succeeded");
    require(result["code"] == code, op + " expected " + code + ", got " + result["code"].as<std::string>());
  }
  void open() { ok("session.open"); }
  void configure(int pin = 12) {
    ok("maintenance.enter");
    const auto existing = ok("config.get");
    const auto revision = existing["data"]["revision"].as<unsigned>();
    ok("config.apply", "{\"expected_revision\":" + std::to_string(revision) +
       ",\"config\":{\"schema_version\":1,\"servos\":[{\"name\":\"head\",\"pin\":" +
       std::to_string(pin) + ",\"min_angle\":30,\"max_angle\":150,\"min_pulse_us\":500,\"max_pulse_us\":2500}]}}");
  }
};

std::string configArgs(const std::string& list, unsigned revision = 0) {
  return "{\"expected_revision\":" + std::to_string(revision) +
         ",\"config\":{\"schema_version\":1,\"servos\":" + list + "}}";
}

void info_and_default_configuration() {
  Fixture f;
  const auto reply = f.ok("device.info");
  const auto info = reply["data"];
  require(info["firmware_family"] == "ai-maker-s3", "teaching firmware family");
  require(info["firmware_version"] == "0.8.0", "teaching firmware version");
  require(info["target"] == "esp32s3" && info["protocol_version"] == 1, "S3 protocol target");
  for (const auto* name : {"gpio", "adc", "pwm", "servo", "configurable_servo_pins", "display", "configurable_display_pins"})
    require(info["capabilities"][name].is<bool>() && info["capabilities"][name].as<bool>(), std::string("implemented capability ") + name);
  for (const auto* name : {"sd", "student_web", "ai"})
    require(info["capabilities"][name].is<bool>() && !info["capabilities"][name].as<bool>(), std::string("future capability ") + name);
  const auto config = f.ok("config.get");
  require(config["data"]["revision"] == 0 && config["data"]["config"]["servos"].size() == 0, "empty initial profile");
  require(f.hardware.servo_writes == 0, "no startup servo pulse");
}

void session_ownership() {
  Fixture f;
  f.error("gpio.setup", R"({"pin":4,"mode":"output"})", "SESSION_REQUIRED");
  f.open();
  auto other = f.call("session.open", "{}", "other-session");
  require(!other["ok"].as<bool>() && other["code"] == "DEVICE_BUSY", "second session cannot take ownership");
  require(!f.call("gpio.setup", R"({"pin":4,"mode":"output"})", "other-session")["ok"].as<bool>(), "foreign identity cannot output");
  f.ok("session.heartbeat");
}

void gpio_modes_and_release() {
  Fixture f;
  f.open();
  f.ok("gpio.setup", R"({"pin":4,"mode":"output"})");
  f.ok("gpio.write", R"({"pin":4,"value":1})");
  require(f.hardware.digital[4] == 1, "digital adapter must receive write");
  auto read = f.ok("gpio.read", R"({"pin":4})");
  require(read["data"]["value"] == 1 && read["data"]["source"] == "commanded", "output reads last commanded level");
  f.ok("gpio.release", R"({"pin":4})");
  require(f.hardware.modes[4] == ai_maker::PinMode::Unset, "released pin high impedance");
  require(!f.call("gpio.write", R"({"pin":4,"value":1})")["ok"].as<bool>(), "write requires setup");
  f.ok("gpio.setup", R"({"pin":4,"mode":"input_pullup"})");
  require(!f.call("gpio.write", R"({"pin":4,"value":1})")["ok"].as<bool>(), "cannot write input");
  f.hardware.digital[4] = 1;
  read = f.ok("gpio.read", R"({"pin":4})");
  require(read["data"]["value"] == 1 && read["data"]["source"] == "input", "input reads actual adapter level");
}

void adc_and_pin_capabilities() {
  Fixture f;
  f.open();
  f.ok("gpio.setup", R"({"pin":1,"mode":"input"})");
  const auto result = f.ok("adc.read", R"({"pin":1})");
  require(result["data"]["raw"] == 1234 && result["data"]["bits"] == 12, "raw 12-bit ADC contract");
  const int digitalOnly = ai_maker::kBuiltinRgbPin == 38 ? 48 : 38;
  const std::string digitalArgs = "{\"pin\":" + std::to_string(digitalOnly);
  f.ok("gpio.setup", digitalArgs + ",\"mode\":\"input\"}");
  f.error("adc.read", digitalArgs + "}", "PIN_CAPABILITY_MISMATCH");
  require(ai_maker::DeviceCore::reservedPin(ai_maker::kBuiltinRgbPin), "selected RGB pin is reserved");
  require(!ai_maker::DeviceCore::reservedPin(digitalOnly), "unselected RGB candidate remains available");
  f.error("gpio.setup", R"({"pin":23,"mode":"output"})", "PIN_INVALID");
  f.error("gpio.setup", R"({"pin":19,"mode":"output"})", "PIN_RESERVED");
  f.error("gpio.setup", R"({"pin":26,"mode":"output"})", "PIN_RESERVED");
  const auto pins = f.ok("pins.list");
  bool analog = false, usb = false;
  for (auto pin : pins["data"]["pins"].as<JsonArrayConst>()) {
    if (pin["pin"] == 1) analog = pin["adc"].as<bool>();
    if (pin["pin"] == 19) usb = pin["reserved"].as<bool>();
  }
  require(analog && usb, "pin list must describe analog and reserved resources");
}

void pwm_contract() {
  Fixture f;
  f.open();
  f.ok("gpio.setup", R"({"pin":5,"mode":"pwm"})");
  auto reply = f.ok("pwm.write", R"({"pin":5,"duty":25})");
  require(reply["data"]["frequency_hz"] == 1000 && f.hardware.pwm[5] == 25, "fixed-frequency percentage PWM");
  f.error("pwm.write", R"({"pin":5,"duty":101})", "INVALID_ARGUMENT");
  f.error("pwm.write", R"({"pin":5,"duty":-1})", "INVALID_ARGUMENT");
}

void strict_numeric_json() {
  Fixture f;
  f.open();
  for (const auto* value : {"true", "4.0", "\"4\""})
    require(!f.call("gpio.setup", "{\"pin\":" + std::string(value) + ",\"mode\":\"output\"}")["ok"].as<bool>(), "integer pin without coercion");
  f.ok("gpio.setup", R"({"pin":4,"mode":"output"})");
  for (const auto* value : {"true", "1.0", "\"1\""})
    require(!f.call("gpio.write", "{\"pin\":4,\"value\":" + std::string(value) + "}")["ok"].as<bool>(), "integer value without coercion");
}

void servo_limits_and_no_feedback() {
  Fixture f;
  f.open();
  f.configure();
  require(f.hardware.servo_writes == 0, "configuration cannot move servo");
  f.error("servo.move", R"({"device":"head","angle":90})", "MAINTENANCE_REQUIRED");
  f.ok("maintenance.exit");
  f.error("servo.move", R"({"device":"head","angle":29})", "ANGLE_OUT_OF_RANGE");
  f.error("servo.move", R"({"device":"head","angle":151})", "ANGLE_OUT_OF_RANGE");
  const auto moved = f.ok("servo.move", R"({"device":"head","angle":90})");
  require(moved["data"]["state"] == "commanded", "servo reports commanded state");
  require(moved["data"]["position_verified"].is<bool>() && !moved["data"]["position_verified"].as<bool>(), "open-loop servo cannot claim measured arrival");
  require(f.hardware.pulse[12] == 1500, "90 degree midpoint pulse");
  f.ok("servo.move", R"({"device":"head","angle":30})");
  require(f.hardware.pulse[12] >= 832 && f.hardware.pulse[12] <= 834, "limits do not redefine full pulse calibration");
  f.ok("servo.release", R"({"device":"head"})");
  require(f.hardware.pulse[12] == 0, "release withdraws pulses");
}

void configured_servo_owns_pin() {
  Fixture f;
  f.open(); f.configure(); f.ok("maintenance.exit");
  f.error("gpio.setup", R"({"pin":12,"mode":"output"})", "RESOURCE_CONFLICT");
  f.error("servo.move", R"({"device":"missing","angle":90})", "DEVICE_NOT_FOUND");
}

void maintenance_survives_restart() {
  Fixture f;
  f.open(); f.configure();
  ai_maker::DeviceCore restarted(f.hardware);
  restarted.begin();
  JsonDocument reply;
  deserializeJson(reply, restarted.process(R"({"kind":"request","protocol_version":1,"request_id":"boot-check","op":"device.status","args":{}})", 0));
  require(reply["ok"].as<bool>() && reply["data"]["maintenance"].as<bool>(), "durable maintenance flag");
  require(reply["data"]["config_revision"] == 1, "durable committed revision");
  require(f.hardware.servo_writes == 0, "restart cannot start servo");
}

void configuration_requires_maintenance_and_revision() {
  Fixture f;
  f.open();
  f.error("config.apply", configArgs("[]"), "MAINTENANCE_REQUIRED");
  f.configure();
  f.error("config.apply", configArgs("[]", 0), "CONFIG_REVISION_MISMATCH");
  const auto result = f.ok("config.get");
  require(result["data"]["revision"] == 1 && result["data"]["config"]["servos"].size() == 1, "stale write cannot publish");
}

void invalid_configuration_is_transactional() {
  Fixture f;
  f.open(); f.ok("maintenance.enter");
  const std::vector<std::string> lists = {
      R"([{"name":"head","pin":12,"min_angle":30,"max_angle":150,"min_pulse_us":500,"max_pulse_us":2500},{"name":"other","pin":12,"min_angle":30,"max_angle":150,"min_pulse_us":500,"max_pulse_us":2500}])",
      R"([{"name":"head","pin":19,"min_angle":30,"max_angle":150,"min_pulse_us":500,"max_pulse_us":2500}])",
      R"([{"name":"head","pin":23,"min_angle":30,"max_angle":150,"min_pulse_us":500,"max_pulse_us":2500}])",
      R"([{"name":"head","pin":12,"min_angle":150,"max_angle":30,"min_pulse_us":500,"max_pulse_us":2500}])",
      R"([{"name":"head","pin":12,"min_angle":30,"max_angle":150,"min_pulse_us":499,"max_pulse_us":2500}])",
      R"([{"name":"head","pin":12,"min_angle":30,"max_angle":150,"min_pulse_us":500,"max_pulse_us":2500,"typo":1}])",
      R"([{"name":"1head","pin":12,"min_angle":30,"max_angle":150,"min_pulse_us":500,"max_pulse_us":2500}])",
      R"([{"name":"head","pin":true,"min_angle":30,"max_angle":150,"min_pulse_us":500,"max_pulse_us":2500}])"};
  for (const auto& list : lists) {
    require(!f.call("config.apply", configArgs(list))["ok"].as<bool>(), "invalid mapping must fail");
    const auto current = f.ok("config.get");
    require(current["data"]["revision"] == 0 && current["data"]["config"]["servos"].size() == 0, "failed config leaves old profile");
  }
  require(f.hardware.servo_writes == 0, "invalid config cannot emit pulses");
}

void config_schema_and_types() {
  Fixture f;
  f.open(); f.ok("maintenance.enter");
  for (const auto* args : {
           R"({"expected_revision":0,"config":{"schema_version":1,"servos":[],"unknown":true}})",
           R"({"expected_revision":0,"config":{"schema_version":true,"servos":[]}})",
           R"({"expected_revision":false,"config":{"schema_version":1,"servos":[]}})",
           R"({"expected_revision":0,"config":{"schema_version":1,"servos":[{"name":"head","pin":12}]}})"})
    require(!f.call("config.apply", args)["ok"].as<bool>(), "bad config shape/type must fail");
}

void save_failure_keeps_old_configuration() {
  Fixture f;
  f.open(); f.configure();
  const auto old = f.hardware.state;
  f.hardware.save_ok = false;
  f.error("config.apply", configArgs(R"([{"name":"head","pin":13,"min_angle":30,"max_angle":150,"min_pulse_us":500,"max_pulse_us":2500}])", 1), "STORAGE_ERROR");
  const auto current = f.ok("config.get");
  require(current["data"]["revision"] == 1 && current["data"]["config"]["servos"][0]["pin"] == 12, "failed save cannot publish candidate");
  require(f.hardware.state == old && f.hardware.servo_writes == 0, "failed save preserves durable state and no motion");
}

void remapping_stops_old_output() {
  Fixture f;
  f.open(); f.configure(); f.ok("maintenance.exit");
  f.ok("servo.move", R"({"device":"head","angle":90})");
  f.configure(13);
  require(f.hardware.pulse[12] == 0 && f.hardware.pulse[13] == 0, "remap stops old and never starts new output");
  f.ok("maintenance.exit");
  f.ok("servo.move", R"({"device":"head","angle":90})");
  require(f.hardware.pulse[12] == 0 && f.hardware.pulse[13] == 1500, "explicit action uses new pin");
  f.ok("gpio.setup", R"({"pin":12,"mode":"output"})");
}

void lease_releases_all_output_types() {
  Fixture f;
  f.open(); f.configure(); f.ok("maintenance.exit");
  f.ok("gpio.setup", R"({"pin":4,"mode":"output"})"); f.ok("gpio.write", R"({"pin":4,"value":1})");
  f.ok("gpio.setup", R"({"pin":5,"mode":"pwm"})"); f.ok("pwm.write", R"({"pin":5,"duty":25})");
  f.ok("servo.move", R"({"device":"head","angle":90})");
  f.core.tick(f.now + ai_maker::kLeaseMs + 1);
  require(f.hardware.digital[4] == 0 && f.hardware.pwm[5] == 0 && f.hardware.pulse[12] == 0, "timeout withdraws GPIO/PWM/servo");
  require(f.hardware.modes[4] == ai_maker::PinMode::Unset, "timeout releases GPIO mode");
  f.now += ai_maker::kLeaseMs + 1;
  f.error("servo.move", R"({"device":"head","angle":90})", "SESSION_REQUIRED");
}

void lease_wraparound() {
  Fixture f;
  f.now = std::numeric_limits<uint32_t>::max() - 100;
  f.open(); f.ok("gpio.setup", R"({"pin":4,"mode":"output"})"); f.ok("gpio.write", R"({"pin":4,"value":1})");
  f.core.tick(f.now + 200);
  require(f.hardware.digital[4] == 1, "wrap cannot expire fresh session");
  f.core.tick(f.now + ai_maker::kLeaseMs + 1);
  require(f.hardware.digital[4] == 0, "timeout across uint32 wrap");
}

void close_and_stop() {
  Fixture f;
  f.open(); f.ok("gpio.setup", R"({"pin":4,"mode":"output"})"); f.ok("gpio.write", R"({"pin":4,"value":1})");
  f.ok("outputs.stop");
  require(f.hardware.digital[4] == 0, "stop releases outputs");
  require(f.ok("device.status")["data"]["session_active"].as<bool>(), "stop keeps session");
  f.ok("session.close");
  require(!f.ok("device.status")["data"]["session_active"].as<bool>(), "close ends session");
  f.error("session.heartbeat", "{}", "SESSION_REQUIRED");
}

void corrupt_storage_is_recoverable() {
  FakeHardware hardware;
  hardware.state = "not-json";
  ai_maker::DeviceCore core(hardware);
  core.begin();
  JsonDocument reply;
  deserializeJson(reply, core.process(R"({"kind":"request","protocol_version":1,"request_id":"query","op":"device.status","args":{}})", 0));
  require(reply["ok"].as<bool>() && reply["data"]["maintenance"].as<bool>(), "corrupt state enters maintenance");
  require(hardware.state == "not-json" && hardware.servo_writes == 0, "do not format corrupt state or move servo");
}

void bounded_malformed_requests() {
  Fixture f;
  for (const auto* line : {"not-json", "[]",
           R"({"kind":"request","protocol_version":1,"request_id":"","op":"device.info","args":{}})",
           R"({"kind":"request","protocol_version":1,"request_id":"id","op":"device.info","args":[]})"}) {
    JsonDocument reply;
    require(!deserializeJson(reply, f.core.process(line, f.now)), "bad requests need structured errors");
    require(!reply["ok"].as<bool>(), "malformed request cannot succeed");
  }
  JsonDocument reply;
  deserializeJson(reply, f.core.process(std::string(ai_maker::kMaxLine + 1, 'x'), f.now));
  require(!reply["ok"].as<bool>() && reply["code"] == "LINE_TOO_LONG", "line length bounded");
  deserializeJson(reply, f.core.process(R"({"kind":"request","protocol_version":2,"request_id":"id","op":"device.info","args":{}})", f.now));
  require(!reply["ok"].as<bool>() && reply["code"] == "PROTOCOL_MISMATCH", "protocol mismatch rejected");
  f.open(); f.error("not.an.operation", "{}", "UNSUPPORTED_OPERATION");
}

void hardware_failure_not_success() {
  Fixture f;
  f.open(); f.ok("gpio.setup", R"({"pin":4,"mode":"output"})");
  f.hardware.output_ok = false;
  f.error("gpio.write", R"({"pin":4,"value":1})", "HARDWARE_ERROR");
  require(f.hardware.digital[4] == 0, "failed adapter must not model successful write");
}

void pwm_resource_limit_and_reuse() {
  Fixture f;
  f.open();
  for (int pin : {4, 5, 6, 7})
    f.ok("gpio.setup", "{\"pin\":" + std::to_string(pin) + ",\"mode\":\"pwm\"}");
  f.error("gpio.setup", R"({"pin":8,"mode":"pwm"})", "RESOURCE_CONFLICT");
  require(f.hardware.modes[8] == ai_maker::PinMode::Unset, "rejected fifth PWM cannot configure hardware");
  f.ok("gpio.release", R"({"pin":4})");
  f.ok("gpio.setup", R"({"pin":8,"mode":"pwm"})");
  require(f.hardware.modes[8] == ai_maker::PinMode::Pwm, "released PWM slot can be reused");
}

void servo_count_limit() {
  Fixture f;
  f.open(); f.ok("maintenance.enter");
  std::string list = "[";
  for (int i = 0; i < 5; ++i) {
    if (i) list += ',';
    list += "{\"name\":\"servo" + std::to_string(i) + "\",\"pin\":" + std::to_string(4 + i) +
            ",\"min_angle\":30,\"max_angle\":150,\"min_pulse_us\":500,\"max_pulse_us\":2500}";
  }
  list += ']';
  require(!f.call("config.apply", configArgs(list))["ok"].as<bool>(), "fifth servo must be rejected before publish");
  require(f.ok("config.get")["data"]["revision"] == 0, "over-limit config cannot advance revision");
}

void heartbeat_renews_but_public_queries_do_not() {
  Fixture f;
  f.open(); f.ok("gpio.setup", R"({"pin":4,"mode":"output"})"); f.ok("gpio.write", R"({"pin":4,"value":1})");
  f.now += 5000;
  f.ok("session.heartbeat");
  f.core.tick(f.now + 5000);
  require(f.hardware.digital[4] == 1, "valid heartbeat renews the lease");
  f.now += 5000;
  f.ok("device.status");
  require(!f.call("session.heartbeat", "{}", "other-session")["ok"].as<bool>(), "foreign heartbeat rejected");
  f.now += 1001;
  f.ok("device.info");
  require(f.hardware.digital[4] == 0, "queries and foreign heartbeat must not renew output ownership");
}

void led_commands_report_only_commanded_state() {
  Fixture f;
  require(f.ok("device.info")["data"]["capabilities"]["builtin_led"].as<bool>(), "firmware must declare builtin LED capability");
  f.error("led.set", R"({"red":2,"green":3,"blue":4})", "SESSION_REQUIRED");
  f.open();
  const auto result = f.ok("led.set", R"({"red":2,"green":3,"blue":4})");
  require(f.hardware.led == std::array<int, 3>{2, 3, 4}, "LED RGB values reach adapter");
  require(result["data"]["red"] == 2 && result["data"]["green"] == 3 && result["data"]["blue"] == 4,
          "LED response exposes commanded RGB");
  require(result["data"]["state"] == "commanded" && result["data"]["physical_verified"].is<bool>() &&
          !result["data"]["physical_verified"].as<bool>(), "software response cannot claim observed physical LED state");
  auto status = f.ok("device.status");
  require(status["data"]["led"]["red"] == 2 && status["data"]["led"]["green"] == 3 && status["data"]["led"]["blue"] == 4,
          "LED status reflects last command");
  f.ok("led.off");
  require(f.hardware.led == std::array<int, 3>{0, 0, 0}, "LED off writes zero RGB");
  f.ok("maintenance.enter");
  f.error("led.set", R"({"red":2,"green":3,"blue":4})", "MAINTENANCE_REQUIRED");
}

void led_range_and_types_are_strict() {
  Fixture f;
  f.open();
  for (const auto* value : {"-1", "33", "true", "2.0", "\"2\""}) {
    f.error("led.set", "{\"red\":" + std::string(value) + ",\"green\":0,\"blue\":0}", "INVALID_ARGUMENT");
    f.error("led.set", "{\"red\":0,\"green\":" + std::string(value) + ",\"blue\":0}", "INVALID_ARGUMENT");
    f.error("led.set", "{\"red\":0,\"green\":0,\"blue\":" + std::string(value) + "}", "INVALID_ARGUMENT");
  }
  f.error("led.set", R"({"red":1,"green":2})", "INVALID_ARGUMENT");
  f.ok("led.set", R"({"red":32,"green":0,"blue":32})");
  require(f.hardware.led == std::array<int, 3>{32, 0, 32}, "RGB limit is inclusive");
}

void led_is_released_by_stop_close_and_timeout() {
  for (const std::string action : {"stop", "close", "timeout", "maintenance"}) {
    Fixture f;
    f.open();
    f.ok("led.set", R"({"red":4,"green":5,"blue":6})");
    if (action == "stop") f.ok("outputs.stop");
    else if (action == "close") f.ok("session.close");
    else if (action == "maintenance") f.ok("maintenance.enter");
    else f.core.tick(f.now + ai_maker::kLeaseMs + 1);
    require(f.hardware.led == std::array<int, 3>{0, 0, 0}, "LED must clear on " + action);
    f.now += action == "timeout" ? ai_maker::kLeaseMs + 1 : 0;
    const auto status = f.ok("device.status");
    require(status["data"]["led"]["red"] == 0 && status["data"]["led"]["green"] == 0 && status["data"]["led"]["blue"] == 0,
            "LED cleared status on " + action);
  }
}

void boot_clears_a_previously_latched_pixel() {
  FakeHardware hardware;
  hardware.led = {24, 24, 24};  // A pixel can survive an MCU-only reset.
  ai_maker::DeviceCore core(hardware);
  core.begin();
  require(hardware.led == std::array<int, 3>{0, 0, 0}, "boot must clear a pixel left by diagnostic firmware");
}

void led_stop_failure_is_visible_and_releases_other_outputs() {
  for (const std::string action : {"outputs.stop", "session.close", "timeout"}) {
    Fixture f;
    f.open();
    f.ok("led.set", R"({"red":4,"green":5,"blue":6})");
    f.ok("gpio.setup", R"({"pin":12,"mode":"output"})");
    f.hardware.output_ok = false;
    if (action == "timeout") f.core.tick(f.now + ai_maker::kLeaseMs);
    else f.error(action, "{}", "HARDWARE_ERROR");
    require(f.hardware.modes[12] == ai_maker::PinMode::Unset, "RGB failure must not prevent GPIO release");
    if (action == "timeout") f.now += ai_maker::kLeaseMs;
    auto status = f.ok("device.status");
    require(status["data"]["led"]["driver_ok"].is<bool>() && !status["data"]["led"]["driver_ok"].as<bool>(),
            "status must expose failed LED driver rather than claim off");
    require(status["data"]["led"]["red"] == 4, "retain last successful color when off failed");
    if (action != "outputs.stop") require(!status["data"]["session_active"].as<bool>(), "failed cleanup still closes ownership");
    f.hardware.output_ok = true;
    if (action != "outputs.stop") f.open();
    f.ok("outputs.stop");
    status = f.ok("device.status");
    require(status["data"]["led"]["driver_ok"].as<bool>() && status["data"]["led"]["red"] == 0,
            "successful retry updates LED state");
  }
}

void protocol_strings_reject_nul_and_excessive_length() {
  Fixture f;
  const std::vector<std::string> lines = {
      R"({"kind":"request","protocol_version":1,"request_id":"valid\u0000tail","op":"device.info","args":{}})",
      "{\"kind\":\"request\",\"protocol_version\":1,\"request_id\":\"ok\\u0000" + std::string(100, 'x') + "\",\"op\":\"device.info\",\"args\":{}}",
      "{\"kind\":\"request\",\"protocol_version\":1,\"request_id\":\"" + std::string(65, 'x') + "\",\"op\":\"device.info\",\"args\":{}}",
      R"({"kind":"request","protocol_version":1,"request_id":"id","session_id":"native-session\u0000tail","op":"session.open","args":{}})",
      "{\"kind\":\"request\",\"protocol_version\":1,\"request_id\":\"id\",\"session_id\":\"ok\\u0000" + std::string(100, 'x') + "\",\"op\":\"session.open\",\"args\":{}}",
      "{\"kind\":\"request\",\"protocol_version\":1,\"request_id\":\"id\",\"session_id\":\"" + std::string(41, 'x') + "\",\"op\":\"session.open\",\"args\":{}}",
      R"({"kind":"request","protocol_version":1,"request_id":"id","op":"device.info\u0000tail","args":{}})",
      "{\"kind\":\"request\",\"protocol_version\":1,\"request_id\":\"id\",\"op\":\"" + std::string(100, 'x') + "\",\"args\":{}}",
      R"({"kind":"request\u0000tail","protocol_version":1,"request_id":"id","op":"device.info","args":{}})",
      "{\"kind\":\"request" + std::string(100, 'x') + "\",\"protocol_version\":1,\"request_id\":\"id\",\"op\":\"device.info\",\"args\":{}}"};
  for (size_t index = 0; index < lines.size(); ++index) {
    JsonDocument reply;
    require(!deserializeJson(reply, f.core.process(lines[index], f.now)), "bad protocol strings must return structured error");
    require(!reply["ok"].as<bool>(), "protocol string case " + std::to_string(index) + " must be rejected");
  }
}
}  // namespace

int main() {
  const std::vector<std::pair<const char*, std::function<void()>>> tests = {
      {"info_and_default_configuration", info_and_default_configuration}, {"session_ownership", session_ownership},
      {"gpio_modes_and_release", gpio_modes_and_release}, {"adc_and_pin_capabilities", adc_and_pin_capabilities},
      {"pwm_contract", pwm_contract}, {"strict_numeric_json", strict_numeric_json},
      {"servo_limits_and_no_feedback", servo_limits_and_no_feedback}, {"configured_servo_owns_pin", configured_servo_owns_pin},
      {"maintenance_survives_restart", maintenance_survives_restart}, {"configuration_requires_maintenance_and_revision", configuration_requires_maintenance_and_revision},
      {"invalid_configuration_is_transactional", invalid_configuration_is_transactional}, {"config_schema_and_types", config_schema_and_types},
      {"save_failure_keeps_old_configuration", save_failure_keeps_old_configuration}, {"remapping_stops_old_output", remapping_stops_old_output},
      {"lease_releases_all_output_types", lease_releases_all_output_types}, {"lease_wraparound", lease_wraparound},
      {"close_and_stop", close_and_stop}, {"corrupt_storage_is_recoverable", corrupt_storage_is_recoverable},
      {"bounded_malformed_requests", bounded_malformed_requests}, {"hardware_failure_not_success", hardware_failure_not_success},
      {"pwm_resource_limit_and_reuse", pwm_resource_limit_and_reuse}, {"servo_count_limit", servo_count_limit},
      {"heartbeat_renews_but_public_queries_do_not", heartbeat_renews_but_public_queries_do_not},
      {"led_commands_report_only_commanded_state", led_commands_report_only_commanded_state},
      {"led_range_and_types_are_strict", led_range_and_types_are_strict},
      {"led_is_released_by_stop_close_and_timeout", led_is_released_by_stop_close_and_timeout},
      {"boot_clears_a_previously_latched_pixel", boot_clears_a_previously_latched_pixel},
      {"led_stop_failure_is_visible_and_releases_other_outputs", led_stop_failure_is_visible_and_releases_other_outputs},
      {"protocol_strings_reject_nul_and_excessive_length", protocol_strings_reject_nul_and_excessive_length}};
  unsigned failures = 0;
  for (const auto& test : tests) {
    try { test.second(); std::cout << "PASS " << test.first << '\n'; }
    catch (const std::exception& error) { ++failures; std::cerr << "FAIL " << test.first << ": " << error.what() << '\n'; }
  }
  std::cout << tests.size() << " tests, " << failures << " failures\n";
  return failures == 0 ? 0 : 1;
}
