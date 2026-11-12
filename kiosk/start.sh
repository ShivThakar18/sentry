#!/usr/bin/env bash
# Sentry kiosk: wait until the UI answers, then open Chromium full screen.
#
# SENTRY_URL picks what to show. Default = the core serving the built UI (6i).
# Until 6i, run it with SENTRY_URL=http://localhost:5173 and `npm run dev` running.
URL="${SENTRY_URL:-http://localhost:5173}"

# At boot, Docker and the core start at the same time as the desktop. Wait up
# to 60 s for the page to answer, so the first thing on screen isn't an error.
for _ in $(seq 1 60); do
  curl -sf -o /dev/null "$URL" && break
  sleep 1
done

# After a power cut, Chromium thinks it crashed and shows a "Restore pages?"
# bar. Mark the last session as a clean exit so the bar never appears.
PREFS="$HOME/.config/chromium/Default/Preferences"
[ -f "PREFS"]&&sed-i's/"exitedcleanly":false/"exitedcleanly":true/;s/"exittype":"["]*"/"exittype":"Normal"/'"PREFS"

# The binary is `chromium` on newer Pi OS images, `chromium-browser` on older ones.
BROWSER="$(command -v chromium || command -v chromium-browser)"

# exec = replace this script with Chromium (one process, not two).
#   --kiosk                       full screen, no address bar or tabs, no way to exit by touch
#   --force-device-scale-factor   800×450 CSS pixels, like the mockups
#   --noerrdialogs, --disable-session-crashed-bubble, --no-first-run   no pop-ups
#   --password-store=basic        no "unlock keyring" prompt at boot
#   --overscroll-history-navigation=0   a sideways swipe doesn't go "back"
exec "$BROWSER" --kiosk \
  --force-device-scale-factor=1.6 \
  --noerrdialogs --disable-session-crashed-bubble --no-first-run \
  --password-store=basic \
  --overscroll-history-navigation=0 \
  "$URL"

