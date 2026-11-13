/**
 * main.tsx: the entry point. Order of the CSS imports matters:
 * font first, then tokens (the variables), then index.css (which uses them).
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

// Krona One from npm (@fontsource). Vite copies the .woff2 files into the
// build, so the kiosk needs no internet for its font.
import "@fontsource/krona-one";
import "./theme/tokens.css";
import "./index.css";
import App from "./App";
import { startCoreConnection } from "./store/store";

// Open the WebSocket to the core once, before the first render (see store.ts
// for why this isn't in a useEffect).
startCoreConnection();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* BrowserRouter keeps the URL in sync with the screen: /fleet, /orders/… */}
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
