#!/usr/bin/env python3
"""
EKSA E900 Pro Real-Time Linux DSP Engine (GStreamer + PipeWire/PulseAudio)
Reverse-engineered using REA from:
  - CMEffectAPO_108B.dll (ev_da7493df0a3c9d9f4761d3a6ab17711330fca2c9c7e7992249323550f28357c7)
  - osConfLib.dll (ev_b2ad95414f4e0b6c528aa4b9c061900713af4deb23d60999fb8bb7a43f98240f)
  - XearAudioCenter_x64.exe (ev_0f87693fab860dee78283f701bc7e65e78e860db58e571dd1b1ab6208e7d6a26)

Provides:
  1. Zero-latency real-time GStreamer Playback DSP pipeline routed from a dedicated
     virtual PipeWire/PulseAudio sink ('eksa_e900pro_dsp') to the physical EKSA E900 Pro
     USB headset ('alsa_output.usb-C-Media_Electronics_Inc._EKSA_E900_Pro-00.analog-stereo').
  2. Zero-latency real-time GStreamer Microphone DSP pipeline routed from the physical
     EKSA E900 Pro microphone to a virtual microphone sink ('eksa_e900pro_mic') + optional
     live headphone preview so the user can immediately hear Magic Voice & Mic Echo.
  3. Interactive 7.1 Surround WAV Test Player using the 8 original C-Media/EKSA WAV files
     (L-Front.wav, R-Front.wav, Center.wav, Subwoofer.wav, L-Surround.wav, R-Surround.wav,
      L-BackSurround.wav, R-BackSurround.wav) spatialized by the 7.1 Virtual Speaker Shifter.
"""

import json
import math
import os
import subprocess
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import gi
gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst

Gst.init(None)

CONFIG_DIR = os.path.expanduser("~/.config/eksa-audio-center")
STATE_FILE = os.path.join(CONFIG_DIR, "dsp_state.json")
EQ_PRESETS_FILE = os.path.join(CONFIG_DIR, "eq_presets.json")
PROFILES_FILE = os.path.join(CONFIG_DIR, "user_profiles.json")

# 10-Band Equalizer Frequencies (Hz) from apoSpeakerEQ.cml
EQ_FREQS = [30, 60, 120, 250, 500, 1000, 2000, 4000, 8000, 16000]
EQ_LABELS = ["30", "60", "120", "250", "500", "1K", "2K", "4K", "8K", "16K"]

