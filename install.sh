#!/usr/bin/env bash
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_SHARE="$HOME/.local/share/eksa-audio-center"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"

echo "[1/4] Installing EKSA Audio Center files & original FaceLift skin assets to $APP_SHARE..."
mkdir -p "$APP_SHARE" "$BIN_DIR" "$DESKTOP_DIR"
cp -f "$SRC_DIR/eksa_hardware.py" "$SRC_DIR/eksa_dsp.py" "$SRC_DIR/eksa_gui.py" "$SRC_DIR/eksa_cli.py" "$APP_SHARE/"
rm -rf "$APP_SHARE/assets"
cp -r "$SRC_DIR/assets" "$APP_SHARE/assets"
chmod +x "$APP_SHARE/eksa_gui.py" "$APP_SHARE/eksa_cli.py"

# Remove any stale static PipeWire filter config from earlier prototype
rm -f "$HOME/.config/pipewire/pipewire.conf.d/99-eksa-e900pro.conf"

echo "[2/4] Creating launcher scripts in $BIN_DIR..."
rm -f "$BIN_DIR/eksa-audio-center" "$BIN_DIR/eksa-cli"
cat > "$BIN_DIR/eksa-audio-center" << 'EOF'
#!/usr/bin/env bash
exec /usr/bin/python3 "$HOME/.local/share/eksa-audio-center/eksa_gui.py" "$@"
EOF
chmod +x "$BIN_DIR/eksa-audio-center"

cat > "$BIN_DIR/eksa-cli" << 'EOF'
#!/usr/bin/env bash
exec /usr/bin/python3 "$HOME/.local/share/eksa-audio-center/eksa_cli.py" "$@"
EOF
chmod +x "$BIN_DIR/eksa-cli"

echo "[3/4] Creating desktop entry in $DESKTOP_DIR/eksa-audio-center.desktop..."
cat > "$DESKTOP_DIR/eksa-audio-center.desktop" << EOF
[Desktop Entry]
Name=EKSA Audio Center
Comment=EKSA E900 Pro 7.1 Surround & Xear DSP Control Center
Exec=$BIN_DIR/eksa-audio-center
Icon=$APP_SHARE/assets/FaceLift/Main/JackHP_se.png
Terminal=false
Type=Application
Categories=AudioVideo;Audio;Mixer;Settings;
Keywords=EKSA;E900;Headset;Surround;7.1;Equalizer;Xear;
StartupWMClass=net.eksa.AudioCenter
EOF

echo "[4/4] Installation complete! Run 'eksa-audio-center' or 'eksa-cli status'."
