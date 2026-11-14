// Production HAL with fault-injected IDF calls, never physical audio hardware.
#include "board_audio.h"
#include <driver/i2s_std.h>
#include <algorithm>
#include <array>
#include <cstring>
#include <functional>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
struct Api {
  int new_calls=0, init_calls=0, enable_calls=0, disable_calls=0, deletes=0;
  int fail_new=0, fail_init=0, fail_enable=0, fail_disable=0, fail_delete=0;
  int fail_pin=-2;
  bool read_ok=true, write_ok=true, short_read=false, short_write=false;
  int flush_reads=0;
  int read_calls=0,write_calls=0;
  uint32_t max_timeout=0;
  i2s_chan_config_t chan{};
  std::vector<i2s_std_config_t> configurations;
  std::vector<int32_t> rx_samples;
  std::vector<int32_t> tx_samples;
  std::map<int,int> levels;
  std::vector<int> reset_pins;
  std::vector<std::string> events;
  FakeI2sChannel tx{true,false}, rx{false,false};
} api;
void require(bool value,const char* message) { if(!value) throw std::runtime_error(message); }
ai_maker::AudioSpec spec() { ai_maker::AudioSpec s; s.enabled=true; return s; }
bool allPinsReset(const ai_maker::AudioSpec& s) {
  for(int pin:{s.bclk,s.ws,s.din,s.dout,s.sd})
    if(pin>=0 && std::find(api.reset_pins.begin(),api.reset_pins.end(),pin)==api.reset_pins.end()) return false;
  return true;
}
void dormant_and_invalid_specs_do_not_touch_hardware() {
  api={}; ai_maker::BoardAudio audio;
  uint8_t bytes[2]={};
  require(audio.release() && audio.stopIO(),"idle cleanup should be idempotent");
  require(!audio.startCapture() && !audio.startPlayback() && audio.read(bytes,2)==0 && audio.write(bytes,2)==0,"no I/O without begin");
  auto s=spec();s.ws=s.bclk;
  require(!audio.begin(s) && api.new_calls==0 && api.events.empty(),"duplicate GPIO must fail before hardware");
  s=spec();s.enabled=false;require(!audio.begin(s),"disabled mapping should not start clocks");
  s=spec();s.din=s.dout=-1;require(!audio.begin(s),"one direction is required");
  s=spec();s.volume=101;require(!audio.begin(s),"gain must be bounded");
  s=spec();s.sd=22;require(!audio.begin(s),"nonexistent S3 GPIO must be rejected");
}
void begin_maps_shared_bus_and_keeps_amplifier_muted() {
  api={}; ai_maker::BoardAudio audio;auto s=spec();
  require(audio.begin(s),"valid full duplex channels must begin");
  require(api.chan.id==I2S_NUM_0 && api.chan.role==I2S_ROLE_MASTER,"one master bus");
  require(api.chan.dma_desc_num==4 && api.chan.dma_frame_num==128 && api.chan.auto_clear_after_cb,"bounded DMA with automatic zero underrun");
  require(api.configurations.size()==2,"both directions configured");
  for(const auto& c:api.configurations) {
    require(c.clk_cfg.sample_rate_hz==16000 && c.slot_cfg.data_bit_width==32 && c.slot_cfg.slot_mode==2,"16000 stereo32 wire");
    require(c.gpio_cfg.mclk==-1 && c.gpio_cfg.bclk==42 && c.gpio_cfg.ws==41 && c.gpio_cfg.din==21 && c.gpio_cfg.dout==40,"runtime shared clock pins");
  }
  require(api.levels[39]==0,"amplifier must remain muted before play");
  require(audio.release() && allPinsReset(s),"release all owned pins");
  require(audio.release(),"repeat release");
}
void microphone_channel_and_pcm_byte_order() {
  for(bool right:{false,true}) {
    api={};ai_maker::BoardAudio audio;auto s=spec();s.mic_right=right;s.dout=-1;s.sd=-1;
    require(audio.begin(s) && audio.startCapture(),"capture begin");
    api.rx_samples={0x12340000,0x56780000,static_cast<int32_t>(0x80000000U),static_cast<int32_t>(0xffff0000U)};
    uint8_t out[4]={};
    require(audio.read(out,4)==4,"exact PCM read");
    const std::array<uint8_t,4> expected=right?std::array<uint8_t,4>{0x78,0x56,0xff,0xff}:std::array<uint8_t,4>{0x34,0x12,0x00,0x80};
    require(std::equal(expected.begin(),expected.end(),out),"select correct slot and emit exact little endian signed16");
    api.short_read=true;require(audio.read(out,4)==0,"partial I2S frames cannot be successful capture");
    require(!audio.startPlayback(),"RX-only mapping cannot play");
  }
}
void output_sign_volume_both_channels_and_drain() {
  api={};ai_maker::BoardAudio audio;auto s=spec();s.volume=50;
  require(audio.begin(s) && audio.startPlayback(),"play begin");
  require(api.levels[39]==1,"SD enabled only for playback");
  require(!audio.startCapture(),"HAL also rejects simultaneous record/play");
  api.tx_samples.clear();
  const uint8_t pcm[]={0xff,0x7f,0x00,0x80,0x01,0x00,0xff,0xff};
  require(audio.write(pcm,sizeof(pcm))==sizeof(pcm),"write PCM bytes");
  const std::vector<int32_t> expected={1073709056,1073709056,-1073741824,-1073741824,32768,32768,-32768,-32768};
  require(api.tx_samples==expected,"signed PCM scaled without left-shifting negative and duplicated L/R");
  const auto before=api.tx_samples.size();
  require(audio.finishPlayback(),"drain successful playback");
  require(api.tx_samples.size()-before>=2*1024,"silence exceeds entire DMA ring");
  require(std::all_of(api.tx_samples.begin()+static_cast<std::ptrdiff_t>(before),api.tx_samples.end(),[](int32_t v){return v==0;}),"drain contains zeros");
  require(api.levels[39]==0,"mute only after prior PCM drained");
  require(api.max_timeout<=80,"bounded individual I2S calls");
  require(audio.startPlayback(),"second playback allowed");
  api.short_write=true;require(audio.write(pcm,sizeof(pcm))==0,"partial write not successful");
}
void init_failures_release_every_owned_resource() {
  for(int phase=0;phase<5;++phase) {
    api={};ai_maker::BoardAudio audio;auto s=spec();
    if(phase==0)api.fail_new=1;
    if(phase==1)api.fail_init=1;
    if(phase==2)api.fail_init=2;
    if(phase==3)api.fail_enable=1;
    if(phase==4)api.fail_enable=2;
    require(!audio.begin(s),"injected begin failure must not be success");
    require(api.levels[39]==0 && allPinsReset(s),"partial init mutes and releases its GPIO");
    require(audio.release(),"release after failed init is idempotent");
  }
}
void cleanup_failures_stay_visible_and_can_retry() {
  for(int phase=0;phase<3;++phase) {
    api={};ai_maker::BoardAudio audio;auto s=spec();require(audio.begin(s),"begin for cleanup fault");
    if(phase==0)api.fail_disable=1;
    if(phase==1)api.fail_delete=1;
    if(phase==2)api.fail_pin=42;
    require(!audio.release(),"cleanup failure must be observable");
    require(api.levels[39]==0,"cleanup attempts mute despite driver fault");
    if(phase<2)require(api.reset_pins.empty(),"do not free GPIO while channel cleanup failed");
    api.fail_disable=api.fail_delete=0;api.fail_pin=-2;
    require(audio.release() && allPinsReset(s),"later cleanup can retry retained resources");
  }
}
void mute_failure_and_missing_shutdown_pin() {
  api={};ai_maker::BoardAudio audio;auto s=spec();require(audio.begin(s) && audio.startPlayback(),"begin playback");
  api.fail_pin=39;require(!audio.stopIO(),"mute failure must be returned");
  api.fail_pin=-2;require(audio.release(),"cleanup after mute fault");
  api={};s=spec();s.sd=-1;require(audio.begin(s) && audio.startPlayback() && audio.stopIO(),"without GPIO shutdown use bounded zero drain");
  require(api.levels.empty(),"never drive an absent shutdown GPIO");
}
void invalid_buffer_hard_io_failure_and_zero_volume() {
  api={};ai_maker::BoardAudio audio;auto s=spec();s.volume=0;
  require(audio.begin(s) && audio.startCapture(),"capture for buffer tests");
  uint8_t pcm[ai_maker::kAudioChunkBytes+2]={};
  const int read_calls=api.read_calls;
  for(size_t bytes:{size_t{0},size_t{1},size_t{3},sizeof(pcm)})
    require(audio.read(pcm,bytes)==0,"bad PCM byte sizes rejected");
  require(audio.read(nullptr,2)==0 && api.read_calls==read_calls,"invalid pointers do not reach I2S");
  api.read_ok=false;pcm[0]=0xaa;pcm[1]=0xbb;
  require(audio.read(pcm,2)==0 && pcm[0]==0xaa && pcm[1]==0xbb,"hard RX failure never publishes partial bytes");
  api.read_ok=true;require(audio.stopIO() && audio.startPlayback(),"stop capture before changing direction");
  const int write_calls=api.write_calls;
  require(audio.write(nullptr,2)==0 && audio.write(pcm,3)==0 && audio.write(pcm,sizeof(pcm))==0 && api.write_calls==write_calls,"invalid output rejected before I2S");
  api.tx_samples.clear();
  const uint8_t loud[]={0xff,0x7f,0x00,0x80};
  require(audio.write(loud,sizeof(loud))==sizeof(loud) &&
      std::all_of(api.tx_samples.begin(),api.tx_samples.end(),[](int32_t v){return v==0;}),"volume0 produces actual zeros");
  api.write_ok=false;require(audio.write(loud,sizeof(loud))==0 && !audio.finishPlayback(),"hard TX and drain failures visible");
  require(api.levels[39]==0,"failed drain still attempts amplifier mute");
  api.write_ok=true;require(audio.release(),"cleanup after TX failure");
}
}  // namespace

