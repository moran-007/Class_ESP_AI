#pragma once

#include <ArduinoJson.h>
#include <cstddef>
#include <cstdint>
#include <map>
#include <string>

namespace ai_maker {
class Hardware;

constexpr size_t kMaxPageProjectBytes = 8192;
constexpr size_t kMaxPageImageBytes = 4608;

struct PageProject {
  JsonDocument document;
  std::string json;
  int width = 0;
  int height = 0;
};

bool parsePageProject(const std::string& json, PageProject& out, std::string& error);
bool hasPage(const PageProject& project, const std::string& page_id);
std::string firstPageId(const PageProject& project);
bool validPageText(const std::string& value);
bool validPageId(const std::string& value);
uint32_t pageCrc32(const std::string& value);
bool decodePageBase64(const std::string& value, std::string& out, size_t max_bytes);
std::string encodePageBase64(const std::string& value);
bool renderPageProject(Hardware& hardware, const PageProject& project,
                       const std::string& page_id,
                       const std::map<std::string, std::string>& text_overrides,
                       std::string& error);
}  // namespace ai_maker
