/**
 * <NavBar>: the four tabs, in the same place on every screen.
 *
 * Question: why does only HQ need `end`? Try removing it and open /fleet.
 * (And why DON'T Fleet, Protocols and Orders want `end`? Open /fleet/hue-3.)
 */
import { Pill } from "./Pill";
import styles from "./NavBar.module.css";

export function NavBar() {
  return (
    <nav className={styles.nav}>
      <Pill to="/" end>
        HQ
      </Pill>
      <Pill to="/fleet">Fleet</Pill>
      <Pill to="/protocols">Protocols</Pill>
      <Pill to="/orders" small>
        Standing
        <br />
        Orders
      </Pill>
    </nav>
  );
}
