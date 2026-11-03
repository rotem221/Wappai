#pragma once
#define FW_VERSION "1.1.0-dev"
#define DEVICE_NAME "Wappai"

#define SCREEN_W 466
#define SCREEN_H 466
#define FRAME_MS 33               // ~30 fps while active

// interaction
#define PTT_HOLD_MS 220           // hold BOOT this long to start talking
#define TOUCH_PTT_MS 650          // or hold the screen this long
#define MAX_REC_MS 45000          // the ring fills in this time; recording stops at the end
#define MAX_MEETING_MS (5UL * 60UL * 60UL * 1000UL)   // meeting transcription stops after 5 h

// power (ms since last interaction)
#define DIM_AFTER_MS 15000
#define OFF_AFTER_MS 30000
#define DEEP_AFTER_MS (5UL * 60UL * 1000UL)   // screen-off time on battery before deep sleep
#define DEEP_POCKET_MS (5UL * 60UL * 1000UL)   // ... when in a pocket / face down
#define BAT_CRITICAL_PCT 3                     // below this (and BAT_CRITICAL_MV) on battery: warn and sleep
#define BAT_CRITICAL_MV 3450
#define BRIGHT_DIM 30
#define BATTERY_CARE true         // charge to 4.1 V (longer battery life) instead of 4.2 V

// Israel time zone (DST: Friday before last Sunday of March -> last Sunday of October)
#define TZ_INFO "IST-2IDT,M3.4.4/26,M10.5.0"
