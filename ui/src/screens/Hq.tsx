/**
 * <Hq>: the home screen (mockups/01-hq.png), live from the store.
 *
 * Split into small components on purpose: each one selects only what it needs
 * from the store, so the clock ticking doesn't re-draw the tiles, and a light
 * changing doesn't re-draw the clock.
 */
import { useMemo } from "react";
import { IconSunHigh, IconTemperature } from "@tabler/icons-react";
import { useShallow } from "zustand/react/shallow";
import { Glass } from "../components/Glass";
import { Tile } from "../components/Tile";
import { useNow } from "../hooks/useNow";
import { formatDate, formatTime } from "../lib/format";
import { climate, hqTiles } from "../lib/tiles";
import { useCore } from "../store/store";
import styles from "./Hq.module.css";

function Clock() {
  const now = useNow();
  return (
    <>
      <div className={styles.brand}>S.E.N.T.R.Y</div>
      {/* <time> with dateTime: the machine-readable value, for screen readers and tests */}
      <time className={styles.clock} dateTime={now.toISOString()}>
        {formatTime(now)}
      </time>
      <div className={styles.date}>{formatDate(now)}</div>
    </>
  );
}

function ClimateCard() {
  // useShallow: climate() builds a NEW object every time. Without useShallow,
  // Zustand would see "new object ≠ old object" on every read and loop.
  // useShallow compares the fields instead, and these fields are STRINGS
  // ("23°C"), which compare by value. So this one is safe; Tiles below isn't.
  const { outdoor, indoor } = useCore(useShallow(climate));
  return (
    <Glass className={styles.climate}>
      <span>Outdoor</span>
      <IconSunHigh size={40} stroke={1.5} />
      <span className={styles.temp}>{outdoor}</span>
      <span>Indoor</span>
      <IconTemperature size={40} stroke={1.5} />
      <span className={styles.temp}>{indoor}</span>
    </Glass>
  );
}

function Tiles() {
  // NOT useCore(useShallow(hqTiles)). hqTiles builds brand-new tile OBJECTS on
  // every call, so even a shallow compare never sees "equal", and React keeps
  // asking again: an endless re-render loop. Instead:
  //   1. select the raw store pieces. They're the store's own objects, so
  //      useShallow returns the same `src` until one of them really changes.
  //   2. compute the tiles from them, only when `src` changes (useMemo).
  const src = useCore(
    useShallow((s) => ({ devices: s.devices, groups: s.groups, protocols: s.protocols, home: s.home })),
  );
  const tiles = useMemo(() => hqTiles(src), [src]);
  return (
    <div className={styles.tiles}>
      {tiles.map((t) => (
        // No onTap yet: 6g adds commands.
        <Tile key={t.key} icon={t.icon} name={t.name} status={t.status} on={t.on} disabled={t.disabled} />
      ))}
    </div>
  );
}

export function Hq() {
  return (
    <>
      <Clock />
      <ClimateCard />
      <Tiles />
    </>
  );
}
