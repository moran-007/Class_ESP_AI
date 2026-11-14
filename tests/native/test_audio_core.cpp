#include "device_core.h"
#include "fake_hardware.h"
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
void require(bool condition, const std::string& message) {
  if (!condition) throw std::runtime_error(message);
}
std::string json(const JsonDocument& value) {
  std::string result; serializeJson(value, result); return result;
}
const std::string kMapping = R"({"bclk":42,"ws":41,"din":21,"dout":40,"sd":39,"mic_channel":"left","volume":20})";
const std::string kScreen = R"({"schema_version":1,"servos":[],"display":{"panel":"st7735s_128x160","sck":4,"mosi":5,"cs":15,"dc":7,"rst":6,"backlight":16,"rotation":1,"invert":false,"brightness":60}})";

std::string modified(const std::string& mapping, const char* key, JsonVariantConst value) {
  JsonDocument doc;
  require(!deserializeJson(doc, mapping), "fixture parses");
  doc[key].set(value); return json(doc);
}
template<typename T> std::string field(const char* key, T value) {
  JsonDocument d; d["value"] = value; return modified(kMapping, key, d["value"]);
}
std::string writeArgs(size_t offset, const std::string& bytes) {
  JsonDocument d; d["offset"] = offset; d["data"] = ai_maker::encodePageBase64(bytes); return json(d);
}

class Channel {
 public:
  FakeHardware& hardware;
  ai_maker::DeviceCore core;
  uint32_t now = 100;
  unsigned sequence = 0;
  explicit Channel(FakeHardware& h, bool open = true) : hardware(h), core(h) {
    core.begin(); if (open) ok("session.open");
  }
  JsonDocument call(const std::string& op, const std::string& args = "{}", const std::string& owner = "audio-owner") {
    JsonDocument request, reply;
    request["kind"] = "request"; request["protocol_version"] = 1;
    request["request_id"] = "a" + std::to_string(++sequence); request["op"] = op;
    if (!owner.empty()) request["session_id"] = owner;
    std::string line = json(request); line.pop_back(); line += ",\"args\":" + args + "}";
    require(!deserializeJson(reply, core.process(line, now)), "response must be JSON");
    return reply;
  }
  JsonDocument ok(const std::string& op, const std::string& args = "{}") {
    auto result = call(op, args);
    require(result["ok"].as<bool>(), op + " failed " + result["code"].as<std::string>() + ": " + result["message"].as<std::string>());
    return result;
  }
  JsonDocument error(const std::string& op, const std::string& args, const std::string& code = "") {
    auto result = call(op, args);
    require(!result["ok"].as<bool>(), op + " unexpectedly succeeded: " + args);
    if (!code.empty()) require(result["code"] == code, op + " expected " + code + " got " + result["code"].as<std::string>());
    return result;
  }
  JsonDocument info() { return ok("audio.info"); }
  JsonDocument status() { return ok("device.status"); }
  void configure(const std::string& mapping = kMapping) {
    ok("maintenance.enter");
    const auto saves = hardware.saves;
    ok("audio.configure", mapping);
    require(hardware.saves == saves, "audio mapping itself does not write NVS");
  }
  void start(const std::string& mapping = kMapping) {
    configure(mapping); ok("maintenance.exit"); ok("audio.begin");
  }
  void apply(const std::string& config) {
    JsonDocument args, parsed;
    args["expected_revision"] = ok("config.get")["data"]["revision"];
    require(!deserializeJson(parsed, config), "config fixture parses");
    args["config"].set(parsed.as<JsonObjectConst>()); ok("config.apply", json(args));
  }
  std::string applyArgs(const std::string& config) {
    JsonDocument args, parsed;
    args["expected_revision"] = ok("config.get")["data"]["revision"];
    require(!deserializeJson(parsed, config), "config fixture parses");
    args["config"].set(parsed.as<JsonObjectConst>()); return json(args);
  }
  std::string owner(int pin) {
    auto result = ok("pins.list");
    const JsonArrayConst pins = result["data"]["pins"].as<JsonArrayConst>();
    for (JsonObjectConst item : pins)
      if (item["pin"] == pin) return item["owner"].as<std::string>();
    throw std::runtime_error("pin absent from list");
  }
};

