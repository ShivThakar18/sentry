/**
 * apply.test.ts: one test per rule in core-api.md §4.2, plus the draft parts.
 * Run: npx vitest   (watches files; press q to quit)
 */
import { describe, expect, it } from "vitest";
import type { Device, WsMessage } from "../api/contract";
import { devices, groups, home } from "../mock/fixtures";
import { apply, empty, type CoreState } from "./apply";

// A loaded state to start from: the fixtures, as a snapshot would deliver them.
const loaded = (): CoreState => apply(empty, { type: "snapshot", devices, groups, home });

const lamp = devices.find((d) => d.id === "hue-3")!;
const lampOff: Device = { ...lamp, state: { ...lamp.state, on: false } };

describe("snapshot (rule 1: replaces everything)", () => {
  it("loads every device by id", () => {
    const s = loaded();
    expect(Object.keys(s.devices)).toHaveLength(devices.length);
    expect(s.devices["hue-3"].name).toBe("Living Room Lamp");
  });

  it("drops devices that are no longer in the new snapshot", () => {
    const s = apply(loaded(), { type: "snapshot", devices: [lamp] });
    expect(Object.keys(s.devices)).toEqual(["hue-3"]);
  });

  it("treats missing draft keys as empty (the real core today)", () => {
    const s = apply(loaded(), { type: "snapshot", devices: [lamp] });
    expect(s.groups).toEqual({});
    expect(s.home).toEqual({ tiles: [] });
  });

  it("forgets adapter status", () => {
    const before = apply(loaded(), { type: "adapter", adapter: "hue", status: "offline" });
    const after = apply(before, { type: "snapshot", devices });
    expect(after.adapters).toEqual({});
  });
});

describe("device (rule 2: full replace)", () => {
  it("replaces the stored device", () => {
    const s = apply(loaded(), { type: "device", device: lampOff });
    expect(s.devices["hue-3"].state.on).toBe(false);
  });

  it("replaces, never merges: a field missing from the update is gone", () => {
    const stateWithoutBrightness = { ...lamp.state };
    delete stateWithoutBrightness.brightness;
    const s = apply(loaded(), { type: "device", device: { ...lamp, state: stateWithoutBrightness } });
    expect(s.devices["hue-3"].state.brightness).toBeUndefined();
  });

  it("adds a device it hasn't seen before", () => {
    const fresh: Device = { ...lamp, id: "hue-99", name: "New Lamp" };
    expect(apply(loaded(), { type: "device", device: fresh }).devices["hue-99"].name).toBe("New Lamp");
  });

  it("doesn't touch the old state object (immutability)", () => {
    const before = loaded();
    apply(before, { type: "device", device: lampOff });
    expect(before.devices["hue-3"].state.on).toBe(true);
  });
});

describe("rule 3: duplicates are harmless", () => {
  it("the same message twice = once", () => {
    const msg: WsMessage = { type: "device", device: lampOff };
    const once = apply(loaded(), msg);
    expect(apply(once, msg)).toEqual(once);
  });
});

describe("removed", () => {
  it("removes the device", () => {
    expect(apply(loaded(), { type: "removed", id: "hue-3" }).devices["hue-3"]).toBeUndefined();
  });

  it("returns the SAME object when the id is unknown (nothing changed)", () => {
    const s = loaded();
    expect(apply(s, { type: "removed", id: "nope" })).toBe(s);
  });
});

describe("rule 4: unknown or non-state messages are ignored", () => {
  it("returns the same object for an unknown type", () => {
    const s = loaded();
    // `as unknown as WsMessage`: TypeScript won't let us build a bad message on
    // purpose, so we tell it to trust us. This is what a newer core could send.
    const future = { type: "firmware_update", id: "hue-3" } as unknown as WsMessage;
    expect(apply(s, future)).toBe(s);
  });

  it("doesn't store events (they happen, they aren't state)", () => {
    const s = loaded();
    const ring: WsMessage = { type: "event", id: "eufy-1", event: { type: "ring", ts: "2026-11-11T20:00:00Z" } };
    expect(apply(s, ring)).toBe(s);
  });
});

describe("adapter", () => {
  it("records the status", () => {
    expect(apply(loaded(), { type: "adapter", adapter: "hue", status: "offline" }).adapters.hue).toBe("offline");
  });

  it("returns the same object when the status didn't change", () => {
    const s = apply(loaded(), { type: "adapter", adapter: "hue", status: "online" });
    expect(apply(s, { type: "adapter", adapter: "hue", status: "online" })).toBe(s);
  });
});

describe("draft: groups", () => {
  it("replaces a group and removes one", () => {
    const g = { ...groups[0], name: "Renamed" };
    const s = apply(loaded(), { type: "group", group: g });
    expect(s.groups[g.id].name).toBe("Renamed");
    expect(apply(s, { type: "group_removed", id: g.id }).groups[g.id]).toBeUndefined();
  });
});