# Built-in 12 EQ Presets from apoSpeakerEQ.cml (dB values in [-20, +20])
BUILTIN_EQ_PRESETS: Dict[str, List[float]] = {
    "Default":  [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "Dance":    [8.0, 6.0, 2.0, 0.0, 0.0, -4.0, -6.0, -6.0, 0.0, 0.0],
    "Bass":     [9.0, 7.0, 5.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "Treble":   [0.0, 0.0, 0.0, 0.0, 0.0, 2.0, 5.0, 8.0, 9.0, 9.0],
    "Live":     [-4.0, 0.0, 3.0, 4.0, 5.0, 5.0, 3.0, 2.0, 2.0, 1.0],
    "Rock":     [6.0, 4.0, -4.0, -6.0, -2.0, 3.0, 6.0, 8.0, 8.0, 8.0],
    "SoftRock": [3.0, 3.0, 1.0, 0.0, -3.0, -4.0, -2.0, 0.0, 2.0, 6.0],
    "Jazz":     [5.0, 3.0, 1.0, 2.0, -2.0, -2.0, 0.0, 2.0, 4.0, 5.0],
    "Metal":    [8.0, 6.0, 0.0, -5.0, -4.0, 0.0, 5.0, 8.0, 9.0, 7.0],
    "Rap":      [7.0, 6.0, 4.0, 1.0, -2.0, -1.0, 2.0, 4.0, 6.0, 7.0],
    "Classic":  [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -5.0, -5.0, -5.0, -7.0],
    "Opera":    [-2.0, -2.0, -1.0, 3.0, 6.0, 6.0, 4.0, 1.0, 0.0, -2.0],
}

# 27 Environment Effects (EAX / I3DL2 Reverb presets from apoSpeakerEM.cml & CMEffectAPO_108B.dll)
# Each tuple: (room_size 0..1, damping 0..1, width 0..1, wet_level 0..1, echo_delay_ms, echo_intensity, lpf_hz)
ENVIRONMENT_PRESETS: Dict[str, Tuple[float, float, float, float, int, float, int]] = {
    "Generic":          (0.50, 0.50, 1.0, 0.30, 20,  0.10, 20000),
    "Padded Cell":      (0.15, 0.95, 0.4, 0.25, 8,   0.05, 8000),
    "Room":             (0.35, 0.65, 0.8, 0.28, 15,  0.10, 18000),
    "Bathroom":         (0.45, 0.15, 0.9, 0.60, 18,  0.35, 14000),
    "Living Room":      (0.40, 0.80, 0.8, 0.22, 14,  0.08, 16000),
    "Stone Room":       (0.60, 0.25, 1.0, 0.48, 30,  0.25, 18000),
    "Auditorium":       (0.78, 0.45, 1.0, 0.50, 55,  0.28, 18000),
    "Concert Hall":     (0.85, 0.40, 1.0, 0.55, 65,  0.32, 19000),
    "Cave":             (0.90, 0.15, 1.0, 0.68, 95,  0.45, 12000),
    "Arena":            (0.92, 0.35, 1.0, 0.62, 110, 0.40, 17000),
    "Hangar":           (0.95, 0.20, 1.0, 0.70, 130, 0.48, 16000),
    "Carpeted Hallway": (0.30, 0.90, 0.6, 0.20, 12,  0.06, 12000),
    "Hallway":          (0.48, 0.40, 0.7, 0.42, 28,  0.22, 16000),
    "Stone Corridor":   (0.65, 0.22, 0.8, 0.52, 42,  0.30, 17000),
    "Alley":            (0.55, 0.50, 0.9, 0.38, 60,  0.32, 15000),
    "Forest":           (0.70, 0.75, 1.0, 0.35, 85,  0.25, 14000),
    "City":             (0.68, 0.55, 1.0, 0.40, 75,  0.28, 15000),
    "Mountains":        (0.96, 0.45, 1.0, 0.58, 180, 0.50, 14000),
    "Quarry":           (0.88, 0.30, 1.0, 0.55, 140, 0.45, 16000),
    "Plain":            (0.80, 0.70, 1.0, 0.28, 120, 0.20, 15000),
    "Parking Lot":      (0.72, 0.30, 1.0, 0.48, 50,  0.30, 17000),
    "Sewer Pipe":       (0.62, 0.10, 0.6, 0.72, 35,  0.52, 3500),
    "Under Water":      (0.75, 0.85, 1.0, 0.78, 45,  0.40, 900),
    "Drugged":          (0.88, 0.15, 1.0, 0.75, 150, 0.55, 6000),
    "Dizzy":            (0.92, 0.20, 1.0, 0.72, 165, 0.52, 8000),
    "Psychotic":        (0.96, 0.10, 1.0, 0.80, 190, 0.58, 11000),
    "Karaoke":          (0.76, 0.35, 1.0, 0.55, 70,  0.36, 18000),
}

ENVIRONMENT_LIST = list(ENVIRONMENT_PRESETS.keys())

# Default 7.1 Virtual Speaker positions in polar coords relative to Head at center (0,0)
# Angle: 0 deg = straight ahead (Center), +deg = clockwise (Right), -deg = counter-clockwise (Left)
# Dist: normalized radius (0.20 .. 0.95), default = 0.68
DEFAULT_VSS_SPEAKERS = {
    "C":  {"angle": 0.0,    "dist": 0.68, "db": 0.0, "wav": "Center.wav",         "label": "Center"},
    "W":  {"angle": 12.0,   "dist": 0.45, "db": 0.0, "wav": "Subwoofer.wav",      "label": "Woofer"},
    "L":  {"angle": -35.0,  "dist": 0.68, "db": 0.0, "wav": "L-Front.wav",        "label": "Front Left"},
    "R":  {"angle": 35.0,   "dist": 0.68, "db": 0.0, "wav": "R-Front.wav",        "label": "Front Right"},
    "Ls": {"angle": -95.0,  "dist": 0.68, "db": 0.0, "wav": "L-Surround.wav",     "label": "Side Left"},
    "Rs": {"angle": 95.0,   "dist": 0.68, "db": 0.0, "wav": "R-Surround.wav",     "label": "Side Right"},
    "Lb": {"angle": -142.0, "dist": 0.68, "db": 0.0, "wav": "L-BackSurround.wav", "label": "Back Left"},
    "Rb": {"angle": 142.0,  "dist": 0.68, "db": 0.0, "wav": "R-BackSurround.wav", "label": "Back Right"},
}


class EksaDspEngine:
    VIRTUAL_SINK_NAME = "eksa_e900pro_dsp"
    VIRTUAL_MIC_NAME = "eksa_e900pro_mic"

    def __init__(self, hw_controller, assets_dir: str):
        self.hw = hw_controller
        self.assets_dir = assets_dir
        self.sound_dir = os.path.join(assets_dir, "sound")
        os.makedirs(CONFIG_DIR, exist_ok=True)

        # Live level meter values (0.0 .. 1.0)
        self.peak_l: float = 0.0
        self.peak_r: float = 0.0
        self.mic_peak: float = 0.0

        # Default full state matching Windows XearAudioCenter_x64.exe
        self.state = self._default_state()
        self.custom_eq_presets: Dict[str, List[float]] = {}
        self.user_profiles: Dict[str, dict] = {}
        self.load_state()

        # GStreamer pipelines
        self.play_pipe: Optional[Gst.Pipeline] = None
        self.mic_pipe: Optional[Gst.Pipeline] = None
        self.test_pipe: Optional[Gst.Pipeline] = None
        self._sink_module_id: Optional[int] = None
        self._mic_module_id: Optional[int] = None
        self._phys_sink: Optional[str] = None
        self._phys_src: Optional[str] = None
        self._auto_test_running: bool = False
        self._play_has_keyshift: bool = False
        self._mic_has_magic_voice: bool = False
        self._last_vss_delay_ns: int = 15000000

    def _default_state(self) -> dict:
        import copy
        return {
            "active_profile": "Manual",
            "speaker_channels": 8,  # 2, 4, 6 (5.1), 8 (7.1)
            "woofer_center_swap": False,
            "channel_vols": {"LF": 100, "RF": 100, "LB": 100, "RB": 100, "C": 100, "W": 100, "LS": 100, "RS": 100},
            "channel_locks": {"Front": True, "Rear": True, "CW": True, "Side": True},
            "hp_gain_mode": 0,  # 0=Normal (0dB), 1=High (+6dB), 2=Extra High (+12dB)
            # 10-Band EQ
            "eq_enabled": True,
            "eq_preset": "Default",
            "eq_bands": [0.0] * 10,
            # Environment Effects (EM)
            "em_enabled": False,
            "em_environment": "Concert Hall",
            "em_room_size": 1,  # 0=Small, 1=Medium, 2=Large
            # 7.1 Virtual Speaker Shifter (VSS)
            "vss_enabled": True,
            "vss_mode": "manual_shift",  # clockwise, counter_clockwise, manual_rotate, manual_shift
            "vss_head": [0.0, 0.0],
            "vss_speakers": copy.deepcopy(DEFAULT_VSS_SPEAKERS),
            # Xear Surround Headphone / Speakers / Max / GX
            "surround_hp_enabled": True,
            "surround_hp_mode": 0,  # 0=Music/Gaming, 1=Movie
            "surround_hp_room": 1,  # 2=Small, 1=Medium, 0=Large
            "surround_spk_enabled": False,
            "surround_spk_mode": 0,
            "surround_spk_expansion": 2,
            "surround_spk_angle": 15,
            "surround_max_enabled": False,
            "gx_enabled": False,
            # Xear SingFX (Speaker Karaoke)
            "keyshift_enabled": False,
            "keyshift_semitones": 0,
            "vocal_cancel_enabled": False,
            "vocal_cancel_level": 50,
            # Xear Dynamic Bass & Flex Bass II
            "dynamic_bass_enabled": False,
            "dynamic_bass_level": 5.0,
            "dynamic_bass_cutoff": 150,
            "flex_bass_enabled": False,
            "flex_bass_cutoff": 120,
            "flex_bass_level": 4.0,
            "flex_bass_sizes": {"LR": 0, "LbRb": 0, "C": 0, "LsRs": 0},
            # Xear Smart Volume (SVN)
            "smart_vol_enabled": False,
            "smart_vol_level": 75,
            "smart_vol_mode": 0,  # 0=Music, 1=Speech
            # Xear Voice Clarity
            "voice_clarity_enabled": False,
            "voice_clarity_level": 4,
            "voice_clarity_supp": 10,
            # Xear Audio Brilliant
            "audio_brilliant_enabled": False,
            "audio_brilliant_level": 4,
            # Hardware EQ (Treble/Bass)
            "hweq_treble": 0.0,
            "hweq_bass": 0.0,
            # Microphone Effects
            "mic_echo_enabled": False,
            "mic_echo_level": 0.0,
            "magic_voice_enabled": False,
            "magic_voice_preset": 0,  # 0=Monster, 1=Cartoon, 2=Male, 3=Female
            "mic_enc_enabled": False,
            "mic_nr_enabled": False,
            "mic_nr_level": 14,
            "mic_aec_enabled": False,
            "mic_bf_enabled": False,
            "mic_boost_db": 0,
            "mic_listen_preview": False,
            # RGB / LED Light
            "led_enabled": True,
            "led_mode": "Steady",
            "led_color_idx": 0,
            "led_rgb": [180, 40, 255],
            "led_brightness": 100,
            # UI settings
            "ui_opacity": 9,
            "show_tray": True,
        }

    def load_state(self) -> None:
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    saved = json.load(f)
                for k, v in saved.items():
                    if k in self.state:
                        self.state[k] = v
            if os.path.exists(EQ_PRESETS_FILE):
                with open(EQ_PRESETS_FILE, "r") as f:
                    self.custom_eq_presets = json.load(f)
            if os.path.exists(PROFILES_FILE):
                with open(PROFILES_FILE, "r") as f:
                    self.user_profiles = json.load(f)
        except Exception:
            pass

    def save_state(self) -> None:
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(self.state, f, indent=2)
            with open(EQ_PRESETS_FILE, "w") as f:
                json.dump(self.custom_eq_presets, f, indent=2)
            with open(PROFILES_FILE, "w") as f:
                json.dump(self.user_profiles, f, indent=2)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # PipeWire / PulseAudio Virtual Sink & Source Setup
    # -------------------------------------------------------------------------
    def _run_cmd(self, cmd: list) -> Tuple[int, str]:
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=3.0)
            return r.returncode, r.stdout.strip()
        except Exception as e:
            return 1, str(e)

    def setup_virtual_audio_routing(self) -> bool:
        """
        Create virtual sink 'eksa_e900pro_dsp' and route all desktop audio through
        our live GStreamer DSP pipeline into the physical EKSA E900 Pro headset.
        Also remove any stale invalid static PipeWire config from earlier prototypes.
        """
        stale_conf = os.path.expanduser("~/.config/pipewire/pipewire.conf.d/99-eksa-e900pro.conf")
        if os.path.exists(stale_conf):
            try:
                os.remove(stale_conf)
            except Exception:
                pass

        phys_sink, phys_src = self.hw.find_pulse_devices()
        self._phys_sink = phys_sink
        self._phys_src = phys_src

        # If an older eksa_e900pro_dsp exists with node.driver=true, unload it so we can
        # recreate it with node.driver=false (slaved to the physical EKSA USB clock!)
        code, info_out = self._run_cmd(["pw-cli", "info", self.VIRTUAL_SINK_NAME])
        if code == 0 and 'node.driver = "true"' in info_out:
            self._run_cmd(["pactl", "unload-module", "module-null-sink"])

        # Check if virtual sink already exists
        code, sinks_out = self._run_cmd(["pactl", "list", "short", "sinks"])
        if code == 0 and self.VIRTUAL_SINK_NAME not in sinks_out:
            c, mod_id = self._run_cmd([
                "pactl", "load-module", "module-null-sink",
                f"sink_name={self.VIRTUAL_SINK_NAME}",
                "sink_properties=device.description=EKSA_E900_Pro_7.1_Surround_DSP node.driver=false",
                "rate=48000", "channels=2"
            ])
            if c == 0 and mod_id.isdigit():
                self._sink_module_id = int(mod_id)

        if code == 0 and self.VIRTUAL_MIC_NAME not in sinks_out:
            c, mod_id = self._run_cmd([
                "pactl", "load-module", "module-null-sink",
                f"sink_name={self.VIRTUAL_MIC_NAME}",
                "sink_properties=device.description=EKSA_E900_Pro_MagicVoice_Mic node.driver=false",
                "rate=48000", "channels=1"
            ])
            if c == 0 and mod_id.isdigit():
                self._mic_module_id = int(mod_id)

        # Set virtual sink as default output so apps play into the DSP engine
        self._run_cmd(["pactl", "set-default-sink", self.VIRTUAL_SINK_NAME])
        self._run_cmd(["pactl", "set-default-source", f"{self.VIRTUAL_MIC_NAME}.monitor"])

        return True

    def route_desktop_streams_to_dsp(self) -> None:
        """Ensure desktop audio streams (Firefox, Brave, games, etc.) are routed into eksa_e900pro_dsp."""
        code, sinks_out = self._run_cmd(["pactl", "list", "short", "sinks"])
        phys_sink_id = None
        if code == 0 and self._phys_sink:
            for line in sinks_out.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2 and parts[1] == self._phys_sink:
                    phys_sink_id = parts[0]
                    break
        if not phys_sink_id:
            return
        code, inputs_out = self._run_cmd(["pactl", "list", "short", "sink-inputs"])
        if code == 0:
            for line in inputs_out.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2 and parts[0].isdigit() and parts[1] == phys_sink_id:
                    self._run_cmd(["pactl", "move-sink-input", parts[0], self.VIRTUAL_SINK_NAME])

    def start_live_pipelines(self) -> None:
        self.setup_virtual_audio_routing()
        self._start_playback_pipeline()
        self._start_mic_pipeline()
        self.apply_live()
        self.route_desktop_streams_to_dsp()

    def _start_playback_pipeline(self) -> None:
        if self.play_pipe is not None:
            self.play_pipe.set_state(Gst.State.NULL)
            self.play_pipe = None

        phys_sink, _ = self.hw.find_pulse_devices()
        self._phys_sink = phys_sink

        use_keyshift = bool(self.state.get("keyshift_enabled", False))
        self._play_has_keyshift = use_keyshift
        keyshift_stage = "pitch name=keyshift pitch=1.0 ! audioconvert ! " if use_keyshift else ""

        if phys_sink:
            out_sink_stage = (
                f'pipewiresink name=hw_out target-object="{phys_sink}" '
                f'stream-properties="props,media.name=EKSA_DSP_Hardware_Out,node.dont-reconnect=true" sync=false'
            )
        else:
            out_sink_stage = 'pulsesink name=hw_out buffer-time=200000 latency-time=20000 sync=false'

        self._last_vss_delay_ns = 15000000
        pipe_str = (
            f'pulsesrc device="{self.VIRTUAL_SINK_NAME}.monitor" buffer-time=400000 latency-time=20000 ! '
            f'audio/x-raw,format=F32LE,channels=2,rate=48000 ! '
            f'queue max-size-buffers=50 max-size-bytes=0 max-size-time=0 ! '
            f'audioconvert ! '
            f'volume name=pre_vol volume=1.0 ! '
            f'audiokaraoke name=karaoke level=0.0 mono-level=0.0 ! '
            f'{keyshift_stage}'
            f'equalizer-10bands name=eq10 ! '
            f'equalizer-nbands name=xear_tone num-bands=4 ! '
            f'audiodynamic name=smartvol characteristics=soft-knee mode=compressor threshold=1.0 ratio=1.0 ! '
            f'audiopanorama name=vss_pan method=simple panorama=0.0 ! '
            f'audioecho name=vss_echo max-delay=500000000 delay=15000000 intensity=0.0 feedback=0.0 ! '
            f'freeverb name=reverb room-size=0.5 damping=0.5 width=1.0 level=0.0 ! '
            f'audiocheblimit name=env_lpf mode=low-pass cutoff=20000 poles=4 ! '
            f'volume name=post_vol volume=1.0 ! '
            f'level name=out_level interval=50000000 post-messages=true ! '
            f'audioconvert ! '
            f'queue max-size-buffers=50 max-size-bytes=0 max-size-time=0 ! '
            f'{out_sink_stage}'
        )
        try:
            self.play_pipe = Gst.parse_launch(pipe_str)
            bus = self.play_pipe.get_bus()
            bus.add_signal_watch()
            bus.connect("message::element", self._on_gst_level_message)
            self.play_pipe.set_state(Gst.State.PLAYING)
        except Exception as e:
            print("Playback DSP pipeline warning:", e)
            self.play_pipe = None

    def _start_mic_pipeline(self) -> None:
        if self.mic_pipe is not None:
            self.mic_pipe.set_state(Gst.State.NULL)
            self.mic_pipe = None

        phys_sink, phys_src = self.hw.find_pulse_devices()
        self._phys_src = phys_src
        src_prop = f'device="{phys_src}"' if phys_src else ""

        use_mv = bool(self.state.get("magic_voice_enabled", False))
        self._mic_has_magic_voice = use_mv
        mv_stage = "pitch name=magic_voice pitch=1.0 ! audioconvert ! " if use_mv else ""

        if self.state.get("mic_listen_preview", False) and phys_sink:
            target_obj = phys_sink
        else:
            target_obj = self.VIRTUAL_MIC_NAME

        pipe_str = (
            f'pulsesrc {src_prop} buffer-time=400000 latency-time=20000 ! '
            f'audio/x-raw,format=F32LE,channels=1,rate=48000 ! '
            f'queue max-size-buffers=50 max-size-bytes=0 max-size-time=0 ! '
            f'audioconvert ! '
            f'audiocheblimit name=enc_hpf mode=high-pass cutoff=40 poles=4 ! '
            f'audiodynamic name=enc_gate characteristics=soft-knee mode=expander threshold=0.0 ratio=1.0 ! '
            f'volume name=mic_boost volume=1.0 ! '
            f'{mv_stage}'
            f'audioecho name=mic_echo max-delay=500000000 delay=140000000 intensity=0.0 feedback=0.0 ! '
            f'level name=mic_level interval=50000000 post-messages=true ! '
            f'audioconvert ! '
            f'queue max-size-buffers=50 max-size-bytes=0 max-size-time=0 ! '
            f'pipewiresink name=mic_out target-object="{target_obj}" '
            f'stream-properties="props,media.name=EKSA_DSP_Mic_Out,node.dont-reconnect=true" sync=false'
        )
        try:
            self.mic_pipe = Gst.parse_launch(pipe_str)
            bus = self.mic_pipe.get_bus()
            bus.add_signal_watch()
            bus.connect("message::element", self._on_gst_level_message)
            self.mic_pipe.set_state(Gst.State.PLAYING)
        except Exception as e:
            print("Mic DSP pipeline warning:", e)
            self.mic_pipe = None

    def _on_gst_level_message(self, bus, msg) -> None:
        s = msg.get_structure()
        if not s or s.get_name() != "level":
            return
        src_name = msg.src.get_name()
        rms = s.get_value("rms")
        if not rms:
            return
        if src_name == "out_level":
            db_l = rms[0] if len(rms) > 0 else -60.0
            db_r = rms[1] if len(rms) > 1 else db_l
            self.peak_l = max(0.0, min(1.0, (db_l + 55.0) / 55.0))
            self.peak_r = max(0.0, min(1.0, (db_r + 55.0) / 55.0))
        elif src_name == "mic_level":
            db_m = rms[0] if len(rms) > 0 else -60.0
            self.mic_peak = max(0.0, min(1.0, (db_m + 55.0) / 55.0))

    # -------------------------------------------------------------------------
    # Live Parameter Application (0ms Real-Time GStreamer Property Updates)
    # -------------------------------------------------------------------------
    def apply_live(self, save: bool = True) -> None:
        """Update all GStreamer DSP elements in real-time without restarting streams."""
        if bool(self.state.get("keyshift_enabled", False)) != self._play_has_keyshift:
            self._start_playback_pipeline()
        if bool(self.state.get("magic_voice_enabled", False)) != self._mic_has_magic_voice:
            self._start_mic_pipeline()
        self._apply_playback_live()
        self._apply_mic_live()
        if save:
            self.save_state()

    def _apply_playback_live(self) -> None:
        if not self.play_pipe:
            return

        st = self.state

        # 1. Headphone Gain Tuning + Front Channel Volume
        pre_vol = self.play_pipe.get_by_name("pre_vol")
        if pre_vol:
            hp_gain_db = {0: 0.0, 1: 3.0, 2: 6.0}.get(st.get("hp_gain_mode", 0), 0.0)
            ch_vols = st.get("channel_vols", {})
            avg_front = (ch_vols.get("LF", 100) + ch_vols.get("RF", 100)) / 200.0
            gain_lin = (10.0 ** (hp_gain_db / 20.0)) * max(0.0, min(1.5, avg_front))
            pre_vol.set_property("volume", float(gain_lin))

        # 2. Xear SingFX: Vocal Cancellation & Key Shifting
        karaoke = self.play_pipe.get_by_name("karaoke")
        if karaoke:
            if st.get("vocal_cancel_enabled", False):
                lvl = max(0.0, min(1.0, st.get("vocal_cancel_level", 50) / 100.0))
                karaoke.set_property("level", float(lvl))
                karaoke.set_property("mono-level", float(lvl))
            else:
                karaoke.set_property("level", 0.0)
                karaoke.set_property("mono-level", 0.0)

        keyshift = self.play_pipe.get_by_name("keyshift")
        if keyshift:
            if st.get("keyshift_enabled", False):
                semi = float(st.get("keyshift_semitones", 0))
                ratio = 2.0 ** (semi / 12.0)
                keyshift.set_property("pitch", float(ratio))
            else:
                keyshift.set_property("pitch", 1.0)

        # 3. 10-Band Equalizer (30Hz..16kHz, -20..+20 dB)
        eq10 = self.play_pipe.get_by_name("eq10")
        if eq10:
            bands = st.get("eq_bands", [0.0] * 10)
            enabled = st.get("eq_enabled", False)
            for i in range(10):
                val = float(bands[i]) if enabled and i < len(bands) else 0.0
                # GStreamer equalizer-10bands accepts [-24.0, +12.0] dB
                gst_db = max(-24.0, min(12.0, val * 0.6))
                eq10.set_property(f"band{i}", gst_db)

        # 4. Xear Tone Bands (Dynamic Bass, Flex Bass II, Voice Clarity, Audio Brilliant, HWEQ)
        xear_tone = self.play_pipe.get_by_name("xear_tone")
        if xear_tone:
            # Band 0: Dynamic Bass / Flex Bass / HWEQ Bass
            bass_gain = float(st.get("hweq_bass", 0.0))
            bass_freq = 120.0
            if st.get("dynamic_bass_enabled", False):
                bass_gain += float(st.get("dynamic_bass_level", 5.0)) * 1.1
                bass_freq = float(st.get("dynamic_bass_cutoff", 150))
            if st.get("flex_bass_enabled", False):
                bass_gain += float(st.get("flex_bass_level", 4.0)) * 0.8
                bass_freq = float(st.get("flex_bass_cutoff", 120))
            if st.get("vss_enabled", False):
                w_db = st.get("vss_speakers", {}).get("W", {}).get("db", 0.0)
                bass_gain += float(w_db) * 0.6

            # Band 1 & 2: Xear Voice Clarity (1kHz & 2.5kHz dialog presence)
            vc_gain = 0.0
            if st.get("voice_clarity_enabled", False):
                vc_gain = float(st.get("voice_clarity_level", 4)) * 1.5
            if st.get("vss_enabled", False):
                c_db = st.get("vss_speakers", {}).get("C", {}).get("db", 0.0)
                vc_gain += float(c_db) * 0.5

            # Band 3: Xear Audio Brilliant + HWEQ Treble (10kHz air/brilliance)
            bril_gain = float(st.get("hweq_treble", 0.0))
            if st.get("audio_brilliant_enabled", False):
                bril_gain += float(st.get("audio_brilliant_level", 4)) * 1.8

            configs = [
                (max(30.0, min(400.0, bass_freq)), 100.0, max(-24.0, min(12.0, bass_gain))),
                (1000.0, 600.0, max(-24.0, min(12.0, vc_gain))),
                (2800.0, 1200.0, max(-24.0, min(12.0, vc_gain * 0.8))),
                (10000.0, 4000.0, max(-24.0, min(12.0, bril_gain))),
            ]
            for idx, (freq, bw, g) in enumerate(configs):
                b = xear_tone.get_child_by_index(idx)
                if b:
                    b.set_property("freq", float(freq))
                    b.set_property("bandwidth", float(bw))
                    b.set_property("gain", float(g))

        # 5. Xear Smart Volume (SVN)
        smartvol = self.play_pipe.get_by_name("smartvol")
        if smartvol:
            if st.get("smart_vol_enabled", False):
                lvl = float(st.get("smart_vol_level", 75)) / 100.0
                # Speech mode compresses harder than Music mode
                mode_mult = 1.3 if st.get("smart_vol_mode", 0) == 1 else 1.0
                thresh = max(0.15, 0.85 - lvl * 0.65)
                ratio = min(8.0, 1.5 + lvl * 4.5 * mode_mult)
                smartvol.set_property("threshold", float(thresh))
                smartvol.set_property("ratio", float(ratio))
            else:
                smartvol.set_property("threshold", 1.0)
                smartvol.set_property("ratio", 1.0)

        # 6. 7.1 Virtual Speaker Shifter + Xear Surround + LivingEM Reverb
        vss_pan = self.play_pipe.get_by_name("vss_pan")
        vss_echo = self.play_pipe.get_by_name("vss_echo")
        reverb = self.play_pipe.get_by_name("reverb")
        env_lpf = self.play_pipe.get_by_name("env_lpf")
        post_vol = self.play_pipe.get_by_name("post_vol")

        # Calculate net spatial balance & distance from 7.1 Virtual Speaker positions
        pan_val = 0.0
        dist_gain = 1.0
        vss_delay_ns = 18000000
        vss_echo_int = 0.0
        vss_echo_fb = 0.0

        if st.get("vss_enabled", False):
            spks = st.get("vss_speakers", DEFAULT_VSS_SPEAKERS)
            hx, hy = st.get("vss_head", [0.0, 0.0])
            weighted_x = 0.0
            total_w = 0.0
            avg_dist = 0.0
            for key, info in spks.items():
                ang_rad = math.radians(float(info.get("angle", 0.0)))
                d = float(info.get("dist", 0.68))
                db_trim = float(info.get("db", 0.0))
                sx = d * math.sin(ang_rad) - hx
                sy = -d * math.cos(ang_rad) - hy
                eff_dist = max(0.15, math.hypot(sx, sy))
                w = 10.0 ** (db_trim / 20.0) / (eff_dist / 0.68)
                weighted_x += (sx / eff_dist) * w
                total_w += w
                avg_dist += eff_dist
            if total_w > 0:
                pan_val = max(-0.85, min(0.85, (weighted_x / total_w) * 0.75))
            avg_dist /= max(1, len(spks))
            dist_gain = max(0.35, min(1.4, 0.68 / max(0.25, avg_dist)))
            vss_delay_ns = int(max(8, min(45, avg_dist * 28)) * 1000000)
            vss_echo_int = 0.22
            vss_echo_fb = 0.12

        if st.get("surround_hp_enabled", False):
            room_idx = st.get("surround_hp_room", 1)  # 2=Small, 1=Medium, 0=Large
            room_delays = {2: 12000000, 1: 22000000, 0: 36000000}
            vss_delay_ns = room_delays.get(room_idx, 22000000)
            vss_echo_int = max(vss_echo_int, 0.28 if st.get("surround_hp_mode", 0) == 1 else 0.20)
            vss_echo_fb = max(vss_echo_fb, 0.16)

        if st.get("surround_spk_enabled", False):
            exp = float(st.get("surround_spk_expansion", 2)) / 3.0
            vss_echo_int = max(vss_echo_int, 0.15 + exp * 0.20)

        if st.get("surround_max_enabled", False) or st.get("gx_enabled", False):
            vss_echo_int = max(vss_echo_int, 0.32)
            vss_echo_fb = max(vss_echo_fb, 0.22)
            dist_gain *= 1.12

        # Environment Effects (LivingEM)
        rev_room = 0.50
        rev_damp = 0.50
        rev_width = 1.0
        rev_level = 0.0
        lpf_cutoff = 20000

        if st.get("em_enabled", False):
            env_name = st.get("em_environment", "Concert Hall")
            rs, dp, wd, lv, edelay_ms, eint, lpf = ENVIRONMENT_PRESETS.get(
                env_name, ENVIRONMENT_PRESETS["Generic"]
            )
            room_mod = {0: 0.72, 1: 1.0, 2: 1.25}.get(st.get("em_room_size", 1), 1.0)
            rev_room = max(0.05, min(0.99, rs * room_mod))
            rev_damp = dp
            rev_width = wd
            rev_level = lv
            vss_delay_ns = int(edelay_ms * room_mod * 1000000)
            vss_echo_int = max(vss_echo_int, eint)
            vss_echo_fb = max(vss_echo_fb, min(0.65, eint * 0.75))
            lpf_cutoff = lpf
        elif st.get("surround_hp_enabled", False) or st.get("vss_enabled", False):
            # Subtle spatial room ambience for 7.1 virtual surround
            rev_room = {2: 0.32, 1: 0.52, 0: 0.76}.get(st.get("surround_hp_room", 1), 0.52)
            rev_damp = 0.60
            rev_width = 1.0
            rev_level = 0.18 if st.get("surround_hp_enabled", False) else 0.12

        if vss_pan:
            vss_pan.set_property("panorama", float(pan_val))
        if vss_echo:
            if abs(int(vss_delay_ns) - self._last_vss_delay_ns) >= 500000:
                vss_echo.set_property("delay", int(vss_delay_ns))
                self._last_vss_delay_ns = int(vss_delay_ns)
            vss_echo.set_property("intensity", float(vss_echo_int))
            vss_echo.set_property("feedback", float(vss_echo_fb))
        if reverb:
            reverb.set_property("room-size", float(rev_room))
            reverb.set_property("damping", float(rev_damp))
            reverb.set_property("width", float(rev_width))
            reverb.set_property("level", float(rev_level))
        if env_lpf:
            env_lpf.set_property("cutoff", float(lpf_cutoff))
        if post_vol:
            post_vol.set_property("volume", float(dist_gain))

    def _apply_mic_live(self) -> None:
        if not self.mic_pipe:
            return
        st = self.state

        # 1. ENC & Noise Reduction (High-pass filter + Noise gate expander)
        enc_hpf = self.mic_pipe.get_by_name("enc_hpf")
        enc_gate = self.mic_pipe.get_by_name("enc_gate")
        if enc_hpf and enc_gate:
            if st.get("mic_enc_enabled", False) or st.get("mic_nr_enabled", False) or st.get("mic_aec_enabled", False):
                nr_db = float(st.get("mic_nr_level", 14))
                enc_hpf.set_property("cutoff", 135.0 if st.get("mic_enc_enabled", False) else 95.0)
                thresh = min(0.35, 0.04 + (nr_db - 8.0) * 0.015)
                enc_gate.set_property("threshold", float(max(0.02, thresh)))
                enc_gate.set_property("ratio", 2.5 if st.get("mic_enc_enabled", False) else 1.8)
            else:
                enc_hpf.set_property("cutoff", 35.0)
                enc_gate.set_property("threshold", 0.0)
                enc_gate.set_property("ratio", 1.0)

        # 2. Microphone Boost (+0 to +20 dB)
        mic_boost = self.mic_pipe.get_by_name("mic_boost")
        if mic_boost:
            boost_db = float(st.get("mic_boost_db", 0))
            gain = 10.0 ** (boost_db / 20.0)
            mic_boost.set_property("volume", float(min(10.0, gain)))

        # 3. Xear Magic Voice (0=Monster, 1=Cartoon, 2=Male, 3=Female)
        magic_voice = self.mic_pipe.get_by_name("magic_voice")
        if magic_voice:
            if st.get("magic_voice_enabled", False):
                preset = int(st.get("magic_voice_preset", 0))
                pitch_map = {
                    0: 0.65,  # Monster (deep growling voice)
                    1: 1.65,  # Cartoon (high chipmunk/cartoon voice)
                    2: 0.82,  # Male (deeper baritone voice)
                    3: 1.28,  # Female (higher voice)
                }
                magic_voice.set_property("pitch", float(pitch_map.get(preset, 1.0)))
            else:
                magic_voice.set_property("pitch", 1.0)

        # 4. Microphone Echo (-12..+12)
        mic_echo = self.mic_pipe.get_by_name("mic_echo")
        if mic_echo:
            if st.get("mic_echo_enabled", False):
                lvl = float(st.get("mic_echo_level", 0.0))  # -12..+12
                norm = max(0.05, (lvl + 12.0) / 24.0)
                mic_echo.set_property("intensity", float(norm * 0.65))
                mic_echo.set_property("feedback", float(norm * 0.45))
            else:
                mic_echo.set_property("intensity", 0.0)
                mic_echo.set_property("feedback", 0.0)

    def set_mic_listen_preview(self, enabled: bool) -> None:
        """Toggle live headphone monitoring of processed Magic Voice / Echo."""
        self.state["mic_listen_preview"] = bool(enabled)
        self._start_mic_pipeline()
        self._apply_mic_live()
        self.save_state()

    # -------------------------------------------------------------------------
    # Presets & Profiles
    # -------------------------------------------------------------------------
    def apply_eq_preset(self, preset_name: str) -> List[float]:
        if preset_name in BUILTIN_EQ_PRESETS:
            self.state["eq_bands"] = list(BUILTIN_EQ_PRESETS[preset_name])
            self.state["eq_preset"] = preset_name
        elif preset_name in self.custom_eq_presets:
            self.state["eq_bands"] = list(self.custom_eq_presets[preset_name])
            self.state["eq_preset"] = preset_name
        self.apply_live()
        return self.state["eq_bands"]

    def save_custom_eq_preset(self, name: str) -> bool:
        name = name.strip()
        if not name or name in BUILTIN_EQ_PRESETS:
            return False
        self.custom_eq_presets[name] = list(self.state["eq_bands"])
        self.state["eq_preset"] = name
        self.save_state()
        return True

    def delete_custom_eq_preset(self, name: str) -> bool:
        if name in self.custom_eq_presets:
            del self.custom_eq_presets[name]
            self.state["eq_preset"] = "Default"
            self.state["eq_bands"] = list(BUILTIN_EQ_PRESETS["Default"])
            self.apply_live()
            return True
        return False

    def apply_profile(self, profile_name: str) -> None:
        self.state["active_profile"] = profile_name
        if profile_name == "HiFi Mode":
            self.state["eq_enabled"] = False
            self.state["em_enabled"] = False
            self.state["vss_enabled"] = False
            self.state["surround_hp_enabled"] = False
            self.state["dynamic_bass_enabled"] = False
            self.state["smart_vol_enabled"] = False
            self.state["voice_clarity_enabled"] = False
            self.state["audio_brilliant_enabled"] = False
        elif profile_name == "Movie Mode":
            self.state["eq_enabled"] = True
            self.state["eq_bands"] = [5.0, 4.0, 2.0, 0.0, 1.0, 3.0, 4.0, 3.0, 4.0, 5.0]
            self.state["em_enabled"] = True
            self.state["em_environment"] = "Auditorium"
            self.state["vss_enabled"] = True
            self.state["surround_hp_enabled"] = True
            self.state["surround_hp_mode"] = 1
            self.state["dynamic_bass_enabled"] = True
            self.state["voice_clarity_enabled"] = True
        elif profile_name == "Music Mode":
            self.state["eq_enabled"] = True
            self.state["eq_bands"] = list(BUILTIN_EQ_PRESETS["Rock"])
            self.state["em_enabled"] = False
            self.state["vss_enabled"] = False
            self.state["surround_hp_enabled"] = True
            self.state["surround_hp_mode"] = 0
            self.state["audio_brilliant_enabled"] = True
            self.state["dynamic_bass_enabled"] = True
        elif profile_name in ("Gaming Mode", "FPS Mode", "Racing Mode", "RTS Mode"):
            self.state["eq_enabled"] = True
            if profile_name == "FPS Mode":
                # Footstep & gunshot localization boost (2kHz - 8kHz + tight sub-bass)
                self.state["eq_bands"] = [4.0, 2.0, -2.0, -3.0, 0.0, 4.0, 7.0, 8.0, 6.0, 4.0]
            else:
                self.state["eq_bands"] = [6.0, 5.0, 2.0, 0.0, 0.0, 2.0, 5.0, 6.0, 6.0, 5.0]
            self.state["vss_enabled"] = True
            self.state["surround_hp_enabled"] = True
            self.state["surround_hp_mode"] = 0
            self.state["smart_vol_enabled"] = True
            self.state["gx_enabled"] = True
        elif profile_name == "Karaoke Mode":
            self.state["em_enabled"] = True
            self.state["em_environment"] = "Karaoke"
            self.state["vocal_cancel_enabled"] = True
            self.state["mic_echo_enabled"] = True
            self.state["mic_echo_level"] = 4.0
        elif profile_name == "Communication Mode":
            self.state["voice_clarity_enabled"] = True
            self.state["smart_vol_enabled"] = True
            self.state["smart_vol_mode"] = 1
            self.state["mic_enc_enabled"] = True
            self.state["mic_nr_enabled"] = True
        elif profile_name in self.user_profiles:
            saved = self.user_profiles[profile_name]
            for k, v in saved.items():
                if k in self.state:
                    self.state[k] = v

        self.apply_live()

    # -------------------------------------------------------------------------
    # 7.1 Virtual Speaker Test Player (Using Bundled Original WAV Files)
    # -------------------------------------------------------------------------
    def play_test_sound(self, spk_key: str, on_done: Optional[Callable] = None) -> None:
        """Play the bundled WAV file for spk_key ('L', 'R', 'C', 'W', 'Ls', 'Rs', 'Lb', 'Rb')
        spatialized according to its current 7.1 Virtual Speaker position."""
        spks = self.state.get("vss_speakers", DEFAULT_VSS_SPEAKERS)
        info = spks.get(spk_key, DEFAULT_VSS_SPEAKERS.get(spk_key))
        if not info:
            return
        wav_path = os.path.join(self.sound_dir, info["wav"])
        if not os.path.exists(wav_path):
            return

        if self.test_pipe is not None:
            self.test_pipe.set_state(Gst.State.NULL)
            self.test_pipe = None

        # Calculate spatial pan, distance gain, and rear/side reflection for this speaker
        ang_deg = float(info.get("angle", 0.0))
        ang_rad = math.radians(ang_deg)
        dist = float(info.get("dist", 0.68))
        db_trim = float(info.get("db", 0.0))
        hx, hy = self.state.get("vss_head", [0.0, 0.0])
        sx = dist * math.sin(ang_rad) - hx
        sy = -dist * math.cos(ang_rad) - hy
        eff_dist = max(0.20, math.hypot(sx, sy))

        pan = max(-1.0, min(1.0, sx / eff_dist))
        gain = (10.0 ** (db_trim / 20.0)) * (0.68 / eff_dist)
        gain = max(0.15, min(2.0, gain))

        # Rear speakers (|angle| > 90) get pinna LPF + early reflection delay
        is_rear = abs(ang_deg) > 100.0
        is_side = 60.0 < abs(ang_deg) <= 100.0
        delay_ns = 28000000 if is_rear else (16000000 if is_side else 6000000)
        echo_int = 0.35 if is_rear else (0.22 if is_side else 0.08)
        lpf_hz = 250 if spk_key == "W" else (7500 if is_rear else 18000)

        phys_sink, _ = self.hw.find_pulse_devices()
        sink_prop = f'device="{phys_sink}"' if phys_sink else ""

        pipe_str = (
            f'filesrc location="{wav_path}" ! wavparse ! audioconvert ! audioresample ! '
            f'audiocheblimit mode=low-pass cutoff={lpf_hz} poles=4 ! '
            f'volume volume={gain:.3f} ! '
            f'audiopanorama method=simple panorama={pan:.3f} ! '
            f'audioecho max-delay=100000000 delay={delay_ns} intensity={echo_int:.2f} feedback=0.1 ! '
            f'audioconvert ! pulsesink {sink_prop} sync=true'
        )
        try:
            self.test_pipe = Gst.parse_launch(pipe_str)
            bus = self.test_pipe.get_bus()
            bus.add_signal_watch()

            def _on_eos(b, msg):
                if self.test_pipe:
                    self.test_pipe.set_state(Gst.State.NULL)
                if on_done:
                    GLib.idle_add(on_done)

            bus.connect("message::eos", _on_eos)
            bus.connect("message::error", _on_eos)
            self.test_pipe.set_state(Gst.State.PLAYING)
        except Exception as e:
            print("Test sound error:", e)
            if on_done:
                GLib.idle_add(on_done)

    def start_auto_speaker_test(self, on_speaker_active: Callable[[Optional[str]], None]) -> None:
        """Sequentially test L -> C -> R -> Rs -> Rb -> Lb -> Ls -> W with glowing UI callback."""
        if self._auto_test_running:
            self._auto_test_running = False
            if self.test_pipe:
                self.test_pipe.set_state(Gst.State.NULL)
            on_speaker_active(None)
            return

        order = ["L", "C", "R", "Rs", "Rb", "Lb", "Ls", "W"]
        ch_count = self.state.get("speaker_channels", 8)
        if ch_count == 2:
            order = ["L", "R"]
        elif ch_count == 4:
            order = ["L", "R", "Lb", "Rb"]
        elif ch_count == 6:
            order = ["L", "C", "R", "Rb", "Lb", "W"]

        self._auto_test_running = True

        def _play_idx(idx: int):
            if not self._auto_test_running or idx >= len(order):
                self._auto_test_running = False
                on_speaker_active(None)
                return
            key = order[idx]
            on_speaker_active(key)
            self.play_test_sound(key, on_done=lambda: _play_idx(idx + 1))

        _play_idx(0)

    def stop_auto_speaker_test(self) -> None:
        self._auto_test_running = False
        if self.test_pipe:
            self.test_pipe.set_state(Gst.State.NULL)

    def shutdown(self) -> None:
        self._auto_test_running = False
        for p in (self.test_pipe, self.play_pipe, self.mic_pipe):
            if p is not None:
                try:
                    p.set_state(Gst.State.NULL)
                except Exception:
                    pass
        # Restore physical sink as default when app exits so audio never goes silent
        if self._phys_sink:
            self._run_cmd(["pactl", "set-default-sink", self._phys_sink])
        if self._phys_src:
            self._run_cmd(["pactl", "set-default-source", self._phys_src])
        self.save_state()
