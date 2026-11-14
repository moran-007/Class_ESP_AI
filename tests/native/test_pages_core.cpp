#include "device_core.h"
#include "fake_hardware.h"
#include <cstdio>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
void require(bool condition, const std::string& why) { if (!condition) throw std::runtime_error(why); }

class PageHardware final : public FakeHardware {
 public:
  std::array<std::string, 2> test_slots;
  bool slot_save_ok = true, slot_erase_ok = true;
  int erase_failure_slot = -1;
  bool init_ok = true, paint_ok = true, cleanup_ok = true;
  size_t begins = 0, cleanup_calls = 0, slot_saves = 0;
  std::vector<std::string> texts;
  std::string loadPageSlot(int slot) override { return test_slots.at(slot); }
  bool savePageSlot(int slot, const std::string& value) override {
    ++slot_saves;
    if (!slot_save_ok) return false;
    test_slots.at(slot) = value; return true;
  }
  bool erasePageSlot(int slot) override {
    if (!slot_erase_ok || slot == erase_failure_slot) return false;
    test_slots.at(slot).clear(); return true;
  }
  bool beginDisplay(const ai_maker::DisplaySpec& spec) override {
    ++begins;
    return init_ok && FakeHardware::beginDisplay(spec);
  }
  bool fillDisplay(uint16_t color) override { return paint_ok && FakeHardware::fillDisplay(color); }
  bool textDisplay(int x, int y, const std::string& value, uint16_t color) override {
    texts.push_back(value); return paint_ok && FakeHardware::textDisplay(x, y, value, color);
  }
  bool bitmapDisplay(int, int, int, int, const uint16_t*) override { return paint_ok && output_ok && display_active; }
  bool releaseDisplay() override {
    ++cleanup_calls;
    if (!cleanup_ok) return false;
    return FakeHardware::releaseDisplay();
  }
  void resetVolatile() {
    modes.fill(ai_maker::PinMode::Unset); digital.fill(0); pwm.fill(0); pulse.fill(0);
    display_active = false; texts.clear(); begins = cleanup_calls = servo_writes = 0;
  }
};

std::string json(const JsonDocument& doc) { std::string value; serializeJson(doc, value); return value; }
std::string crc(const std::string& value) {
  char buffer[9]; std::snprintf(buffer, sizeof(buffer), "%08lx", static_cast<unsigned long>(ai_maker::pageCrc32(value))); return buffer;
}
std::string project(const std::string& title = "Saved") {
  JsonDocument d;
  require(!deserializeJson(d, R"({"schema_version":1,"width":160,"height":128,"pages":[{"id":"home","background":0,"widgets":[{"id":"title","type":"text","x":8,"y":8,"text":"Saved","color":65535}]},{"id":"other","background":31,"widgets":[]}],"images":[]})"), "project fixture");
  d["pages"][0]["widgets"][0]["text"] = title;
  return json(d);
}

