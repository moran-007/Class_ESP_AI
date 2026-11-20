#include "device_core.h"
#include "fake_hardware.h"
#include <functional>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
void require(bool value, const std::string& why) { if (!value) throw std::runtime_error(why); }
const std::string rgb = R"({"schema_version":1,"config":{"schema_version":1,"servos":[]},"steps":[{"op":"led.set","args":{"red":8,"green":0,"blue":0}},{"op":"wait","args":{"ms":1000}},{"op":"led.set","args":{"red":0,"green":8,"blue":0}},{"op":"wait","args":{"ms":1000}}]})";
std::string json(JsonVariantConst value) { std::string s; serializeJson(value, s); return s; }
class Link {
 public:
  ai_maker::DeviceCore core;
  uint32_t now = 100;
  explicit Link(FakeHardware& h, bool open = true) : core(h) { core.begin(); if (open) ok("session.open"); }
  JsonDocument call(const std::string& op, const std::string& args = "{}") {
    JsonDocument request, a, reply;
    deserializeJson(a, args, DeserializationOption::NestingLimit(24));
    request["kind"] = "request"; request["protocol_version"] = 1; request["request_id"] = "p";
    request["session_id"] = "program-tests"; request["op"] = op; request["args"].set(a.as<JsonVariantConst>());
    require(!deserializeJson(reply, core.process(json(request.as<JsonVariantConst>()), now)), "valid JSON reply"); return reply;
  }
  JsonDocument ok(const std::string& op, const std::string& args = "{}") {
    auto r = call(op, args); require(r["ok"].as<bool>(), op + ": " + r["code"].as<std::string>() + " " + r["message"].as<std::string>()); return r;
  }
  void error(const std::string& op, const std::string& args, const std::string& code) {
    auto r = call(op, args); require(!r["ok"].as<bool>() && r["code"] == code, op + " must fail with " + code);
  }
  void save(const std::string& body = rgb, bool loop = true, bool boot = true) {
    ok("maintenance.enter"); ok("program.save", "{\"program\":" + body + ",\"loop\":" + (loop ? "true" : "false") + ",\"autostart\":" + (boot ? "true" : "false") + "}"); ok("maintenance.exit");
  }
  void tick(uint32_t n) { now = n; core.tick(n); }
};
void save_and_reboot_without_a_host() {
  FakeHardware h; Link live(h);
  require(live.ok("device.info")["data"]["capabilities"]["standalone_program"].as<bool>(), "capability");
  live.error("program.save", "{}", "MAINTENANCE_REQUIRED");
  live.save(); require(h.led[0] == 0 && h.program_saves == 1, "save never executes or writes repeatedly");
  live.ok("session.close"); require(h.led[0] == 0, "closing uploader does not start program");
  Link boot(h, false); boot.tick(100); require(h.led[0] == 8, "boot executes without host");
  boot.tick(1099); require(h.led[0] == 8, "nonblocking wait");
  boot.tick(1100); require(h.led[1] == 8 && h.led[0] == 0, "next action at deadline");
  boot.tick(2100); boot.tick(2101); require(h.led[0] == 8, "root repeat");
  require(h.program_saves == 1, "runtime does not wear flash");
}
void host_takeover_close_and_maintenance_block_boot() {
  FakeHardware h; Link writer(h); writer.save(); writer.ok("session.close");
  Link boot(h, false); boot.tick(100); boot.now = 101; boot.ok("session.open");
  require(h.led[0] == 0 && !boot.ok("program.info")["data"]["running"].as<bool>(), "takeover stops offline output");
  boot.ok("session.close"); boot.tick(3000); require(h.led[0] == 0, "no unexpected motion after close");
  boot.ok("session.open"); boot.ok("maintenance.enter");
  Link maintained(h, false); maintained.tick(100); require(h.led[0] == 0, "persistent maintenance beats boot policy");
}
void explicit_start_lease_and_finite_completion() {
  FakeHardware h; Link live(h); live.save(rgb, false, false); live.ok("program.start");
  live.error("led.set", R"({"red":1,"green":1,"blue":1})", "RESOURCE_CONFLICT");
  live.tick(1100); live.tick(2100); require(h.led[0] == 0 && h.led[1] == 0, "finite program releases outputs");
  live.ok("program.start"); live.tick(2101); live.tick(3101); live.tick(4101); live.tick(4200);
  require(!live.ok("program.info")["data"]["running"].as<bool>(), "finite program stays stopped");
  live.save(rgb, true, false); live.ok("program.start");
  const uint32_t lease_start = live.now;
  for (uint32_t n = 1; n <= 6; ++n) live.tick(lease_start + n * 1000);
  require(h.led[0] == 0 && h.led[1] == 0, "internal actions do not renew host lease");
  require(!live.ok("program.info")["data"]["running"].as<bool>(), "expiry cancels explicit execution");
}
void storage_failure_disable_clear_and_corruption() {
  FakeHardware h; Link live(h); live.save(); const std::string saved = h.program_state;
  h.program_save_ok = false; live.ok("maintenance.enter");
  live.error("program.disable", "{}", "STORAGE_ERROR");
  require(h.program_state == saved && live.ok("program.info")["data"]["enabled"].as<bool>(), "failed save retains old policy");
  h.program_save_ok = true; live.ok("program.disable"); live.ok("maintenance.exit"); live.ok("session.close");
  Link boot(h, false); boot.tick(100); require(h.led[0] == 0, "disabled boot");
  boot.ok("session.open"); boot.ok("maintenance.enter"); boot.ok("program.enable"); boot.ok("program.clear");
  boot.error("program.enable", "{}", "DEVICE_NOT_FOUND"); require(!boot.ok("program.info")["data"]["saved"].as<bool>(), "clear");
  h.program_state = "corrupt"; Link broken(h, false); broken.tick(100);
  require(!broken.ok("program.info")["data"]["error"].as<std::string>().empty(), "corruption reported");
  broken.ok("session.open"); broken.ok("maintenance.enter"); broken.ok("program.clear");
  require(broken.ok("program.info")["data"]["error"] == "", "clear repairs invalid record");
}
void conditions_and_failure_stop_outputs() {
  const std::string body = R"({"schema_version":1,"config":{"schema_version":1,"servos":[]},"steps":[{"op":"gpio.setup","args":{"pin":2,"mode":"input_pullup"}},{"op":"gpio.setup","args":{"pin":12,"mode":"output"}},{"op":"if.digital","args":{"pin":2,"value":0},"then":[{"op":"gpio.write","args":{"pin":12,"value":1}}],"else":[{"op":"gpio.write","args":{"pin":12,"value":0}}]},{"op":"wait","args":{"ms":10}}]})";
  class InputHardware : public FakeHardware {
   public:
    int button = 0;
    int readDigital(int pin) override { return pin == 2 ? button : FakeHardware::readDigital(pin); }
  } h;
  Link live(h); live.save(body); live.ok("session.close"); Link boot(h, false);
  boot.tick(100); require(h.digital[12] == 1, "button true branch");
  h.button = 1; boot.tick(110); boot.tick(111); require(h.digital[12] == 0, "button false branch");
  boot.now = 112; boot.ok("session.open");
  const std::string adc = R"({"schema_version":1,"config":{"schema_version":1,"servos":[]},"steps":[{"op":"gpio.setup","args":{"pin":1,"mode":"input"}},{"op":"if.analog","args":{"pin":1,"operator":">=","value":1000},"then":[{"op":"led.set","args":{"red":1,"green":2,"blue":3}}]},{"op":"wait","args":{"ms":100}}]})";
  boot.save(adc); boot.ok("program.start"); boot.tick(113); require(h.led[1] == 2, "ADC condition");
  boot.ok("program.stop"); boot.save(R"({"schema_version":1,"config":{"schema_version":1,"servos":[]},"steps":[{"op":"if.digital","args":{"pin":2,"value":0},"then":[{"op":"led.off","args":{}}]}]})");
  boot.ok("program.start"); boot.tick(114);
  require(!boot.ok("program.info")["data"]["running"].as<bool>() && boot.ok("program.info")["data"]["error"] != "", "missing setup stops program");
}
void mappings_are_private_and_cleanup_faults_retain_ownership() {
  FakeHardware h; Link live(h);
  live.ok("maintenance.enter"); live.ok("config.apply", R"({"expected_revision":0,"config":{"schema_version":1,"servos":[{"name":"original","pin":14,"min_angle":30,"max_angle":150,"min_pulse_us":1000,"max_pulse_us":2000}]}})"); live.ok("maintenance.exit");
  const std::string before = h.state;
  const std::string servo = R"({"schema_version":1,"config":{"schema_version":1,"servos":[{"name":"offline","pin":21,"min_angle":30,"max_angle":150,"min_pulse_us":1000,"max_pulse_us":2000}]},"steps":[{"op":"servo.move","args":{"device":"offline","angle":90}},{"op":"wait","args":{"ms":1000}}]})";
  live.save(servo); const auto stable = h.state; live.ok("program.start"); live.tick(101); require(h.pulse[21] == 1500, "program mapping");
  live.ok("program.stop"); require(h.pulse[21] == 0, "program servo released");
  require(live.ok("config.get")["data"]["config"]["servos"][0]["name"] == "original" && h.state == stable, "live mapping restored without flash write");
  require(before == stable, "save does not rewrite live config values");
  live.save(rgb); live.ok("program.start"); live.tick(102); h.output_ok = false;
  live.error("program.stop", "{}", "HARDWARE_ERROR");
  require(live.ok("program.info")["data"]["cleanup_required"].as<bool>(), "failed cleanup visible");
  live.error("led.off", "{}", "RESOURCE_CONFLICT");
  h.output_ok = true; live.ok("program.stop"); require(!live.ok("program.info")["data"]["cleanup_required"].as<bool>(), "retry cleanup");
}
void wait_wraparound_and_bounded_tight_loop() {
  FakeHardware h; Link live(h); live.save(); live.ok("session.close"); Link boot(h, false);
  boot.tick(0xfffffff0u); boot.tick(0x00000020u); require(h.led[0] == 8, "unsigned wait rollover");
  boot.tick(0x000003d8u); require(h.led[1] == 8, "rollover wait expires at1000ms");
  boot.now = 1000; boot.ok("session.open");
  boot.save(R"({"schema_version":1,"config":{"schema_version":1,"servos":[]},"steps":[{"op":"led.set","args":{"red":1,"green":0,"blue":0}}]})");
  boot.ok("program.start"); const auto writes = h.led_writes;
  boot.tick(1001); require(h.led_writes <= writes + 8, "work budget bounded");
  boot.ok("session.heartbeat"); boot.ok("program.stop");
}
void failed_cleanup_cannot_persist_program_mapping() {
  FakeHardware h; Link live(h);
  live.ok("maintenance.enter"); live.ok("config.apply", R"({"expected_revision":0,"config":{"schema_version":1,"servos":[{"name":"original","pin":14,"min_angle":30,"max_angle":150,"min_pulse_us":1000,"max_pulse_us":2000}]}})"); live.ok("maintenance.exit");
  JsonDocument program; deserializeJson(program, rgb);
  auto s = program["config"]["servos"].to<JsonArray>().add<JsonObject>();
  s["name"] = "offline"; s["pin"] = 21; s["min_angle"] = 30; s["max_angle"] = 150; s["min_pulse_us"] = 1000; s["max_pulse_us"] = 2000;
  live.save(json(program.as<JsonVariantConst>())); live.ok("program.start"); live.tick(101);
  h.output_ok = false; live.error("maintenance.enter", "{}", "HARDWARE_ERROR");
  JsonDocument saved; deserializeJson(saved, h.state);
  require(saved["config"]["servos"][0]["name"] == "original" && saved["config"]["servos"][0]["pin"] == 14, "cleanup failure must not persist offline snapshot into live NVS");
  require(saved["maintenance"].as<bool>(), "maintenance still persisted");
  h.output_ok = true; live.ok("program.stop");
}
void trailing_storage_corruption_never_autostarts() {
  FakeHardware h; Link live(h); live.save(); live.ok("session.close");
  h.program_state += " garbage";
  Link broken(h, false); broken.tick(100);
  require(h.led[0] == 0 && !broken.ok("program.info")["data"]["running"].as<bool>(), "trailing bytes must disable corrupted boot program");
  require(broken.ok("program.info")["data"]["error"] != "", "corruption visible");
}
void audio_mapping_restores_without_restarting_hardware() {
  FakeHardware h; Link live(h);
  live.ok("maintenance.enter"); live.ok("audio.configure", R"({"bclk":42,"ws":41,"din":21,"dout":40,"sd":39,"mic_channel":"left","volume":20})");
  live.ok("maintenance.exit"); live.ok("audio.begin");
  live.save(rgb, true, false); live.ok("program.start"); live.tick(101);
  require(!h.audio_active && !live.ok("audio.info")["data"]["configured"].as<bool>(), "program temporarily owns resources");
  live.ok("program.stop"); auto info = live.ok("audio.info");
  require(info["data"]["configured"].as<bool>() && !info["data"]["active"].as<bool>(), "audio mapping restored dormant");
  live.ok("audio.begin"); require(h.audio_active && !h.audio_capturing && !h.audio_playing, "live audio can begin again without reconfiguration");
}
void failed_close_and_expiry_never_leak_old_session_audio() {
  for (bool expiry : {false, true}) {
    FakeHardware h; Link live(h);
    live.ok("maintenance.enter"); live.ok("audio.configure", R"({"bclk":42,"ws":41,"din":21,"dout":40,"sd":39,"mic_channel":"left","volume":20})"); live.ok("maintenance.exit");
    live.save(rgb, true, false); live.ok("program.start"); live.tick(101);
    h.output_ok = false;
    if (expiry) live.tick(7000);
    else live.error("session.close", "{}", "HARDWARE_ERROR");
    h.output_ok = true; live.ok("session.open");
    require(!live.ok("audio.info")["data"]["configured"].as<bool>(), "old audio snapshot must not cross failed close/expiry into a new session");
  }
}
}
int main() {
  const std::vector<std::pair<const char*, std::function<void()>>> tests = {
    {"save_and_reboot_without_a_host", save_and_reboot_without_a_host},
    {"host_takeover_close_and_maintenance_block_boot", host_takeover_close_and_maintenance_block_boot},
    {"explicit_start_lease_and_finite_completion", explicit_start_lease_and_finite_completion},
    {"storage_failure_disable_clear_and_corruption", storage_failure_disable_clear_and_corruption},
    {"conditions_and_failure_stop_outputs", conditions_and_failure_stop_outputs},
    {"mappings_are_private_and_cleanup_faults_retain_ownership", mappings_are_private_and_cleanup_faults_retain_ownership},
    {"wait_wraparound_and_bounded_tight_loop", wait_wraparound_and_bounded_tight_loop},
    {"failed_cleanup_cannot_persist_program_mapping", failed_cleanup_cannot_persist_program_mapping},
    {"trailing_storage_corruption_never_autostarts", trailing_storage_corruption_never_autostarts},
    {"audio_mapping_restores_without_restarting_hardware", audio_mapping_restores_without_restarting_hardware},
    {"failed_close_and_expiry_never_leak_old_session_audio", failed_close_and_expiry_never_leak_old_session_audio}};
  int failures = 0;
  for (const auto& test : tests) { try { test.second(); std::cout << "PASS " << test.first << '\n'; }
    catch (const std::exception& e) { ++failures; std::cout << "FAIL " << test.first << ": " << e.what() << '\n'; } }
  std::cout << tests.size() << " program-core groups, " << failures << " failures\n"; return failures ? 1 : 0;
}
