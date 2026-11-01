#!/usr/bin/env bash

# Philips Hue API v2 controller

# Find script directory
HUE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables
if [[ -f "$HUE_SCRIPT_DIR/.env" ]]; then
    set -a
    source "$HUE_SCRIPT_DIR/.env"
    set +a
else
    echo "Error: Hue .env file not found."
    return 1 2>/dev/null || exit 1
fi

# Send a command to a single light
_hue_send() {
    local light_id="$1"
    local payload="$2"

    curl -fsSk -X PUT \
        -H "hue-application-key: $HUE_APP_KEY" \
        -H "Content-Type: application/json" \
        -d "$payload" \
        "https://$HUE_BRIDGE_IP/clip/v2/resource/light/$light_id" \
        | jq
}

# Main Hue controller
hue() {
    local target="$1"
    local payload="$2"

    if [[ -z "$HUE_BRIDGE_IP" || -z "$HUE_APP_KEY" ]]; then
        echo "Error: Missing Hue configuration."
        return 1
    fi

    if [[ -z "$target" || -z "$payload" ]]; then
        echo "Usage: hue <rightLight|leftLight|all> '<json>'"
        return 1
    fi

    # Validate JSON before sending
    if ! jq -e . >/dev/null 2>&1 <<< "$payload"; then
        echo "Error: Invalid JSON payload."
        return 1
    fi

    case "$target" in
        rightLight)
            _hue_send "$HUE_DESK_RIGHT_ID" "$payload"
            ;;
        leftLight)
            _hue_send "$HUE_DESK_LEFT_ID" "$payload"
            ;;
        all)
            local result=0
            _hue_send "$HUE_DESK_RIGHT_ID" "$payload" || result=1
            _hue_send "$HUE_DESK_LEFT_ID" "$payload" || result=1
            return "$result"
            ;;
        *)
            echo "Error: Unknown light '$target'"
            echo "Available: desk, bedroom, all"
            return 1
            ;;
    esac
}