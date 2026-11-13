#!/usr/bin/env python3
"""
EKSA E900 Pro Hardware & ALSA/PipeWire Control Layer for Linux (Fedora 45)
Reverse-engineered using REA from:
  - 108B.sys (ev_0919fe2ba56fd08f4c09799923fadda8cdb9579f4a40d4e9f7ff73c433a81519)
  - osConfLib.dll (ev_b2ad95414f4e0b6c528aa4b9c061900713af4deb23d60999fb8bb7a43f98240f)
  - ConfHIDDLL_X64.dll (ev_55af541ec3874bf293a3f1469629d2133ab77c67)
  - CM108B_CMEDIA_STANDARD_2021.Inf

Controls USB VID 0x0D8C / PID 0x0012 (C-Media CM108B / EKSA E900 Pro):
  - numid=3: Mic Playback Switch (Hardware Sidetone/Monitor Mute)
  - numid=4: Mic Playback Volume (0..31, -23dB to +8dB)
  - numid=5: Speaker Playback Switch (Hardware Master Mute)
  - numid=6: Speaker Playback Volume (2ch 0..37, -37dB to 0dB)
  - numid=7: Mic Capture Switch (Hardware Mic Mute)
  - numid=8: Mic Capture Volume (0..35, -12dB to +23dB)
  - numid=9: Auto Gain Control (Hardware Mic Boost / AGC)
"""

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple

USB_VID = "0d8c"
USB_PID = "0012"


@dataclass
class HardwareState:
    connected: bool = False
    card_index: int = -1
    card_id: str = "Pro"
    usb_bus_dev: str = ""
    usb_product: str = "EKSA E900 Pro"
    driver_version: str = "6.0.11.1103 (Linux ALSA/PipeWire)"
    firmware_version: str = "1.00 (CM108B)"
    audio_codec: str = "C-Media CM108B USB Audio"
    # Speaker playback (numid=5, 6: 0..37 -> 0..100%)
    speaker_vol_l: int = 85
    speaker_vol_r: int = 85
    speaker_muted: bool = False
    speaker_db_l: float = -5.0
    speaker_db_r: float = -5.0
    # Mic capture (numid=7, 8: 0..35 -> 0..100%)
    mic_vol: int = 80
    mic_muted: bool = False
    mic_db: float = 16.0
    # Mic monitor / hardware sidetone (numid=3, 4: 0..31 -> 0..100%)
    sidetone_vol: int = 50
    sidetone_muted: bool = True
    sidetone_db: float = -7.0
    # Auto Gain Control / Hardware Boost (numid=9)
    mic_agc: bool = True
    # Sample rate & bit depth
    sample_rate: int = 48000
    bit_depth: int = 16


