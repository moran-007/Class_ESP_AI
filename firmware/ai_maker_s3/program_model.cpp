#include "program_model.h"
#include "device_core.h"
#include <cstring>
#include <initializer_list>
#include <cstdint>
#include <utility>

namespace ai_maker {
namespace {
bool number(JsonVariantConst value, int low, int high) {
  return value.is<int>() && !value.is<bool>() && value.as<int>() >= low && value.as<int>() <= high;
}
bool keys(JsonObjectConst object, std::initializer_list<const char*> allowed) {
  for (JsonPairConst pair : object) {
    bool found = false;
    for (const auto* name : allowed) if (pair.key() == name) found = true;
    if (!found) return false;
  }
  return true;
}
bool string(JsonVariantConst value, size_t limit) {
  if (!value.is<const char*>()) return false;
  const auto s = value.as<JsonString>();
  return s.size() > 0 && s.size() <= limit && std::strlen(s.c_str()) == s.size();
}
bool name(JsonVariantConst value) {
  if (!string(value, 24)) return false;
  const auto letter = [](char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); };
  const auto text = value.as<std::string>();
  if (!letter(text[0])) return false;
  for (char c : text) if (!letter(c) && !(c >= '0' && c <= '9') && c != '_') return false;
  return true;
}
bool utf8(JsonVariantConst input) {
  if (!string(input, 192)) return false;
  const auto text = input.as<std::string>();
  for (size_t i = 0; i < text.size();) {
    const auto lead = static_cast<uint8_t>(text[i++]);
    uint32_t cp = lead; int extra = 0;
    if (lead >= 0xc2 && lead <= 0xdf) { cp = lead & 31; extra = 1; }
    else if (lead >= 0xe0 && lead <= 0xef) { cp = lead & 15; extra = 2; }
    else if (lead >= 0xf0 && lead <= 0xf4) { cp = lead & 7; extra = 3; }
    else if (lead >= 0x80) return false;
    if (i + static_cast<size_t>(extra) > text.size()) return false;
    for (int j = 0; j < extra; ++j) {
      const auto tail = static_cast<uint8_t>(text[i++]);
      if ((tail & 0xc0) != 0x80) return false;
      cp = (cp << 6) | (tail & 63);
    }
    if ((extra == 1 && cp < 0x80) || (extra == 2 && cp < 0x800) || (extra == 3 && cp < 0x10000) ||
        cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff) ||
        (cp < 32 && cp != 10) || (cp >= 0x7f && cp <= 0x9f)) return false;
  }
  return true;
}
bool oneObject(const std::string& text) {
  const auto whitespace = [](char c) { return c == ' ' || c == '\r' || c == '\n' || c == '\t'; };
  size_t start = 0;
  while (start < text.size() && whitespace(text[start])) ++start;
  if (start == text.size() || text[start] != '{') return false;
  int depth = 0; bool quoted = false, escape = false;
  for (size_t i = start; i < text.size(); ++i) {
    const char c = text[i];
    if (quoted) {
      if (escape) escape = false;
      else if (c == '\\') escape = true;
      else if (c == '"') quoted = false;
    } else if (c == '"') quoted = true;
    else if (c == '{' || c == '[') ++depth;
    else if (c == '}' || c == ']') {
      if (--depth < 0) return false;
      if (depth == 0) {
        for (++i; i < text.size(); ++i) if (!whitespace(text[i])) return false;
        return true;
      }
    }
  }
  return false;
}
std::string json(JsonVariantConst value) { std::string result; serializeJson(value, result); return result; }

struct Compiler {
  JsonObjectConst config;
  ProgramModel& model;
  std::string& error;
  size_t nodes = 0;

