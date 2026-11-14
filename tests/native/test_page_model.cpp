#include "page_model.h"
#include "fake_hardware.h"
#include <functional>
#include <iostream>
#include <stdexcept>
#include <utility>
#include <vector>

namespace {
using ai_maker::PageProject;

void require(bool condition, const std::string& message) {
  if (!condition) throw std::runtime_error(message);
}

JsonDocument blank() {
  JsonDocument doc;
  require(!deserializeJson(doc, R"({"schema_version":1,"width":160,"height":128,"pages":[{"id":"home","background":0,"widgets":[]}],"images":[]})"), "fixture JSON");
  return doc;
}

std::string encode(const JsonDocument& doc) {
  std::string value;
  serializeJson(doc, value);
  return value;
}

PageProject parse(const JsonDocument& doc) {
  PageProject project;
  std::string error;
  require(ai_maker::parsePageProject(encode(doc), project, error), "valid project rejected: " + error);
  return project;
}

void rejects(const JsonDocument& doc) {
  auto prior = blank();
  PageProject project = parse(prior);
  const auto before = project.json;
  std::string error;
  require(!ai_maker::parsePageProject(encode(doc), project, error), "invalid project accepted: " + encode(doc));
  require(!error.empty(), "rejected project must explain why");
  require(project.json == before && project.width == 160 && ai_maker::hasPage(project, "home"), "failed parse must preserve previous project");
}

JsonObject addText(JsonDocument& doc, const std::string& id = "title", const std::string& text = "你好，创客！") {
  auto widget = doc["pages"][0]["widgets"].as<JsonArray>().add<JsonObject>();
  widget["id"] = id; widget["type"] = "text"; widget["x"] = 8; widget["y"] = 8;
  widget["text"] = text; widget["color"] = 65535;
  return widget;
}

JsonObject addImage(JsonDocument& doc, const std::string& id, int width, int height, const std::string& pixels) {
  auto image = doc["images"].as<JsonArray>().add<JsonObject>();
  image["id"] = id; image["width"] = width; image["height"] = height;
  image["data"] = ai_maker::encodePageBase64(pixels);
  return image;
}

JsonObject addImageWidget(JsonDocument& doc, const std::string& asset, int x = 0, int y = 0) {
  auto widget = doc["pages"][0]["widgets"].as<JsonArray>().add<JsonObject>();
  widget["id"] = "icon"; widget["type"] = "image"; widget["x"] = x; widget["y"] = y; widget["asset"] = asset;
  return widget;
}

void valid_project_is_canonical_and_failure_is_transactional() {
  auto doc = blank();
  addText(doc);
  auto project = parse(doc);
  require(project.width == 160 && project.height == 128, "dimensions retained");
  require(ai_maker::firstPageId(project) == "home" && ai_maker::hasPage(project, "home") && !ai_maker::hasPage(project, "missing"), "page lookup");
  require(project.document["pages"][0]["widgets"][0]["text"] == "你好，创客！", "UTF8 text retained");
  std::string error;
  const std::string before = project.json;
  for (const auto& source : {before + "{}", before + "invalid", std::string("[]"), std::string("null"), std::string("{}"), std::string("{\"width\":1")}) {
    require(!ai_maker::parsePageProject(source, project, error), "malformed root should fail");
    require(project.json == before, "malformed input cannot replace saved page");
  }
  require(ai_maker::parsePageProject(" \r\n" + before + "\t ", project, error), "JSON whitespace allowed");
  require(project.json == before, "canonical JSON excludes formatting");
}

void strict_fields_and_numeric_types() {
  for (const auto* key : {"schema_version", "width", "height", "pages", "images"}) {
    auto doc = blank(); doc.remove(key); rejects(doc);
  }
  for (const auto* source : {"true", "1.0", "\"1\"", "null", "-1", "0", "321"}) {
    std::string raw = encode(blank());
    const auto start = raw.find("\"width\":160");
    raw.replace(start, 11, "\"width\":" + std::string(source));
    PageProject project; std::string error;
    require(!ai_maker::parsePageProject(raw, project, error), "invalid JSON numeric spelling accepted");
  }
  { auto doc = blank(); doc["schema_version"] = 2; rejects(doc); }
  { auto doc = blank(); doc["script"] = "do_something"; rejects(doc); }
  { auto doc = blank(); doc["pages"][0]["extra"] = true; rejects(doc); }
  { auto doc = blank(); auto w = addText(doc); w["callback"] = "x"; rejects(doc); }
  { auto doc = blank(); auto w = addText(doc); w["color"] = true; rejects(doc); }
  { auto doc = blank(); auto w = addText(doc); w["color"] = 65536; rejects(doc); }
  { auto doc = blank(); auto w = addText(doc); w["type"] = "web"; rejects(doc); }
  { auto doc = blank(); doc["pages"][0]["background"] = -1; rejects(doc); }
  { auto doc = blank(); doc["pages"][0]["widgets"] = 1; rejects(doc); }
  { auto doc = blank(); doc["images"] = false; rejects(doc); }
}

void ids_and_uniqueness_are_bounded() {
  for (const auto& id : {std::string(""), std::string("1bad"), std::string("a-b"), std::string("中文"), std::string(25, 'a'), std::string("a\0b", 3)}) {
    require(!ai_maker::validPageId(id), "bad ID helper accepts invalid ID");
    auto doc = blank(); doc["pages"][0]["id"] = id; rejects(doc);
  }
  require(ai_maker::validPageId("Home_02") && ai_maker::validPageId(std::string(24, 'a')), "valid ASCII IDs");
  { auto doc = blank(); doc["pages"].as<JsonArray>().add(doc["pages"][0]); rejects(doc); }
  { auto doc = blank(); addText(doc, "dup"); addText(doc, "dup"); rejects(doc); }
  { auto doc = blank(); addImage(doc, "dup", 1, 1, std::string(2, '\0')); addImage(doc, "dup", 1, 1, std::string(2, '\0')); rejects(doc); }
  { // Widget IDs may be reused on a different page.
    auto doc = blank(); addText(doc, "same");
    auto p = doc["pages"].as<JsonArray>().add<JsonObject>();
    p.set(doc["pages"][0]); p["id"] = "other";
    parse(doc);
  }
}

void utf8_text_and_control_policy() {
  require(ai_maker::validPageText("中文\nASCII"), "Chinese and newline valid");
  require(ai_maker::validPageText(std::string(192, 'a')) && !ai_maker::validPageText(std::string(193, 'a')), "192byte text cap");
  require(ai_maker::validPageText("😀"), "legal UTF8 outside font repertoire is a valid string");
  const std::vector<std::string> invalid = {"", "a\rb", "a\tb", std::string("a\0b", 3), std::string(1, '\x7f'),
      std::string("\xc2\x85", 2), std::string("\xc0\xaf", 2), std::string("\xed\xa0\x80", 3),
      std::string("\xf4\x90\x80\x80", 4), std::string("\xe4\xb8", 2), std::string("\x80", 1), std::string(193, 'a')};
  for (const auto& value : invalid) {
    require(!ai_maker::validPageText(value), "invalid text accepted by helper");
    auto doc = blank(); addText(doc, "title", value); rejects(doc);
  }
  { auto doc = blank(); addText(doc, "title", std::string(192, 'a')); parse(doc); }
  { auto doc = blank(); addText(doc, "title", std::string(193, 'a')); rejects(doc); }
  PageProject project; std::string error;
  auto valid = encode(blank());
  valid.insert(1, std::string("\xff", 1));
  require(!ai_maker::parsePageProject(valid, project, error), "raw invalid UTF8 rejected before JSON parser");
}

void widget_geometry_and_types() {
  { auto doc = blank(); auto w = addText(doc); w["x"] = 159; w["y"] = 127; parse(doc); }
  for (const auto* key : {"x", "y"}) {
    auto doc = blank(); auto w = addText(doc); w[key] = -1; rejects(doc);
    doc = blank(); w = addText(doc); w[key] = true; rejects(doc);
  }
  { auto doc = blank(); auto w = addText(doc); w["x"] = 160; rejects(doc); }
  { auto doc = blank(); auto w = addText(doc); w["y"] = 128; rejects(doc); }
  auto rectangle = []() {
    auto doc = blank(); auto w = doc["pages"][0]["widgets"].as<JsonArray>().add<JsonObject>();
    w["id"] = "box"; w["type"] = "rect"; w["x"] = 0; w["y"] = 0; w["width"] = 160; w["height"] = 128; w["color"] = 31; w["filled"] = true;
    return doc;
  };
  parse(rectangle());
  for (const auto* key : {"width", "height"}) {
    auto doc = rectangle(); doc["pages"][0]["widgets"][0][key] = 0; rejects(doc);
    doc = rectangle(); doc["pages"][0]["widgets"][0][key] = 321; rejects(doc);
  }
  { auto doc = rectangle(); doc["pages"][0]["widgets"][0]["filled"] = 1; rejects(doc); }
  { auto doc = rectangle(); doc["pages"][0]["widgets"][0]["x"] = 1; rejects(doc); }
  { auto doc = rectangle(); doc["pages"][0]["widgets"][0].remove("filled"); rejects(doc); }
  auto doc = blank(); auto line = doc["pages"][0]["widgets"].as<JsonArray>().add<JsonObject>();
  line["id"] = "line"; line["type"] = "line"; line["x0"] = 0; line["y0"] = 0; line["x1"] = 159; line["y1"] = 127; line["color"] = 65535;
  parse(doc); line["x1"] = 160; rejects(doc);
}

void project_limits_bound_all_resources() {
  auto doc = blank();
  for (int i = 0; i < 32; ++i) addText(doc, "text" + std::to_string(i), "x");
  parse(doc); addText(doc, "tooMany", "x"); rejects(doc);
  doc = blank();
  for (int i = 1; i < 4; ++i) {
    auto p = doc["pages"].as<JsonArray>().add<JsonObject>(); p["id"] = "page" + std::to_string(i); p["background"] = 0; p["widgets"].to<JsonArray>();
  }
  parse(doc);
  { auto p = doc["pages"].as<JsonArray>().add<JsonObject>(); p["id"] = "fifth"; p["background"] = 0; p["widgets"].to<JsonArray>(); }
  rejects(doc);
  doc = blank(); doc["pages"].as<JsonArray>().clear(); rejects(doc);
  doc = blank(); addImage(doc, "large", 48, 48, std::string(4608, '\0')); parse(doc);
  addImage(doc, "extra", 1, 1, std::string(2, '\0')); rejects(doc);
  doc = blank();
  for (int i = 0; i < 4; ++i) addImage(doc, "img" + std::to_string(i), 1, 1, std::string(2, '\0'));
  parse(doc); addImage(doc, "fifth", 1, 1, std::string(2, '\0')); rejects(doc);
  doc = blank(); addImage(doc, "wide", 49, 1, std::string(98, '\0')); rejects(doc);
  std::string json = encode(blank()); json += std::string(8192 - json.size(), ' ');
  PageProject project; std::string error;
  require(ai_maker::parsePageProject(json, project, error), "8192byte formatted package permitted");
  require(!ai_maker::parsePageProject(json + " ", project, error), "8193byte package rejected");
}

void base64_and_crc_match_standard_vectors() {
  for (const auto& pair : std::vector<std::pair<std::string, std::string>>{{"", ""}, {"f", "Zg=="}, {"fo", "Zm8="}, {"foo", "Zm9v"}, {"foob", "Zm9vYg=="}, {"fooba", "Zm9vYmE="}, {"foobar", "Zm9vYmFy"}}) {
    require(ai_maker::encodePageBase64(pair.first) == pair.second, "RFC4648 encode vector");
    std::string result = "before";
    require(ai_maker::decodePageBase64(pair.second, result, pair.first.size()) && result == pair.first, "RFC4648 decode vector");
  }
  std::string binary;
  for (int i = 0; i < 256; ++i) binary.push_back(static_cast<char>(i));
  std::string decoded;
  require(ai_maker::decodePageBase64(ai_maker::encodePageBase64(binary), decoded, 256) && decoded == binary, "all byte values roundtrip");
  for (const auto* invalid : {"Zg", "Zg===", "Zh==", "Zm9=", "Zg==AAAA", "AA=A", "====", "_w==", "-w==", "Z g==", "Zg==\n", "A===", "AAA?"}) {
    decoded = "preserve";
    require(!ai_maker::decodePageBase64(invalid, decoded, 8192) && decoded == "preserve", "noncanonical base64 rejected without publishing partial output");
  }
  decoded = "preserve";
  require(!ai_maker::decodePageBase64("Zm9v", decoded, 2) && decoded == "preserve", "decoded bound enforced");
  require(ai_maker::pageCrc32("") == 0 && ai_maker::pageCrc32("123456789") == 0xcbf43926U, "CRC32/ISO-HDLC standard vectors");
}

void images_have_exact_pixels_and_valid_references() {
  auto doc = blank();
  auto image = addImage(doc, "face", 2, 2, std::string(8, '\0'));
  auto widget = addImageWidget(doc, "face", 158, 126);
  parse(doc); widget["x"] = 159; rejects(doc); widget["x"] = 158;
  widget["asset"] = "absent"; rejects(doc); widget["asset"] = "face";
  image["data"] = "AAAA"; rejects(doc); image["data"] = "AAAAAAAAAAAA"; rejects(doc);
  image["data"] = ai_maker::encodePageBase64(std::string(8, '\0'));
  image["width"] = false; rejects(doc); image["width"] = 2;
  image["extra"] = 1; rejects(doc);
}

class DrawingHardware final : public FakeHardware {
 public:
  std::vector<std::string> calls;
  std::string last_text;
  std::vector<uint16_t> pixels;
  size_t fail_at = 0;
  size_t begins = 0;
  bool recorded(const char* name) { calls.push_back(name); return calls.size() != fail_at; }
  bool beginDisplay(const ai_maker::DisplaySpec&) override { ++begins; return true; }
  bool fillDisplay(uint16_t color) override { require(color == 31, "page background color passed"); return recorded("fill"); }
  bool textDisplay(int x, int y, const std::string& value, uint16_t color) override {
    require(x == 8 && y == 8 && color == 65535, "text arguments passed"); last_text = value; return recorded("text");
  }
  bool rectDisplay(int x, int y, int width, int height, uint16_t color, bool filled) override {
    require(x == 1 && y == 30 && width == 10 && height == 20 && color == 2016 && filled, "rectangle arguments passed"); return recorded("rect");
  }
  bool lineDisplay(int x0, int y0, int x1, int y1, uint16_t color) override {
    require(x0 == 0 && y0 == 0 && x1 == 159 && y1 == 127 && color == 0, "line arguments passed"); return recorded("line");
  }
  bool bitmapDisplay(int x, int y, int width, int height, const uint16_t* value) override {
    require(x == 20 && y == 20 && width == 2 && height == 2, "bitmap arguments passed");
    pixels.assign(value, value + 4); return recorded("image");
  }
};

PageProject drawingProject() {
  auto doc = blank(); doc["pages"][0]["background"] = 31;
  addText(doc);
  auto widgets = doc["pages"][0]["widgets"].as<JsonArray>();
  auto rect = widgets.add<JsonObject>(); rect["id"] = "bar"; rect["type"] = "rect";
  rect["x"] = 1; rect["y"] = 30; rect["width"] = 10; rect["height"] = 20; rect["color"] = 2016; rect["filled"] = true;
  auto line = widgets.add<JsonObject>(); line["id"] = "line"; line["type"] = "line";
  line["x0"] = 0; line["y0"] = 0; line["x1"] = 159; line["y1"] = 127; line["color"] = 0;
  auto image = doc["images"].as<JsonArray>().add<JsonObject>(); image["id"] = "pixels"; image["width"] = 2; image["height"] = 2;
  image["data"] = "+AAH4AAf//8=";
  addImageWidget(doc, "pixels", 20, 20);
  return parse(doc);
}

void renderer_preserves_order_pixels_and_runtime_overrides() {
  auto project = drawingProject();
  DrawingHardware hardware; std::string error;
  const auto before = project.json;
  require(ai_maker::renderPageProject(hardware, project, "home", {{"title", "运行中"}}, error), "draw valid page: " + error);
  require(hardware.calls == std::vector<std::string>{"fill", "text", "rect", "line", "image"}, "render in saved stacking order");
  require(hardware.last_text == "运行中", "runtime text override passed");
  require(hardware.pixels == std::vector<uint16_t>{0xf800, 0x07e0, 0x001f, 0xffff}, "big-endian RGB565 becomes host words without byte swap");
  require(project.json == before && project.document["pages"][0]["widgets"][0]["text"] == "你好，创客！", "runtime overrides cannot modify saved project");
  require(hardware.begins == 0 && hardware.saves == 0 && hardware.servo_writes == 0, "renderer does not initialize, persist or actuate other devices");
}

void renderer_validates_overrides_before_drawing_and_stops_on_faults() {
  auto project = drawingProject();
  for (const auto& overrides : std::vector<std::map<std::string, std::string>>{{{"missing", "x"}}, {{"bar", "x"}}, {{"title", ""}}, {{"title", "bad\r"}}}) {
    DrawingHardware hardware; std::string error;
    require(!ai_maker::renderPageProject(hardware, project, "home", overrides, error) && hardware.calls.empty(), "invalid override must not clear screen first");
  }
  { DrawingHardware hardware; std::string error;
    require(!ai_maker::renderPageProject(hardware, project, "absent", {}, error) && hardware.calls.empty(), "unknown page cannot draw"); }
  for (size_t fault = 1; fault <= 5; ++fault) {
    DrawingHardware hardware; hardware.fail_at = fault; std::string error;
    require(!ai_maker::renderPageProject(hardware, project, "home", {}, error), "hardware failure must propagate");
    require(hardware.calls.size() == fault && !error.empty(), "do not continue after a hardware failure");
  }
}
}  // namespace

