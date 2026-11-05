// Waveshare ESP32-S3-Touch-AMOLED-1.75C: round 466x466 AMOLED (CO5300, QSPI), CST9217 touch,
// ES8311 speaker codec + ES7210 dual mic, AXP2101 PMU, QMI8658 IMU, AXP2101 power-key sensing (GPIO3).
// Display/touch/audio bring-up adapted from Pana (github.com/eriktaveras/pana-companion, MIT),
// Pin map: official 1.75C pin_config.h and schematic in docs/wappai/hardware-reference.
#pragma once
#define LGFX_USE_V1
#include <LovyanGFX.hpp>

#define PIN_I2C_SDA 15      // shared: CST9217 0x5A, ES8311 0x18, ES7210 0x40, AXP2101 0x34, PCF85063 0x51, QMI8658 0x6B, TCA9554 0x20
#define PIN_I2C_SCL 14
#define I2C_PORT 0
#define PIN_TP_INT 11       // RTC-capable: deep-sleep wake on touch
#define PIN_TP_RST 2        // 1.75C schematic: GPIO2, not the bare board's GPIO40
#define PIN_BOOT 0          // push-to-talk button (active low), deep-sleep wake
#define PIN_IMU_INT2 21
#define PIN_LCD_TE 13       // CO5300 tearing-effect output (TE enabled by 0x35 in the init list)

#define PIN_I2S_MCLK 16     // 1.75C: shared by ES8311 and ES7210
#define PIN_PWR_SENSE 3     // SYS_OUT, high while physical PWR button is held
#define PIN_I2S_BCLK 9
#define PIN_I2S_WS 45
#define PIN_I2S_DOUT 8
#define PIN_I2S_DIN 10
#define PIN_PA 46           // amplifier enable, high = on
#define HAS_ES7210 1

#define ADDR_PMU 0x34
#define ADDR_RTC 0x51
#define ADDR_IMU 0x6B
#define ADDR_EXP 0x20
#define ADDR_TOUCH 0x5A

// CO5300 on this board: 480-column memory with a 6-pixel offset; init sequence from the Waveshare BSP
struct Panel_CO5300_175 : public lgfx::Panel_CO5300 {
    const uint8_t *getInitCommands(uint8_t listno) const override {
        static constexpr uint8_t list0[] = {
            0xFE, 1, 0x20, 0x19, 1, 0x10, 0x1C, 1, 0xA0, 0xFE, 1, 0x00, 0xC4, 1, 0x80, 0x3A, 1, 0x55,
            0x35, 1, 0x00, 0x53, 1, 0x20, 0x51, 1, 0xFF, 0x63, 1, 0xFF,
            0x2A, 4, 0x00, 0x06, 0x01, 0xD7, 0x2B, 4, 0x00, 0x00, 0x01, 0xD1,
            0x11, 0x80, 0, 0x29, 0x80, 0, 0xff, 0xff,
        };
        return listno == 0 ? list0 : nullptr;
    }
};

class LGFX : public lgfx::LGFX_Device {
    Panel_CO5300_175 _panel;
    lgfx::Bus_SPI _bus;
    bool _touchOk = false;
    volatile bool _down = false;

public:
    static const int WIDTH = 466, HEIGHT = 466;
    LGFX() {
        auto b = _bus.config();
        b.spi_host = SPI2_HOST;
        b.spi_mode = 0;
        b.freq_write = 80000000;
        b.freq_read = 20000000;
        b.spi_3wire = true;
        b.use_lock = true;
        b.dma_channel = SPI_DMA_CH_AUTO;
        b.pin_sclk = 38;
        b.pin_io0 = 4;
        b.pin_io1 = 5;
        b.pin_io2 = 6;
        b.pin_io3 = 7;
        _bus.config(b);
        _panel.setBus(&_bus);
        auto p = _panel.config();
        p.pin_cs = 12;
        p.pin_rst = 1;
        p.pin_busy = -1;
        p.panel_width = WIDTH;
        p.panel_height = HEIGHT;
        p.memory_width = 480;
        p.memory_height = HEIGHT;
        p.offset_x = 6;
        p.offset_y = 0;
        p.readable = false;
        p.bus_shared = false;
        _panel.config(p);
        setPanel(&_panel);
    }
    bool init();
    bool getTouch(lgfx::touch_point_t *tp);
    void flush(LGFX_Sprite &s, int x, int y, int w, int h, bool edgeBand=false,const uint16_t *previous=nullptr,int slideRemaining=0);   // copy a region of the full-screen sprite (even-aligned)
    void panelBrightness(uint8_t v);                          // CO5300 0x51
    void panelSleep(bool on);                                 // display off + sleep-in / wake
};

// --- other on-board devices (board.cpp) -------------------------------------------------
bool i2cWrite(uint8_t addr, uint8_t reg, uint8_t v);
int i2cRead(uint8_t addr, uint8_t reg);
bool i2cReadN(uint8_t addr, uint8_t reg, uint8_t *dst, size_t n);

struct Accel { float x, y, z; bool ok; };   // g units, screen frame (x right, y down, z out of screen)
bool imuBegin();
Accel imuRead();
void imuSleep();

bool rtcRead(struct tm *t);                 // local time from PCF85063
void rtcWrite(const struct tm *t);

bool pwrButtonDown();                       // PWR key level via SYS_OUT GPIO3
