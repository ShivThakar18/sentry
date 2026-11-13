/**
 * <ConnectionBadge>: a small "Reconnecting…" note, shown only when the link to
 * the core has been down for a while (core-api.md §4.2 rule 6).
 *
 * Why wait 2 s before showing it? A 1013 kick or a core restart reconnects in
 * well under a second. Flashing a warning for that would just be noise.
 */
import { useEffect, useState } from "react";
import { IconPlugConnectedX } from "@tabler/icons-react";
import { TIMING } from "../api/contract";
import { useCore } from "../store/store";
import { glassClass } from "./glassClass";
import styles from "./ConnectionBadge.module.css";

export function ConnectionBadge() {
  // Select ONLY the status: this component re-draws when the connection
  // changes, not every time a light changes.
  const status = useCore((s) => s.status);
  // "Has this outage lasted longer than the delay?" Only ever set by the timer.
  const [late, setLate] = useState(false);

  useEffect(() => {
    if (status === "open") return;
    // Still down after the delay → late. If we reconnect first, the cleanup
    // cancels the timer and nothing is shown.
    const timer = setTimeout(() => setLate(true), TIMING.showReconnectingAfterMs);
    // The cleanup runs when `status` changes (and on unmount). Resetting
    // `late` here means the NEXT outage starts its 2 s wait from zero.
    return () => {
      clearTimeout(timer);
      setLate(false);
    };
  }, [status]); // re-run whenever status changes (react/exhaustive-deps checks this list)

  // Derived during render, not stored: "down AND it's been a while".
  // (Setting state straight inside the effect body to hide it would draw twice:
  // the linter's set-state-in-effect warning.)
  if (status === "open" || !late) return null;
  return (
    <div className={glassClass(false, styles.badge)} role="status">
      <IconPlugConnectedX size={18} stroke={1.5} />
      {status === "connecting" ? "Connecting…" : "Reconnecting…"}
    </div>
  );
}
