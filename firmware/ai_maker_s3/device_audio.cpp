#include "device_core.h"
#include <initializer_list>
#include <vector>

namespace ai_maker {
namespace {
constexpr uint32_t kMaxAudioStreamBytes = 1920000;
bool number(JsonVariantConst value) { return value.is<int>() && !value.is<bool>(); }
bool keys(JsonObjectConst object, std::initializer_list<const char*> allowed) {
  for (JsonPairConst pair : object) {
    bool found = false;
    for (const char* key : allowed) if (pair.key() == key) found = true;
    if (!found) return false;
  }
  return true;
}
void fail(JsonDocument& response, const char* code, const char* message) {
  response["ok"] = false; response["code"] = code; response["message"] = message;
  response.remove("data");
}
}

bool DeviceCore::audioPin(int pin) const {
  if (!audio_.enabled || pin < 0) return false;
  return pin == audio_.bclk || pin == audio_.ws || pin == audio_.din || pin == audio_.dout || pin == audio_.sd;
}

void DeviceCore::writeAudioInfo(JsonObject out) const {
  out["configured"] = audio_.enabled; out["active"] = audio_active_;
  out["driver_ok"] = audio_driver_ok_; out["recording"] = audio_recording_;
  out["cleanup_required"] = audio_cleanup_fault_;
  out["playing"] = audio_playing_; out["read_bytes"] = audio_read_bytes_;
  out["written_bytes"] = audio_written_bytes_;
  out["format"] = "pcm_s16le"; out["sample_rate"] = kAudioSampleRate;
  out["channels"] = 1; out["sample_width"] = 2; out["byte_order"] = "little";
  out["physical_verified"] = false; out["session_scoped"] = true;
  if (audio_.enabled) {
    out["bclk"] = audio_.bclk; out["ws"] = audio_.ws;
    out["din"] = audio_.din; out["dout"] = audio_.dout; out["sd"] = audio_.sd;
    out["mic_channel"] = audio_.mic_right ? "right" : "left"; out["volume"] = audio_.volume;
  }
}

bool DeviceCore::releaseAudioDevice(bool clear_config) {
  if (audio_active_ || !audio_driver_ok_) {
    const bool released = hardware_.releaseAudio();
    audio_driver_ok_ = released;
    if (!released) { audio_cleanup_fault_ = true; return false; }
  }
  audio_cleanup_fault_ = false;
  audio_active_ = audio_recording_ = audio_playing_ = false;
  audio_read_bytes_ = audio_written_bytes_ = 0;
  if (clear_config) audio_ = AudioSpec{};
  return true;
}

void DeviceCore::clearAudioSession() {
  // A failed release must retain reservations until a later explicit cleanup.
  if (!audio_active_ && audio_driver_ok_) audio_ = AudioSpec{};
}

void DeviceCore::dispatchAudio(const std::string& op, JsonObjectConst args, JsonDocument& response) {
  auto data = response["data"].as<JsonObject>();
  if (!kAudioTransportSupported) return fail(response, "UNSUPPORTED_OPERATION", "PCM streaming requires native USB CDC firmware, not 115200 UART");
  if (op == "audio.configure") {
    if (!maintenance_) return fail(response, "MAINTENANCE_REQUIRED", "Enter maintenance before changing audio wiring");
    if (!keys(args, {"bclk", "ws", "din", "dout", "sd", "mic_channel", "volume"}))
      return fail(response, "CONFIG_INVALID", "Unknown audio configuration field");
    for (const char* key : {"bclk", "ws", "din", "dout", "sd", "volume"})
      if (!number(args[key])) return fail(response, "CONFIG_INVALID", "Audio GPIOs and volume must be integers");
    if (!args["mic_channel"].is<const char*>()) return fail(response, "CONFIG_INVALID", "mic_channel must be left or right");
    const std::string channel = args["mic_channel"].as<std::string>();
    AudioSpec next; next.enabled = true;
    next.bclk = args["bclk"]; next.ws = args["ws"]; next.din = args["din"];
    next.dout = args["dout"]; next.sd = args["sd"]; next.volume = args["volume"];
    next.mic_right = channel == "right";
    if ((channel != "left" && channel != "right") || next.volume < 0 || next.volume > 100 ||
        next.din < -1 || next.dout < -1 || next.sd < -1 || (next.din == -1 && next.dout == -1) ||
        (next.dout == -1 && next.sd != -1))
      return fail(response, "CONFIG_INVALID", "Invalid channel, volume, data direction or shutdown GPIO");
    const std::array<int, 5> pins{{next.bclk, next.ws, next.din, next.dout, next.sd}};
    for (size_t i = 0; i < pins.size(); ++i) {
      const int pin = pins[i];
      if (i >= 2 && pin == -1) continue;
      if (!validPin(pin) || reservedPin(pin)) return fail(response, "CONFIG_INVALID", "Audio GPIO is invalid or reserved");
      for (size_t j = 0; j < i; ++j) if (pin == pins[j])
        return fail(response, "CONFIG_INVALID", "Audio signals must use distinct GPIOs");
      if (servoForPin(pin) || (display_.enabled && (pin == display_.sck || pin == display_.mosi ||
          pin == display_.cs || pin == display_.dc || pin == display_.rst || pin == display_.backlight)) ||
          modes_[pin] != PinMode::Unset)
        return fail(response, "RESOURCE_CONFLICT", "Audio GPIO is already assigned to another device");
    }
    if (!releaseAudioDevice(false)) return fail(response, "HARDWARE_ERROR", "Old audio resources could not be released");
    audio_ = next; writeAudioInfo(data); return;
  }
  if (op == "audio.release" || op == "audio.unconfigure") {
    if (!keys(args, {})) return fail(response, "INVALID_ARGUMENT", "Audio release takes no arguments");
    if (!releaseAudioDevice(op == "audio.unconfigure")) return fail(response, "HARDWARE_ERROR", "Audio cleanup failed; GPIO ownership retained");
    writeAudioInfo(data); data["released"] = true; return;
  }
  if (op == "audio.stop") {
    if (!keys(args, {})) return fail(response, "INVALID_ARGUMENT", "Audio stop takes no arguments");
    if (audio_cleanup_fault_) return fail(response, "HARDWARE_ERROR", "Full audio release is required after failed cleanup");
    if (audio_active_ || !audio_driver_ok_) {
      audio_driver_ok_ = hardware_.stopAudioIO();
      if (!audio_driver_ok_) return fail(response, "HARDWARE_ERROR", "Audio stop failed; physical output is unknown");
    }
    audio_recording_ = audio_playing_ = false; audio_read_bytes_ = audio_written_bytes_ = 0;
    writeAudioInfo(data); data["stopped"] = true; return;
  }
  if (maintenance_) return fail(response, "MAINTENANCE_REQUIRED", "Audio is disabled in maintenance");
  if (op == "audio.begin") {
    if (!keys(args, {})) return fail(response, "INVALID_ARGUMENT", "Audio begin takes no arguments");
    if (!audio_.enabled) return fail(response, "INVALID_ARGUMENT", "Call audio.configure before audio.begin");
    if (audio_active_) {
      if (!audio_driver_ok_) return fail(response, "HARDWARE_ERROR", "Release failed audio driver before reuse");
      writeAudioInfo(data); data["started"] = false; return;
    }
    if (!audio_driver_ok_ && !releaseAudioDevice(false)) return fail(response, "HARDWARE_ERROR", "Audio fault cleanup failed");
    if (!hardware_.beginAudio(audio_)) {
      const bool released = hardware_.releaseAudio();
      audio_cleanup_fault_ = !released;
      audio_active_ = !released; audio_driver_ok_ = false;
      return fail(response, "HARDWARE_ERROR", "I2S audio initialization failed");
    }
    audio_active_ = audio_driver_ok_ = true; writeAudioInfo(data); data["started"] = true; return;
  }
  if (!audio_active_ || !audio_driver_ok_) return fail(response, "INVALID_ARGUMENT", "Call audio.begin with a healthy driver first");
  if (op == "audio.record.begin" || op == "audio.play.begin") {
    if (!keys(args, {})) return fail(response, "INVALID_ARGUMENT", "Audio mode begin takes no arguments");
    if (audio_recording_ || audio_playing_) return fail(response, "RESOURCE_CONFLICT", "Recording and playback are half duplex");
    const bool record = op == "audio.record.begin";
    if ((record && audio_.din < 0) || (!record && audio_.dout < 0))
      return fail(response, "INVALID_ARGUMENT", "This data direction is not configured");
    const bool ok = record ? hardware_.startAudioCapture() : hardware_.startAudioPlayback();
    if (!ok) {
      audio_driver_ok_ = hardware_.stopAudioIO();
      return fail(response, "HARDWARE_ERROR", "Audio mode could not start");
    }
    if (record) { audio_recording_ = true; audio_read_bytes_ = 0; }
    else { audio_playing_ = true; audio_written_bytes_ = 0; }
    writeAudioInfo(data); return;
  }
  if (op == "audio.read") {
    if (!audio_recording_ || !keys(args, {"bytes"}) || !number(args["bytes"]))
      return fail(response, "INVALID_ARGUMENT", "Audio read requires recording and an integer byte count");
    const int count = args["bytes"];
    if (count < 2 || count > static_cast<int>(kAudioChunkBytes) || count % 2 ||
        audio_read_bytes_ > kMaxAudioStreamBytes - static_cast<uint32_t>(count))
      return fail(response, "INVALID_ARGUMENT", "Audio read must be even 2..768 bytes within the stream limit");
    std::string pcm(static_cast<size_t>(count), '\0');
    if (hardware_.readAudio(reinterpret_cast<uint8_t*>(pcm.data()), pcm.size()) != pcm.size()) {
      audio_driver_ok_ = hardware_.stopAudioIO();
      if (audio_driver_ok_) audio_recording_ = audio_playing_ = false;
      return fail(response, "HARDWARE_ERROR", "I2S read did not return the complete chunk; partial data discarded");
    }
    data["data"] = encodePageBase64(pcm); data["bytes"] = count; data["offset"] = audio_read_bytes_;
    audio_read_bytes_ += static_cast<uint32_t>(count); return;
  }
  if (op == "audio.write") {
    if (!audio_playing_ || !keys(args, {"offset", "data"}) || !number(args["offset"]) ||
        args["offset"].as<int>() < 0 || args["offset"].as<uint32_t>() != audio_written_bytes_ || !args["data"].is<const char*>())
      return fail(response, "INVALID_ARGUMENT", "Audio write requires playback, exact offset and base64 data");
    std::string pcm;
    if (!decodePageBase64(args["data"].as<std::string>(), pcm, kAudioChunkBytes) || pcm.empty() || pcm.size() % 2 ||
        audio_written_bytes_ > kMaxAudioStreamBytes - static_cast<uint32_t>(pcm.size()))
      return fail(response, "INVALID_ARGUMENT", "Audio PCM chunk must be nonempty even base64 within limits");
    if (hardware_.writeAudio(reinterpret_cast<const uint8_t*>(pcm.data()), pcm.size()) != pcm.size()) {
      audio_driver_ok_ = hardware_.stopAudioIO();
      if (audio_driver_ok_) audio_recording_ = audio_playing_ = false;
      return fail(response, "HARDWARE_ERROR", "I2S write was incomplete; audio may have partially played, no retry");
    }
    audio_written_bytes_ += static_cast<uint32_t>(pcm.size());
    data["bytes"] = pcm.size(); data["next_offset"] = audio_written_bytes_; return;
  }
  if (op == "audio.record.end" || op == "audio.play.end") {
    if (!keys(args, {})) return fail(response, "INVALID_ARGUMENT", "Audio mode end takes no arguments");
    const bool record = op == "audio.record.end";
    if ((record && audio_playing_) || (!record && audio_recording_))
      return fail(response, "RESOURCE_CONFLICT", "End does not match the active audio direction");
    if (record && audio_recording_ && !hardware_.stopAudioIO()) {
      audio_driver_ok_ = false;
      return fail(response, "HARDWARE_ERROR", "Capture stop failed; release audio before reuse");
    }
    if (!record && audio_playing_ && !hardware_.finishAudioPlayback()) {
      audio_driver_ok_ = hardware_.stopAudioIO();
      if (audio_driver_ok_) audio_playing_ = false;
      return fail(response, "HARDWARE_ERROR", "Audio drain/mute failed; completion is unknown");
    }
    if (record) audio_recording_ = false; else audio_playing_ = false;
    writeAudioInfo(data);
    data["bytes"] = record ? audio_read_bytes_ : audio_written_bytes_;
    data["samples"] = (record ? audio_read_bytes_ : audio_written_bytes_) / 2;
    return;
  }
  fail(response, "UNSUPPORTED_OPERATION", "Unknown audio operation");
}
}  // namespace ai_maker