class Channel {
 public:
  PageHardware& hardware;
  ai_maker::DeviceCore core;
  uint32_t now = 100;
  unsigned sequence = 0;
  std::string owner = "test-owner";
  explicit Channel(PageHardware& h) : hardware(h), core(h) { core.begin(); }
  JsonDocument call(const std::string& op, const std::string& args = "{}", const std::string& identity = "test-owner") {
    JsonDocument request, reply;
    request["kind"] = "request"; request["protocol_version"] = 1; request["request_id"] = "p" + std::to_string(++sequence);
    request["op"] = op;
    if (!identity.empty()) request["session_id"] = identity;
    std::string line = json(request); line.pop_back(); line += ",\"args\":" + args + "}";
    require(!deserializeJson(reply, core.process(line, now)), "protocol reply must be JSON");
    return reply;
  }
  JsonDocument ok(const std::string& op, const std::string& args = "{}") {
    auto reply = call(op, args, owner);
    require(reply["ok"].as<bool>(), op + " failed: " + reply["code"].as<std::string>() + " / " + reply["message"].as<std::string>());
    return reply;
  }
  void error(const std::string& op, const std::string& args, const char* code) {
    auto reply = call(op, args, owner);
    require(!reply["ok"].as<bool>() && reply["code"] == code, op + " expected " + code + ", got " + reply["code"].as<std::string>());
  }
  void open() { ok("session.open"); }
  JsonDocument info() { return ok("pages.info"); }
  void configure(bool servo = false, const char* panel = "st7735s_128x160") {
    ok("maintenance.enter");
    JsonDocument args, config;
    args["expected_revision"] = ok("config.get")["data"]["revision"];
    require(!deserializeJson(config, R"({"schema_version":1,"servos":[],"display":{"panel":"st7735s_128x160","sck":4,"mosi":5,"cs":15,"dc":7,"rst":6,"backlight":-1,"rotation":1,"invert":false,"brightness":100}})"), "screen fixture");
    config["display"]["panel"] = panel;
    if (servo) {
      auto s = config["servos"].as<JsonArray>().add<JsonObject>();
      s["name"] = "head"; s["pin"] = 12; s["min_angle"] = 30; s["max_angle"] = 150; s["min_pulse_us"] = 1000; s["max_pulse_us"] = 2000;
    }
    args["config"].set(config.as<JsonObjectConst>());
    ok("config.apply", json(args)); ok("maintenance.exit");
  }
  std::string beginUpload(const std::string& value, const std::string& checksum = "") {
    JsonDocument args; args["bytes"] = value.size(); args["crc32"] = checksum.empty() ? crc(value) : checksum;
    return ok("pages.upload.begin", json(args))["data"]["upload_id"].as<std::string>();
  }
  void chunk(const std::string& token, size_t offset, const std::string& bytes) {
    JsonDocument args; args["upload_id"] = token; args["offset"] = offset; args["data"] = ai_maker::encodePageBase64(bytes);
    auto result = ok("pages.upload.chunk", json(args));
    require(result["data"]["next_offset"].as<size_t>() == offset + bytes.size(), "chunk acknowledgement tracks exact bytes");
  }
  std::string stage(const std::string& value, const std::string& checksum = "") {
    const auto token = beginUpload(value, checksum);
    for (size_t offset = 0; offset < value.size(); offset += 137) chunk(token, offset, value.substr(offset, 137));
    return token;
  }
  static std::string tokenArgs(const std::string& token) { JsonDocument d; d["upload_id"] = token; return json(d); }
  void upload(const std::string& value) { ok("pages.upload.commit", tokenArgs(stage(value))); }
  std::string download() {
    const size_t expected = info()["data"]["bytes"];
    std::string all;
    while (all.size() < expected) {
      const auto result = ok("pages.read", "{\"offset\":" + std::to_string(all.size()) + ",\"max_bytes\":97}");
      const auto data = result["data"];
      require(data["offset"].as<size_t>() == all.size() && data["total_bytes"].as<size_t>() == expected, "read offsets and total length");
      std::string part;
      require(ai_maker::decodePageBase64(data["data"].as<std::string>(), part, 97), "read base64 valid");
      require(!part.empty(), "nonfinal read must make progress");
      all += part;
      require(data["eof"].as<bool>() == (all.size() == expected), "eof matches exact length");
    }
    return all;
  }
};

