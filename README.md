# EKSA Audio Center for Linux (Fedora 45)

Native Linux control software and DSP suite for the **EKSA E900 Pro Gaming Headset** (C-Media CM108B USB Audio, VID: `0d8c:0012`).

Built using **GTK 4**, **Libadwaita**, **ALSA**, and **PipeWire**.

---

## Features

### 1. Hardware Control (Direct CM108B ALSA Driver Interface)
- **Master Headphone Volume**: 0 - 100% fine slider control.
- **Hardware Mute Switch**: Instant hardware mute/unmute.
- **Microphone Capture Gain**: 0 - 100% slider control.
- **Microphone Hardware Mute**: Direct microphone mute toggle.
- **Zero-Latency Sidetone (Mic Monitoring)**: 
  Hear your own voice directly through the headset with zero delay (processed on-chip by CM108B). Includes monitoring volume control.
- **Hardware Auto Gain Control (AGC)**: On-chip dynamic microphone level normalization.

### 2. 10-Band Graphic Equalizer
- **Exact Frequency Bands**: `30Hz, 60Hz, 120Hz, 250Hz, 500Hz, 1kHz, 2kHz, 4kHz, 8kHz, 16kHz`.
- **Gain Range**: -20 dB to +20 dB.
- **12 Factory Presets**: Default (Flat), Dance, Bass Boost, Treble Boost, Live, Rock, SoftRock, Jazz, Metal, Rap, Classic, Opera (Vocal).
- **Custom Profiles**: Ability to adjust any band and save custom profiles.

### 3. 7.1 Virtual Surround Sound (Virtual Speaker Shifter)
- Multi-channel 8-speaker binaural downmix (`FL, FR, FC, LFE, SL, SR, RL, RR`).
- Individual dB trim controls for every speaker channel (-12 dB to +12 dB).
- Spatial expansion and rotation centering.

### 4. VoClear Environmental Noise Cancellation (ENC)
- AI/WebRTC Acoustic Echo Cancellation (AEC) and Noise Suppression (ENC).
- Filters out keyboard clicks, background chatter, and pc fan noise for crystal-clear voice communication.

### 5. LivingEM Environment Effects (Reverb)
- Room simulation: Concert Hall, Arena, Bathroom, Living Room, Cave, Auditorium, etc.
- Room Size: Small, Medium, Large.

---

## How to Launch

### Graphical Application (GUI)
- Launch **EKSA Audio Center** from your GNOME Applications Menu, or
- Run in terminal:
  ```bash
  eksa-audio-center
  ```

### Command Line Interface (CLI)
You can inspect and control all headset settings from terminal or keyboard shortcuts:

```bash
# Check status
eksa-cli status

# Headphone volume
eksa-cli volume 80
eksa-cli mute toggle

# Microphone volume & mute
eksa-cli mic-volume 100
eksa-cli mic-mute toggle

# Hardware Sidetone (Mic monitoring)
eksa-cli sidetone on
eksa-cli sidetone 60
eksa-cli sidetone off

# Hardware AGC
eksa-cli agc on

# Equalizer
eksa-cli eq Rock
eksa-cli eq Bass
eksa-cli eq Default
eksa-cli list-presets

# 7.1 Surround & ENC
eksa-cli surround on
eksa-cli enc on
```

