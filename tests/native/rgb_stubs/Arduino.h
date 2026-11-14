#pragma once
#include <cstddef>
#include <cstdint>
enum rmt_ch_dir_t { RMT_RX_MODE, RMT_TX_MODE };
enum rmt_reserve_memsize_t { RMT_MEM_NUM_BLOCKS_1 = 1 };
struct rmt_data_t { uint16_t duration0; uint16_t level0; uint16_t duration1; uint16_t level1; };
bool rmtInit(int, rmt_ch_dir_t, rmt_reserve_memsize_t, uint32_t);
bool rmtDeinit(int);
bool rmtWrite(int, rmt_data_t*, size_t, uint32_t);
void delay(uint32_t);
