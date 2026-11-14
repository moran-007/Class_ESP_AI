#pragma once
#include "gpio.h"
#include <cstddef>
#include <cstdint>
struct FakeI2sChannel { bool tx = false; bool enabled = false; };
using i2s_chan_handle_t = FakeI2sChannel*;
constexpr int I2S_NUM_0 = 0;
constexpr int I2S_ROLE_MASTER = 1;
constexpr int I2S_DATA_BIT_WIDTH_32BIT = 32;
constexpr int I2S_SLOT_MODE_STEREO = 2;
constexpr gpio_num_t I2S_GPIO_UNUSED = GPIO_NUM_NC;
struct i2s_chan_config_t {
  int id, role;
  uint32_t dma_desc_num, dma_frame_num;
  bool auto_clear_after_cb, auto_clear_before_cb, allow_pd;
  int intr_priority;
};
#define I2S_CHANNEL_DEFAULT_CONFIG(id,role) {id,role,6,240,false,false,false,0}
struct i2s_std_clk_config_t { uint32_t sample_rate_hz; };
struct i2s_std_slot_config_t { int data_bit_width, slot_mode; };
struct i2s_std_gpio_config_t {
  gpio_num_t mclk,bclk,ws,dout,din;
  struct { uint32_t mclk_inv:1; uint32_t bclk_inv:1; uint32_t ws_inv:1; } invert_flags;
};
struct i2s_std_config_t {
  i2s_std_clk_config_t clk_cfg;
  i2s_std_slot_config_t slot_cfg;
  i2s_std_gpio_config_t gpio_cfg;
};
#define I2S_STD_CLK_DEFAULT_CONFIG(rate) {rate}
#define I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(bits,slots) {bits,slots}
esp_err_t i2s_new_channel(const i2s_chan_config_t*,i2s_chan_handle_t*,i2s_chan_handle_t*);
esp_err_t i2s_channel_init_std_mode(i2s_chan_handle_t,const i2s_std_config_t*);
esp_err_t i2s_channel_enable(i2s_chan_handle_t);
esp_err_t i2s_channel_disable(i2s_chan_handle_t);
esp_err_t i2s_del_channel(i2s_chan_handle_t);
esp_err_t i2s_channel_read(i2s_chan_handle_t,void*,size_t,size_t*,uint32_t);
esp_err_t i2s_channel_write(i2s_chan_handle_t,const void*,size_t,size_t*,uint32_t);
