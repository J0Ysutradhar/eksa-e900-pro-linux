#!/usr/bin/env bash
set -euo pipefail

echo "[1/4] Stopping any running EKSA Audio Center instances..."
pkill -f "eksa_gui.py" 2>/dev/null || true
pkill -f "eksa_cli.py" 2>/dev/null || true

echo "[2/4] Restoring physical audio routing & unloading virtual PipeWire/Pulse sinks..."
# Find physical sink
PHYS_SINK=$(pactl list short sinks 2>/dev/null | awk -F'\t' '/EKSA_E900_Pro|0d8c/ {print $2; exit}')
if [ -n "$PHYS_SINK" ]; then
    pactl set-default-sink "$PHYS_SINK" 2>/dev/null || true
fi

# Find physical source
PHYS_SRC=$(pactl list short sources 2>/dev/null | awk -F'\t' '/EKSA_E900_Pro|0d8c/ && !/\.monitor/ {print $2; exit}')
if [ -n "$PHYS_SRC" ]; then
    pactl set-default-source "$PHYS_SRC" 2>/dev/null || true
fi

# Move any active streams off virtual sinks before removing them
pactl list short sink-inputs 2>/dev/null | while read -r line; do
    idx=$(echo "$line" | cut -f1)
    if [ -n "$PHYS_SINK" ] && [ -n "$idx" ]; then
        pactl move-sink-input "$idx" "$PHYS_SINK" 2>/dev/null || true
    fi
done

# Unload virtual modules
pactl unload-module module-null-sink 2>/dev/null || true

echo "[3/4] Removing installed binaries, desktop launchers, and application files..."
rm -f "$HOME/.local/bin/eksa-audio-center"
rm -f "$HOME/.local/bin/eksa-cli"
rm -f "$HOME/.local/share/applications/eksa-audio-center.desktop"
rm -rf "$HOME/.local/share/eksa-audio-center"
rm -f "$HOME/.config/pipewire/pipewire.conf.d/99-eksa-e900pro.conf"

echo "[4/4] Removing user configuration files..."
rm -rf "$HOME/.config/eksa-audio-center"

# Update desktop database if available
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi

echo "EKSA Audio Center has been completely uninstalled from your system."

