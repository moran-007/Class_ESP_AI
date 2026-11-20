#include "program_model.h"
#include <ArduinoJson.h>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
void require(bool value, const std::string& why) { if (!value) throw std::runtime_error(why); }
std::string json(JsonVariantConst value) { std::string result; serializeJson(value, result); return result; }
const std::string screen = R"({"schema_version":1,"servos":[],"display":{"panel":"st7735s_128x160","sck":4,"mosi":5,"cs":15,"dc":7,"rst":6,"backlight":16,"rotation":1,"invert":false,"brightness":60}})";
const std::string counter = R"({"op":"display.counter","args":{"name":"count","start":0,"step":1,"interval_ms":1000,"x":8,"y":40,"width":144,"height":20,"color":65535,"background":0}})";
std::string project(const std::string& steps, const std::string& config = screen) {
  return "{\"schema_version\":1,\"config\":" + config + ",\"steps\":" + steps + "}";
}
ai_maker::ProgramModel accept(const std::string& text) {
  ai_maker::ProgramModel model; std::string error;
  const bool parsed = ai_maker::parseProgram(text, model, error);
  require(parsed, "Counter model should be accepted: " + error);
  return model;
}
void reject(const std::string& text) {
  ai_maker::ProgramModel model; model.canonical = "unchanged";
  model.has_counter = true;
  model.instructions.push_back({"sentinel", "{}", 7}); std::string error;
  require(!ai_maker::parseProgram(text, model, error), "Counter model must reject invalid input: " + text);
  require(!error.empty(), "Rejected input supplies explanation");
  require(model.has_counter && model.canonical == "unchanged" && model.instructions.size() == 1 && model.instructions[0].target == 7,
          "Rejected counter must preserve prior model");
}
std::string withArg(const std::string& key, const std::string& literal) {
  // Keep numeric lexemes verbatim: serializing a parsed1.0 would become1 and
  // accidentally test an integer instead of the intended floating-point value.
  std::string step = counter;
  const auto marker = "\"" + key + "\":";
  const size_t position = step.find(marker);
  require(position != std::string::npos, "fixture contains requested argument");
  const size_t start = position + marker.size(), end = step.find_first_of(",}", start);
  step.replace(start, end - start, literal);
  return project("[" + step + "]");
}
void valid_counter_and_legacy_programs() {
  const auto model = accept(project("[{\"op\":\"display.begin\",\"args\":{}}," + counter + "]"));
  require(model.instructions.size() == 2 && model.instructions[1].op == "display.counter", "Counter is retained after display initialization");
  require(model.has_counter, "Counter capability is explicit");
  require(accept(model.canonical).canonical == model.canonical, "Counter canonical roundtrip");
  const auto legacy = accept(project(R"([{"op":"led.off","args":{}}])", R"({"schema_version":1,"servos":[]})"));
  require(legacy.instructions.size() == 1 && legacy.instructions[0].op == "led.off", "Legacy schema1 remains accepted");
  require(!legacy.has_counter, "Legacy flow has no counter capability");
}
void int64_start_is_exact_and_strict() {
  const auto model = accept(withArg("start", "9223372036854775807"));
  require(model.canonical.find("9223372036854775807") != std::string::npos, "INT64_MAX serialization is exact");
  for (const auto* value : {"-1", "9223372036854775808", "18446744073709551615", "18446744073709551616", "true", "1.0", "1e0", "\"1\"", "null"}) reject(withArg("start", value));
}
void args_schema_ranges_and_name_are_strict() {
  for (const auto* value : {"0", "-1", "2147483648", "true", "1.0", "\"1\""}) reject(withArg("step", value));
  accept(withArg("step", "2147483647"));
  for (const auto* value : {"49", "60001", "true", "1.0", "\"1000\""}) reject(withArg("interval_ms", value));
  accept(withArg("interval_ms", "50")); accept(withArg("interval_ms", "60000"));
  for (const auto* value : {"\"\"", "\"1count\"", "\"bad-name\"", "\"abcdefghijklmnopqrstuvwxy\"", "true", "\"nul\\u0000tail\""}) reject(withArg("name", value));
  accept(withArg("name", "\"A_count9\""));
  accept(withArg("name", "\"abcdefghijklmnopqrstuvwx\""));
  for (const auto* key : {"color", "background"}) {
    for (const auto* value : {"-1", "65536", "true", "1.0"}) reject(withArg(key, value));
  }
  JsonDocument step; deserializeJson(step, counter);
  step["args"]["unexpected"] = 1; reject(project("[" + json(step.as<JsonVariantConst>()) + "]"));
  step["args"].remove("unexpected"); step["args"].remove("name"); reject(project("[" + json(step.as<JsonVariantConst>()) + "]"));
}
void requires_screen_and_reserved_rectangle() {
  reject(project("[" + counter + "]", R"({"schema_version":1,"servos":[]})"));
  for (const auto& pair : std::vector<std::pair<std::string, std::string>>{
      {"width", "132"}, {"height", "15"}, {"width", "153"}, {"height", "89"}, {"x", "-1"}, {"y", "128"}, {"x", "true"}})
    reject(withArg(pair.first, pair.second));
  accept(withArg("width", "133")); accept(withArg("height", "16"));
  JsonDocument config, step; deserializeJson(config, screen); deserializeJson(step, counter);
  config["display"]["rotation"] = 0; step["args"]["width"] = 120;
  reject(project("[" + json(step.as<JsonVariantConst>()) + "]", json(config.as<JsonVariantConst>())));
  config["display"]["panel"] = "st7789_240x320"; step["args"]["width"] = 144;
  accept(project("[" + json(step.as<JsonVariantConst>()) + "]", json(config.as<JsonVariantConst>())));
}
void counter_is_terminal_and_not_a_branch() {
  reject(project("[" + counter + R"(,{"op":"led.off","args":{}}])"));
  reject(project("[" + counter + "," + counter + "]"));
  reject(project(R"([{"op":"if.digital","args":{"pin":2,"value":0},"then":[)" + counter + "]}]"));
  reject(project(R"([{"op":"if.digital","args":{"pin":2,"value":0},"then":[{"op":"led.off","args":{}}],"else":[)" + counter + "]}]"));
}
}
int main() {
  const std::vector<std::pair<const char*, std::function<void()>>> tests = {
    {"valid_counter_and_legacy_programs", valid_counter_and_legacy_programs},
    {"int64_start_is_exact_and_strict", int64_start_is_exact_and_strict},
    {"args_schema_ranges_and_name_are_strict", args_schema_ranges_and_name_are_strict},
    {"requires_screen_and_reserved_rectangle", requires_screen_and_reserved_rectangle},
    {"counter_is_terminal_and_not_a_branch", counter_is_terminal_and_not_a_branch}};
  int failures = 0;
  for (const auto& test : tests) {
    try { test.second(); std::cout << "PASS " << test.first << '\n'; }
    catch (const std::exception& error) { ++failures; std::cout << "FAIL " << test.first << ": " << error.what() << '\n'; }
  }
  std::cout << tests.size() << " counter-model groups, " << failures << " failures\n";
  return failures ? 1 : 0;
}