void capabilities_public_info_and_owner_bound_reads() {
  PageHardware h; Channel c(h);
  auto info = c.ok("device.info");
  for (const auto* cap : {"pages", "page_images", "page_startup"}) require(info["data"]["capabilities"][cap].as<bool>(), "page capability");
  require(info["data"]["limits"]["page_project_bytes"] == 8192, "project bound advertised");
  auto public_info = c.call("pages.info", "{}", "");
  require(public_info["ok"].as<bool>() && !public_info["data"]["saved"].as<bool>(), "page info public with no project");
  c.error("pages.read", R"({"offset":0,"max_bytes":32})", "SESSION_REQUIRED");
  c.open(); c.upload(project());
  auto other = c.call("pages.read", R"({"offset":0,"max_bytes":32})", "other");
  require(!other["ok"].as<bool>() && other["code"] == "SESSION_REQUIRED", "read does not cross ownership");
  require(c.download() == project(), "saved project readback exact");
  c.error("pages.read", R"({"offset":-1,"max_bytes":32})", "INVALID_ARGUMENT");
  c.error("pages.read", R"({"offset":0,"max_bytes":769})", "INVALID_ARGUMENT");
  c.error("pages.read", R"({"offset":true,"max_bytes":1})", "INVALID_ARGUMENT");
}

void upload_validates_crc_offsets_token_and_preserves_prior_project() {
  PageHardware h; Channel c(h); c.open(); c.upload(project("Original"));
  const auto original = c.download();
  for (const auto* args : {R"({"bytes":0,"crc32":"00000000"})", R"({"bytes":8193,"crc32":"00000000"})", R"({"bytes":true,"crc32":"00000000"})", R"({"bytes":10,"crc32":"not-hex!"})"}) c.error("pages.upload.begin", args, "INVALID_ARGUMENT");
  const auto value = project("New");
  const auto token = c.beginUpload(value);
  c.error("pages.upload.begin", "{\"bytes\":1,\"crc32\":\"00000000\"}", "RESOURCE_CONFLICT");
  c.error("pages.upload.chunk", "{\"upload_id\":\"wrong\",\"offset\":0,\"data\":\"eA==\"}", "INVALID_ARGUMENT");
  c.error("pages.upload.chunk", "{\"upload_id\":\"" + token + "\",\"offset\":1,\"data\":\"eA==\"}", "INVALID_ARGUMENT");
  c.error("pages.upload.chunk", "{\"upload_id\":\"" + token + "\",\"offset\":0,\"data\":\"eB==\"}", "INVALID_ARGUMENT");
  c.error("pages.upload.commit", Channel::tokenArgs(token), "INVALID_ARGUMENT");
  require(c.download() == original, "partial upload is never published");
  c.ok("pages.upload.abort", Channel::tokenArgs(token));
  c.ok("pages.upload.abort", Channel::tokenArgs(token));
  auto foreign_abort = c.call("pages.upload.abort", Channel::tokenArgs(token), "other-owner");
  require(!foreign_abort["ok"].as<bool>() && foreign_abort["code"] == "SESSION_REQUIRED", "idempotent abort remains owner-scoped");
  const auto crc_token = c.stage(value, "00000000");
  c.error("pages.upload.abort", Channel::tokenArgs(token), "INVALID_ARGUMENT");
  c.error("pages.upload.commit", Channel::tokenArgs(crc_token), "INVALID_ARGUMENT");
  c.ok("pages.upload.abort", Channel::tokenArgs(crc_token));
  const auto bad_token = c.stage("{\"schema_version\":99}");
  c.error("pages.upload.commit", Channel::tokenArgs(bad_token), "INVALID_ARGUMENT");
  c.ok("pages.upload.abort", Channel::tokenArgs(bad_token));
  require(c.download() == original, "CRC/model failure retains old saved project");
  c.upload(value);
  require(c.download() == value && !c.info()["data"]["startup_enabled"].as<bool>(), "complete upload replaces atomically and starts disabled");
}

