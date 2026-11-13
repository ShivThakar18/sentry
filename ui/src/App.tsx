/**
 * App.tsx: the shell (nav on top of every screen) and the routes.
 *
 * Routes are NESTED: the outer <Route element={<Layout />}> has no path, and
 * renders the nav plus an <Outlet />. Whichever child route matches is drawn
 * where the <Outlet /> is. So the nav is written once and never re-mounts when
 * you switch tabs.
 */
import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { ConnectionBadge } from "./components/ConnectionBadge";
import { NavBar } from "./components/NavBar";
import { Debug } from "./screens/Debug";
import { Hq } from "./screens/Hq";
import { Placeholder } from "./screens/Placeholder";
import styles from "./App.module.css";

function Layout() {
  return (
    <div className={styles.screen}>
      {/* The screen comes first and the header second, so the header is drawn
          on top. HQ's tiles reach up into the nav row, so the screen fills the
          whole page and doesn't start below the nav. */}
      <main className={styles.main}>
        <Outlet />
      </main>
      <header className={styles.header}>
        <NavBar />
      </header>
      {/* Floats bottom-centre over every screen; only visible while the
          connection to the core is down (6e). */}
      <div className={styles.status}>
        <ConnectionBadge />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Hq />} />
        <Route path="fleet" element={<Placeholder title="Fleet" />} />
        <Route path="fleet/:id" element={<Placeholder title="Fleet / Detail" />} />
        <Route path="protocols" element={<Placeholder title="Protocols" />} />
        <Route path="protocols/:id" element={<Placeholder title="Protocols / Edit" />} />
        <Route path="orders" element={<Placeholder title="Standing Orders" />} />
        <Route path="orders/:id" element={<Placeholder title="Standing Orders / Edit" />} />
        <Route path="debug" element={<Debug />} />
        {/* Anything else (a typo, an old link) → back to HQ. `replace` so
            the bad URL doesn't stay in history. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