void audio_capabilities_and_public_status_are_truthful() {
  FakeHardware h; Channel c(h, false);
  auto info = c.call("device.info", "{}", "");
  for (const char* cap : {"audio_in", "audio_out", "i2s_audio", "configurable_audio_pins"})
    require(info["data"]["capabilities"][cap].as<bool>(), std::string("missing capability ") + cap);
  require(!info["data"]["capabilities"]["full_duplex_audio"].as<bool>(), "RPC interface is half duplex");
  require(info["data"]["limits"]["audio_chunk_bytes"] == 768, "bounded audio payload advertised");
  auto audio = c.call("audio.info", "{}", "");
  require(audio["ok"].as<bool>(), "audio.info does not require a session");
  const auto data = audio["data"];
  require(data["format"] == "pcm_s16le" && data["sample_rate"] == 16000 &&
          data["channels"] == 1 && data["sample_width"] == 2 && data["byte_order"] == "little", "fixed PCM metadata");
  require(!data["configured"].as<bool>() && !data["active"].as<bool>(), "no default audio mapping or hardware at boot");
  require(h.audio_begins == 0 && h.audio_play_starts == 0 && h.audio_capture_starts == 0, "boot performs no audio IO");
  c.error("audio.configure", kMapping, "SESSION_REQUIRED");
  c.error("audio.read", R"({"bytes":2})", "SESSION_REQUIRED");
  c.ok("session.open");
  auto stranger = c.call("audio.begin", "{}", "someone-else");
  require(stranger["code"] == "SESSION_REQUIRED", "audio operations bound to owning lease");
  bool found_adc = false, found_digital = false;
  for (int offset : {0, 36}) {
    const auto pins = c.ok("pins.list", "{\"offset\":" + std::to_string(offset) + ",\"limit\":12}");
    const JsonArrayConst listed = pins["data"]["pins"].as<JsonArrayConst>();
    for (JsonObjectConst pin : listed) {
      require(!pin["analog_output"].as<bool>(), "S3 teaching profile exposes no true DAC");
      if (pin["pin"] == 1) found_adc = pin["analog_input"].as<bool>() && pin["digital_input"].as<bool>();
      if (pin["pin"] == 42) found_digital = pin["digital_output"].as<bool>() && !pin["analog_input"].as<bool>() && pin["pwm_output"].as<bool>();
    }
  }
  require(found_adc && found_digital, "pin capabilities distinguish ADC from digital/PWM");
}

void configuration_requires_maintenance_and_is_transactional() {
  FakeHardware h; Channel c(h);
  c.error("audio.configure", kMapping, "MAINTENANCE_REQUIRED");
  c.configure();
  auto info = c.info();
  require(info["data"]["configured"].as<bool>() && !info["data"]["active"].as<bool>(), "setting does not start audio");
  require(info["data"]["bclk"] == 42 && info["data"]["mic_channel"] == "left", "canonical mapping published");
  for (const auto& bad : {field("bclk", 19), field("ws", 42), field("din", true), field("dout", 99),
          field("sd", 21), field("mic_channel", "both"), field("volume", 101), field("volume", 1.5)}) {
    c.error("audio.configure", bad);
    require(c.info()["data"]["bclk"] == 42 && c.info()["data"]["volume"] == 20, "invalid configuration preserves old mapping");
  }
  JsonDocument neither; require(!deserializeJson(neither, kMapping), "fixture");
  neither["din"] = -1; neither["dout"] = -1; neither["sd"] = -1;
  c.error("audio.configure", json(neither));
  JsonDocument missing; require(!deserializeJson(missing, kMapping), "fixture"); missing.remove("ws");
  c.error("audio.configure", json(missing));
  JsonDocument unknown; require(!deserializeJson(unknown, kMapping), "fixture"); unknown["unknown"] = 4;
  c.error("audio.configure", json(unknown));
  require(h.audio_begins == 0, "invalid and successful configure do not initialize HAL");
  c.error("audio.begin", "{}", "MAINTENANCE_REQUIRED");
  c.ok("maintenance.exit"); c.ok("audio.begin"); c.ok("audio.begin");
  require(h.audio_begins == 1 && !h.audio_capturing && !h.audio_playing, "begin idempotent and starts no stream");
}

