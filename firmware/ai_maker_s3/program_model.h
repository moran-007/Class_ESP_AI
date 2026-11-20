#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace ai_maker {
constexpr size_t kMaxProgramBytes = 3072;

struct ProgramInstruction {
  std::string op;
  std::string args_json;
  size_t target = 0;
};

struct ProgramModel {
  std::string canonical;
  std::string config_json;
  std::vector<ProgramInstruction> instructions;
  bool has_counter = false;
};

// Pure validation/compilation. The caller must also validate config with the
// device's current board/resource policy. Failure leaves output unchanged.
bool parseProgram(const std::string& source, ProgramModel& output, std::string& error);
}  // namespace ai_maker
