/**
 * <Debug>: a plain list of everything in the store, at /debug.
 * Not part of the design. It's for checking 6e works, and it stays useful
 * later whenever "is it the UI or the data?" comes up.
 */
import { useCore } from "../store/store";
import styles from "./Debug.module.css";

export function Debug() {
  const devices = useCore((s) => s.devices);
  const groups = useCore((s) => s.groups);
  const adapters = useCore((s) => s.adapters);
  const status = useCore((s) => s.status);

  // Object.values gives the devices in insertion order; sort so the list
  // doesn't jump around when one device updates.
  const list = Object.values(devices).sort((a, b) => a.name.localeCompare(b.name));

  return (
    <div className={styles.debug}>
      <p>
        socket: <b>{status}</b> · devices: {list.length} · groups: {Object.keys(groups).length} · adapters:{" "}
        {Object.entries(adapters).map(([name, st]) => `${name}=${st}`).join(", ") || "—"}
      </p>
      <table>
        <tbody>
          {list.map((d) => (
            // `key` lets React match each row to the same device between renders.
            <tr key={d.id} className={d.usable ? undefined : styles.dead}>
              <td>{d.name}</td>
              <td>{d.id}</td>
              <td>{d.state.on === undefined ? "" : d.state.on ? "on" : "off"}</td>
              <td>{d.state.brightness ?? ""}</td>
              <td>{d.usable ? "" : "unusable"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
