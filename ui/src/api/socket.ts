/**
 * socket.ts: one WebSocket to the core that never gives up.
 *
 * Knows nothing about React or the store. It parses messages and hands them to
 * a callback, and reports its connection status to another. That keeps it
 * small, and the same file would work in a phone app or a test.
 *
 * Rules it follows (core-api.md §4.2 rule 5):
 *   - any close → reconnect, waiting 0.5 s, 1 s, 2 s, 4 s, then 5 s each time
 *   - close code 1013 ("you fell behind") → reconnect straight away
 *   - the wait resets once a snapshot arrives (a connection that opens and
 *     dies before sending anything doesn't count as success)
 */
import { TIMING, WS_CLOSE_TRY_AGAIN, type WsMessage } from "./contract";

/**
 *   connecting    first attempt, nothing received yet
 *   open          connected AND the snapshot has arrived: the data is fresh
 *   reconnecting  lost it; showing the last known state while we retry
 */
export type ConnStatus = "connecting" | "open" | "reconnecting";

export interface CoreSocketOptions {
  url: string;
  onMessage: (m: WsMessage) => void;
  onStatus: (s: ConnStatus) => void;
}

/** The core's WebSocket URL, on whatever host served this page. */
export function coreSocketUrl(): string {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  // location.host = "pi.local:5173" in dev (Vite proxies it) or ":8000" in the
  // kiosk (the core serves the page). Same code works for both.
  return `${scheme}://${location.host}/api/ws`;
}

/** Connect, and keep reconnecting until the returned stop() is called. */
export function connectCore({ url, onMessage, onStatus }: CoreSocketOptions): () => void {
  let ws: WebSocket | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;
  let failures = 0;      // closes since the last good snapshot → picks the wait
  let stopped = false;

  function open(): void {
    onStatus(failures === 0 ? "connecting" : "reconnecting");
    ws = new WebSocket(url);

    ws.onmessage = (e: MessageEvent<string>) => {
      let msg: WsMessage;
      try {
        msg = JSON.parse(e.data) as WsMessage;
      } catch {
        console.warn("core sent something that isn't JSON:", e.data);
        return;
      }
      if (msg.type === "snapshot") {
        failures = 0;    // this connection really works: reset the backoff
        onStatus("open");
      }
      onMessage(msg);
    };

    // A failed connection fires `error` and then `close`. All the retry logic
    // lives in `close`, so `error` has nothing to do.
    ws.onclose = (e: CloseEvent) => {
      ws = null;
      if (stopped) return;
      const steps = TIMING.reconnectBackoffMs;
      const wait =
        e.code === WS_CLOSE_TRY_AGAIN && failures === 0
          ? 0 // kicked for being slow: come straight back for a fresh snapshot
          : steps[Math.min(failures, steps.length - 1)];
      failures += 1;
      onStatus("reconnecting");
      console.info(`core socket closed (code ${e.code}); retrying in ${wait} ms`);
      retryTimer = setTimeout(open, wait);
    };
  }

  open();

  return function stop(): void {
    stopped = true;
    clearTimeout(retryTimer);
    ws?.close();
  };
}