esp_err_t gpio_set_level(gpio_num_t pin,uint32_t value) {
  api.events.push_back(value?"unmute":"mute");
  if(pin==api.fail_pin)return ESP_FAIL;
  api.levels[pin]=static_cast<int>(value);return ESP_OK;
}
esp_err_t gpio_set_direction(gpio_num_t pin,gpio_mode_t) { return pin==api.fail_pin?ESP_FAIL:ESP_OK; }
esp_err_t gpio_reset_pin(gpio_num_t pin) { api.reset_pins.push_back(pin);return pin==api.fail_pin?ESP_FAIL:ESP_OK; }
esp_err_t i2s_new_channel(const i2s_chan_config_t* config,i2s_chan_handle_t* tx,i2s_chan_handle_t* rx) {
  api.chan=*config;++api.new_calls;
  if(api.new_calls==api.fail_new)return ESP_FAIL;
  if(tx)*tx=&api.tx;
  if(rx)*rx=&api.rx;
  return ESP_OK;
}
esp_err_t i2s_channel_init_std_mode(i2s_chan_handle_t,const i2s_std_config_t* config) {
  api.configurations.push_back(*config);return ++api.init_calls==api.fail_init?ESP_FAIL:ESP_OK;
}
esp_err_t i2s_channel_enable(i2s_chan_handle_t channel) {
  if(++api.enable_calls==api.fail_enable)return ESP_FAIL;
  channel->enabled=true;return ESP_OK;
}
esp_err_t i2s_channel_disable(i2s_chan_handle_t channel) {
  if(++api.disable_calls==api.fail_disable)return ESP_FAIL;
  channel->enabled=false;return ESP_OK;
}
esp_err_t i2s_del_channel(i2s_chan_handle_t channel) {
  require(!channel->enabled,"cannot delete enabled I2S channel");
  return ++api.deletes==api.fail_delete?ESP_FAIL:ESP_OK;
}
esp_err_t i2s_channel_read(i2s_chan_handle_t channel,void* target,size_t bytes,size_t* read,uint32_t timeout) {
  ++api.read_calls;
  require(!channel->tx && channel->enabled,"RX must be enabled");api.max_timeout=std::max(api.max_timeout,timeout);
  *read=0;
  if(timeout==0) {++api.flush_reads;return ESP_ERR_TIMEOUT;}
  if(!api.read_ok)return ESP_FAIL;
  if(api.rx_samples.empty())std::memset(target,0,bytes);
  else {require(api.rx_samples.size()*sizeof(int32_t)>=bytes,"enough fake RX data");std::memcpy(target,api.rx_samples.data(),bytes);}
  *read=api.short_read?bytes/2:bytes;return ESP_OK;
}
esp_err_t i2s_channel_write(i2s_chan_handle_t channel,const void* source,size_t bytes,size_t* written,uint32_t timeout) {
  ++api.write_calls;
  require(channel->tx && channel->enabled,"TX must be enabled");api.max_timeout=std::max(api.max_timeout,timeout);
  *written=0;if(!api.write_ok)return ESP_FAIL;
  const auto* data=static_cast<const int32_t*>(source);api.tx_samples.insert(api.tx_samples.end(),data,data+bytes/sizeof(int32_t));
  *written=api.short_write?bytes/2:bytes;return ESP_OK;
}