void maximum_size_upload_and_chunk_boundaries_are_enforced() {
  PageHardware h; Channel c(h); c.open();
  const auto compact = project("Boundary");
  std::string value = compact + std::string(8192 - compact.size(), ' ');
  const auto token = c.beginUpload(value);
  JsonDocument too_big;
  too_big["upload_id"] = token; too_big["offset"] = 0;
  too_big["data"] = ai_maker::encodePageBase64(std::string(769, 'x'));
  c.error("pages.upload.chunk", json(too_big), "INVALID_ARGUMENT");
  for (size_t offset = 0; offset < value.size(); offset += 768) c.chunk(token, offset, value.substr(offset, 768));
  c.ok("pages.upload.commit", Channel::tokenArgs(token));
  require(c.download() == compact, "maximum upload is validated then normalized before saving");
  c.error("pages.startup", R"({"enabled":true})", "CONFIG_INVALID");
  c.error("pages.show", R"({"id":"home"})", "CONFIG_INVALID");
  c.configure();
  c.error("pages.show", R"({"id":"unknown"})", "DEVICE_NOT_FOUND");
  c.error("pages.show", R"({"id":"bad-id"})", "INVALID_ARGUMENT");
  c.error("pages.startup", R"({"enabled":1})", "INVALID_ARGUMENT");
  c.error("pages.startup", R"({"enabled":true,"id":null})", "INVALID_ARGUMENT");
  c.error("pages.startup", R"({"enabled":true,"id":"absent"})", "INVALID_ARGUMENT");
}

void failed_slot_or_metadata_write_keeps_old_active_slot_and_policy() {
  for (const std::string failure : {"erase", "slot", "metadata"}) {
    PageHardware h; Channel c(h); c.open(); c.configure(); c.upload(project("Old"));
    c.ok("pages.startup", R"({"enabled":true,"id":"home"})");
    const auto state_before = h.state;
    JsonDocument state; require(!deserializeJson(state, state_before), "saved state");
    const int old_slot = state["pages"]["slot"];
    const auto old_blob = h.test_slots[old_slot];
    const auto token = c.stage(project("Replacement"));
    if (failure == "erase") h.slot_erase_ok = false;
    if (failure == "slot") h.slot_save_ok = false;
    if (failure == "metadata") h.save_ok = false;
    c.error("pages.upload.commit", Channel::tokenArgs(token), "STORAGE_ERROR");
    require(h.state == state_before && h.test_slots[old_slot] == old_blob, "active slot and metadata remain recoverable after " + failure);
    require(c.download() == old_blob && c.info()["data"]["startup_enabled"].as<bool>(), "failed commit does not change in-memory project/policy");
    h.slot_erase_ok = h.slot_save_ok = h.save_ok = true;
    c.ok("pages.upload.abort", Channel::tokenArgs(token));
    h.resetVolatile(); Channel rebooted(h);
    require(rebooted.info()["data"]["standalone_active"].as<bool>() && h.texts.back() == "Old", "reboot still restores old active project");
  }
}

void new_slot_is_published_before_old_slot_cleanup() {
  PageHardware h; Channel c(h); c.open(); c.upload(project("Old"));
  JsonDocument state; deserializeJson(state, h.state);
  const int old_slot = state["pages"]["slot"];
  h.erase_failure_slot = old_slot;
  c.upload(project("New"));
  require(c.download() == project("New"), "old-slot cleanup failure cannot invalidate published new project");
  require(!h.test_slots[old_slot].empty(), "faulted stale slot remains unreferenced");
  h.resetVolatile(); Channel rebooted(h); rebooted.open();
  require(rebooted.download() == project("New"), "reboot follows new metadata slot, not stale old slot");
}

void boot_default_takeover_close_and_stop_obey_display_ownership() {
  PageHardware h; Channel first(h); first.open(); first.configure(true); first.upload(project());
  first.ok("pages.startup", R"({"enabled":true,"id":"home"})");
  require(h.begins == 0 && h.servo_writes == 0, "save/startup settings do not initialize or move");
  first.ok("session.close");
  require(h.display_active && first.info()["data"]["standalone_active"].as<bool>(), "close restores default page");
  h.resetVolatile(); Channel c(h);
  require(h.begins == 1 && h.display_active && h.servo_writes == 0, "boot initializes only default screen, no servo motion");
  const auto closes_before = h.cleanup_calls;
  c.open();
  require(h.cleanup_calls == closes_before + 1 && !h.display_active && !c.info()["data"]["standalone_active"].as<bool>(), "session takes over after stopping default display");
  c.ok("pages.show", R"({"id":"other"})");
  c.ok("outputs.stop");
  require(!h.display_active && !c.info()["data"]["standalone_active"].as<bool>(), "explicit stop does not resume while lease remains");
  c.ok("servo.move", R"({"device":"head","angle":90})");
  c.ok("session.close");
  require(h.pulse[12] == 0 && h.display_active && h.texts.back() == "Saved", "close releases servo then restores saved page");
}

