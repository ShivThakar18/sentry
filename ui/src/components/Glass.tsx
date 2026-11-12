/**
 * <Glass>: a div with the glass look. For panels and cards
 * (the weather card on HQ, the big panel on the group screen).
 *
 *   <Glass className={styles.weather}>…</Glass>
 *   <Glass on>…</Glass>                       // lit
 */
import type { ComponentProps } from "react";
import { glassClass } from "./glass";

// ComponentProps<"div"> = every prop a normal <div> accepts (style, onClick,
// children, …). We add `on` and pass the rest straight through with {...rest}.
type GlassProps = ComponentProps<"div"> & { on?: boolean };

export function Glass({ on = false, className, ...rest }: GlassProps) {
  return <div className={glassClass(on, className)} {...rest} />;
}
