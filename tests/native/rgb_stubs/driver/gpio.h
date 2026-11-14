#pragma once
#include <cstdint>
using gpio_num_t = int;
constexpr int ESP_OK = 0;
constexpr int GPIO_MODE_OUTPUT = 2;
struct gpio_config_t { uint64_t pin_bit_mask; int mode; };
int gpio_config(const gpio_config_t*);
int gpio_set_level(gpio_num_t, int);