void expiry_restores_default_and_discards_uncommitted_upload() {
  PageHardware h; Channel c(h); c.open(); c.configure(); c.upload(project());
  c.ok("pages.startup", R"({"enabled":true,"id":"home"})");
  const auto token = c.beginUpload(project("NeverPublished"));
  c.chunk(token, 0, "{");
  c.now += ai_maker::kLeaseMs;
  c.core.tick(c.now);
  auto status = c.ok("device.status");
  require(!status["data"]["session_active"].as<bool>() && status["data"]["standalone_active"].as<bool>(), "lease expiry restores standalone display");
  c.open(); c.error("pages.upload.commit", Channel::tokenArgs(token), "INVALID_ARGUMENT");
  require(c.download() == project(), "uncommitted stage cannot replace saved project after expiry");
  c.ok("pages.startup", R"({"enabled":false})"); c.ok("session.close");
  require(!h.display_active, "disabled startup remains off on close");
}

void maintenance_survives_boot_and_geometry_change_disables_startup() {
  PageHardware h; Channel c(h); c.open(); c.configure(); c.upload(project());
  c.ok("pages.startup", R"({"enabled":true})"); c.ok("maintenance.enter");
  c.error("pages.show", R"({"id":"home"})", "MAINTENANCE_REQUIRED");
  c.error("pages.text", R"({"id":"title","text":"x"})", "MAINTENANCE_REQUIRED");
  c.error("pages.startup", R"({"enabled":false})", "MAINTENANCE_REQUIRED");
  c.ok("session.close"); h.resetVolatile(); Channel rebooted(h);
  require(rebooted.ok("device.status")["data"]["maintenance"].as<bool>() && h.begins == 0, "maintenance boot never resumes stored page");
  rebooted.open(); rebooted.configure(false, "st7789_240x320");
  require(!rebooted.info()["data"]["startup_enabled"].as<bool>() && rebooted.info()["data"]["saved"].as<bool>(), "incompatible display geometry disables startup but retains package");
  rebooted.error("pages.show", R"({"id":"home"})", "CONFIG_INVALID");
  rebooted.ok("session.close"); require(!h.display_active, "changed geometry cannot auto-show old page");
}

void runtime_text_is_not_persisted_and_has_strict_bounds() {
  PageHardware h; Channel c(h); c.open(); c.configure(); c.upload(project("Saved"));
  c.error("pages.text", R"({"id":"title","text":"Runtime"})", "INVALID_ARGUMENT");
  c.ok("pages.show", R"({"id":"home"})");
  const auto before = h.state; const size_t saves = h.saves;
  c.ok("pages.text", R"({"id":"title","text":"运行中"})");
  require(h.texts.back() == "运行中" && h.saves == saves && h.state == before, "runtime text draws but never saves state");
  require(c.download() == project("Saved"), "download excludes volatile text changes");
  for (const auto* args : {R"({"id":"title","text":""})", R"({"id":"title","text":"bad\u0000value"})", R"({"id":"title","text":"bad\u0085"})"}) c.error("pages.text", args, "INVALID_ARGUMENT");
  c.error("pages.text", R"({"id":"missing","text":"x"})", "DEVICE_NOT_FOUND");
  c.error("pages.text", "{\"id\":\"title\",\"text\":\"" + std::string(193, 'a') + "\"}", "INVALID_ARGUMENT");
  c.ok("pages.startup", R"({"enabled":true,"id":"home"})"); c.ok("session.close");
  require(h.texts.back() == "Saved", "default restore clears runtime text overrides");
}