void persisted_peripherals_and_audio_runtime_pins_cannot_conflict() {
  FakeHardware h; Channel c(h);
  c.ok("maintenance.enter"); c.apply(kScreen);
  c.error("audio.configure", field("bclk", 4));
  c.configure();
  require(c.owner(42).find("audio") != std::string::npos && c.owner(21).find("audio") != std::string::npos, "configured audio owns clock and input pins");
  c.ok("maintenance.exit");
  c.error("gpio.setup", R"({"pin":42,"mode":"output"})", "RESOURCE_CONFLICT");
  c.error("gpio.setup", R"({"pin":21,"mode":"input"})", "RESOURCE_CONFLICT");
  c.ok("maintenance.enter");
  JsonDocument display; require(!deserializeJson(display, kScreen), "fixture"); display["display"]["sck"] = 42;
  c.error("config.apply", c.applyArgs(json(display)));
  const auto servo = R"({"schema_version":1,"servos":[{"name":"head","pin":40,"min_angle":30,"max_angle":150,"min_pulse_us":1000,"max_pulse_us":2000}]})";
  c.error("config.apply", c.applyArgs(servo));
  require(c.info()["data"]["configured"].as<bool>(), "failed peripheral change keeps audio mapping");
  c.ok("audio.unconfigure"); c.apply(servo);
  c.error("audio.configure", kMapping);
}

void recording_is_exact_bounded_little_endian_and_half_duplex() {
  FakeHardware h; Channel c(h); c.start();
  c.error("audio.read", R"({"bytes":2})");
  c.ok("audio.record.begin");
  c.error("audio.play.begin", "{}", "RESOURCE_CONFLICT");
  c.error("audio.record.begin", "{}", "RESOURCE_CONFLICT");
  for (const auto& args : {R"({"bytes":0})", R"({"bytes":1})", R"({"bytes":770})", R"({"bytes":true})", R"({"bytes":2.5})", R"({})"}) c.error("audio.read", args);
  require(h.audio_reads == 0, "invalid read size rejected before HAL");
  auto first = c.ok("audio.read", R"({"bytes":768})");
  require(first["data"]["bytes"] == 768 && first["data"]["offset"] == 0, "maximum read chunk offset");
  std::string raw;
  require(ai_maker::decodePageBase64(first["data"]["data"].as<std::string>(), raw, 768) && raw.size() == 768, "exact PCM response length");
  require(static_cast<unsigned char>(raw[0]) == 0xf0 && static_cast<unsigned char>(raw[1]) == 0xd8, "known signed sample -10000 is little endian");
  auto second = c.ok("audio.read", R"({"bytes":2})");
  require(second["data"]["offset"] == 768 && second["data"]["bytes"] == 2, "consecutive read offsets");
  auto ended = c.ok("audio.record.end");
  require(ended["data"]["bytes"] == 770 && ended["data"]["samples"] == 385, "record result derives samples from bytes");
  require(!c.info()["data"]["recording"].as<bool>() && c.info()["data"]["active"].as<bool>(), "record end keeps bus ready");
}

