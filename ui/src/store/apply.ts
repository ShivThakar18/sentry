/**
 * apply.ts: (current state, one WebSocket message) → new state.
 *
 * PURE, like the core's registry.py: no React, no WebSocket, no fetch, no
 * timers. That's why apply.test.ts can check every rule in core-api.md §4.2
 * in milliseconds, with plain objects.
 *
 * Two rules every branch follows:
 *   1. Never change `s`. Build a new object. React (and Zustand) decide "did
 *      anything change?" by comparing object identity (===), not contents.
 *      If you edit `s` in place, the screen never re-draws.
 *   2. When nothing changes, return `s` ITSELF. Same identity = "no change",
 *      so nothing re-draws.
 */
import type { Device, Group, HomeLayout, Order, Protocol, WsMessage } from "../api/contract";

/** Everything the UI knows about the house. Lists are stored as id → object. */
export interface CoreState {
  devices: Record<string, Device>;
  groups: Record<string, Group>;
  protocols: Record<string, Protocol>;
  orders: Record<string, Order>;
  home: HomeLayout;
  adapters: Record<string, "online" | "offline">;
}

export const empty: CoreState = {
  devices: {},
  groups: {},
  protocols: {},
  orders: {},
  home: { tiles: [] },
  adapters: {},
};

/** [{id: "a", …}, {id: "b", …}] → {a: {…}, b: {…}}. A missing list → {}. */
function byId<T extends { id: string }>(list: T[] = []): Record<string, T> {
  return Object.fromEntries(list.map((item) => [item.id, item]));
}

/** A copy of `rec` without `id`. Returns `rec` itself if `id` wasn't there (rule 2). */
function without<T>(rec: Record<string, T>, id: string): Record<string, T> {
  if (!(id in rec)) return rec;
  const next = { ...rec };
  delete next[id];
  return next;
}

/**
 * Generic over S so the Zustand store (CoreState + its own fields) can pass
 * itself in and get the same type back, with its extra fields untouched.
 */
export function apply<S extends CoreState>(s: S, m: WsMessage): S {
  switch (m.type) {
    // §4.2 rule 1: a snapshot REPLACES everything. Not merged: a device that
    // was deleted while we were disconnected must disappear.
    case "snapshot":
      return {
        ...s,
        devices: byId(m.devices),
        // Draft keys: the real core doesn't send them yet. Missing = empty.
        groups: byId(m.groups),
        protocols: byId(m.protocols),
        orders: byId(m.orders),
        home: m.home ?? { tiles: [] },
        // Adapter status isn't in the snapshot, so anything we knew is out of
        // date. Forget it; the `usable` on each device already covers it.
        adapters: {},
      };

    // §4.2 rule 2: the full device. Replace, never merge.
    // (Rule 3, duplicates are harmless, follows from that: replacing a device
    // with the same thing twice gives the same result.)
    case "device":
      return { ...s, devices: { ...s.devices, [m.device.id]: m.device } };

    case "removed": {
      const devices = without(s.devices, m.id);
      return devices === s.devices ? s : { ...s, devices };
    }

    case "adapter":
      if (s.adapters[m.adapter] === m.status) return s;
      return { ...s, adapters: { ...s.adapters, [m.adapter]: m.status } };

    // ---- 🟡 draft messages (the mock sends these; the real core doesn't yet)
    case "group":
      return { ...s, groups: { ...s.groups, [m.group.id]: m.group } };
    case "group_removed": {
      const groups = without(s.groups, m.id);
      return groups === s.groups ? s : { ...s, groups };
    }
    case "protocol":
      return { ...s, protocols: { ...s.protocols, [m.protocol.id]: m.protocol } };
    case "protocol_removed": {
      const protocols = without(s.protocols, m.id);
      return protocols === s.protocols ? s : { ...s, protocols };
    }
    case "order":
      return { ...s, orders: { ...s.orders, [m.order.id]: m.order } };
    case "order_removed": {
      const orders = without(s.orders, m.id);
      return orders === s.orders ? s : { ...s, orders };
    }
    case "home":
      return { ...s, home: m.home };

    // `event` (doorbell ring) and `show` (open the camera) are things that
    // HAPPEN, not state. They don't belong in the store; the socket hands them
    // to a separate listener (later: the doorbell pop-up).
    case "event":
    case "show":
      return s;

    // §4.2 rule 4: a type we don't know (a newer core) → ignore it.
    // TypeScript thinks this can't happen, since it only knows the types in
    // contract.ts. At runtime, a newer core can send anything.
    default:
      return s;
  }
}
