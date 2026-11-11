/**
 * fixtures.ts: fake data that matches the mockups, typed against contract.ts.
 *
 * Two jobs:
 *   1. The mock core (VITE_MOCK=1) serves this, so every screen can be built
 *      before the real adapters exist.
 *   2. It's a compile-time check of the contract: if contract.ts changes in a
 *      way the fixtures no longer fit, `tsc` fails here first.
 */
import type { Device, Group, HomeLayout, Order, Protocol } from "../api/contract";

const light = (
  id: string,
  name: string,
  room: string,
  manufacturer: string,
  on: boolean,
  brightness = 60,
): Device => ({
  id,
  name,
  type: "light",
  room,
  manufacturer,
  capabilities: ["on_off", "brightness", "color_temp_k", "color_xy"],
  limits: { color_temp_k_range: [2000, 6500] },
  state: { available: true, on, brightness, color_temp_k: 2700, color_xy: null },
  usable: true,
});

export const devices: Device[] = [
  light("hue-3", "Living Room Lamp", "Living Room", "Philips", true, 80),
  light("hue-7", "Kitchen Hue Strip", "Kitchen", "Philips", false),
  light("hue-hall", "Hall Light", "Hall", "Philips", false),
  light("govee-a1", "Pot Light 1", "Bedroom", "Govee", true),
  light("govee-a2", "Pot Light 2", "Bedroom", "Govee", true),
  light("govee-a3", "Pot Light 3", "Bedroom", "Govee", true),
  light("govee-a4", "Pot Light 4", "Bedroom", "Govee", true),
  {
    id: "tuya-heater",
    name: "Office Heater",
    type: "plug",
    room: "Office",
    manufacturer: "NBG",
    capabilities: ["on_off"],
    limits: {},
    state: { available: true, on: false },
    usable: true,
  },
  {
    // An unusable device, so you can see the greyed-out style.
    id: "tuya-desk",
    name: "Desk Plug",
    type: "plug",
    room: "Office",
    manufacturer: "NBG",
    capabilities: ["on_off"],
    limits: {},
    state: { available: false, on: false },
    usable: false,
  },
  {
    id: "ecobee-1",
    name: "Ecobee",
    type: "thermostat",
    room: "Hall",
    manufacturer: "ecobee",
    capabilities: ["target_temperature", "hvac_mode", "temperature", "humidity"],
    limits: { target_temp_c_range: [16, 26] },
    state: { available: true, target_temp_c: 21, mode: "heat", temperature_c: 20.5, humidity_pct: 41 },
    usable: true,
  },
  {
    id: "pi-bme280",
    name: "Display Sensor",
    type: "sensor",
    room: "Living Room",
    manufacturer: "Bosch",
    capabilities: ["temperature", "humidity", "pressure"],
    limits: {},
    state: { available: true, temperature_c: 21.5, humidity_pct: 38, pressure_hpa: 1012 },
    usable: true,
  },
  {
    id: "weather-home",
    name: "Outdoor",
    type: "sensor",
    room: "Outdoor",
    manufacturer: "Open-Meteo",
    capabilities: ["temperature"],
    limits: {},
    state: { available: true, temperature_c: 23 },
    usable: true,
  },
  {
    id: "eufy-1",
    name: "Front Doorbell",
    type: "doorbell",
    room: "Entrance",
    manufacturer: "Eufy",
    capabilities: ["battery"],
    limits: {},
    state: { available: true, battery_pct: 87 },
    usable: true,
  },
];

export const groups: Group[] = [
  {
    id: "group-bedroom-pot-lights",
    name: "Bedroom Pot Lights",
    room: "Bedroom",
    icon: "stack",
    members: ["govee-a1", "govee-a2", "govee-a3", "govee-a4"],
    capabilities: ["on_off", "brightness", "color_temp_k", "color_xy"],
    limits: { color_temp_k_range: [2000, 6500] },
    state: { on: true, brightness: 60, color_temp_k: 2700, color_xy: null, members_on: 4 },
    usable: true,
  },
];

export const protocols: Protocol[] = [
  {
    id: "proto-movie-night",
    name: "Movie Night",
    icon: "film",
    active: true,
    actions: [
      { target: { kind: "device", id: "hue-3" }, set: { on: true, brightness: 20, color_temp_k: 2200 } },
      { target: { kind: "group", id: "group-bedroom-pot-lights" }, set: { on: false } },
      { target: { kind: "device", id: "ecobee-1" }, set: { mode: "heat", target_temp_c: 21 } },
    ],
  },
  {
    id: "proto-lights-out",
    name: "Lights Out",
    icon: "moon",
    active: false,
    actions: [
      { target: { kind: "device", id: "hue-3" }, set: { on: false } },
      { target: { kind: "device", id: "hue-7" }, set: { on: false } },
      { target: { kind: "group", id: "group-bedroom-pot-lights" }, set: { on: false } },
    ],
  },
];

export const orders: Order[] = [
  {
    id: "order-night-visitor",
    name: "Night Visitor",
    icon: "bell",
    enabled: true,
    when: [{ kind: "device_event", device_id: "eufy-1", event: "ring" }],
    if: [
      { kind: "time_between", from: "22:00", to: "06:00" },
      { kind: "device_state", device_id: "hue-hall", field: "on", op: "eq", value: false },
    ],
    then: [
      { kind: "set", target: { kind: "device", id: "hue-hall" }, set: { on: true, brightness: 100 } },
      { kind: "notify", title: "Doorbell", message: "Someone's at the front door" },
      { kind: "show", screen: "camera", device_id: "eufy-1" },
    ],
    next_run: null,
    last_run: null,
  },
  {
    id: "order-wake-up",
    name: "Wake Up",
    icon: "sun",
    enabled: true,
    when: [{ kind: "time", at: "07:00", days: ["mon", "tue", "wed", "thu", "fri"] }],
    if: [],
    then: [{ kind: "set", target: { kind: "group", id: "group-bedroom-pot-lights" }, set: { on: true, brightness: 40 } }],
    next_run: "2026-11-10T12:00:00Z",
    last_run: null,
  },
];

export const home: HomeLayout = {
  tiles: [
    { kind: "device", id: "hue-3" },
    { kind: "device", id: "tuya-heater" },
    { kind: "group", id: "group-bedroom-pot-lights" },
    { kind: "device", id: "hue-7" },
    { kind: "protocol", id: "proto-movie-night" },
    { kind: "protocol", id: "proto-lights-out" },
  ],
};