void playback_validates_base64_offsets_and_drains_before_end() {
  FakeHardware h; Channel c(h); c.start(); c.ok("audio.play.begin");
  c.error("audio.record.begin", "{}", "RESOURCE_CONFLICT");
  c.error("audio.play.begin", "{}", "RESOURCE_CONFLICT");
  for (const auto& args : {R"({"offset":0,"data":""})", R"({"offset":0,"data":"!!!!"})", R"({"offset":0,"data":"AA=="})", R"({"offset":true,"data":"AAA="})", R"({"offset":1,"data":"AAA="})"}) c.error("audio.write", args);
  c.error("audio.write", writeArgs(0, std::string(770, '\0')));
  require(h.audio_writes == 0 && h.audio_written.empty(), "invalid write never reaches HAL");
  const std::string samples("\0\0\xff\x7f\0\x80", 6);
  auto written = c.ok("audio.write", writeArgs(0, samples));
  require(written["data"]["bytes"] == 6 && written["data"]["next_offset"] == 6, "write acknowledgement exact");
  c.error("audio.write", writeArgs(0, samples));
  c.ok("audio.write", writeArgs(6, std::string(768, '\0')));
  auto ended = c.ok("audio.play.end");
  require(ended["data"]["bytes"] == 774 && ended["data"]["samples"] == 387, "play counter exact");
  require(h.audio_finishes == 1 && !h.audio_playing, "drain/mute reached before success");
  require(h.audio_written.size() == 774 && std::string(h.audio_written.begin(), h.audio_written.begin() + 6) == samples, "byte order preserved to HAL");
  require(!c.info()["data"]["playing"].as<bool>() && c.info()["data"]["active"].as<bool>(), "completed playback keeps configured bus");
}

void single_direction_setups_and_explicit_stop_remain_reusable() {
  FakeHardware h; Channel c(h);
  c.start(field("din", -1));
  c.error("audio.record.begin", "{}");
  c.ok("audio.play.begin"); c.ok("audio.write", writeArgs(0, std::string(2, '\0'))); c.ok("audio.stop");
  auto status = c.info();
  require(status["data"]["active"].as<bool>() && !status["data"]["playing"].as<bool>(), "stop mutes but does not release bus");
  c.ok("audio.play.begin"); c.ok("audio.play.end");
  JsonDocument mic; require(!deserializeJson(mic, kMapping), "fixture"); mic["dout"] = -1; mic["sd"] = -1;
  c.start(json(mic)); c.error("audio.play.begin", "{}");
  c.ok("audio.record.begin"); c.ok("audio.stop"); c.ok("audio.record.begin"); c.ok("audio.record.end");
}

void release_retains_mapping_and_unconfigure_frees_owned_gpio() {
  FakeHardware h; Channel c(h); c.start();
  c.ok("audio.release"); c.ok("audio.release");
  require(!c.info()["data"]["active"].as<bool>() && c.info()["data"]["configured"].as<bool>(), "release retains runtime configuration");
  c.error("gpio.setup", R"({"pin":42,"mode":"output"})", "RESOURCE_CONFLICT");
  c.ok("audio.begin"); c.ok("maintenance.enter");
  c.ok("audio.release"); c.ok("audio.unconfigure"); c.ok("audio.unconfigure");
  require(!c.info()["data"]["configured"].as<bool>() && c.owner(42).empty(), "unconfigure frees runtime reservation");
  c.ok("maintenance.exit"); c.ok("gpio.setup", R"({"pin":42,"mode":"output"})");
}

