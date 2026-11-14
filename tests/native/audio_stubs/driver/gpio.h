#pragma once
#include <cstdint>
using esp_err_t = int;
constexpr esp_err_t ESP_OK = 0;
constexpr esp_err_t ESP_FAIL = -1;
constexpr esp_err_t ESP_ERR_TIMEOUT = 0x107;
using gpio_num_t = int;
constexpr gpio_num_t GPIO_NUM_NC = -1;
enum gpio_mode_t { GPIO_MODE_INPUT, GPIO_MODE_OUTPUT };
esp_err_t gpio_set_level(gpio_num_t pin, uint32_t level);
esp_err_t gpio_set_direction(gpio_num_t pin, gpio_mode_t mode);
esp_err_t gpio_reset_pin(gpio_num_t pin);