void resume_failure_and_cleanup_failure_are_visible() {
  PageHardware h; Channel c(h); c.open(); c.configure(true); c.upload(project());
  c.ok("pages.startup", R"({"enabled":true,"id":"home"})");
  h.init_ok = false; c.error("session.close", "{}", "HARDWARE_ERROR");
  auto status = c.ok("device.status");
  require(!status["data"]["session_active"].as<bool>() && !status["data"]["standalone_active"].as<bool>() &&
          !status["data"]["display"]["driver_ok"].as<bool>(), "resume failure cannot claim a live standalone screen");
  require(!status["data"]["pages"]["last_error"].as<std::string>().empty(), "resume error exposed in state");
  h.init_ok = true; c.open(); c.ok("pages.show", R"({"id":"home"})");
  c.ok("gpio.setup", R"({"pin":18,"mode":"output"})"); c.ok("gpio.write", R"({"pin":18,"value":1})");
  c.ok("servo.move", R"({"device":"head","angle":90})");
  h.cleanup_ok = false; c.error("outputs.stop", "{}", "HARDWARE_ERROR");
  require(h.digital[18] == 0 && h.pulse[12] == 0, "display cleanup failure still releases GPIO and servo");
  h.cleanup_ok = true; c.ok("session.close");
  h.cleanup_ok = false;
  auto failed_open = c.call("session.open");
  require(!failed_open["ok"].as<bool>() && failed_open["code"] == "HARDWARE_ERROR", "default cleanup failure prevents new ownership");
  require(!c.ok("device.status")["data"]["session_active"].as<bool>(), "failed takeover cannot grant a session");
}

void clear_is_maintenance_only_and_preserves_hardware_configuration() {
  PageHardware h; Channel c(h); c.open(); c.configure(true); c.upload(project());
  std::string config;
  serializeJson(c.ok("config.get")["data"]["config"], config);
  c.error("pages.clear", "{}", "MAINTENANCE_REQUIRED");
  c.ok("maintenance.enter"); const auto prior = h.state; h.save_ok = false;
  c.error("pages.clear", "{}", "STORAGE_ERROR"); require(h.state == prior && c.info()["data"]["saved"].as<bool>(), "failed clear retains old project");
  h.save_ok = true; c.ok("pages.clear");
  require(!c.info()["data"]["saved"].as<bool>() && h.test_slots[0].empty() && h.test_slots[1].empty(), "clear removes saved project and slots");
  std::string after_config;
  serializeJson(c.ok("config.get")["data"]["config"], after_config);
  require(after_config == config, "page clear keeps servo and display mappings");
  h.resetVolatile(); Channel rebooted(h);
  require(!rebooted.info()["data"]["saved"].as<bool>() && rebooted.ok("device.status")["data"]["maintenance"].as<bool>(), "cleared state reboots in maintenance without pages");
}