void maintenance_and_configuration_keep_only_session_mapping() {
  FakeHardware h; Channel c(h); c.start(); c.ok("audio.record.begin");
  c.ok("maintenance.enter");
  require(!h.audio_active && !c.info()["data"]["recording"].as<bool>(), "maintenance releases bus and record state");
  require(c.info()["data"]["configured"].as<bool>(), "maintenance retains mapping within lease");
  c.apply(kScreen);
  auto saved = c.ok("config.get");
  require(saved["data"]["config"]["audio"].isNull(), "runtime audio not persisted in config schema");
  require(h.state.find("\"audio\"") == std::string::npos, "no audio config in NVS state");
  c.ok("maintenance.exit"); c.ok("audio.begin");
  require(c.info()["data"]["active"].as<bool>(), "bus restart after unrelated configuration change");
  c.ok("session.close");
  require(!c.call("audio.info", "{}", "")["data"]["configured"].as<bool>(), "close clears runtime mapping");
  Channel rebooted(h);
  require(!rebooted.info()["data"]["configured"].as<bool>(), "reboot never restores audio mapping");
  require(h.audio_begins == 2, "reboot did not open I2S");
}

void outputs_stop_close_and_expiry_all_release_audio() {
  for (const std::string route : {"outputs.stop", "session.close", "expiry"}) {
    FakeHardware h; Channel c(h); c.start(); c.ok("audio.play.begin"); c.ok("audio.write", writeArgs(0, std::string(2, '\0')));
    if (route == "expiry") c.core.tick(c.now + ai_maker::kLeaseMs);
    else c.ok(route);
    auto state = c.call("audio.info", "{}", "");
    require(!state["data"]["active"].as<bool>() && !h.audio_active && !h.audio_playing, route + " releases hardware");
    require(!state["data"]["recording"].as<bool>() && !state["data"]["playing"].as<bool>(), route + " discards transfer state");
    require(state["data"]["configured"].as<bool>() == (route == "outputs.stop"), route + " mapping lifetime");
    require(h.audio_releases > 0, route + " really calls HAL release");
  }
}

void failed_begin_and_partial_reads_never_claim_capture_success() {
  FakeHardware h; Channel c(h); c.configure(); c.ok("maintenance.exit");
  h.audio_begin_ok = false;
  c.error("audio.begin", "{}", "HARDWARE_ERROR");
  require(!c.info()["data"]["active"].as<bool>() && !c.info()["data"]["driver_ok"].as<bool>(), "begin error observable");
  h.audio_begin_ok = true; c.ok("audio.begin");
  h.audio_capture_ok = false; c.error("audio.record.begin", "{}", "HARDWARE_ERROR");
  require(!c.info()["data"]["recording"].as<bool>(), "failed capture begin is not recording");
  h.audio_capture_ok = true;
  for (bool partial : {false, true}) {
    c.ok("audio.record.begin"); h.audio_read_ok = partial; h.audio_read_partial = partial;
    const auto stops = h.audio_stops;
    c.error("audio.read", R"({"bytes":8})", "HARDWARE_ERROR");
    auto status = c.info();
    require(!status["data"]["recording"].as<bool>() && status["data"]["read_bytes"] == 0, "failed/partial read cannot publish a complete chunk");
    require(h.audio_stops > stops, "read error attempts mute/cancel");
    h.audio_read_ok = true; h.audio_read_partial = false;
  }
}

void failed_write_and_drain_end_stream_without_replay() {
  FakeHardware h; Channel c(h); c.start();
  h.audio_play_ok = false; c.error("audio.play.begin", "{}", "HARDWARE_ERROR");
  require(!c.info()["data"]["playing"].as<bool>(), "play begin failed without starting");
  h.audio_play_ok = true;
  for (bool partial : {false, true}) {
    c.ok("audio.play.begin"); h.audio_write_ok = partial; h.audio_write_partial = partial;
    const auto writes = h.audio_writes;
    c.error("audio.write", writeArgs(0, std::string(8, '\0')), "HARDWARE_ERROR");
    require(h.audio_writes == writes + 1 && !c.info()["data"]["playing"].as<bool>(), "write failure is single attempt and stops mode");
    require(c.info()["data"]["written_bytes"] == 0, "partial write not acknowledged as a complete chunk");
    h.audio_write_ok = true; h.audio_write_partial = false;
  }
  c.ok("audio.play.begin"); c.ok("audio.write", writeArgs(0, std::string(8, '\0')));
  h.audio_finish_ok = false;
  c.error("audio.play.end", "{}", "HARDWARE_ERROR");
  require(!c.info()["data"]["playing"].as<bool>() && h.audio_stops > 0, "failed drain still attempts mute and clears playing");
}

