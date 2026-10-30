
#!/usr/bin/env bash

# Philips Hue Event Stream Logger

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
else
    echo "Error: .env file not found."
    exit 1
fi

# Validate configuration
if [[ -z "$HUE_BRIDGE_IP" || -z "$HUE_APP_KEY" ]]; then
    echo "Error: Missing Hue Bridge IP or application key."
    exit 1
fi

URL="https://$HUE_BRIDGE_IP/eventstream/clip/v2"

# Raw event stream
raw_logs() {
    echo "Starting RAW Hue event stream..."
    echo "Press Ctrl+C to stop."
    echo

    curl -skN --fail-with-body \
        -H "hue-application-key: $HUE_APP_KEY" \
        -H "Accept: text/event-stream" \
        "$URL"
}

# Formatted JSON event stream
formatted_logs() {
    if ! command -v jq &>/dev/null; then
        echo "Error: jq is not installed."
        echo "Install it with: sudo apt install jq"
        return 1
    fi

    echo "Starting FORMATTED Hue event stream..."
    echo "Press Ctrl+C to stop."
    echo

    curl -skN --fail-with-body \
        -H "hue-application-key: $HUE_APP_KEY" \
        -H "Accept: text/event-stream" \
        "$URL" \
        | grep --line-buffered '^data:' \
        | sed -u 's/^data: //' \
        | jq --unbuffered .
}

# Menu
echo "================================"
echo "     Philips Hue Log Viewer"
echo "================================"
echo "1) Raw event stream"
echo "2) Formatted JSON event stream"
echo "3) Exit"
echo

read -rp "Choose an option [1-3]: " choice

case "$choice" in
    1)
        raw_logs
        ;;
    2)
        formatted_logs
        ;;
    3)
        echo "Exiting."
        exit 0
        ;;
    *)
        echo "Invalid option."
        exit 1
        ;;
esac