void corrupt_page_slot_enters_maintenance_without_motion() {
  for (const std::string fault : {"missing", "crc", "metadata", "default_id", "geometry"}) {
    PageHardware h; Channel c(h); c.open(); c.configure(true); c.upload(project());
    c.ok("pages.startup", R"({"enabled":true})");
    JsonDocument state; deserializeJson(state, h.state); const int slot = state["pages"]["slot"];
    if (fault == "missing") h.test_slots[slot].clear();
    if (fault == "crc") h.test_slots[slot] += " ";
    if (fault == "metadata") { state["pages"]["slot"] = 2; h.state = json(state); }
    if (fault == "default_id") { state["pages"]["default_page"] = "missing"; h.state = json(state); }
    if (fault == "geometry") { state["config"]["display"]["panel"] = "st7789_240x320"; h.state = json(state); }
    h.resetVolatile(); Channel rebooted(h);
    const auto status = rebooted.ok("device.status");
    require(status["data"]["maintenance"].as<bool>() && status["data"]["storage_fault"].as<bool>(), "corrupt saved page enters maintenance");
    require(h.begins == 0 && h.servo_writes == 0, "corrupt state cannot initialize or move anything");
    const auto pages = rebooted.info();
    require(!pages["data"]["saved"].as<bool>() && pages["data"]["bytes"] == 0 &&
            pages["data"]["page_ids"].size() == 0 && !pages["data"]["startup_enabled"].as<bool>(),
            "failed saved metadata validation cannot publish orphan page data: " + fault);

    // Repair only the hardware configuration through the ordinary maintenance
    // API. It must not turn an uncommitted slot into a displayable project.
    rebooted.open();
    const auto current = rebooted.ok("config.get");
    JsonDocument repair;
    repair["expected_revision"] = current["data"]["revision"];
    repair["config"].set(current["data"]["config"]);
    rebooted.ok("config.apply", json(repair));
    rebooted.ok("maintenance.exit");
    rebooted.error("pages.startup", R"({"enabled":true})", "CONFIG_INVALID");
    rebooted.error("pages.show", R"({"id":"home"})", "DEVICE_NOT_FOUND");
    require(!rebooted.info()["data"]["saved"].as<bool>() && h.begins == 0,
            "configuration repair must not resurrect rejected page data: " + fault);
    rebooted.ok("session.close");
    h.resetVolatile(); Channel repaired_boot(h);
    require(!repaired_boot.ok("device.status")["data"]["storage_fault"].as<bool>() &&
            !repaired_boot.info()["data"]["startup_enabled"].as<bool>() && h.begins == 0,
            "repaired metadata stays free of orphan startup across another reboot: " + fault);
  }
}
}  // namespace

int main() {
  const std::vector<std::pair<const char*, std::function<void()>>> tests = {
      {"capabilities_public_info_and_owner_bound_reads", capabilities_public_info_and_owner_bound_reads},
      {"upload_validates_crc_offsets_token_and_preserves_prior_project", upload_validates_crc_offsets_token_and_preserves_prior_project},
      {"maximum_size_upload_and_chunk_boundaries_are_enforced", maximum_size_upload_and_chunk_boundaries_are_enforced},
      {"failed_slot_or_metadata_write_keeps_old_active_slot_and_policy", failed_slot_or_metadata_write_keeps_old_active_slot_and_policy},
      {"new_slot_is_published_before_old_slot_cleanup", new_slot_is_published_before_old_slot_cleanup},
      {"boot_default_takeover_close_and_stop_obey_display_ownership", boot_default_takeover_close_and_stop_obey_display_ownership},
      {"expiry_restores_default_and_discards_uncommitted_upload", expiry_restores_default_and_discards_uncommitted_upload},
      {"maintenance_survives_boot_and_geometry_change_disables_startup", maintenance_survives_boot_and_geometry_change_disables_startup},
      {"runtime_text_is_not_persisted_and_has_strict_bounds", runtime_text_is_not_persisted_and_has_strict_bounds},
      {"resume_failure_and_cleanup_failure_are_visible", resume_failure_and_cleanup_failure_are_visible},
      {"clear_is_maintenance_only_and_preserves_hardware_configuration", clear_is_maintenance_only_and_preserves_hardware_configuration},
      {"corrupt_page_slot_enters_maintenance_without_motion", corrupt_page_slot_enters_maintenance_without_motion}};
  size_t failed = 0;
  for (const auto& test : tests) {
    try { test.second(); std::cout << "PASS " << test.first << '\n'; }
    catch (const std::exception& error) { ++failed; std::cerr << "FAIL " << test.first << ": " << error.what() << '\n'; }
  }
  std::cout << tests.size() << " page-runtime tests, " << failed << " failures\n";
  return failed ? 1 : 0;
}
