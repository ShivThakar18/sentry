/**
 * config.ts: settings for THIS display. Small on purpose.
 *
 * Everything here is a choice about how this screen looks, not data about the
 * house. If a second display is ever added, these are the things it might
 * want different.
 */
export const CONFIG = {
  /** Language/region for the clock and date. "en-CA" → "Wednesday, November 12". */
  locale: "en-CA",
  /** 24-hour clock ("18:05") or 12-hour ("6:05", no am/pm, like the mockup). */
  clock24h: true,

  /**
   * Which device is "Indoor" on HQ. The BME280 on the Pi, once its adapter
   * exists. Until then the card shows "—".
   */
  indoorSensorId: "pi-bme280",
  /**
   * "Outdoor" = the first device in this room with a temperature reading
   * (core-api.md §10: weather is just another device, from a weather adapter).
   */
  outdoorRoom: "Outdoor",

  /** HQ shows at most this many tiles (2 columns × 3 rows; core-api.md §6.3). */
  hqTileCount: 6,
} as const;
