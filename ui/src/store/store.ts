/**
 * store.ts: the ONE place the UI keeps what it knows about the house.
 *
 * Zustand in one sentence: `create` makes a store, and `useCore(selector)` in
 * a component reads from it AND re-draws that component when the selected
 * part changes. No providers, no reducers to wire up.
 *
 * All the logic is in apply.ts (pure, tested). This file only connects it to
 * React, so there's very little here that can go wrong.
 */
import { create } from "zustand";
import type { WsMessage } from "../api/contract";
import { connectCore, coreSocketUrl, type ConnStatus } from "../api/socket";
import { apply, empty, type CoreState } from "./apply";

interface CoreStore extends CoreState {
  status: ConnStatus;
  receive: (m: WsMessage) => void;
  setStatus: (status: ConnStatus) => void;
}

export const useCore = create<CoreStore>()((set) => ({
  ...empty,
  status: "connecting",
  // apply() returns the same object when nothing changed. Zustand compares
  // with ===, so in that case nobody re-draws.
  receive: (m) => set((s) => apply(s, m)),
  setStatus: (status) => set({ status }),
}));

/**
 * Start the WebSocket. Called ONCE, from main.tsx, before React renders.
 *
 * Why not in a useEffect inside <App>? In development, React's StrictMode runs
 * every effect twice on purpose (mount → unmount → mount) to flush out bugs.
 * That would open two sockets for a moment. Out here there's exactly one.
 */
export function startCoreConnection(): () => void {
  const { receive, setStatus } = useCore.getState();
  return connectCore({ url: coreSocketUrl(), onMessage: receive, onStatus: setStatus });
}
