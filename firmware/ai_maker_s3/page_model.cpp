#include "page_model.h"
#include "device_core.h"

#include <cstring>
#include <initializer_list>
#include <set>
#include <utility>
#include <vector>

namespace ai_maker {
namespace {
bool integer(JsonVariantConst value) { return value.is<int>() && !value.is<bool>(); }

bool stringValue(JsonVariantConst value, size_t limit) {
  if (!value.is<const char*>()) return false;
  const auto s = value.as<JsonString>();
  return s.size() > 0 && s.size() <= limit && std::strlen(s.c_str()) == s.size();
}

bool keys(JsonObjectConst object, std::initializer_list<const char*> allowed) {
  for (JsonPairConst pair : object) {
    bool found = false;
    for (const auto* name : allowed) {
      if (pair.key().size() == std::strlen(name) && pair.key() == name) found = true;
    }
    if (!found) return false;
  }
  return true;
}

bool utf8(const std::string& value, bool controls) {
  for (size_t i = 0; i < value.size();) {
    const auto lead = static_cast<uint8_t>(value[i++]);
    uint32_t cp = lead;
    int extra = 0;
    if (lead >= 0xc2 && lead <= 0xdf) { cp = lead & 0x1f; extra = 1; }
    else if (lead >= 0xe0 && lead <= 0xef) { cp = lead & 0x0f; extra = 2; }
    else if (lead >= 0xf0 && lead <= 0xf4) { cp = lead & 7; extra = 3; }
    else if (lead >= 0x80) return false;
    if (i + extra > value.size()) return false;
    for (int n = 0; n < extra; ++n) {
      const auto tail = static_cast<uint8_t>(value[i++]);
      if ((tail & 0xc0) != 0x80) return false;
      cp = (cp << 6) | (tail & 0x3f);
    }
    if ((extra == 1 && cp < 0x80) || (extra == 2 && cp < 0x800) ||
        (extra == 3 && cp < 0x10000) || cp > 0x10ffff ||
        (cp >= 0xd800 && cp <= 0xdfff) || cp == 0 ||
        (controls && ((cp < 0x20 && cp != '\n') || (cp >= 0x7f && cp <= 0x9f)))) return false;
  }
  return true;
}

bool oneObject(const std::string& value) {
  const auto space = [](char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; };
  size_t start = 0;
  while (start < value.size() && space(value[start])) ++start;
  if (start == value.size() || value[start] != '{') return false;
  int depth = 0;
  bool quoted = false, escaped = false;
  for (size_t i = start; i < value.size(); ++i) {
    const char c = value[i];
    if (quoted) {
      if (escaped) escaped = false;
      else if (c == '\\') escaped = true;
      else if (c == '"') quoted = false;
    } else if (c == '"') quoted = true;
    else if (c == '{' || c == '[') ++depth;
    else if (c == '}' || c == ']') {
      if (--depth < 0) return false;
      if (depth == 0) {
        for (++i; i < value.size(); ++i) if (!space(value[i])) return false;
        return true;
      }
    }
  }
  return false;
}

bool between(JsonVariantConst value, int low, int high) {
  return integer(value) && value.as<int>() >= low && value.as<int>() <= high;
}

bool idValue(JsonVariantConst value) {
  return stringValue(value, 24) && validPageId(value.as<std::string>());
}

JsonObjectConst imageWithId(JsonArrayConst images, const std::string& id) {
  for (JsonObjectConst image : images) if (image["id"] == id) return image;
  return JsonObjectConst();
}

JsonObjectConst pageWithId(const PageProject& project, const std::string& id) {
  for (JsonObjectConst page : project.document["pages"].as<JsonArrayConst>()) {
    if (page["id"] == id) return page;
  }
  return JsonObjectConst();
}

int base64Value(char c) {
  if (c >= 'A' && c <= 'Z') return c - 'A';
  if (c >= 'a' && c <= 'z') return c - 'a' + 26;
  if (c >= '0' && c <= '9') return c - '0' + 52;
  if (c == '+') return 62;
  if (c == '/') return 63;
  return -1;
}
}  // namespace

bool validPageId(const std::string& value) {
  const auto letter = [](char c) { return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'); };
  if (value.empty() || value.size() > 24 || !letter(value[0])) return false;
  for (char c : value) if (!letter(c) && !(c >= '0' && c <= '9') && c != '_') return false;
  return true;
}

bool validPageText(const std::string& value) {
  return !value.empty() && value.size() <= 192 && utf8(value, true);
}

uint32_t pageCrc32(const std::string& value) {
  uint32_t crc = 0xffffffffU;
  for (unsigned char byte : value) {
    crc ^= byte;
    for (int bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ ((crc & 1) ? 0xedb88320U : 0U);
  }
  return ~crc;
}

bool decodePageBase64(const std::string& value, std::string& out, size_t max_bytes) {
  if (value.size() % 4 != 0) return false;
  const size_t groups = value.size() / 4;
  if (groups > max_bytes / 3 + 1) return false;
  size_t padding = 0;
  if (!value.empty() && value.back() == '=') {
    padding = 1;
    if (value[value.size() - 2] == '=') padding = 2;
  }
  const size_t length = groups * 3 - padding;
  if (length > max_bytes) return false;
  std::string candidate;
  candidate.reserve(length);
  for (size_t start = 0; start < value.size(); start += 4) {
    const int a = base64Value(value[start]), b = base64Value(value[start + 1]);
    const int c = base64Value(value[start + 2]), d = base64Value(value[start + 3]);
    if (a < 0 || b < 0) return false;
    const bool last = start + 4 == value.size();
    candidate.push_back(static_cast<char>((a << 2) | (b >> 4)));
    if (value[start + 2] == '=') {
      if (!last || value[start + 3] != '=' || (b & 15) != 0) return false;
    } else {
      if (c < 0) return false;
      candidate.push_back(static_cast<char>((b << 4) | (c >> 2)));
      if (value[start + 3] == '=') {
        if (!last || (c & 3) != 0) return false;
      } else {
        if (d < 0) return false;
        candidate.push_back(static_cast<char>((c << 6) | d));
      }
    }
  }
  if (candidate.size() != length) return false;
  out = std::move(candidate);
  return true;
}

std::string encodePageBase64(const std::string& value) {
  static constexpr char alphabet[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::string result;
  result.reserve(((value.size() + 2) / 3) * 4);
  for (size_t i = 0; i < value.size(); i += 3) {
    const auto a = static_cast<uint8_t>(value[i]);
    const auto b = i + 1 < value.size() ? static_cast<uint8_t>(value[i + 1]) : 0;
    const auto c = i + 2 < value.size() ? static_cast<uint8_t>(value[i + 2]) : 0;
    result.push_back(alphabet[a >> 2]);
    result.push_back(alphabet[((a & 3) << 4) | (b >> 4)]);
    result.push_back(i + 1 < value.size() ? alphabet[((b & 15) << 2) | (c >> 6)] : '=');
    result.push_back(i + 2 < value.size() ? alphabet[c & 63] : '=');
  }
  return result;
}

bool parsePageProject(const std::string& json, PageProject& out, std::string& error) {
  error.clear();
  const auto reject = [&](const char* message) { error = message; return false; };
  if (json.empty() || json.size() > kMaxPageProjectBytes || !utf8(json, false) || !oneObject(json))
    return reject("Project must be one valid UTF8 JSON object of at most 8192 bytes");
  JsonDocument doc;
  if (deserializeJson(doc, json, DeserializationOption::NestingLimit(10))) return reject("Project JSON is invalid or too deeply nested");
  const auto object = doc.as<JsonObjectConst>();
  if (object.isNull() || !keys(object, {"schema_version", "width", "height", "pages", "images"}) ||
      !integer(object["schema_version"]) || object["schema_version"].as<int>() != 1 ||
      !between(object["width"], 1, 320) || !between(object["height"], 1, 320) ||
      !object["pages"].is<JsonArrayConst>() || !object["images"].is<JsonArrayConst>())
    return reject("Project requires schema_version 1, dimensions, pages and images");
  const int width = object["width"], height = object["height"];
  const auto images = object["images"].as<JsonArrayConst>();
  const auto pages = object["pages"].as<JsonArrayConst>();
  if (images.size() > 4 || pages.size() < 1 || pages.size() > 4) return reject("Project supports one to four pages and at most four images");
  std::set<std::string> image_ids;
  size_t decoded_bytes = 0;
  for (JsonVariantConst value : images) {
    const auto image = value.as<JsonObjectConst>();
    if (image.isNull() || !keys(image, {"id", "width", "height", "data"}) || !idValue(image["id"]) ||
        !between(image["width"], 1, 48) || !between(image["height"], 1, 48) ||
        !stringValue(image["data"], 6144)) return reject("Image fields or dimensions are invalid");
    if (!image_ids.insert(image["id"].as<std::string>()).second) return reject("Image IDs must be unique");
    std::string bytes;
    const size_t expected = static_cast<size_t>(image["width"].as<int>()) * image["height"].as<int>() * 2;
    if (!decodePageBase64(image["data"].as<std::string>(), bytes, kMaxPageImageBytes) || bytes.size() != expected)
      return reject("Image data must be canonical base64 RGB565 with exact pixel length");
    decoded_bytes += bytes.size();
    if (decoded_bytes > kMaxPageImageBytes) return reject("Total decoded image data exceeds 4608 bytes");
  }
  size_t widget_count = 0;
  std::set<std::string> page_ids;
  for (JsonVariantConst value : pages) {
    const auto page = value.as<JsonObjectConst>();
    if (page.isNull() || !keys(page, {"id", "background", "widgets"}) || !idValue(page["id"]) ||
        !between(page["background"], 0, 65535) || !page["widgets"].is<JsonArrayConst>()) return reject("Page fields are invalid");
    if (!page_ids.insert(page["id"].as<std::string>()).second) return reject("Page IDs must be unique");
    const auto widgets = page["widgets"].as<JsonArrayConst>();
    widget_count += widgets.size();
    if (widget_count > 32) return reject("Project has more than 32 widgets");
    std::set<std::string> widget_ids;
    for (JsonVariantConst widget_value : widgets) {
      const auto widget = widget_value.as<JsonObjectConst>();
      if (widget.isNull() || !idValue(widget["id"]) || !stringValue(widget["type"], 8)) return reject("Widget ID or type is invalid");
      if (!widget_ids.insert(widget["id"].as<std::string>()).second) return reject("Widget IDs must be unique in each page");
      const std::string type = widget["type"].as<std::string>();
      const auto point = [&](const char* x, const char* y) { return between(widget[x], 0, width - 1) && between(widget[y], 0, height - 1); };
      if (type == "text") {
        if (!keys(widget, {"id", "type", "x", "y", "text", "color"}) || !point("x", "y") ||
            !between(widget["color"], 0, 65535) || !stringValue(widget["text"], 192) ||
            !validPageText(widget["text"].as<std::string>())) return reject("Text widget fields are invalid");
      } else if (type == "rect") {
        if (!keys(widget, {"id", "type", "x", "y", "width", "height", "color", "filled"}) || !point("x", "y") ||
            !between(widget["color"], 0, 65535) || !widget["filled"].is<bool>() ||
            !between(widget["width"], 1, width - widget["x"].as<int>()) ||
            !between(widget["height"], 1, height - widget["y"].as<int>())) return reject("Rectangle must fit the page canvas");
      } else if (type == "line") {
        if (!keys(widget, {"id", "type", "x0", "y0", "x1", "y1", "color"}) || !point("x0", "y0") ||
            !point("x1", "y1") || !between(widget["color"], 0, 65535)) return reject("Line endpoints must fit the page canvas");
      } else if (type == "image") {
        if (!keys(widget, {"id", "type", "x", "y", "asset"}) || !point("x", "y") || !idValue(widget["asset"]))
          return reject("Image widget fields are invalid");
        const auto image = imageWithId(images, widget["asset"].as<std::string>());
        if (image.isNull() || image["width"].as<int>() > width - widget["x"].as<int>() ||
            image["height"].as<int>() > height - widget["y"].as<int>()) return reject("Image reference is missing or outside the page canvas");
      } else return reject("Unknown widget type");
    }
  }
  PageProject candidate;
  serializeJson(doc, candidate.json);
  if (candidate.json.empty() || candidate.json.size() > kMaxPageProjectBytes) return reject("Canonical project size exceeds limit");
  candidate.width = width;
  candidate.height = height;
  candidate.document = std::move(doc);
  out = std::move(candidate);
  return true;
}

bool hasPage(const PageProject& project, const std::string& page_id) {
  return !pageWithId(project, page_id).isNull();
}

std::string firstPageId(const PageProject& project) {
  const auto pages = project.document["pages"].as<JsonArrayConst>();
  if (pages.size() == 0 || !pages[0]["id"].is<const char*>()) return "";
  return pages[0]["id"].as<std::string>();
}

bool renderPageProject(Hardware& hardware, const PageProject& project,
                       const std::string& page_id,
                       const std::map<std::string, std::string>& text_overrides,
                       std::string& error) {
  error.clear();
  const auto reject = [&](const char* message) { error = message; return false; };
  const auto page = pageWithId(project, page_id);
  if (page.isNull()) return reject("Page ID was not found");
  const auto widgets = page["widgets"].as<JsonArrayConst>();
  // Validate every override before drawing so bad input cannot partially clear
  // an otherwise valid page. Overrides are runtime data, never page storage.
  for (const auto& entry : text_overrides) {
    bool found = false;
    if (!validPageId(entry.first) || !validPageText(entry.second)) return reject("Text override is invalid");
    for (JsonObjectConst widget : widgets) if (widget["id"] == entry.first && widget["type"] == "text") found = true;
    if (!found) return reject("Text override must refer to a text widget on the selected page");
  }
  if (!hardware.fillDisplay(page["background"].as<uint16_t>())) return reject("Page background render failed");
  for (JsonObjectConst widget : widgets) {
    const std::string type = widget["type"].as<std::string>();
    bool success = false;
    if (type == "text") {
      const auto override = text_overrides.find(widget["id"].as<std::string>());
      const std::string value = override == text_overrides.end() ? widget["text"].as<std::string>() : override->second;
      success = hardware.textDisplay(widget["x"], widget["y"], value, widget["color"].as<uint16_t>());
    } else if (type == "rect") {
      success = hardware.rectDisplay(widget["x"], widget["y"], widget["width"], widget["height"], widget["color"].as<uint16_t>(), widget["filled"]);
    } else if (type == "line") {
      success = hardware.lineDisplay(widget["x0"], widget["y0"], widget["x1"], widget["y1"], widget["color"].as<uint16_t>());
    } else if (type == "image") {
      const auto image = imageWithId(project.document["images"].as<JsonArrayConst>(), widget["asset"].as<std::string>());
      if (image.isNull()) return reject("Page image reference is missing");
      std::string bytes;
      const size_t count = static_cast<size_t>(image["width"].as<int>()) * image["height"].as<int>();
      if (!decodePageBase64(image["data"].as<std::string>(), bytes, kMaxPageImageBytes) || bytes.size() != count * 2)
        return reject("Page image data is invalid");
      std::vector<uint16_t> pixels(count);
      for (size_t i = 0; i < count; ++i) pixels[i] = (static_cast<uint16_t>(static_cast<uint8_t>(bytes[i * 2])) << 8) | static_cast<uint8_t>(bytes[i * 2 + 1]);
      success = hardware.bitmapDisplay(widget["x"], widget["y"], image["width"], image["height"], pixels.data());
    } else return reject("Unknown widget type in stored page");
    if (!success) return reject("Page widget render failed");
  }
  return true;
}
}  // namespace ai_maker
