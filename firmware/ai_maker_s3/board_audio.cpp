#include "board_audio.h"
#include <algorithm>
#include <driver/gpio.h>

namespace ai_maker {
namespace {
constexpr uint32_t kDmaDescriptors = 4;
constexpr uint32_t kDmaFrames = 128;
constexpr uint32_t kIoTimeoutMs = 80;
constexpr uint32_t kDrainWriteTimeoutMs = 16;
constexpr size_t kDrainWrites = 8;
static_assert(kDrainWrites * kDmaFrames > kDmaDescriptors * kDmaFrames,
              "Drain more silence than the complete TX DMA ring");
bool validPin(int pin) { return (pin >= 0 && pin <= 21) || (pin >= 26 && pin <= 48); }
}  // namespace

bool BoardAudio::validSpec(const AudioSpec& s) {
  if (!s.enabled || !validPin(s.bclk) || !validPin(s.ws) ||
      (s.din < 0 && s.dout < 0) || s.volume < 0 || s.volume > 100) return false;
  const std::array<int,5> pins{{s.bclk,s.ws,s.din,s.dout,s.sd}};
  for (size_t i=0;i<pins.size();++i) {
    if (i>=2 && pins[i]==-1) continue;
    if (!validPin(pins[i])) return false;
    for (size_t j=0;j<i;++j) if (pins[j]==pins[i]) return false;
  }
  return true;
}

bool BoardAudio::amplifier(bool enabled) {
  const int pin=owned_pins_[4];
  return pin<0 || gpio_set_level(static_cast<gpio_num_t>(pin),enabled?1:0)==ESP_OK;
}

bool BoardAudio::begin(const AudioSpec& s) {
  if (!validSpec(s)) return false;
  if (!release()) return false;
  spec_=s;
  owned_pins_={{s.bclk,s.ws,s.din,s.dout,s.sd}};
  if (s.sd>=0 && (!amplifier(false) ||
      gpio_set_direction(static_cast<gpio_num_t>(s.sd),GPIO_MODE_OUTPUT)!=ESP_OK)) {
    release();return false;
  }
  i2s_chan_config_t channel=I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0,I2S_ROLE_MASTER);
  channel.dma_desc_num=kDmaDescriptors;
  channel.dma_frame_num=kDmaFrames;
  channel.auto_clear_after_cb=true;
  if (i2s_new_channel(&channel,s.dout>=0?&tx_:nullptr,s.din>=0?&rx_:nullptr)!=ESP_OK) {
    release();return false;
  }
  i2s_std_config_t standard{};
  standard.clk_cfg=I2S_STD_CLK_DEFAULT_CONFIG(kAudioSampleRate);
  standard.slot_cfg=I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT,I2S_SLOT_MODE_STEREO);
  standard.gpio_cfg.mclk=I2S_GPIO_UNUSED;
  standard.gpio_cfg.bclk=static_cast<gpio_num_t>(s.bclk);
  standard.gpio_cfg.ws=static_cast<gpio_num_t>(s.ws);
  standard.gpio_cfg.dout=s.dout<0?I2S_GPIO_UNUSED:static_cast<gpio_num_t>(s.dout);
  standard.gpio_cfg.din=s.din<0?I2S_GPIO_UNUSED:static_cast<gpio_num_t>(s.din);
  if ((tx_ && i2s_channel_init_std_mode(tx_,&standard)!=ESP_OK) ||
      (rx_ && i2s_channel_init_std_mode(rx_,&standard)!=ESP_OK)) {
    release();return false;
  }
  if (tx_) {
    if (i2s_channel_enable(tx_)!=ESP_OK) {release();return false;}
    tx_enabled_=true;
  }
  if (rx_) {
    if (i2s_channel_enable(rx_)!=ESP_OK) {release();return false;}
    rx_enabled_=true;
  }
  active_=true;
  return true;
}

bool BoardAudio::drainSilence() {
  if (!active_ || !tx_ || !tx_enabled_) return true;
  const std::array<StereoFrame,kDmaFrames> zero{};
  // A write may acknowledge queued DMA bytes before they are audible. Pushing
  // twice the entire ring in silence ensures preceding user PCM has left the
  // queue before muting. Each call is bounded; total timeout budget is128ms.
  for (size_t i=0;i<kDrainWrites;++i) {
    size_t written=0;
    if (i2s_channel_write(tx_,zero.data(),sizeof(zero),&written,kDrainWriteTimeoutMs)!=ESP_OK ||
        written!=sizeof(zero)) return false;
  }
  return true;
}

bool BoardAudio::stopIO() {
  const bool muted=amplifier(false);
  capturing_=playing_=false;
  const bool silent=drainSilence();
  return muted && silent;
}

