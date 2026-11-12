/**
 * glass.ts: one helper that builds the glass class list.
 *
 * Why a helper and not only the <Glass> component? A Pill is a router link
 * (<NavLink>) and a Tile is a <button>. Neither can be a <div>, but both need
 * the glass look. So they call glassClass() for their className.
 *
 * Why its own file? The linter's react/only-export-components rule wants
 * .tsx files to export only components, so hot reload keeps working.
 */
import styles from "./Glass.module.css";

/** Join class names, skipping false / undefined / "". */
export function cx(...names: (string | false | null | undefined)[]): string {
  return names.filter(Boolean).join(" ");
}

/** The glass classes, lit when `on`, plus any extra classes. */
export function glassClass(on = false, ...extra: (string | false | null | undefined)[]): string {
  return cx(styles.glass, on && styles.on, ...extra);
}
