/**
 * <Pill>: one nav button. It's a router link, lit while its route is active.
 *
 *   <Pill to="/" end>HQ</Pill>
 *   <Pill to="/fleet">Fleet</Pill>
 */
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { glassClass } from "./glassClass";
import styles from "./Pill.module.css";

interface PillProps {
  to: string;
  children: ReactNode;
  /** Only match this exact path. HQ needs it: every path starts with "/". */
  end?: boolean;
  /** Smaller text, for two-line labels. */
  small?: boolean;
}

export function Pill({ to, children, end = false, small = false }: PillProps) {
  return (
    <NavLink
      to={to}
      end={end}
      // NavLink calls this function with { isActive } on every render, so the
      // pill lights up by itself when the route changes. It also sets
      // aria-current="page" on the active one.
      className={({ isActive }) => glassClass(isActive, styles.pill, small && styles.small)}
    >
      {children}
    </NavLink>
  );
}
