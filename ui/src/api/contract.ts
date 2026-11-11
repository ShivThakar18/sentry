/**
 * contract.ts: the UI's copy of docs/core-api.md, as TypeScript types.
 *
 * Every type here has a section number from core-api.md next to it. If you
 * change one, change the doc (and the core) in the same PR.
 *
 * Why hand-written instead of generated from /openapi.json?
 *   - OpenAPI only covers REST. The WebSocket messages (the part the UI uses
 *     most) aren't in it.
 *   - The draft sections (groups, protocols, orders) don't exist in the core
 *     yet, so there's nothing to generate them from.
 *   Later, a test can compare these types against the live /openapi.json (see
 *   steps-6-ui.md, 6h).
 */

// ===================================================================== //
// §2 Device
// ===================================================================== //

/** The capability names from mqtt-topics.md §4. `string & {}` keeps
 *  autocomplete for the known names but still accepts unknown ones, because
 *  §2.1 says an unknown capability must be ignored, not crash the UI. */
export type Capability =
  | "on_off"
  | "brightness"
  | "color_temp_k"
  | "color_xy"
  | "target_temperature"
  | "hvac_mode"
  | "temperature"
  | "humidity"
  | "pressure"
  | "occupancy"
  | "battery"
  | (string & {});

export type HvacMode = "heat" | "cool" | "auto" | "off";

export interface XY {
  x: number; // 0–1
  y: number; // 0–1
}

/** A [min, max] pair from `limits`. */
export type Range = [number, number];

/** The controllable/readable fields from mqtt-topics.md §4. Every field is
 *  optional because a device only has the fields for its own capabilities.
 *  Shared by devices and groups. */
export interface ControlState {
  on?: boolean;
  brightness?: number;
  color_temp_k?: number | null; // null while in colour (xy) mode
  color_xy?: XY | null;         // null while in white (temperature) mode
  target_temp_c?: number;
  mode?: HvacMode;
  temperature_c?: number;
  humidity_pct?: number;
  pressure_hpa?: number;
  occupied?: boolean;
  battery_pct?: number;
}

/** mqtt-topics.md §3.2: a device's full state. `available` is always there. */
export interface DeviceState extends ControlState {
  available: boolean;
  ts?: string;
  /** Adapters may add fields we don't know about yet. */
  [extra: string]: unknown;
}

export interface Limits {
  color_temp_k_range?: Range;
  target_temp_c_range?: Range;
  [key: `${string}_range`]: Range | undefined;
}

export interface Device {
  id: string;
  name: string;
  type: string;            // light, sensor, thermostat, … (icon only, §2)
  room: string | null;
  manufacturer?: string;   // 🔧 §9.2. Optional until the core adds it. DISPLAY ONLY.
  capabilities: Capability[];
  limits: Limits;
  state: DeviceState;
  usable: boolean;         // use this to grey out controls, not state.available
}

// ===================================================================== //
// §3.1 SetCommand
// ===================================================================== //

/** Partial: only send what changes. The core rejects {} and nulls (422).
 *  The `never` pairs make TypeScript refuse color_xy + color_temp_k together. */
type SetBase = {
  on?: boolean;
  brightness?: number;     // 0 < x ≤ 100. Never 0: send {on:false} instead.
  target_temp_c?: number;
  mode?: HvacMode;
};
export type SetCommand =
  | (SetBase & { color_xy?: XY; color_temp_k?: never })
  | (SetBase & { color_temp_k?: number; color_xy?: never });

export interface SetAccepted {
  accepted: SetCommand;
}

/** §6.2 / §7: group set and protocol run also say who it reached. */
export interface FanOutResult {
  accepted?: SetCommand;
  sent_to: string[];
  skipped: { id: string; reason: string }[];
}

// ===================================================================== //
// §1.2 Errors
// ===================================================================== //

export interface ValidationIssue {
  loc: (string | number)[];
  msg: string;
  type: string;
}

/** FastAPI sends either a string (our own checks) or a list (Pydantic). */
export interface ErrorBody {
  detail: string | ValidationIssue[];
}

// ===================================================================== //
// §6 Groups, §6.3 HQ layout (🟡 draft: mock only for now)
// ===================================================================== //

/** Icon names the UI owns (§6.1). Map each to a Tabler icon in one place. */
export type IconName =
  | "stack" | "bulb" | "lamp" | "bed" | "sofa" | "plug" | "tv"
  | "speaker" | "thermostat" | "film" | "moon" | "sun" | "bell";