class EksaHardwareController:
    def __init__(self):
        self.state = HardwareState()
        self.refresh()

    def _run(self, cmd: list, timeout: float = 2.5) -> Tuple[int, str]:
        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
            )
            return res.returncode, res.stdout
        except Exception as e:
            return 1, str(e)

    def detect_device(self) -> bool:
        code, out = self._run(["lsusb", "-d", f"{USB_VID}:{USB_PID}"])
        if code == 0 and out.strip():
            line = out.strip().splitlines()[0]
            self.state.usb_bus_dev = line.split("ID")[0].strip()
            self.state.connected = True
        else:
            self.state.connected = False

        try:
            if os.path.exists("/proc/asound/cards"):
                with open("/proc/asound/cards", "r") as f:
                    cards_txt = f.read()
                m = re.search(r"^\s*(\d+)\s+\[(\w+)\s*\]:.*EKSA E900 Pro", cards_txt, re.M | re.I)
                if not m:
                    m = re.search(r"^\s*(\d+)\s+\[(\w+)\s*\]:.*USB-Audio", cards_txt, re.M | re.I)
                if m:
                    self.state.card_index = int(m.group(1))
                    self.state.card_id = m.group(2)
                    self.state.connected = True
        except Exception:
            pass
        return self.state.connected

    def _card_arg(self) -> str:
        if self.state.card_index >= 0:
            return str(self.state.card_index)
        return self.state.card_id

    def refresh(self) -> HardwareState:
        if not self.detect_device():
            return self.state

        c = self._card_arg()
        code, out = self._run(["amixer", "-c", c, "contents"])
        if code != 0:
            return self.state

        # Parse numid blocks
        blocks = re.split(r"(?=numid=\d+)", out)
        for blk in blocks:
            if "numid=3," in blk:  # Mic Playback Switch
                m = re.search(r": values=(on|off)", blk)
                if m:
                    self.state.sidetone_muted = (m.group(1) == "off")
            elif "numid=4," in blk:  # Mic Playback Volume (0..31, -23..+8 dB)
                m = re.search(r": values=(\d+)", blk)
                if m:
                    raw = int(m.group(1))
                    self.state.sidetone_vol = round(raw * 100.0 / 31.0)
                    self.state.sidetone_db = round(-23.0 + raw * 1.0, 1)
            elif "numid=5," in blk:  # Speaker Playback Switch
                m = re.search(r": values=(on|off)", blk)
                if m:
                    self.state.speaker_muted = (m.group(1) == "off")
            elif "numid=6," in blk:  # Speaker Playback Volume (0..37, -37..0 dB)
                m = re.search(r": values=(\d+),(\d+)", blk)
                if m:
                    raw_l, raw_r = int(m.group(1)), int(m.group(2))
                    self.state.speaker_vol_l = round(raw_l * 100.0 / 37.0)
                    self.state.speaker_vol_r = round(raw_r * 100.0 / 37.0)
                    self.state.speaker_db_l = round(-37.0 + raw_l * 1.0, 1)
                    self.state.speaker_db_r = round(-37.0 + raw_r * 1.0, 1)
            elif "numid=7," in blk:  # Mic Capture Switch
                m = re.search(r": values=(on|off)", blk)
                if m:
                    self.state.mic_muted = (m.group(1) == "off")
            elif "numid=8," in blk:  # Mic Capture Volume (0..35, -12..+23 dB)
                m = re.search(r": values=(\d+)", blk)
                if m:
                    raw = int(m.group(1))
                    self.state.mic_vol = round(raw * 100.0 / 35.0)
                    self.state.mic_db = round(-12.0 + raw * 1.0, 1)
            elif "numid=9," in blk:  # Auto Gain Control
                m = re.search(r": values=(on|off)", blk)
                if m:
                    self.state.mic_agc = (m.group(1) == "on")

        return self.state

    def set_speaker_volume(self, left_pct: int, right_pct: Optional[int] = None) -> None:
        if right_pct is None:
            right_pct = left_pct
        left_pct = max(0, min(100, int(left_pct)))
        right_pct = max(0, min(100, int(right_pct)))
        raw_l = round(left_pct * 37.0 / 100.0)
        raw_r = round(right_pct * 37.0 / 100.0)
        self.state.speaker_vol_l = left_pct
        self.state.speaker_vol_r = right_pct
        self.state.speaker_db_l = round(-37.0 + raw_l, 1)
        self.state.speaker_db_r = round(-37.0 + raw_r, 1)
        if self.state.connected:
            self._run(["amixer", "-c", self._card_arg(), "cset", "numid=6", f"{raw_l},{raw_r}"])

    def set_speaker_mute(self, muted: bool) -> None:
        self.state.speaker_muted = bool(muted)
        if self.state.connected:
            val = "off" if muted else "on"
            self._run(["amixer", "-c", self._card_arg(), "cset", "numid=5", val])

    def set_mic_volume(self, pct: int) -> None:
        pct = max(0, min(100, int(pct)))
        raw = round(pct * 35.0 / 100.0)
        self.state.mic_vol = pct
        self.state.mic_db = round(-12.0 + raw, 1)
        if self.state.connected:
            self._run(["amixer", "-c", self._card_arg(), "cset", "numid=8", str(raw)])

    def set_mic_mute(self, muted: bool) -> None:
        self.state.mic_muted = bool(muted)
        if self.state.connected:
            val = "off" if muted else "on"
            self._run(["amixer", "-c", self._card_arg(), "cset", "numid=7", val])

    def set_sidetone_volume(self, pct: int) -> None:
        pct = max(0, min(100, int(pct)))
        raw = round(pct * 31.0 / 100.0)
        self.state.sidetone_vol = pct
        self.state.sidetone_db = round(-23.0 + raw, 1)
        if self.state.connected:
            self._run(["amixer", "-c", self._card_arg(), "cset", "numid=4", str(raw)])

    def set_sidetone_mute(self, muted: bool) -> None:
        self.state.sidetone_muted = bool(muted)
        if self.state.connected:
            val = "off" if muted else "on"
            self._run(["amixer", "-c", self._card_arg(), "cset", "numid=3", val])

    def set_mic_agc(self, enabled: bool) -> None:
        self.state.mic_agc = bool(enabled)
        if self.state.connected:
            val = "on" if enabled else "off"
            self._run(["amixer", "-c", self._card_arg(), "cset", "numid=9", val])

    def set_sample_rate(self, rate: int, bit_depth: int = 16) -> None:
        rate = int(rate)
        self.state.sample_rate = rate
        self.state.bit_depth = int(bit_depth)
        self._run(["pw-metadata", "-n", "settings", "0", "clock.force-rate", str(rate)])

    def find_pulse_devices(self) -> Tuple[Optional[str], Optional[str]]:
        """Return (physical_sink_name, physical_source_name) for EKSA E900 Pro."""
        phys_sink = None
        phys_src = None
        code, out = self._run(["pactl", "list", "short", "sinks"])
        if code == 0:
            for line in out.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2 and ("EKSA_E900_Pro" in parts[1] or "0d8c" in parts[1]):
                    phys_sink = parts[1]
                    break
        code, out = self._run(["pactl", "list", "short", "sources"])
        if code == 0:
            for line in out.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2 and ("EKSA_E900_Pro" in parts[1] or "0d8c" in parts[1]) and not parts[1].endswith(".monitor"):
                    phys_src = parts[1]
                    break
        return phys_sink, phys_src
