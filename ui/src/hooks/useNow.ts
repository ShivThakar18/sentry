/**
 * useNow(): the current time, re-rendering the component when the minute changes.
 *
 * Why not setInterval(…, 1000)? That re-draws 60 times a minute to change the
 * screen once. This waits exactly until the next minute starts, then repeats,
 * so the clock flips right on :00 and the Pi does almost nothing in between.
 */
import { useEffect, useState } from "react";

export function useNow(): Date {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const scheduleNext = () => {
      const msToNextMinute = 60_000 - (Date.now() % 60_000);
      timer = setTimeout(() => {
        setNow(new Date());
        scheduleNext();
      }, msToNextMinute + 20); // +20 ms so we land just AFTER the minute ticks over
    };
    scheduleNext();
    return () => clearTimeout(timer); // stop when the component goes away
  }, []); // [] = set this up once, on mount

  return now;
}