/** Not `Omit<DeviceState, "available">`: Omit on a type with an index
 *  signature silently drops every named field. Extend the base instead. */
export interface GroupState extends ControlState {
  members_on: number;
}

export interface Group {
  id: string;              // "group-<slug>"
  name: string;
  room: string | null;
  icon: IconName;
  members: string[];       // device ids
  capabilities: Capability[]; // intersection of members' (computed by core)
  limits: Limits;             // overlap of members' ranges (computed by core)
  state: GroupState;          // computed by core
  usable: boolean;            // at least one member usable
}

/** What the UI sends to create or replace a group. */
export type GroupInput = Pick<Group, "name" | "room" | "icon" | "members">;

export type TargetKind = "device" | "group";
export interface Target {
  kind: TargetKind;
  id: string;
}

export interface HomeTile {
  kind: "device" | "group" | "protocol";
  id: string;
}
export interface HomeLayout {
  tiles: HomeTile[];
}

// ===================================================================== //
// §7 Protocols (🟡)
// ===================================================================== //

export interface ProtocolAction {
  target: Target;
  set: SetCommand;
}

export interface Protocol {
  id: string;
  name: string;
  icon: IconName;
  actions: ProtocolAction[];
  active: boolean;         // computed by core
}
export type ProtocolInput = Pick<Protocol, "name" | "icon" | "actions">;

// ===================================================================== //
// §8 Standing orders (🟡)
// ===================================================================== //

export type Day = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
export type CompareOp = "eq" | "ne" | "lt" | "gt";

/** A "discriminated union": the `kind` field tells TypeScript which shape it is.
 *  Inside `if (t.kind === "time")`, TypeScript knows `t.at` exists. */
export type Trigger =
  | { kind: "time"; at: string; days: Day[] }
  | { kind: "device_event"; device_id: string; event: string }
  | { kind: "device_state"; device_id: string; field: string; op: CompareOp; value: unknown };

export type Condition =
  | { kind: "time_between"; from: string; to: string }
  | { kind: "device_state"; device_id: string; field: string; op: CompareOp; value: unknown };

export type OrderAction =
  | { kind: "set"; target: Target; set: SetCommand }
  | { kind: "run_protocol"; protocol_id: string }
  | { kind: "notify"; title: string; message: string }
  | { kind: "show"; screen: "camera"; device_id: string };

export interface Order {
  id: string;
  name: string;
  icon: IconName;
  enabled: boolean;
  when: Trigger[];
  if: Condition[];
  then: OrderAction[];
  next_run: string | null; // computed by core
  last_run: string | null;
}
export type OrderInput = Pick<Order, "name" | "icon" | "enabled" | "when" | "if" | "then">;

// ===================================================================== //
// §4 WebSocket messages (server → UI)
// ===================================================================== //

export interface DeviceEvent {
  type: string;            // ring, motion, …
  ts: string;
  [extra: string]: unknown;
}

export type WsMessage =
  // ✅ live
  | {
      type: "snapshot";
      devices: Device[];
      // 🟡 draft keys: may be missing. Missing = empty (§4.2 rule 1).
      groups?: Group[];
      protocols?: Protocol[];
      orders?: Order[];
      home?: HomeLayout;
    }
  | { type: "device"; device: Device }
  | { type: "removed"; id: string }
  | { type: "event"; id: string; event: DeviceEvent }
  | { type: "adapter"; adapter: string; status: "online" | "offline" }
  // 🟡 draft
  | { type: "group"; group: Group }
  | { type: "group_removed"; id: string }
  | { type: "protocol"; protocol: Protocol }
  | { type: "protocol_removed"; id: string }
  | { type: "order"; order: Order }
  | { type: "order_removed"; id: string }
  | { type: "home"; home: HomeLayout }
  | { type: "show"; screen: "camera"; device_id: string };

/** Close code the core uses when a client falls behind (§4.2 rule 5). */
export const WS_CLOSE_TRY_AGAIN = 1013;

/** Timings from §4.2 and §5, kept here so they're not magic numbers in the code. */
export const TIMING = {
  pendingTimeoutMs: 5000,
  sliderThrottleMs: 150,
  reconnectBackoffMs: [500, 1000, 2000, 4000, 5000],
  showReconnectingAfterMs: 2000,
} as const;


