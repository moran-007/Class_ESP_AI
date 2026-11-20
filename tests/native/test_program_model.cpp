#include "program_model.h"
#include <ArduinoJson.h>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
void require(bool value, const std::string& message) {
  if (!value) throw std::runtime_error(message);
}
std::string project(const std::string& steps, const std::string& config = R"({"schema_version":1,"servos":[]})") {
  return "{\"schema_version\":1,\"config\":" + config + ",\"steps\":" + steps + "}";
}
ai_maker::ProgramModel accept(const std::string& source) {
  ai_maker::ProgramModel model; std::string error;
  const bool parsed = ai_maker::parseProgram(source, model, error);
  require(parsed, "Expected accepted program: " + error);
  return model;
}
void reject(const std::string& source) {
  ai_maker::ProgramModel model; model.canonical = "unchanged";
  model.instructions.push_back({"sentinel", "{}", 7}); std::string error;
  require(!ai_maker::parseProgram(source, model, error), "Expected rejected program");
  require(!error.empty(), "Failure supplies an error");
  require(model.canonical == "unchanged" && model.instructions.size() == 1 && model.instructions[0].target == 7,
          "Failed validation must be transactional");
}
const std::string screen = R"({"schema_version":1,"servos":[],"display":{"panel":"st7735s_128x160","sck":4,"mosi":5,"cs":15,"dc":7,"rst":6,"backlight":16,"rotation":1,"invert":false,"brightness":60}})";
const std::string servo = R"({"schema_version":1,"servos":[{"name":"arm","pin":14,"min_angle":30,"max_angle":150,"min_pulse_us":1000,"max_pulse_us":2000}]})";
void valid_flat_program_and_canonical_roundtrip() {
  const auto model = accept(project(R"([{"op":"led.set","args":{"red":8,"green":3,"blue":0}},{"op":"wait","args":{"ms":1000}},{"op":"led.off","args":{}}])"));
  require(model.instructions.size() == 3 && model.instructions[1].op == "wait", "Flat instructions preserve order");
  require(accept(model.canonical).canonical == model.canonical, "Canonical roundtrip");
  require(model.config_json == R"({"schema_version":1,"servos":[]})", "Configuration is retained separately");
}
void conditional_targets_skip_exact_branches() {
  const auto model = accept(project(R"([{"op":"if.digital","args":{"pin":2,"value":0},"then":[{"op":"led.set","args":{"red":8,"green":0,"blue":0}}],"else":[{"op":"led.off","args":{}}]},{"op":"wait","args":{"ms":1}}])"));
  require(model.instructions.size() == 5 && model.instructions[0].target == 3, "False target starts else");
  require(model.instructions[2].op == "jump" && model.instructions[2].target == 4, "True branch skips else");
  require(model.instructions[4].op == "wait", "Following instruction remains reachable");
  const auto no_else = accept(project(R"([{"op":"if.analog","args":{"pin":1,"operator":">=","value":2048},"then":[{"op":"led.off","args":{}}]}])"));
  require(no_else.instructions[0].target == no_else.instructions.size(), "No-else target reaches end");
}
void strict_json_shape_types_and_unknown_operations() {
  for (const auto& source : {"{}", "[]", "null", "{\"schema_version\":true,\"config\":{},\"steps\":[]}"}) reject(source);
  reject(project("[]")); reject(project(R"([{"op":"jump","args":{}}])"));
  reject(project(R"([{"op":"wait","args":{"ms":true}}])"));
  reject(project(R"([{"op":"wait","args":{"ms":1.0}}])"));
  reject(project(R"([{"op":"wait","args":{"ms":"1"}}])"));
  reject(project(R"([{"op":"wait","args":{"ms":0}}])"));
  reject(project(R"([{"op":"wait","args":{"ms":60001}}])"));
  reject(project(R"([{"op":"led.off","args":{},"extra":1}])"));
  reject(project(R"([{"op":"led.set","args":{"red":0,"green":0,"blue":33}}])"));
  reject(project(R"([{"op":"led.off","args":null}])"));
  reject(project(R"([{"op":"led.off","args":{}},{"op":"network.request","args":{}}])"));
  reject(project(R"([{"op":"led.off","args":{}}])") + "{}");
  reject(project(R"([{"op":"led.off","args":{}}])") + std::string(1, '\0'));
}
void pin_modes_conditions_and_mapping_ownership() {
  accept(project(R"([{"op":"gpio.setup","args":{"pin":2,"mode":"input_pullup"}},{"op":"gpio.setup","args":{"pin":12,"mode":"output"}},{"op":"gpio.write","args":{"pin":12,"value":1}},{"op":"gpio.release","args":{"pin":12}},{"op":"pwm.write","args":{"pin":17,"duty":25}}])"));
  for (int pin : {19, 26, 46, 48, 22}) reject(project("[{\"op\":\"gpio.setup\",\"args\":{\"pin\":" + std::to_string(pin) + ",\"mode\":\"output\"}}]"));
  reject(project(R"([{"op":"gpio.setup","args":{"pin":2,"mode":"analog"}}])"));
  reject(project(R"([{"op":"gpio.write","args":{"pin":12,"value":true}}])"));
  reject(project(R"([{"op":"pwm.write","args":{"pin":17,"duty":101}}])"));
  reject(project(R"([{"op":"gpio.setup","args":{"pin":4,"mode":"output"}}])", screen));
  reject(project(R"([{"op":"if.digital","args":{"pin":14,"value":0},"then":[{"op":"led.off","args":{}}]}])", servo));
  reject(project(R"([{"op":"if.analog","args":{"pin":21,"operator":">","value":0},"then":[{"op":"led.off","args":{}}]}])"));
  reject(project(R"([{"op":"if.analog","args":{"pin":1,"operator":"contains","value":0},"then":[{"op":"led.off","args":{}}]}])"));
  for (const auto* operation : {"<", "<=", "==", "!=", ">=", ">"})
    accept(project(std::string(R"([{"op":"if.analog","args":{"pin":1,"operator":")") + operation + R"(","value":4095},"then":[{"op":"led.off","args":{}}],"else":[]}])"));
  reject(project(R"([{"op":"if.digital","args":{"pin":2,"value":0},"then":[]}])"));
}
void display_geometry_utf8_and_servo_calibration() {
  accept(project(R"([{"op":"display.begin","args":{}},{"op":"display.fill","args":{"color":0}},{"op":"display.text","args":{"text":"你好","x":8,"y":8,"color":65535}},{"op":"display.rect","args":{"x":8,"y":40,"width":80,"height":20,"color":65535,"filled":true}},{"op":"display.line","args":{"x0":0,"y0":0,"x1":159,"y1":127,"color":0}},{"op":"display.brightness","args":{"percent":20}},{"op":"display.release","args":{}}])", screen));
  reject(project(R"([{"op":"display.begin","args":{}}])"));
  reject(project(R"([{"op":"display.text","args":{"text":"bad\u0000text","x":0,"y":0,"color":0}}])", screen));
  reject(project(R"([{"op":"display.text","args":{"text":"x","x":160,"y":0,"color":0}}])", screen));
  reject(project(R"([{"op":"display.rect","args":{"x":159,"y":0,"width":2,"height":1,"color":0,"filled":true}}])", screen));
  reject(project(R"([{"op":"display.begin","args":{}}])", R"({"schema_version":1,"servos":[5],"display":true})"));
  accept(project(R"([{"op":"servo.move","args":{"device":"arm","angle":90}},{"op":"servo.release","args":{"device":"arm"}}])", servo));
  reject(project(R"([{"op":"servo.move","args":{"device":"arm","angle":20}}])", servo));
  reject(project(R"([{"op":"servo.release","args":{"device":"other"}}])", servo));
  reject(project(R"([{"op":"servo.move","args":{"device":"arm","angle":90}}])"));
}
void bounds_and_conditional_depth_are_enforced() {
  std::string steps = "[";
  for (int i = 0; i < 64; ++i) { if (i) steps += ','; steps += R"({"op":"led.off","args":{}})"; }
  accept(project(steps + "]"));
  reject(project(steps + R"(,{"op":"led.off","args":{}}])"));
  std::string nested = R"([{"op":"led.off","args":{}}])";
  for (int i = 0; i < 4; ++i) nested = R"([{"op":"if.digital","args":{"pin":2,"value":0},"then":)" + nested + "}]";
  accept(project(nested));
  reject(project(R"([{"op":"if.digital","args":{"pin":2,"value":0},"then":)" + nested + "}]"));
  reject(std::string(ai_maker::kMaxProgramBytes + 1, ' '));
}
}  // namespace

int main() {
  const std::vector<std::pair<const char*, std::function<void()>>> tests = {
      {"valid_flat_program_and_canonical_roundtrip", valid_flat_program_and_canonical_roundtrip},
      {"conditional_targets_skip_exact_branches", conditional_targets_skip_exact_branches},
      {"strict_json_shape_types_and_unknown_operations", strict_json_shape_types_and_unknown_operations},
      {"pin_modes_conditions_and_mapping_ownership", pin_modes_conditions_and_mapping_ownership},
      {"display_geometry_utf8_and_servo_calibration", display_geometry_utf8_and_servo_calibration},
      {"bounds_and_conditional_depth_are_enforced", bounds_and_conditional_depth_are_enforced}};
  int failures = 0;
  for (const auto& test : tests) {
    try { test.second(); std::cout << "PASS " << test.first << '\n'; }
    catch (const std::exception& e) { ++failures; std::cout << "FAIL " << test.first << ": " << e.what() << '\n'; }
  }
  std::cout << tests.size() << " program-model groups, " << failures << " failures\n";
  return failures ? 1 : 0;
}
