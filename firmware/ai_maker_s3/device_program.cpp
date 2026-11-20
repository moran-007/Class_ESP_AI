#include "device_core.h"
#include <cstring>
#include <initializer_list>
#include <limits>

namespace ai_maker {
namespace {
void rejectProgram(JsonDocument& r, const char* code, const std::string& error) {
  r["ok"] = false; r["code"] = code; r["message"] = error; r.remove("data");
}
bool fields(JsonObjectConst object, std::initializer_list<const char*> names) {
  for (JsonPairConst p : object) {
    bool found = false;
    for (const char* name : names) if (p.key() == name) found = true;
    if (!found) return false;
  }
  return true;
}
std::string jsonProgram(JsonVariantConst v) { std::string s; serializeJson(v, s); return s; }
bool completeRecord(const std::string& source) {
  const auto blank = [](char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; };
  size_t start = 0;
  while (start < source.size() && blank(source[start])) ++start;
  if (start == source.size() || source[start] != '{') return false;
  int depth = 0; bool quoted = false, escaped = false;
  for (size_t i = start; i < source.size(); ++i) {
    const char c = source[i];
    if (!c) return false;
    if (quoted) {
      if (escaped) escaped = false;
      else if (c == '\\') escaped = true;
      else if (c == '"') quoted = false;
    } else if (c == '"') quoted = true;
    else if (c == '{' || c == '[') ++depth;
    else if (c == '}' || c == ']') {
      if (--depth < 0) return false;
      if (!depth) {
        for (++i; i < source.size(); ++i) if (!blank(source[i])) return false;
        return true;
      }
    }
  }
  return false;
}
}

bool DeviceCore::validateProgram(const std::string& source, ProgramModel& out, std::string& error) const {
  ProgramModel candidate;
  if (!parseProgram(source, candidate, error)) return false;
  JsonDocument config;
  if (deserializeJson(config, candidate.config_json)) { error = "Invalid program configuration"; return false; }
  std::array<ServoSpec, kMaxServos> servos{}; size_t count = 0; DisplaySpec display;
  if (!parseConfig(config.as<JsonObjectConst>(), servos, count, display, error, true)) return false;
  out = std::move(candidate); return true;
}

std::string DeviceCore::programState(const ProgramModel& model, bool enabled, bool loop) const {
  JsonDocument record, body;
  record["storage_version"] = 1; record["enabled"] = enabled; record["loop"] = loop;
  if (model.canonical.empty()) record["program"] = nullptr;
  else {
    deserializeJson(body, model.canonical, DeserializationOption::NestingLimit(24));
    record["program"].set(body.as<JsonVariantConst>());
  }
  return jsonProgram(record.as<JsonVariantConst>());
}

void DeviceCore::loadProgram() {
  const std::string saved = hardware_.loadProgramState();
  if (saved.empty()) return;
  JsonDocument record;
  if (saved.size() > 3584 || !completeRecord(saved) || deserializeJson(record, saved, DeserializationOption::NestingLimit(24)) ||
      !record.is<JsonObjectConst>() || !fields(record.as<JsonObjectConst>(), {"storage_version", "enabled", "loop", "program"}) ||
      !record["storage_version"].is<int>() || record["storage_version"].is<bool>() || record["storage_version"] != 1 ||
      !record["enabled"].is<bool>() || !record["loop"].is<bool>() || record.as<JsonObjectConst>().size() != 4) {
    program_error_ = "Invalid saved program record; clear or save it again"; return;
  }
  if (record["program"].isNull()) {
    if (record["enabled"].as<bool>() || record["loop"].as<bool>()) program_error_ = "Invalid empty program policy";
    return;
  }
  if (!validateProgram(jsonProgram(record["program"]), program_, program_error_)) return;
  if (program_.has_counter && record["loop"].as<bool>()) {
    program_ = ProgramModel{}; program_error_ = "Counter programs cannot use root loop"; return;
  }
  program_enabled_ = record["enabled"]; program_loop_ = record["loop"];
  program_boot_pending_ = program_enabled_ && !maintenance_ && !storage_fault_;
}

void DeviceCore::writeProgramInfo(JsonObject target) const {
  target["saved"] = !program_.canonical.empty(); target["enabled"] = program_enabled_;
  target["loop"] = program_loop_; target["running"] = program_running_;
  target["boot_pending"] = program_boot_pending_; target["instruction"] = program_pc_;
  target["error"] = program_error_; target["cleanup_required"] = program_context_active_ && !program_running_;
  target["physical_verified"] = false;
  auto counter = target["counter"].to<JsonObject>();
  counter["active"] = program_counter_.active; counter["name"] = program_counter_.name;
  counter["value"] = program_counter_.value; counter["interval_ms"] = program_counter_.interval_ms;
}

void DeviceCore::restoreProgramConfiguration() {
  if (!program_context_active_) return;
  servos_ = program_previous_servos_; servo_count_ = program_previous_servo_count_;
  display_ = program_previous_display_; display_brightness_ = display_.brightness;
  audio_ = program_previous_audio_;  // Restore mapping; never auto-start recording/playback.
  program_context_active_ = false;
}

bool DeviceCore::startProgram() {
  if (program_.canonical.empty() || maintenance_ || storage_fault_) return false;
  if (!stopOutputs()) { program_error_ = "Output cleanup failed before program start"; return false; }
  JsonDocument config;
  deserializeJson(config, program_.config_json);
  std::array<ServoSpec, kMaxServos> next{}; size_t count = 0; DisplaySpec display; std::string error;
  if (!parseConfig(config.as<JsonObjectConst>(), next, count, display, error, true)) {
    program_error_ = error; return false;
  }
  program_previous_servos_ = servos_; program_previous_servo_count_ = servo_count_;
  program_previous_display_ = display_;
  program_previous_audio_ = audio_; clearAudioSession();
  servos_ = next; servo_count_ = count; display_ = display; display_brightness_ = display_.brightness;
  program_context_active_ = program_running_ = true;
  program_counter_ = ProgramCounter{};
  program_pc_ = 0; program_waiting_ = false; program_error_.clear(); return true;
}

void DeviceCore::failProgram(const std::string& error) {
  program_error_ = error;
  if (!stopOutputs()) program_error_ += "; output cleanup failed";
}

bool DeviceCore::renderProgramCounter() {
  if (!display_active_ || !display_driver_ok_) return false;
  const auto& c = program_counter_;
  display_driver_ok_ = hardware_.rectDisplay(c.x, c.y, c.width, c.height, c.background, true) &&
      hardware_.textDisplay(c.x, c.y, std::to_string(c.value), c.color);
  return display_driver_ok_;
}

void DeviceCore::tickProgramCounter(uint32_t now_ms) {
  auto& c = program_counter_;
  const uint32_t elapsed = static_cast<uint32_t>(now_ms - c.last_ms);
  const uint32_t ticks = elapsed / c.interval_ms;
  if (!ticks) return;
  const uint64_t room = static_cast<uint64_t>(std::numeric_limits<int64_t>::max() - c.value);
  if (static_cast<uint64_t>(ticks) > room / c.step) { failProgram("Counter reached its signed64bit limit"); return; }
  c.value += static_cast<int64_t>(ticks) * c.step;
  c.last_ms += ticks * c.interval_ms;
  if (!renderProgramCounter()) failProgram("Counter display update failed");
}

void DeviceCore::tickProgram(uint32_t now_ms) {
  if (program_boot_pending_) {
    program_boot_pending_ = false;
    if (!startProgram()) return;
  }
  if (!program_running_) return;
  if (maintenance_ || storage_fault_) { failProgram("Program interrupted by maintenance or storage fault"); return; }
  if (program_counter_.active) { tickProgramCounter(now_ms); return; }
  if (program_waiting_) {
    if (static_cast<uint32_t>(now_ms - program_wait_since_) < program_wait_ms_) return;
    program_waiting_ = false;
  }
  // Bound interpreter work independently of loop nesting or incoming USB data.
  // All waits yield; even a tight root loop cannot starve USB or the lease timer.
  for (unsigned budget = 0; budget < 8 && program_running_; ++budget) {
    if (program_pc_ >= program_.instructions.size()) {
      if (program_loop_) { program_pc_ = 0; return; }
      const bool stopped = stopOutputs();
      if (!stopped) program_error_ = "Program completed; output cleanup failed";
      else if (session_.empty()) resumeDefaultPage();
      return;
    }
    const auto& instruction = program_.instructions[program_pc_++];
    if (instruction.op == "jump") { program_pc_ = instruction.target; continue; }
    JsonDocument args;
    if (deserializeJson(args, instruction.args_json)) { failProgram("Invalid compiled arguments"); return; }
    if (instruction.op == "display.counter") {
      // Start its clock on a fresh tick after preceding SPI initialization.
      if (budget) { --program_pc_; return; }
      auto& c = program_counter_;
      c.name = args["name"].as<std::string>(); c.value = args["start"].as<int64_t>();
      c.step = args["step"]; c.interval_ms = args["interval_ms"]; c.last_ms = now_ms;
      c.x = args["x"]; c.y = args["y"]; c.width = args["width"]; c.height = args["height"];
      c.color = args["color"]; c.background = args["background"]; c.active = true;
      if (!renderProgramCounter()) failProgram("Counter display initialization failed");
      return;
    }
    if (instruction.op == "wait") {
      program_wait_since_ = now_ms; program_wait_ms_ = args["ms"]; program_waiting_ = true; return;
    }
    if (instruction.op == "if.digital" || instruction.op == "if.analog") {
      const int pin = args["pin"];
      if (instruction.op == "if.digital") {
        if (modes_[pin] != PinMode::Input && modes_[pin] != PinMode::InputPullup && modes_[pin] != PinMode::InputPulldown) {
          failProgram("Digital condition requires a configured input"); return;
        }
        const int value = hardware_.readDigital(pin);
        if (value != 0 && value != 1) { failProgram("Digital input failed"); return; }
        if (value != args["value"].as<int>()) program_pc_ = instruction.target;
      } else {
        if (modes_[pin] != PinMode::Input) { failProgram("ADC condition requires plain input"); return; }
        const int value = hardware_.readAdc(pin), threshold = args["value"];
        if (value < 0 || value > 4095) { failProgram("ADC input failed"); return; }
        const std::string compare = args["operator"].as<std::string>();
        const bool result = compare == "<" ? value < threshold : compare == "<=" ? value <= threshold :
            compare == "==" ? value == threshold : compare == "!=" ? value != threshold :
            compare == ">=" ? value >= threshold : value > threshold;
        if (!result) program_pc_ = instruction.target;
      }
      continue;
    }
    JsonDocument request, reply;
    request["op"] = instruction.op; request["args"].set(args.as<JsonVariantConst>());
    // Reuse the same driver validation and error paths as live SDK operations.
    // The private marker cannot be selected through a public JSON request.
    const std::string previous_session = session_;
    const uint32_t previous_seen = last_seen_ms_;
    if (session_.empty()) session_ = "program-internal";
    request["session_id"] = session_;
    reply["ok"] = true; internal_program_action_ = true;
    dispatch(request.as<JsonObjectConst>(), reply, now_ms);
    internal_program_action_ = false; session_ = previous_session; last_seen_ms_ = previous_seen;
    if (!reply["ok"].as<bool>()) {
      failProgram(instruction.op + ": " + reply["code"].as<std::string>() + " " + reply["message"].as<std::string>()); return;
    }
  }
}

void DeviceCore::dispatchProgram(const std::string& op, JsonObjectConst args, JsonDocument& response, uint32_t) {
  auto data = response["data"].as<JsonObject>();
  if (op == "program.download") {
    if (!fields(args, {})) return rejectProgram(response, "INVALID_ARGUMENT", "download takes no arguments");
    if (program_.canonical.empty()) return rejectProgram(response, "DEVICE_NOT_FOUND", "No saved program");
    JsonDocument body; deserializeJson(body, program_.canonical, DeserializationOption::NestingLimit(24));
    data["program"].set(body.as<JsonVariantConst>()); data["enabled"] = program_enabled_; data["loop"] = program_loop_; return;
  }
  if (op == "program.stop") {
    if (!fields(args, {})) return rejectProgram(response, "INVALID_ARGUMENT", "stop takes no arguments");
    program_boot_pending_ = false;
    if (program_context_active_ && !stopOutputs()) return rejectProgram(response, "HARDWARE_ERROR", "Program cleanup failed");
    data["stopped"] = true; return;
  }
  if (op == "program.start") {
    if (!fields(args, {})) return rejectProgram(response, "INVALID_ARGUMENT", "start takes no arguments");
    if (maintenance_ || storage_fault_) return rejectProgram(response, "MAINTENANCE_REQUIRED", "Leave maintenance with valid storage before starting");
    if (program_.canonical.empty()) return rejectProgram(response, "DEVICE_NOT_FOUND", "No saved program");
    if (!startProgram()) return rejectProgram(response, "HARDWARE_ERROR", program_error_);
    writeProgramInfo(data); return;
  }
  if (op != "program.save" && op != "program.enable" && op != "program.disable" && op != "program.clear")
    return rejectProgram(response, "UNSUPPORTED_OPERATION", "Unknown program operation");
  if (!maintenance_) return rejectProgram(response, "MAINTENANCE_REQUIRED", "Enter maintenance before changing a saved program");
  ProgramModel next = program_; bool enabled = program_enabled_, loop = program_loop_;
  if (op == "program.save") {
    if (!fields(args, {"program", "loop", "autostart"}) || !args["program"].is<JsonObjectConst>() ||
        !args["loop"].is<bool>() || !args["autostart"].is<bool>())
      return rejectProgram(response, "INVALID_ARGUMENT", "save requires program, boolean loop and autostart");
    std::string error;
    if (!validateProgram(jsonProgram(args["program"]), next, error)) return rejectProgram(response, "PROGRAM_INVALID", error);
    enabled = args["autostart"]; loop = args["loop"];
    if (next.has_counter && loop) return rejectProgram(response, "PROGRAM_INVALID", "Counter runs continuously; use loop=false");
  } else {
    if (!fields(args, {})) return rejectProgram(response, "INVALID_ARGUMENT", "Unknown program arguments");
    if (op == "program.enable" && next.canonical.empty()) return rejectProgram(response, "DEVICE_NOT_FOUND", "No saved program");
    if (op == "program.clear") { next = ProgramModel{}; loop = false; }
    enabled = op == "program.enable";
  }
  if (!stopOutputs()) return rejectProgram(response, "HARDWARE_ERROR", "Release outputs before saving a program");
  const std::string saved = programState(next, enabled, loop);
  if (saved.size() > 3584 || !hardware_.saveProgramState(saved))
    return rejectProgram(response, "STORAGE_ERROR", "Program was not confirmed saved; previous in-memory program retained, no automatic retry");
  program_ = std::move(next); program_enabled_ = enabled; program_loop_ = loop;
  if (op == "program.clear") program_counter_ = ProgramCounter{};
  program_pc_ = 0; program_error_.clear(); writeProgramInfo(data);
}
}  // namespace ai_maker