int main() {
  int failed=0;
  for(const auto& t:std::vector<std::pair<const char*,std::function<void()>>>{
      {"dormant_and_invalid_specs_do_not_touch_hardware",dormant_and_invalid_specs_do_not_touch_hardware},
      {"begin_maps_shared_bus_and_keeps_amplifier_muted",begin_maps_shared_bus_and_keeps_amplifier_muted},
      {"microphone_channel_and_pcm_byte_order",microphone_channel_and_pcm_byte_order},
      {"output_sign_volume_both_channels_and_drain",output_sign_volume_both_channels_and_drain},
      {"init_failures_release_every_owned_resource",init_failures_release_every_owned_resource},
      {"cleanup_failures_stay_visible_and_can_retry",cleanup_failures_stay_visible_and_can_retry},
      {"mute_failure_and_missing_shutdown_pin",mute_failure_and_missing_shutdown_pin},
      {"invalid_buffer_hard_io_failure_and_zero_volume",invalid_buffer_hard_io_failure_and_zero_volume}}) {
    try{t.second();std::cout<<"PASS "<<t.first<<'\n';}
    catch(const std::exception& e){++failed;std::cout<<"FAIL "<<t.first<<": "<<e.what()<<'\n';}
  }
  std::cout<<"8 audio HAL groups, "<<failed<<" failures\n";
  return failed?1:0;
}
