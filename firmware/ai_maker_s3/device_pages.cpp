#include "device_core.h"
#include <cstdio>
#include <cstring>
#include <initializer_list>

namespace ai_maker {
namespace {
void reject(JsonDocument& response, const char* code, const std::string& message) {
  response["ok"] = false; response["code"] = code; response["message"] = message; response.remove("data");
}
bool keys(JsonObjectConst object, std::initializer_list<const char*> allowed) {
  for (JsonPairConst pair : object) {
    bool found = false;
    for (const auto* name : allowed) if (pair.key() == name) found = true;
    if (!found) return false;
  }
  return true;
}
bool number(JsonVariantConst value) { return value.is<int>() && !value.is<bool>(); }
bool stringValue(JsonVariantConst value, size_t maximum, bool empty = false) {
  if (!value.is<const char*>()) return false;
  const auto s = value.as<JsonString>();
  return (empty || s.size() > 0) && s.size() <= maximum && std::strlen(s.c_str()) == s.size();
}
std::string crcString(uint32_t value) {
  char text[9]; std::snprintf(text, sizeof(text), "%08lx", static_cast<unsigned long>(value)); return text;
}
bool parseCrc(JsonVariantConst value, uint32_t& result) {
  if (!stringValue(value, 8) || value.as<JsonString>().size() != 8) return false;
  result = 0;
  for (const char c : value.as<std::string>()) {
    const int digit = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
    if (digit < 0) return false;
    result = (result << 4) | static_cast<uint32_t>(digit);
  }
  return true;
}
}

void DeviceCore::clearPageUpload() {
  upload_id_.clear(); upload_data_.clear(); aborted_upload_id_.clear(); upload_expected_ = 0; upload_crc_ = 0;
}

void DeviceCore::writePagesInfo(JsonObject target) const {
  target["saved"] = page_settings_.slot >= 0;
  target["bytes"] = page_project_.json.size();
  target["crc32"] = page_project_.json.empty() ? "" : crcString(pageCrc32(page_project_.json));
  target["width"] = page_project_.width; target["height"] = page_project_.height;
  auto ids = target["page_ids"].to<JsonArray>();
  for (JsonObjectConst page : page_project_.document["pages"].as<JsonArrayConst>()) ids.add(page["id"]);
  target["startup_enabled"] = page_settings_.startup_enabled;
  target["default_page"] = page_settings_.default_page;
  target["shown_page"] = shown_page_; target["standalone_active"] = standalone_active_;
  target["last_error"] = page_error_;
}

bool DeviceCore::pageFitsDisplay(const PageProject& project, const DisplaySpec& spec) const {
  if (!spec.enabled || project.json.empty()) return false;
  int width = 0, height = 0;
  if (spec.panel == "st7789_240x320") { width = 240; height = 320; }
  else if (spec.panel == "st7789_240x240") width = height = 240;
  else if (spec.panel == "st7735s_128x160") { width = 128; height = 160; }
  if (spec.rotation % 2) { const int old = width; width = height; height = old; }
  return width == project.width && height == project.height;
}

bool DeviceCore::loadPagesState(JsonObjectConst state, int version) {
  if (version == 1) return state["pages"].isNull();
  const auto p = state["pages"].as<JsonObjectConst>();
  uint32_t crc = 0;
  if (p.isNull() || !keys(p, {"slot", "crc32", "startup_enabled", "default_page"}) ||
      !number(p["slot"]) || p["slot"].as<int>() < 0 || p["slot"].as<int>() > 1 ||
      !parseCrc(p["crc32"], crc) || !p["startup_enabled"].is<bool>() || !stringValue(p["default_page"], 24)) {
    page_error_ = "Invalid saved page metadata"; return false;
  }
  const int slot = p["slot"];
  const std::string blob = hardware_.loadPageSlot(slot);
  PageProject candidate;
  if (blob.empty() || blob.size() > kMaxPageProjectBytes || pageCrc32(blob) != crc ||
      !parsePageProject(blob, candidate, page_error_)) {
    page_error_ = "Saved page slot is missing or invalid"; return false;
  }
  const std::string id = p["default_page"].as<std::string>();
  if (!hasPage(candidate, id) || (p["startup_enabled"].as<bool>() && !pageFitsDisplay(candidate, display_))) {
    page_error_ = "Saved default page does not match screen"; return false;
  }
  page_settings_.slot = slot; page_settings_.crc32 = crcString(crc);
  page_settings_.startup_enabled = p["startup_enabled"]; page_settings_.default_page = id;
  page_project_ = std::move(candidate);
  return true;
}

bool DeviceCore::showPage(const std::string& id, bool standalone) {
  if (!hasPage(page_project_, id)) { page_error_ = "Page ID not found"; return false; }
  if (!pageFitsDisplay(page_project_, display_)) { page_error_ = "Page canvas does not match configured screen"; return false; }
  if (!display_active_ || !display_driver_ok_) {
    if ((display_active_ || !display_driver_ok_) && !hardware_.releaseDisplay()) {
      display_driver_ok_ = false; page_error_ = "Display cleanup failed"; return false;
    }
    display_driver_ok_ = hardware_.beginDisplay(display_);
    if (!display_driver_ok_) {
      hardware_.releaseDisplay(); display_active_ = false;
      page_error_ = "Display initialization failed"; return false;
    }
    display_active_ = true; display_brightness_ = display_.brightness;
  }
  display_driver_ok_ = renderPageProject(hardware_, page_project_, id, page_text_overrides_, page_error_);
  if (!display_driver_ok_) return false;
  shown_page_ = id; standalone_active_ = standalone; page_error_.clear(); return true;
}

bool DeviceCore::resumeDefaultPage() {
  if (maintenance_ || storage_fault_ || !session_.empty() || program_context_active_ || program_boot_pending_ || !page_settings_.startup_enabled) return true;
  page_text_overrides_.clear();
  return showPage(page_settings_.default_page, true);
}

void DeviceCore::dispatchPages(const std::string& op, JsonObjectConst args, JsonDocument& response) {
  auto data = response["data"].as<JsonObject>();
  if (op == "pages.read") {
    if (!keys(args, {"offset", "max_bytes"}) || !number(args["offset"]) || !number(args["max_bytes"]) ||
        args["offset"].as<int>() < 0 || args["max_bytes"].as<int>() < 1 || args["max_bytes"].as<int>() > 768)
      return reject(response, "INVALID_ARGUMENT", "Invalid page read offset or size");
    if (page_settings_.slot < 0) return reject(response, "DEVICE_NOT_FOUND", "No saved page project");
    const size_t offset = args["offset"].as<size_t>();
    if (offset > page_project_.json.size()) return reject(response, "INVALID_ARGUMENT", "Read offset exceeds project");
    const auto bytes = page_project_.json.substr(offset, args["max_bytes"].as<size_t>());
    data["offset"] = offset; data["data"] = encodePageBase64(bytes);
    data["total_bytes"] = page_project_.json.size(); data["eof"] = offset + bytes.size() == page_project_.json.size(); return;
  }
  if (op == "pages.upload.begin") {
    uint32_t crc = 0;
    if (!keys(args, {"bytes", "crc32"}) || !number(args["bytes"]) || args["bytes"].as<int>() < 1 ||
        args["bytes"].as<int>() > static_cast<int>(kMaxPageProjectBytes) || !parseCrc(args["crc32"], crc))
      return reject(response, "INVALID_ARGUMENT", "Project must be 1 to 8192 bytes with CRC32 hex");
    if (!upload_id_.empty()) return reject(response, "RESOURCE_CONFLICT", "Abort the current page upload first");
    aborted_upload_id_.clear(); upload_expected_ = args["bytes"].as<size_t>(); upload_crc_ = crc;
    upload_data_.clear(); upload_data_.reserve(upload_expected_);
    upload_id_ = "upload-" + std::to_string(++upload_sequence_);
    data["upload_id"] = upload_id_; return;
  }
  if (op == "pages.upload.chunk" || op == "pages.upload.commit" || op == "pages.upload.abort") {
    if (op == "pages.upload.abort" && upload_id_.empty() && !aborted_upload_id_.empty() &&
        keys(args, {"upload_id"}) && stringValue(args["upload_id"], 40) && args["upload_id"].as<std::string>() == aborted_upload_id_) {
      data["aborted"] = true; return;
    }
    if (!stringValue(args["upload_id"], 40) || upload_id_.empty() || args["upload_id"].as<std::string>() != upload_id_)
      return reject(response, "INVALID_ARGUMENT", "Upload ID is not current");
    if (op == "pages.upload.abort") {
      if (!keys(args, {"upload_id"})) return reject(response, "INVALID_ARGUMENT", "Unexpected upload arguments");
      const std::string cancelled = upload_id_;
      clearPageUpload(); aborted_upload_id_ = cancelled; data["aborted"] = true; return;
    }
    if (op == "pages.upload.chunk") {
      std::string decoded;
      if (!keys(args, {"upload_id", "offset", "data"}) || !number(args["offset"]) || args["offset"].as<int>() < 0 ||
          args["offset"].as<size_t>() != upload_data_.size() || !stringValue(args["data"], 1024) ||
          !decodePageBase64(args["data"].as<std::string>(), decoded, 768) || decoded.empty() ||
          decoded.size() > upload_expected_ - upload_data_.size())
        return reject(response, "INVALID_ARGUMENT", "Invalid upload offset, base64 or chunk size");
      upload_data_ += decoded; data["next_offset"] = upload_data_.size(); return;
    }
    if (!keys(args, {"upload_id"}) || upload_data_.size() != upload_expected_ || pageCrc32(upload_data_) != upload_crc_)
      return reject(response, "INVALID_ARGUMENT", "Upload length or CRC32 does not match");
    PageProject next;
    std::string error;
    if (!parsePageProject(upload_data_, next, error)) return reject(response, "INVALID_ARGUMENT", error);
    const int slot = page_settings_.slot == 0 ? 1 : 0;
    if (!hardware_.erasePageSlot(slot) || !hardware_.savePageSlot(slot, next.json))
      return reject(response, "STORAGE_ERROR", "Page project not saved; previous project retained");
    PageSettings settings;
    settings.slot = slot; settings.crc32 = crcString(pageCrc32(next.json)); settings.default_page = firstPageId(next);
    if (!hardware_.saveState(stateBlob(maintenance_, revision_, servos_, servo_count_, display_, &settings)))
      return reject(response, "STORAGE_ERROR", "Page metadata not saved; previous project retained");
    const int old_slot = page_settings_.slot;
    page_settings_ = settings; page_project_ = std::move(next); page_text_overrides_.clear(); shown_page_.clear();
    if (old_slot >= 0) hardware_.erasePageSlot(old_slot);
    clearPageUpload(); page_error_.clear(); writePagesInfo(data); return;
  }
  if (op == "pages.clear") {
    if (!keys(args, {})) return reject(response, "INVALID_ARGUMENT", "pages.clear takes no arguments");
    if (!maintenance_) return reject(response, "MAINTENANCE_REQUIRED", "Enter maintenance before removing saved pages");
    const PageSettings empty;
    if (!hardware_.saveState(stateBlob(true, revision_, servos_, servo_count_, display_, &empty)))
      return reject(response, "STORAGE_ERROR", "Page metadata could not be cleared");
    PageProject blank;
    page_settings_ = empty; page_project_ = std::move(blank);
    clearPageUpload(); shown_page_.clear(); page_text_overrides_.clear(); page_error_.clear();
    hardware_.erasePageSlot(0); hardware_.erasePageSlot(1); writePagesInfo(data); return;
  }
  if (maintenance_) return reject(response, "MAINTENANCE_REQUIRED", "Page display and startup are disabled in maintenance");
  if (op == "pages.show") {
    if (!keys(args, {"id"}) || !stringValue(args["id"], 24) || !validPageId(args["id"].as<std::string>()))
      return reject(response, "INVALID_ARGUMENT", "Invalid page ID");
    const std::string id = args["id"].as<std::string>();
    if (!hasPage(page_project_, id)) return reject(response, "DEVICE_NOT_FOUND", "Page ID not found");
    if (!pageFitsDisplay(page_project_, display_)) return reject(response, "CONFIG_INVALID", "Configure matching screen size before showing page");
    page_text_overrides_.clear();
    if (!showPage(id, false)) return reject(response, "HARDWARE_ERROR", page_error_);
    data["id"] = id; data["state"] = "commanded"; data["physical_verified"] = false; return;
  }
  if (op == "pages.text") {
    if (!keys(args, {"id", "text"}) || !stringValue(args["id"], 24) || !stringValue(args["text"], 192) ||
        !validPageText(args["text"].as<std::string>())) return reject(response, "INVALID_ARGUMENT", "Invalid widget ID or text");
    if (!display_active_ || shown_page_.empty()) return reject(response, "INVALID_ARGUMENT", "Show a page before updating text");
    bool found = false;
    for (JsonObjectConst page : page_project_.document["pages"].as<JsonArrayConst>()) {
      if (page["id"].as<std::string>() != shown_page_) continue;
      for (JsonObjectConst widget : page["widgets"].as<JsonArrayConst>())
        if (widget["id"] == args["id"] && widget["type"] == "text") found = true;
    }
    if (!found) return reject(response, "DEVICE_NOT_FOUND", "Text widget not found on the current page");
    page_text_overrides_[args["id"].as<std::string>()] = args["text"].as<std::string>();
    if (!showPage(shown_page_, false)) return reject(response, "HARDWARE_ERROR", page_error_);
    data["state"] = "commanded"; data["physical_verified"] = false; return;
  }
  if (op == "pages.startup") {
    if (!keys(args, {"enabled", "id"}) || !args["enabled"].is<bool>()) return reject(response, "INVALID_ARGUMENT", "enabled must be boolean");
    PageSettings next = page_settings_;
    next.startup_enabled = args["enabled"];
    if (!args["id"].isUnbound()) {
      if (!stringValue(args["id"], 24) || !hasPage(page_project_, args["id"].as<std::string>()))
        return reject(response, "INVALID_ARGUMENT", "Default page ID not found");
      next.default_page = args["id"].as<std::string>();
    }
    if (next.startup_enabled && (next.slot < 0 || !hasPage(page_project_, next.default_page) || !pageFitsDisplay(page_project_, display_)))
      return reject(response, "CONFIG_INVALID", "Saved page and matching screen are required for startup");
    if (!hardware_.saveState(stateBlob(false, revision_, servos_, servo_count_, display_, &next)))
      return reject(response, "STORAGE_ERROR", "Startup settings not saved; previous settings retained");
    page_settings_ = next; writePagesInfo(data); return;
  }
  reject(response, "UNSUPPORTED_OPERATION", "Unknown page operation");
}
}  // namespace ai_maker
