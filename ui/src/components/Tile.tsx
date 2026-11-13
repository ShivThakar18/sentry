/**
 * <Tile>: icon + name + status line. Used on HQ and in Fleet.
 *
 *   <Tile icon={IconBulb} name="Living Room Lamp" status="On · 80%" on onTap={toggle} />
 *   <Tile icon={IconOutlet} name="Desk Plug" status="Unavailable" disabled />
 *
 * It's a real <button>, so `disabled` blocks taps for free and the CSS can use
 * the :disabled selector. The tile doesn't know about devices: the screen
 * decides name / status / on / disabled. That keeps it reusable for groups and
 * protocols too.
 */
import type { Icon } from "@tabler/icons-react";
import { glassClass } from "./glassClass";
import styles from "./Tile.module.css";

interface TileProps {
  /** A Tabler icon COMPONENT (IconBulb), not an element (<IconBulb />). */
  icon: Icon;
  name: string;
  status: string;
  /** Lit (device on, protocol active). */
  on?: boolean;
  /** Greyed out, taps ignored (device not usable). */
  disabled?: boolean;
  onTap?: () => void;
}

export function Tile({ icon: TileIcon, name, status, on = false, disabled = false, onTap }: TileProps) {
  // A disabled tile is never lit, even if its last known state was "on":
  // showing "on" for a device we can't reach would be a lie.
  const lit = on && !disabled;

  return (
    <button
      type="button"
      className={glassClass(lit, styles.tile)}
      disabled={disabled}
      onClick={onTap}
      aria-pressed={lit} // screen readers (and tests) can see on/off
    >
      {/* Renamed to TileIcon above: JSX needs a capitalised name for a component. */}
      <TileIcon className={styles.icon} size={36} stroke={1.5} />
      <span className={styles.name}>{name}</span>
      <span className={styles.status}>{status}</span>
    </button>
  );
}