void failed_cleanup_retains_ownership_until_recovery() {
  for (const std::string route : {"audio.release", "session.close", "expiry"}) {
    FakeHardware h; Channel c(h); c.start(); c.ok("audio.play.begin");
    h.audio_release_ok = false;
    if (route == "expiry") c.core.tick(c.now + ai_maker::kLeaseMs);
    else c.error(route, "{}", "HARDWARE_ERROR");
    auto public_info = c.call("audio.info", "{}", "");
    require(public_info["data"]["active"].as<bool>() && public_info["data"]["configured"].as<bool>() &&
            !public_info["data"]["driver_ok"].as<bool>(), "failed cleanup cannot advertise inactive/free pins");
    if (route != "audio.release") c.ok("session.open");
    c.error("audio.stop", "{}", "HARDWARE_ERROR");
    require(c.info()["data"]["cleanup_required"].as<bool>(), "stop cannot clear an incomplete release");
    c.error("audio.begin", "{}", "HARDWARE_ERROR");
    require(c.owner(42).find("audio") != std::string::npos, "failed cleanup keeps pin owner");
    c.error("gpio.setup", R"({"pin":42,"mode":"output"})", "RESOURCE_CONFLICT");
    h.audio_release_ok = true; c.ok("audio.unconfigure");
    require(c.owner(42).empty(), "successful retry clears uncertain ownership");
    c.ok("gpio.setup", R"({"pin":42,"mode":"output"})");
  }
}
}  // namespace

int main() {
  const std::vector<std::pair<const char*, std::function<void()>>> tests = {
    {"audio_capabilities_and_public_status_are_truthful", audio_capabilities_and_public_status_are_truthful},
    {"configuration_requires_maintenance_and_is_transactional", configuration_requires_maintenance_and_is_transactional},
    {"persisted_peripherals_and_audio_runtime_pins_cannot_conflict", persisted_peripherals_and_audio_runtime_pins_cannot_conflict},
    {"recording_is_exact_bounded_little_endian_and_half_duplex", recording_is_exact_bounded_little_endian_and_half_duplex},
    {"playback_validates_base64_offsets_and_drains_before_end", playback_validates_base64_offsets_and_drains_before_end},
    {"single_direction_setups_and_explicit_stop_remain_reusable", single_direction_setups_and_explicit_stop_remain_reusable},
    {"release_retains_mapping_and_unconfigure_frees_owned_gpio", release_retains_mapping_and_unconfigure_frees_owned_gpio},
    {"maintenance_and_configuration_keep_only_session_mapping", maintenance_and_configuration_keep_only_session_mapping},
    {"outputs_stop_close_and_expiry_all_release_audio", outputs_stop_close_and_expiry_all_release_audio},
    {"failed_begin_and_partial_reads_never_claim_capture_success", failed_begin_and_partial_reads_never_claim_capture_success},
    {"failed_write_and_drain_end_stream_without_replay", failed_write_and_drain_end_stream_without_replay},
    {"failed_cleanup_retains_ownership_until_recovery", failed_cleanup_retains_ownership_until_recovery}};
  size_t failed = 0;
  for (const auto& test : tests) {
    try { test.second(); std::cout << "PASS " << test.first << '\n'; }
    catch (const std::exception& error) { ++failed; std::cerr << "FAIL " << test.first << ": " << error.what() << '\n'; }
  }
  std::cout << tests.size() << " audio-core tests, " << failed << " failures\n";
  return failed ? 1 : 0;
}