bool BoardAudio::startCapture() {
  if (!active_ || !rx_ || !rx_enabled_ || capturing_ || playing_) return false;
  if (!stopIO()) return false;
  std::array<StereoFrame,kDmaFrames> discarded{};
  // Do not return samples left in RX DMA while the PC was idle. Zero timeout
  // and a fixed iteration bound prevent a continuously clocked mic blocking
  // this command. This flush is not an assertion of analog microphone quality.
  for (size_t i=0;i<kDrainWrites;++i) {
    size_t count=0;
    const auto result=i2s_channel_read(rx_,discarded.data(),sizeof(discarded),&count,0);
    if (count>sizeof(discarded) || count%sizeof(StereoFrame)!=0) return false;
    if (result==ESP_ERR_TIMEOUT && count==0) break;
    if (result!=ESP_OK && result!=ESP_ERR_TIMEOUT) return false;
    if (!count) break;
  }
  capturing_=true;
  return true;
}

size_t BoardAudio::read(uint8_t* pcm,size_t bytes) {
  if (!active_ || !capturing_ || !rx_ || !pcm || bytes<2 || bytes>kAudioChunkBytes || bytes%2) return 0;
  std::array<StereoFrame,kAudioChunkBytes/2> frames{};
  const size_t samples=bytes/2, wanted=samples*sizeof(StereoFrame);
  size_t received=0;
  if (i2s_channel_read(rx_,frames.data(),wanted,&received,kIoTimeoutMs)!=ESP_OK || received!=wanted) return 0;
  for (size_t i=0;i<samples;++i) {
    // INMP44124-bit MSB-aligned samples occupy a32-bit I2S slot. Unsigned
    // extraction defines negative sample behavior without signed-shift UB.
    const uint32_t slot=static_cast<uint32_t>(spec_.mic_right?frames[i].right:frames[i].left);
    const uint16_t value=static_cast<uint16_t>(slot>>16);
    pcm[2*i]=static_cast<uint8_t>(value);
    pcm[2*i+1]=static_cast<uint8_t>(value>>8);
  }
  return bytes;
}

bool BoardAudio::startPlayback() {
  if (!active_ || !tx_ || !tx_enabled_ || capturing_ || playing_) return false;
  if (!stopIO() || !amplifier(true)) return false;
  playing_=true;
  return true;
}

size_t BoardAudio::write(const uint8_t* pcm,size_t bytes) {
  if (!active_ || !playing_ || !tx_ || !pcm || bytes<2 || bytes>kAudioChunkBytes || bytes%2) return 0;
  std::array<StereoFrame,kAudioChunkBytes/2> frames{};
  const size_t samples=bytes/2;
  for (size_t i=0;i<samples;++i) {
    const uint16_t raw=static_cast<uint16_t>(pcm[2*i]) | static_cast<uint16_t>(pcm[2*i+1])<<8;
    const int32_t signed_sample=raw>=32768?static_cast<int32_t>(raw)-65536:raw;
    const int32_t value=static_cast<int32_t>(static_cast<int64_t>(signed_sample)*65536*spec_.volume/100);
    frames[i]={value,value};
  }
  const size_t wanted=samples*sizeof(StereoFrame);
  size_t written=0;
  if (i2s_channel_write(tx_,frames.data(),wanted,&written,kIoTimeoutMs)!=ESP_OK || written!=wanted) return 0;
  return bytes;
}

bool BoardAudio::finishPlayback() {
  if (!active_ || !playing_ || !tx_) return false;
  const bool drained=drainSilence();
  const bool muted=amplifier(false);
  playing_=false;
  return drained && muted;
}

bool BoardAudio::release() {
  bool ok=amplifier(false);
  active_=capturing_=playing_=false;
  if (tx_ && tx_enabled_) {
    if (i2s_channel_disable(tx_)==ESP_OK) tx_enabled_=false; else ok=false;
  }
  if (rx_ && rx_enabled_) {
    if (i2s_channel_disable(rx_)==ESP_OK) rx_enabled_=false; else ok=false;
  }
  if (tx_ && !tx_enabled_) {
    if (i2s_del_channel(tx_)==ESP_OK) tx_=nullptr; else ok=false;
  }
  if (rx_ && !rx_enabled_) {
    if (i2s_del_channel(rx_)==ESP_OK) rx_=nullptr; else ok=false;
  }
  // If a channel remains owned after a failure, its routing must not be
  // advertised free. Retain GPIO ownership and permit a later release retry.
  if (tx_ || rx_) return false;
  for (auto& pin:owned_pins_) if (pin>=0) {
    if (gpio_reset_pin(static_cast<gpio_num_t>(pin))==ESP_OK) pin=-1;
    else ok=false;
  }
  return ok;
}

}  // namespace ai_maker
