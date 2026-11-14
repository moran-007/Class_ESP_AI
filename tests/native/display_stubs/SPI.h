#pragma once
#include "fake_display_api.h"
struct spi_t {};
class SPIClass {
 public:
  explicit SPIClass(int) {}
  bool begin(int sck, int miso, int mosi, int cs) {
    ++display_api.spi_starts;
    display_api.spi_pins = {sck,miso,mosi,cs};
    allocated_ = true;  // Failed begin can still leave a partially owned bus.
    return display_api.spi_begin_ok;
  }
  spi_t* bus() { return allocated_ ? &bus_ : nullptr; }
  void end() { if (allocated_) ++display_api.spi_ends; allocated_=false; }
 private:
  bool allocated_ = false;
  spi_t bus_;
};