  bool fail(const char* message) { error = message; return false; }
  bool mappedPin(int pin) const {
    for (JsonVariantConst servo : config["servos"].as<JsonArrayConst>())
      if (number(servo["pin"], 0, 48) && servo["pin"].as<int>() == pin) return true;
    const auto display = config["display"].as<JsonObjectConst>();
    for (const auto* field : {"sck", "mosi", "cs", "dc", "rst", "backlight"})
      if (number(display[field], 0, 48) && display[field].as<int>() == pin) return true;
    return false;
  }
  bool pin(JsonVariantConst value, bool adc = false) const {
    if (!number(value, 0, 48)) return false;
    const int p = value.as<int>();
    return DeviceCore::validPin(p) && !DeviceCore::reservedPin(p) && !mappedPin(p) && (!adc || DeviceCore::adcPin(p));
  }
  JsonObjectConst servo(JsonVariantConst device) const {
    if (!name(device)) return {};
    for (JsonVariantConst item : config["servos"].as<JsonArrayConst>())
      if (item["name"] == device) return item.as<JsonObjectConst>();
    return {};
  }
  bool displaySize(int& width, int& height) const {
    const auto d = config["display"].as<JsonObjectConst>();
    if (!number(d["rotation"], 0, 3)) return false;
    if (d["panel"] == "st7735s_128x160") { width = 128; height = 160; }
    else if (d["panel"] == "st7789_240x320") { width = 240; height = 320; }
    else if (d["panel"] == "st7789_240x240") width = height = 240;
    else return false;
    if (d["rotation"].as<int>() % 2) std::swap(width, height);
    return true;
  }
  bool action(const std::string& op, JsonObjectConst args) const {
    if (op == "led.off") return keys(args, {});
    if (op == "led.set") return keys(args, {"red", "green", "blue"}) &&
      number(args["red"], 0, 32) && number(args["green"], 0, 32) && number(args["blue"], 0, 32);
    if (op == "wait") return keys(args, {"ms"}) && number(args["ms"], 1, 60000);
    if (op == "gpio.setup") return keys(args, {"pin", "mode"}) && pin(args["pin"]) &&
      (args["mode"] == "input" || args["mode"] == "input_pullup" || args["mode"] == "input_pulldown" ||
       args["mode"] == "output" || args["mode"] == "pwm");
    if (op == "gpio.write") return keys(args, {"pin", "value"}) && pin(args["pin"]) && number(args["value"], 0, 1);
    if (op == "gpio.release") return keys(args, {"pin"}) && pin(args["pin"]);
    if (op == "pwm.write") return keys(args, {"pin", "duty"}) && pin(args["pin"]) && number(args["duty"], 0, 100);
    if (op == "if.digital") return keys(args, {"pin", "value"}) && pin(args["pin"]) && number(args["value"], 0, 1);
    if (op == "if.analog") return keys(args, {"pin", "operator", "value"}) && pin(args["pin"], true) && number(args["value"], 0, 4095) &&
      (args["operator"] == "<" || args["operator"] == "<=" || args["operator"] == "==" ||
       args["operator"] == "!=" || args["operator"] == ">=" || args["operator"] == ">");
    if (op == "servo.move" || op == "servo.release") {
      const auto s = servo(args["device"]);
      if (s.isNull()) return false;
      if (op == "servo.release") return keys(args, {"device"});
      return keys(args, {"device", "angle"}) && number(s["min_angle"], 0, 180) && number(s["max_angle"], 0, 180) &&
        number(args["angle"], s["min_angle"].as<int>(), s["max_angle"].as<int>());
    }
    int width = 0, height = 0;
    if (op.compare(0, 8, "display.") != 0 || !displaySize(width, height)) return false;
    if (op == "display.begin" || op == "display.release") return keys(args, {});
    if (op == "display.brightness") return keys(args, {"percent"}) && number(args["percent"], 0, 100) &&
      number(config["display"]["backlight"], 0, 48);
    if (op == "display.fill") return keys(args, {"color"}) && number(args["color"], 0, 65535);
    if (op == "display.counter") return keys(args, {"name", "start", "step", "interval_ms", "x", "y", "width", "height", "color", "background"}) &&
      name(args["name"]) && args["start"].is<int64_t>() && !args["start"].is<bool>() && args["start"].as<int64_t>() >= 0 &&
      number(args["step"], 1, 2147483647) && number(args["interval_ms"], 50, 60000) &&
      number(args["color"], 0, 65535) && number(args["background"], 0, 65535) &&
      number(args["x"], 0, width - 1) && number(args["y"], 0, height - 1) &&
      number(args["width"], 133, width - args["x"].as<int>()) &&
      number(args["height"], 16, height - args["y"].as<int>());
    if (!number(args["color"], 0, 65535)) return false;
    if (op == "display.text") return keys(args, {"text", "x", "y", "color"}) && utf8(args["text"]) &&
      number(args["x"], 0, width - 1) && number(args["y"], 0, height - 1);
    if (op == "display.rect") return keys(args, {"x", "y", "width", "height", "color", "filled"}) &&
      number(args["x"], 0, width - 1) && number(args["y"], 0, height - 1) &&
      number(args["width"], 1, width - args["x"].as<int>()) && number(args["height"], 1, height - args["y"].as<int>()) &&
      args["filled"].is<bool>();
    if (op == "display.line") return keys(args, {"x0", "y0", "x1", "y1", "color"}) &&
      number(args["x0"], 0, width - 1) && number(args["x1"], 0, width - 1) &&
      number(args["y0"], 0, height - 1) && number(args["y1"], 0, height - 1);
    return false;
  }
  bool steps(JsonArrayConst sequence, size_t depth, bool empty_allowed) {
    if (sequence.isNull() || (!empty_allowed && sequence.size() == 0)) return fail("Program branches require step arrays");
    for (size_t position = 0; position < sequence.size(); ++position) {
      const JsonVariantConst value = sequence[position];
      if (++nodes > 64) return fail("Program has more than64 steps");
      const auto node = value.as<JsonObjectConst>();
      if (node.isNull() || !string(node["op"], 32) || !node["args"].is<JsonObjectConst>())
        return fail("Each step requires op and object args");
      const std::string op = node["op"].as<std::string>();
      if (op == "display.counter") {
        if (depth != 0 || position + 1 != sequence.size() || model.has_counter)
          return fail("A counter must be the last root step and cannot appear in a branch");
        model.has_counter = true;
      }
      const bool condition = op == "if.digital" || op == "if.analog";
      if (!(condition ? keys(node, {"op", "args", "then", "else"}) : keys(node, {"op", "args"})) ||
          !action(op, node["args"].as<JsonObjectConst>())) return fail("Unsupported or invalid program action arguments");
      const size_t index = model.instructions.size();
      model.instructions.push_back({op, json(node["args"]), 0});
      if (condition) {
        if (depth >= 4) return fail("At most4 nested conditions are supported");
        if (!steps(node["then"].as<JsonArrayConst>(), depth + 1, false)) return false;
        const size_t jump = model.instructions.size();
        model.instructions.push_back({"jump", "{}", 0});
        model.instructions[index].target = model.instructions.size();
        bool has_else = false;
        for (JsonPairConst pair : node) if (pair.key() == "else") has_else = true;
        if (has_else && !steps(node["else"].as<JsonArrayConst>(), depth + 1, true)) return false;
        model.instructions[jump].target = model.instructions.size();
      }
      if (model.instructions.size() > 128) return fail("Compiled program exceeds128 instructions");
    }
    return true;
  }
};
}  // namespace

bool parseProgram(const std::string& source, ProgramModel& output, std::string& error) {
  error.clear();
  if (source.empty() || source.size() > kMaxProgramBytes || source.find('\0') != std::string::npos || !oneObject(source)) {
    error = "Program must be a single bounded JSON object"; return false;
  }
  JsonDocument doc;
  if (deserializeJson(doc, source, DeserializationOption::NestingLimit(24)) || !doc.is<JsonObjectConst>()) {
    error = "Program JSON cannot be parsed"; return false;
  }
  const auto root = doc.as<JsonObjectConst>();
  if (!keys(root, {"schema_version", "config", "steps"}) || !number(root["schema_version"], 1, 1) ||
      !root["config"].is<JsonObjectConst>() || !root["steps"].is<JsonArrayConst>()) {
    error = "Expected schema_version1, config object and steps array"; return false;
  }
  ProgramModel candidate;
  candidate.canonical = json(root); candidate.config_json = json(root["config"]);
  Compiler compiler{root["config"].as<JsonObjectConst>(), candidate, error};
  if (!compiler.steps(root["steps"].as<JsonArrayConst>(), 0, false)) return false;
  output = std::move(candidate);
  return true;
}
}  // namespace ai_maker
