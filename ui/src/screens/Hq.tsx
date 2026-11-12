/**
 * <Hq>: placeholder for 6c. Three hard-coded tiles (on / off / disabled) so
 * you can compare the look with mockups/01-hq.png. In 6f this becomes the
 * real HQ, fed from the store.
 */
import { useState } from "react";
import { IconBulb, IconBulbOff, IconOutlet } from "@tabler/icons-react";
import { Tile } from "../components/Tile";
import styles from "./Hq.module.css";

export function Hq() {
  // Local state only, to see the tile switch between lit and dark.
  // In 6g a tap sends a real command instead.
  const [lampOn, setLampOn] = useState(true);
  const [heaterOn, setHeaterOn] = useState(false);

  return (
    <div className={styles.tiles}>
      <Tile
        icon={IconBulb}
        name="Living Room Lamp"
        status={lampOn ? "On · 80%" : "Off"}
        on={lampOn}
        onTap={() => setLampOn(!lampOn)}
      />
      <Tile
        icon={IconOutlet}
        name="Office Heater"
        status={heaterOn ? "On" : "Off"}
        on={heaterOn}
        onTap={() => setHeaterOn(!heaterOn)}
      />
      <Tile icon={IconBulbOff} name="Kitchen Hue Strip" status="Unavailable" on disabled />
    </div>
  );
}
