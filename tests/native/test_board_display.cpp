// Runs production board_display.cpp with fault-injectable peripheral APIs.
// It verifies resource cleanup/command flow, not actual SPI waveforms or pixels.
#include "board_display.h"
#include <driver/gpio.h>
#include <algorithm>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <utility>

FakeDisplayApi display_api;
const uint8_t u8g2_font_wqy12_t_gb2312[] = {0};
void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
void pinMode(int, int) {}
bool ledcAttachChannel(uint8_t pin, uint32_t hz, uint8_t bits, uint8_t channel) {
  require(pin==16 && hz==1000 && bits==14 && channel==3, "wrong backlight resource");
  ++display_api.attaches; return display_api.attach_ok;
}
bool ledcWrite(uint8_t pin, uint32_t duty) { require(pin==16,"wrong backlight pin"); display_api.duty=duty; return display_api.write_ok; }
bool ledcDetach(uint8_t pin) { require(pin==16,"wrong detach pin"); ++display_api.detaches; return display_api.detach_ok; }
int gpio_config(const gpio_config_t* config) {
  require(config->mode==GPIO_MODE_INPUT && !config->pull_up_en && !config->pull_down_en,"cleanup must leave high impedance input");
  int pin=0; while (!(config->pin_bit_mask & (1ULL<<pin))) ++pin;
  display_api.input_pins.push_back(pin);
  return pin==display_api.gpio_failure_pin ? -1 : ESP_OK;
}
int gpio_set_level(gpio_num_t pin, int level) { require(pin==16 && level==0,"backlight must start off"); return ESP_OK; }

namespace {
ai_maker::DisplaySpec spec(bool backlight=false) {
  ai_maker::DisplaySpec value;
  value.enabled=true;
  value.sck=10; value.mosi=11; value.cs=12; value.dc=13; value.rst=14;
  value.backlight=backlight?16:-1; value.brightness=backlight?60:100;
  return value;
}
bool allReleased(bool backlight) {
  for (int pin : {10,11,12,13,14})
    if (std::find(display_api.input_pins.begin(),display_api.input_pins.end(),pin)==display_api.input_pins.end()) return false;
  return !backlight || std::find(display_api.input_pins.begin(),display_api.input_pins.end(),16)!=display_api.input_pins.end();
}

void dormant_and_idempotent() {
  display_api={}; ai_maker::BoardDisplay display;
  require(!display.fill(1) && !display.text(0,0,"test",1) && !display.brightness(50),"no output before begin");
  require(display.release() && display.release(),"empty release must be idempotent");
  require(display_api.spi_starts==0 && display_api.input_pins.empty(),"empty release must not touch pins");
}
void panels_rotation_mapping_and_text() {
  for (const char* name : {"st7789_240x320","st7789_240x240","st7735s_128x160"}) {
    for (int rotation=0;rotation<4;++rotation) {
      display_api={}; ai_maker::BoardDisplay display; auto value=spec();value.panel=name;value.rotation=rotation;
      require(display.begin(value),"supported panel/rotation must initialize");
      require(display_api.spi_pins==std::array<int,4>{10,-1,11,12},"SPI pins must be runtime-configurable, no MISO");
      require(display_api.control_pins==std::array<int,3>{12,13,14},"control pins must be runtime-configurable");
      require(display_api.init_hz==8000000 && display_api.drawing_hz==8000000,"init must also use the conservative SPI clock");
      require(display.fill(0xF800) && display_api.fill_color==0xF800,"RGB565 fill must reach panel");
      require(display.text(8,2,"你好\nESP32",0xFFFF),"UTF8 text command");
      require(display_api.text==std::vector<std::tuple<int,int,std::string>>{{8,14,"你好"},{8,30,"ESP32"}},"text must preserve x and top-left/16px line baseline");
      require(display.rect(1,2,20,30,1,true) && display_api.last_rect_filled,"filled rectangle");
      require(display.rect(1,2,20,30,1,false) && !display_api.last_rect_filled,"outlined rectangle");
      require(display.line(1,2,20,30,1) && display_api.shape==std::array<int,4>{1,2,20,30},"line command");
      const uint16_t pixels[] = {0xF800, 0x07E0, 0x001F, 0xFFFF};
      require(display.image(3,4,2,2,pixels) && display_api.pixels == std::vector<uint16_t>{0xF800,0x07E0,0x001F,0xFFFF}, "RGB565 bitmap colors and geometry reach driver");
      require(!display.image(0,0,2,2,nullptr) && !display.image(1000,0,2,2,pixels), "bitmap pointer and bounds checked");
      require(display.release() && allReleased(false),"all screen pins released");
      require(display_api.off_commands==1 && display_api.sleep_commands==1 && display_api.spi_ends==1,"screen must sleep and SPI must end");
      require(display.release() && display_api.spi_ends==1,"repeat release must not end a foreign bus");
    }
  }
}
void backlight_and_cleanup_retry() {
  display_api={}; ai_maker::BoardDisplay display;
  require(display.begin(spec(true)) && display_api.attaches==1,"backlight attach");
  require(display.brightness(0) && display_api.duty==0,"zero brightness");
  require(display.brightness(100) && display_api.duty==16383,"full brightness");
  require(!display.brightness(101),"reject invalid brightness");
  display_api.detach_ok=false;
  require(!display.release(),"failed detach must not report success");
  require(allReleased(true) && display_api.duty==0 && display_api.spi_ends==1,"detach failure must not stop remaining cleanup");
  require(!display.fill(1),"failed release must not permit drawing");
  display_api.detach_ok=true;
  require(display.release(),"transient cleanup failure may recover");
}
void partial_begin_failures_cleanup() {
  for (int fault=0;fault<5;++fault) {
    display_api={}; ai_maker::BoardDisplay display;
    display_api.spi_begin_ok=fault!=0;
    display_api.geometry_ok=fault!=1;
    display_api.attach_ok=fault!=2;
    display_api.write_ok=fault!=3;
    if (fault==4) display_api.gpio_failure_pin=12;
    if (fault==4) {
      require(display.begin(spec(true)),"setup before GPIO cleanup fault");
      require(!display.release(),"GPIO cleanup failure must remain visible");
    } else require(!display.begin(spec(true)),"injected initialization fault must fail");
    require(!display.fill(1) && allReleased(true) && display_api.spi_ends==1,"partial begin failure must release every resource");
    display_api.spi_begin_ok=display_api.geometry_ok=display_api.attach_ok=display_api.write_ok=true;
    display_api.gpio_failure_pin=-1;
    require(display.release(),"cleanup retry after fault removal");
    require(display.begin(spec(true)),"new begin after successful cleanup");
  }
}
}

int main() {
  try {
    dormant_and_idempotent();
    panels_rotation_mapping_and_text();
    backlight_and_cleanup_retry();
    partial_begin_failures_cleanup();
    std::cout<<"PASS display panel/rotation/map/text, brightness, partial init and cleanup faults\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr<<"FAIL board display: "<<error.what()<<'\n';return 1;
  }
}