int main() {
  const std::vector<std::pair<const char*, std::function<void()>>> tests = {
      {"valid_project_is_canonical_and_failure_is_transactional", valid_project_is_canonical_and_failure_is_transactional},
      {"strict_fields_and_numeric_types", strict_fields_and_numeric_types},
      {"ids_and_uniqueness_are_bounded", ids_and_uniqueness_are_bounded},
      {"utf8_text_and_control_policy", utf8_text_and_control_policy},
      {"widget_geometry_and_types", widget_geometry_and_types},
      {"project_limits_bound_all_resources", project_limits_bound_all_resources},
      {"base64_and_crc_match_standard_vectors", base64_and_crc_match_standard_vectors},
      {"images_have_exact_pixels_and_valid_references", images_have_exact_pixels_and_valid_references},
      {"renderer_preserves_order_pixels_and_runtime_overrides", renderer_preserves_order_pixels_and_runtime_overrides},
      {"renderer_validates_overrides_before_drawing_and_stops_on_faults", renderer_validates_overrides_before_drawing_and_stops_on_faults}};
  size_t failures = 0;
  for (const auto& test : tests) {
    try { test.second(); std::cout << "PASS " << test.first << '\n'; }
    catch (const std::exception& e) { ++failures; std::cerr << "FAIL " << test.first << ": " << e.what() << '\n'; }
  }
  std::cout << tests.size() << " page-model tests, " << failures << " failures\n";
  return failures ? 1 : 0;
}
