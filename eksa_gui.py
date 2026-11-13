#!/usr/bin/env python3
"""
EKSA Audio Center (XearAudioCenter_x64.exe Native Linux Replica for Fedora 45)
Skin-authentic 800x600 GTK4 GUI using the original C-Media / EKSA FaceLift skin assets
and real-time GStreamer + ALSA/PipeWire DSP engine.

Reverse-engineered with REA from:
  - XearAudioCenter_x64.exe (ev_0f87693fab860dee78283f701bc7e65e78e860db58e571dd1b1ab6208e7d6a26)
  - CMEffectAPO_108B.dll (ev_da7493df0a3c9d9f4761d3a6ab17711330fca2c9c7e7992249323550f28357c7)
  - osConfLib.dll (ev_b2ad95414f4e0b6c528aa4b9c061900713af4deb23d60999fb8bb7a43f98240f)
  - Skin/FaceLift/*.cml & lang/en-US/*.xaml
"""

import math
import os
import subprocess
import sys
import threading
import warnings
from typing import Callable, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore", category=DeprecationWarning)

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

from eksa_hardware import EksaHardwareController
from eksa_dsp import (
    BUILTIN_EQ_PRESETS,
    DEFAULT_VSS_SPEAKERS,
    ENVIRONMENT_LIST,
    EQ_LABELS,
    EksaDspEngine,
)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(APP_DIR, "assets")
SKIN_DIR = os.path.join(ASSETS_DIR, "FaceLift")

SKIN_CSS = """
window.eksa-main-window {
    background-color: #2b1055;
    color: #ffffff;
    font-family: "Sans", "Arial", sans-serif;
}
.eksa-title-banner {
    color: #555555;
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 0.5px;
}
.apo-title {
    color: #ffffff;
    font-size: 19px;
    font-weight: bold;
}
.apo-text {
    color: #ffffff;
    font-size: 12px;
    font-weight: 600;
}
.apo-subtext {
    color: #d8c8ff;
    font-size: 11px;
}
.status-head {
    color: #ffffff;
    font-size: 10px;
    font-weight: bold;
}
.status-val {
    color: #f0e6ff;
    font-size: 10px;
}
.status-khz {
    color: #ffffff;
    font-size: 18px;
    font-weight: bold;
}
.status-tag-on {
    color: #00ffcc;
    font-size: 10px;
    font-weight: bold;
}
.status-tag-off {
    color: rgba(255, 255, 255, 0.30);
    font-size: 10px;
}
button.skin-img-btn {
    background: transparent;
    border: none;
    box-shadow: none;
    padding: 0px;
    margin: 0px;
    min-width: 0px;
    min-height: 0px;
}
button.skin-img-btn:hover {
    filter: brightness(1.18);
}
button.skin-pill-btn {
    background: rgba(30, 10, 60, 0.65);
    color: #e2d4ff;
    border: 1px solid rgba(190, 140, 255, 0.35);
    border-radius: 5px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: bold;
    min-height: 22px;
}
button.skin-pill-btn:hover {
    background: rgba(130, 60, 230, 0.75);
    color: #ffffff;
}
button.skin-pill-active {
    background: linear-gradient(180deg, #9d4edd, #5a189a);
    color: #00ffcc;
    border: 1px solid #00ffcc;
    border-radius: 5px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: bold;
    min-height: 22px;
}
button.eq-preset-btn {
    background: linear-gradient(180deg, #f4f4f8, #d0d0dc);
    color: #444444;
    border: 1px solid #9999aa;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: bold;
    min-width: 68px;
    min-height: 26px;
}
button.eq-preset-btn:hover {
    background: linear-gradient(180deg, #ffffff, #e2d9ff);
    color: #222222;
}
button.eq-preset-active {
    background: linear-gradient(180deg, #ffb703, #fb8500);
    color: #111111;
    border: 1px solid #ffffff;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: bold;
    min-width: 68px;
    min-height: 26px;
}
entry.db-entry {
    background: rgba(20, 8, 42, 0.85);
    color: #00ffcc;
    border: 1px solid rgba(180, 130, 255, 0.5);
    border-radius: 3px;
    padding: 1px 4px;
    font-size: 11px;
    font-weight: bold;
    min-height: 20px;
}
scale.eksa-slider trough {
    background-color: rgba(20, 8, 45, 0.85);
    border: 1px solid rgba(190, 150, 255, 0.45);
    border-radius: 4px;
    min-height: 8px;
    min-width: 8px;
}
scale.eksa-slider highlight {
    background: linear-gradient(90deg, #00f5d4, #9b5de5);
    border-radius: 4px;
}
scale.eksa-slider slider {
    background: linear-gradient(180deg, #ffffff, #c8b6ff);
    border: none;
    border-radius: 4px;
    padding: 0px;
    margin: 0px;
    min-width: 14px;
    min-height: 14px;
}
popover.eksa-menu contents {
    background-color: #f2f0f8;
    color: #222222;
    border: 2px solid #7b2cbf;
    border-radius: 8px;
    padding: 6px;
}
button.menu-item-btn {
    background: transparent;
    color: #222222;
    border: none;
    border-radius: 4px;
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 600;
}
button.menu-item-btn:hover {
    background: #7b2cbf;
    color: #ffffff;
}
"""


def skin_path(rel: str) -> str:
    rel_norm = rel.replace("\\", "/")
    p = os.path.join(SKIN_DIR, rel_norm)
    if os.path.exists(p):
        return p
    # Case-insensitive fallback for Windows paths like infoBtn_no.png vs InfoBtn_no.png
    parent = os.path.dirname(p)
    target = os.path.basename(p).lower()
    if os.path.isdir(parent):
        for fn in os.listdir(parent):
            if fn.lower() == target:
                return os.path.join(parent, fn)
    return p


def load_picture(rel: str, width: int = -1, height: int = -1, keep_aspect: bool = False) -> Gtk.Picture:
    p = skin_path(rel)
    pic = Gtk.Picture()
    if os.path.exists(p):
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file(p)
            if width > 0 and height > 0:
                pb = pb.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
            tex = Gdk.Texture.new_for_pixbuf(pb)
            pic.set_paintable(tex)
        except Exception:
            pic.set_filename(p)
    pic.set_can_shrink(True)
    if hasattr(Gtk, "ContentFit"):
        pic.set_content_fit(Gtk.ContentFit.CONTAIN if keep_aspect else Gtk.ContentFit.FILL)
    if width > 0 and height > 0:
        pic.set_size_request(width, height)
    return pic


class SkinImageButton(Gtk.Button):
    """Clickable button backed by normal/hover/selected skin PNGs."""

    def __init__(
        self,
        normal_rel: str,
        width: int,
        height: int,
        checked_rel: Optional[str] = None,
        tooltip: str = "",
        on_click: Optional[Callable] = None,
    ):
        super().__init__()
        self.add_css_class("skin-img-btn")
        self.normal_rel = normal_rel
        self.checked_rel = checked_rel or normal_rel
        self.w = width
        self.h = height
        self._checked = False
        self.set_size_request(width, height)
        if tooltip:
            self.set_tooltip_text(tooltip)

        self.pic = load_picture(self.normal_rel, width, height)
        self.set_child(self.pic)

        if on_click:
            self.connect("clicked", lambda _b: on_click())

    def set_checked(self, checked: bool) -> None:
        self._checked = bool(checked)
        rel = self.checked_rel if self._checked else self.normal_rel
        p = skin_path(rel)
        if os.path.exists(p):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file(p)
                if self.w > 0 and self.h > 0:
                    pb = pb.scale_simple(self.w, self.h, GdkPixbuf.InterpType.BILINEAR)
                self.pic.set_paintable(Gdk.Texture.new_for_pixbuf(pb))
            except Exception:
                pass

    def is_checked(self) -> bool:
        return self._checked


class EksaApoWindow(Gtk.ApplicationWindow):
    """
    800x600 fixed-layout replica of XearAudioCenter_x64.exe (MainWindow.cml).
    """

    SPEAKER_PAGES = [
        ("SpeakerVol", "Volume Control"),
        ("SpeakerSetting", "Speaker Settings"),
        ("SpeakerSamplingRate", "Sample Rate"),
        ("SpeakerEQ", "Equalizer"),
        ("SpeakerEM", "Environment Effects"),
        ("SpeakerVirtual", "7.1 Virtual Speaker Shifter"),
        ("SpeakerXearSurroundHeadPhone", "Xear Surround Headphone"),
        ("SpeakerXearSurroundSpeakers", "Xear Surround Speaker"),
        ("SpeakerSurroundMax", "Xear Surround Max"),
        ("SpeakerKaraoke", "Xear SingFX"),
        ("SpeakerFlexBass", "Flex Bass II"),
        ("SpeakerXearDynamicBass", "Xear Dynamic Bass"),
        ("SpeakerXearSmartVolume", "Xear Smart Volume"),
        ("SpeakerXearVoiceClarity", "Xear Voice Clarity"),
        ("SpeakerXearAudioBrilliant", "Xear Audio Brilliant"),
    ]

    MIC_PAGES = [
        ("MicInVol", "Volume Control"),
        ("MicInSamplingRate", "Sample Rate"),
        ("MicInKaraoke", "Xear SingFX & Magic Voice"),
        ("MicInENC", "Environmental Noise Cancellation"),
        ("MicInNoiseReduction", "VoClear Noise Reduction"),
        ("MicInBoost", "Microphone Boost"),
    ]

    LED_PAGES = [
        ("LEDLight", "RGB LED Lighting"),
    ]

    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="EKSA Audio Center - INNOVATION FOR GAMERS")
        self.add_css_class("eksa-main-window")
        self.set_default_size(800, 628)
        self.set_resizable(False)

        self.hw = EksaHardwareController()
        self.dsp = EksaDspEngine(self.hw, ASSETS_DIR)
        self.dsp.start_live_pipelines()

        self._updating_ui = False
        self.active_device_group = "Speakers"  # "Speakers", "Headphone", "MicIn", "LED"
        self.active_page_name = "SpeakerVirtual"
        self.show_profile_panel = False

        # VSS interactive drag & rotation state
        self._vss_drag_target: Optional[str] = None
        self._vss_selected_spk: str = "L"
        self._test_active_spk: Optional[str] = None

        # Root 800x600 Fixed Canvas matching MainWindow.cml
        self.root_fixed = Gtk.Fixed()
        self.root_fixed.set_size_request(800, 600)
        self.set_child(self.root_fixed)

        self._build_main_shell()
        self._build_all_pages()
        self.switch_page("SpeakerVirtual")

        # Periodic 50ms timer for live peak meters & VSS clockwise/counter-clockwise rotation
        GLib.timeout_add(50, self._on_tick_50ms)
        # Periodic 3s hardware poll
        GLib.timeout_add(3000, self._on_hw_poll)

        self.connect("close-request", self._on_close_request)

    def _on_close_request(self, _win) -> bool:
        self.dsp.shutdown()
        return False

    # =========================================================================
    # Main Shell (MainWindow.cml, PanelDeviceList.cml, PanelStatus.cml, PanelProfile.cml)
    # =========================================================================
    def _build_main_shell(self) -> None:
        # 1. Background (Main/bg.png 800x600)
        bg = load_picture("Main/bg.png", 800, 600)
        self.root_fixed.put(bg, 0, 0)

        # 2. Top TitleBar (Left=185, Top=0, Width=425, Height=24) & SysBar (Left=661, Top=0)
        self.root_fixed.put(load_picture("Main/TitleBar.png", 425, 24), 185, 0)
        banner_lbl = Gtk.Label(label="INNOVATION FOR GAMERS")
        banner_lbl.add_css_class("eksa-title-banner")
        self.root_fixed.put(banner_lbl, 305, 3)

        self.root_fixed.put(load_picture("Main/SysBar.png", 141, 26), 661, 0)
        self.btn_info = SkinImageButton("Main/infoBtn_no.png", 26, 22, "Main/InfoBtn_mo.png", "Information", self._show_info_dialog)
        self.btn_setting = SkinImageButton("Main/SettingBtn_no.png", 26, 22, "Main/SettingBtn_mo.png", "Application Setting", self._show_setting_dialog)
        self.btn_min = SkinImageButton("Main/MiniBtn_no.png", 24, 22, "Main/MiniBtn_mo.png", "Minimize", lambda: self.minimize())
        self.btn_close = SkinImageButton("Main/CloseBtn_no.png", 24, 22, "Main/CloseBtn_mo.png", "Close", lambda: self.close())
        self.root_fixed.put(self.btn_info, 686, 2)
        self.root_fixed.put(self.btn_setting, 717, 2)
        self.root_fixed.put(self.btn_min, 748, 2)
        self.root_fixed.put(self.btn_close, 774, 2)

        # 3. EKSA Main Logo (Left=27, Top=47, Width=80, Height=60)
        self.btn_logo = SkinImageButton("Main/Logo.png", 80, 60, tooltip="EKSA E900 Pro Official Linux Audio Center", on_click=self._show_info_dialog)
        self.root_fixed.put(self.btn_logo, 27, 47)

        # 4. PanelStatus & PanelProfile (Left=138, Top=51, Width=490, Height=66)
        self.status_fixed = Gtk.Fixed()
        self.status_fixed.set_size_request(490, 66)
        self._build_panel_status()
        self.root_fixed.put(self.status_fixed, 138, 51)

        self.profile_fixed = Gtk.Fixed()
        self.profile_fixed.set_size_request(490, 66)
        self._build_panel_profile()
        self.profile_fixed.set_visible(False)
        self.root_fixed.put(self.profile_fixed, 138, 51)

        # PanelSwitchButton (Left=602, Top=91, Width=25, Height=24)
        self.btn_panel_switch = SkinImageButton(
            "Main/PanelSwtichButton_no.png", 25, 24, "Main/PanelSwtichButton_se.png",
            "Switch between Status Panel and Profile Panel", self._toggle_status_profile_panel
        )
        self.root_fixed.put(self.btn_panel_switch, 602, 91)

        # 5. Top-Right Master Volume, Mute, SVN, GX, ASIO (Left=646..785, Top=55..122)
        self.root_fixed.put(load_picture("Main/VolDown.png", 9, 4), 648, 69)
        self.top_vol_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.top_vol_scale.set_draw_value(False)
        self.top_vol_scale.add_css_class("eksa-slider")
        self.top_vol_scale.set_size_request(86, 22)
        self.top_vol_scale.set_value((self.hw.state.speaker_vol_l + self.hw.state.speaker_vol_r) / 2.0)
        self.top_vol_scale.connect("value-changed", self._on_top_vol_changed)
        self.root_fixed.put(self.top_vol_scale, 658, 58)
        self.root_fixed.put(load_picture("Main/VolUp.png", 9, 8), 745, 66)

        self.btn_top_mute = SkinImageButton(
            "Main/UnmuteBtn_no.png", 26, 20, "Main/MuteBtn_no.png",
            "Mute / UnMute Master Output", self._on_top_mute_clicked
        )
        self.btn_top_mute.set_checked(self.hw.state.speaker_muted)
        self.root_fixed.put(self.btn_top_mute, 758, 59)

        self.btn_top_svn = SkinImageButton(
            "Main/SVN_no.png", 42, 40, "Main/SVN_Selected_no.png",
            "Enable / Disable Smart Volume Normalizer (SVN)", self._on_top_svn_clicked
        )
        self.btn_top_svn.set_checked(self.dsp.state.get("smart_vol_enabled", False))
        self.root_fixed.put(self.btn_top_svn, 646, 82)

        self.btn_top_gx = SkinImageButton(
            "Main/GX_no.png", 42, 40, "Main/GX_Selected_no.png",
            "Enable / Disable EKSA 3D EX Gaming Audio Engine", self._on_top_gx_clicked
        )
        self.btn_top_gx.set_checked(self.dsp.state.get("gx_enabled", False))
        self.root_fixed.put(self.btn_top_gx, 688, 82)

        self.btn_top_asio = SkinImageButton(
            "Main/ASIO_no.png", 42, 40, "Main/ASIO_Enable.png",
            "PipeWire / Low-Latency DSP Status (Click to restart live DSP stream)", self._on_top_asio_clicked
        )
        self.btn_top_asio.set_checked(True)
        self.root_fixed.put(self.btn_top_asio, 730, 82)

        # 6. Left PanelDeviceList (Left=20, Top=126, Width=110, Height=442)
        self._build_device_list()

        # 7. ContentFrame (Left=138, Top=125, Width=656, Height=466)
        self.root_fixed.put(load_picture("Main/ContentFrame.png", 656, 466), 138, 125)

        # Quick Page Navigation Strip inside top of ContentFrame (Left=146, Top=130, Width=618, Height=26)
        self.nav_scroll = Gtk.ScrolledWindow()
        self.nav_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.nav_scroll.set_size_request(612, 28)
        self.nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.nav_scroll.set_child(self.nav_box)
        self.root_fixed.put(self.nav_scroll, 146, 130)
        self.nav_buttons: Dict[str, Gtk.Button] = {}

        # Active APO Feature Page Stack (Left=140, Top=156, Width=620, Height=430)
        self.page_stack = Gtk.Stack()
        self.page_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.page_stack.set_transition_duration(120)
        self.page_stack.set_size_request(620, 430)
        self.root_fixed.put(self.page_stack, 140, 156)

        # Right-edge Live Stereo L/R Peak Meter (Left=764, Top=162, Width=24, Height=412)
        self.peak_area = Gtk.DrawingArea()
        self.peak_area.set_size_request(24, 412)
        self.peak_area.set_draw_func(self._draw_peak_meter)
        self.peak_area.set_tooltip_text("Live Stereo L/R Output & Mic Peak Level Meter")
        self.root_fixed.put(self.peak_area, 764, 162)

    def _build_panel_status(self) -> None:
        self.status_fixed.put(load_picture("PanelStatus/bg.png", 490, 66), 0, 0)

        lbl_pb = Gtk.Label(label="Playback")
        lbl_pb.add_css_class("status-head")
        self.status_fixed.put(lbl_pb, 8, 5)

        self.lbl_render_method = Gtk.Label(label="Headphone / 7.1")
        self.lbl_render_method.add_css_class("status-val")
        self.status_fixed.put(self.lbl_render_method, 14, 19)

        lbl_cap = Gtk.Label(label="Capture")
        lbl_cap.add_css_class("status-head")
        self.status_fixed.put(lbl_cap, 8, 34)

        self.lbl_capture_method = Gtk.Label(label="EKSA MicIn")
        self.lbl_capture_method.add_css_class("status-val")
        self.status_fixed.put(self.lbl_capture_method, 14, 47)

        # Channel count indicators: 2 / 4 / 5.1 / 7.1
        self.lbl_ch_tags: Dict[int, Gtk.Label] = {}
        x_pos = 105
        for ch, txt in [(2, "2"), (4, "4"), (6, "5.1"), (8, "7.1")]:
            l = Gtk.Label(label=txt)
            l.add_css_class("status-tag-on" if ch == 8 else "status-tag-off")
            self.status_fixed.put(l, x_pos, 6)
            self.lbl_ch_tags[ch] = l
            x_pos += len(txt) * 7 + 8

        self.lbl_khz = Gtk.Label(label="48 KHz")
        self.lbl_khz.add_css_class("status-khz")
        self.status_fixed.put(self.lbl_khz, 105, 28)

        # Out DSP effect status badges
        lbl_out = Gtk.Label(label="Out")
        lbl_out.add_css_class("status-head")
        self.status_fixed.put(lbl_out, 200, 5)

        self.out_status_labels: Dict[str, Gtk.Label] = {}
        out_badges = [
            ("EQ", "eq_enabled", 200, 20, "Equalizer"),
            ("EM", "em_enabled", 200, 33, "Environment Effects"),
            ("VSS", "vss_enabled", 200, 46, "7.1 Virtual Speaker Shifter"),
            ("FB", "flex_bass_enabled", 230, 20, "Flex Bass II"),
            ("KS", "keyshift_enabled", 230, 33, "Key Shifting"),
            ("VF", "vocal_cancel_enabled", 230, 46, "Vocal Fading"),
            ("XHP", "surround_hp_enabled", 260, 20, "Xear Surround Headphone"),
            ("XS", "surround_spk_enabled", 260, 33, "Xear Surround Speaker"),
            ("AB", "audio_brilliant_enabled", 260, 46, "Xear Audio Brilliant"),
            ("DB", "dynamic_bass_enabled", 292, 20, "Xear Dynamic Bass"),
            ("SVN", "smart_vol_enabled", 292, 33, "Xear Smart Volume"),
            ("VC", "voice_clarity_enabled", 292, 46, "Xear Voice Clarity"),
            ("SMX", "surround_max_enabled", 324, 20, "Xear Surround Max"),
            ("3DX", "gx_enabled", 324, 33, "EKSA 3D EX"),
        ]
        for tag, state_key, bx, by, tip in out_badges:
            l = Gtk.Label(label=tag)
            l.set_tooltip_text(tip)
            self.status_fixed.put(l, bx, by)
            self.out_status_labels[state_key] = l

        # In DSP effect status badges
        lbl_in = Gtk.Label(label="In")
        lbl_in.add_css_class("status-head")
        self.status_fixed.put(lbl_in, 368, 5)

        in_badges = [
            ("SF", "mic_echo_enabled", 368, 20, "Xear SingFX Microphone Echo"),
            ("MV", "magic_voice_enabled", 368, 33, "Xear Magic Voice"),
            ("ENC", "mic_enc_enabled", 368, 46, "Environmental Noise Cancellation"),
            ("NR", "mic_nr_enabled", 400, 20, "VoClear Noise Reduction"),
            ("AEC", "mic_aec_enabled", 400, 33, "Acoustic Echo Cancellation"),
        ]
        for tag, state_key, bx, by, tip in in_badges:
            l = Gtk.Label(label=tag)
            l.set_tooltip_text(tip)
            self.status_fixed.put(l, bx, by)
            self.out_status_labels[state_key] = l

        self.status_fixed.put(load_picture("PanelStatus/DTSLogo.png", 48, 16, True), 432, 6)
        lbl_usb = Gtk.Label(label="CM108B\n0d8c:0012")
        lbl_usb.add_css_class("status-val")
        self.status_fixed.put(lbl_usb, 430, 26)

    def _build_panel_profile(self) -> None:
        self.profile_fixed.put(load_picture("PanelProfile/bg.png", 490, 66), 0, 0)
        profiles = [
            ("HiFi Mode", "PanelProfile/HiFi_no.png", "PanelProfile/HiFi_se.png", 16),
            ("Movie Mode", "PanelProfile/Movie_no.png", "PanelProfile/Movie_se.png", 68),
            ("Music Mode", "PanelProfile/Music_no.png", "PanelProfile/Music_se.png", 120),
            ("Gaming Mode", "PanelProfile/Gaming_no.png", "PanelProfile/Gaming_se.png", 172),
            ("FPS Mode", "PanelProfile/FPS_no.png", "PanelProfile/FPS_se.png", 224),
            ("Karaoke Mode", "PanelProfile/Karaoke_no.png", "PanelProfile/Karaoke_se.png", 276),
            ("Communication Mode", "PanelProfile/Communication_no.png", "PanelProfile/Communication_se.png", 328),
            ("Manual", "PanelProfile/Manual_no.png", "PanelProfile/Manual_se.png", 380),
        ]
        self.profile_btns: Dict[str, SkinImageButton] = {}
        for pname, norm_img, sel_img, px in profiles:
            btn = SkinImageButton(
                norm_img, 44, 42, sel_img, pname,
                on_click=lambda p=pname: self._on_profile_selected(p)
            )
            self.profile_fixed.put(btn, px, 12)
            self.profile_btns[pname] = btn

    def _build_device_list(self) -> None:
        # 4 main icons in PanelDeviceList (Left=20, Top=126..560)
        self.dev_btns: Dict[str, SkinImageButton] = {}

        devices = [
            ("Speakers", "Main/JackSpeakers_no.png", "Main/JackSpeakers_se.png", 136, "Speakers (7.1 Virtual Surround & DSP)", self.SPEAKER_PAGES),
            ("Headphone", "Main/JackHP_no.png", "Main/JackHP_se.png", 242, "EKSA E900 Pro Headphone", self.SPEAKER_PAGES),
            ("MicIn", "Main/JackMicIn_no.png", "Main/JackMicIn_se.png", 348, "EKSA Noise-Cancelling Microphone", self.MIC_PAGES),
            ("LED", "LED/LEDicon_no.png", "LED/LEDicon_se.png", 454, "EKSA RGB LED Lighting", self.LED_PAGES),
        ]

        for dkey, norm_rel, sel_rel, y_pos, tip, pages in devices:
            btn = SkinImageButton(
                norm_rel, 101, 95, sel_rel,
                f"{tip}\nClick to view {dkey} features, Right-Click for popup menu",
                on_click=lambda k=dkey, pg=pages: self._on_device_icon_clicked(k, pg, show_popover=False)
            )
            # Also attach right-click gesture to open the authentic popup menu
            rc = Gtk.GestureClick.new()
            rc.set_button(3)
            rc.connect("pressed", lambda _g, _n, _x, _y, k=dkey, pg=pages: self._on_device_icon_clicked(k, pg, show_popover=True))
            btn.add_controller(rc)

            self.root_fixed.put(btn, 20, y_pos)
            self.dev_btns[dkey] = btn

            # Default device checkmark badge at bottom-right of Speaker, Headphone, Mic
            if dkey in ("Speakers", "Headphone", "MicIn"):
                chk = load_picture("Resources/Res_CheckBox_se.png", 22, 22)
                self.root_fixed.put(chk, 96, y_pos + 66)

    def _on_device_icon_clicked(self, dev_key: str, pages: List[Tuple[str, str]], show_popover: bool = False) -> None:
        self.active_device_group = dev_key
        for k, b in self.dev_btns.items():
            b.set_checked(k == dev_key)

        self._rebuild_nav_strip(pages)
        # Switch to first page of this device if current page isn't in pages
        page_ids = [p[0] for p in pages]
        if self.active_page_name not in page_ids:
            self.switch_page(page_ids[0])

        if show_popover:
            pop = Gtk.Popover()
            pop.add_css_class("eksa-menu")
            pop.set_parent(self.dev_btns[dev_key])
            pop.set_position(Gtk.PositionType.RIGHT)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            for pid, ptitle in pages:
                mb = Gtk.Button(label=f"• {ptitle}")
                mb.add_css_class("menu-item-btn")
                mb.set_halign(Gtk.Align.FILL)
                mb.connect("clicked", lambda _b, target=pid, p=pop: (p.popdown(), self.switch_page(target)))
                box.append(mb)
            pop.set_child(box)
            pop.popup()

    def _rebuild_nav_strip(self, pages: List[Tuple[str, str]]) -> None:
        while True:
            child = self.nav_box.get_first_child()
            if not child:
                break
            self.nav_box.remove(child)
        self.nav_buttons.clear()

        for pid, ptitle in pages:
            short_title = ptitle.replace("Xear ", "").replace("7.1 Virtual ", "7.1 ").replace("Environmental ", "")
            b = Gtk.Button(label=short_title)
            b.add_css_class("skin-pill-active" if pid == self.active_page_name else "skin-pill-btn")
            b.set_tooltip_text(ptitle)
            b.connect("clicked", lambda _btn, target=pid: self.switch_page(target))
            self.nav_box.append(b)
            self.nav_buttons[pid] = b

    def switch_page(self, page_id: str) -> None:
        self.active_page_name = page_id
        if page_id.startswith("MicIn"):
            self.active_device_group = "MicIn"
            pages = self.MIC_PAGES
        elif page_id == "LEDLight":
            self.active_device_group = "LED"
            pages = self.LED_PAGES
        else:
            if self.active_device_group not in ("Speakers", "Headphone"):
                self.active_device_group = "Speakers"
            pages = self.SPEAKER_PAGES

        for k, b in self.dev_btns.items():
            b.set_checked(k == self.active_device_group)

        self._rebuild_nav_strip(pages)
        self.page_stack.set_visible_child_name(page_id)
        self.refresh_status_indicators()

    def refresh_status_indicators(self) -> None:
        st = self.dsp.state
        for state_key, lbl in self.out_status_labels.items():
            on = bool(st.get(state_key, False))
            lbl.remove_css_class("status-tag-on")
            lbl.remove_css_class("status-tag-off")
            lbl.add_css_class("status-tag-on" if on else "status-tag-off")

        ch_val = st.get("speaker_channels", 8)
        for ch, lbl in self.lbl_ch_tags.items():
            lbl.remove_css_class("status-tag-on")
            lbl.remove_css_class("status-tag-off")
            lbl.add_css_class("status-tag-on" if ch == ch_val else "status-tag-off")

        khz = self.hw.state.sample_rate / 1000.0
        self.lbl_khz.set_label(f"{khz:g} KHz")
        self.btn_top_svn.set_checked(st.get("smart_vol_enabled", False))
        self.btn_top_gx.set_checked(st.get("gx_enabled", False))
        for pname, pbtn in self.profile_btns.items():
            pbtn.set_checked(st.get("active_profile") == pname)


    # =========================================================================
    # Feature Pages Builder (All 22 Original Windows Panels)
    # =========================================================================
    def _build_all_pages(self) -> None:
        self._build_page_speaker_vol()
        self._build_page_speaker_setting()
        self._build_page_speaker_sample_rate()
        self._build_page_speaker_eq()
        self._build_page_speaker_em()
        self._build_page_speaker_virtual()
        self._build_page_surround_headphone()
        self._build_page_surround_speakers()
        self._build_page_surround_max()
        self._build_page_speaker_karaoke()
        self._build_page_flex_bass()
        self._build_page_dynamic_bass()
        self._build_page_smart_volume()
        self._build_page_voice_clarity()
        self._build_page_audio_brilliant()
        self._build_page_mic_vol()
        self._build_page_mic_sample_rate()
        self._build_page_mic_karaoke()
        self._build_page_mic_enc()
        self._build_page_mic_nr()
        self._build_page_mic_boost()
        self._build_page_led_light()

    def _make_canvas(self, page_id: str, title_text: str) -> Gtk.Fixed:
        c = Gtk.Fixed()
        c.set_size_request(620, 430)
        lbl = Gtk.Label(label=title_text)
        lbl.add_css_class("apo-title")
        c.put(lbl, 24, 10)
        self.page_stack.add_named(c, page_id)
        return c

    def _make_enable_row(
        self, canvas: Gtk.Fixed, x: int, y: int, label_text: str, state_key: str, on_toggle: Optional[Callable] = None
    ) -> SkinImageButton:
        btn = SkinImageButton(
            "Resources/Res_CheckBox_no.png", 26, 25, "Resources/Res_CheckBox_se.png", label_text
        )
        btn.set_checked(self.dsp.state.get(state_key, False))

        def _clicked():
            new_val = not btn.is_checked()
            btn.set_checked(new_val)
            self.dsp.state[state_key] = new_val
            self.dsp.apply_live()
            self.refresh_status_indicators()
            if on_toggle:
                on_toggle(new_val)

        btn.connect("clicked", lambda _b: _clicked())
        canvas.put(btn, x, y)
        lbl = Gtk.Label(label=label_text)
        lbl.add_css_class("apo-text")
        canvas.put(lbl, x + 32, y + 4)
        return btn

    # -------------------------------------------------------------------------
    # 1. apoSpeakerVol.cml (Master + 8-Channel L/R Volume & Balance)
    # -------------------------------------------------------------------------
    def _build_page_speaker_vol(self) -> None:
        c = self._make_canvas("SpeakerVol", "Volume Control")

        # Master Volume Slider
        lbl_m = Gtk.Label(label="Master")
        lbl_m.add_css_class("apo-text")
        c.put(lbl_m, 28, 62)

        self.spk_master_scale = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, 0, 100, 1)
        self.spk_master_scale.set_inverted(True)
        self.spk_master_scale.set_draw_value(False)
        self.spk_master_scale.add_css_class("eksa-slider")
        self.spk_master_scale.set_size_request(28, 185)
        self.spk_master_scale.set_value((self.hw.state.speaker_vol_l + self.hw.state.speaker_vol_r) / 2.0)
        self.spk_master_scale.connect("value-changed", self._on_spk_master_vol_changed)
        c.put(self.spk_master_scale, 36, 88)

        self.btn_spk_mute = SkinImageButton(
            "Resources/Res_Unmute_no.png", 22, 22, "Resources/Res_Mute_no.png",
            "Mute / UnMute Speaker", self._on_top_mute_clicked
        )
        self.btn_spk_mute.set_checked(self.hw.state.speaker_muted)
        c.put(self.btn_spk_mute, 39, 282)

        self.entry_master_db = Gtk.Entry()
        self.entry_master_db.add_css_class("db-entry")
        self.entry_master_db.set_editable(False)
        self.entry_master_db.set_width_chars(6)
        self.entry_master_db.set_text(f"{self.hw.state.speaker_db_l:.1f}dB")
        c.put(self.entry_master_db, 20, 312)

        # 4 Channel Pairs: Front (LF/RF), Rear (LB/RB), Cen/LFE (C/W), Side (LS/RS)
        groups = [
            ("Front", "Front", "LF", "RF", "L", "R", 118),
            ("Rear", "Rear", "LB", "RB", "L", "R", 242),
            ("CW", "Cen / LFE", "C", "W", "C", "W", 366),
            ("Side", "Side", "LS", "RS", "L", "R", 490),
        ]
        self.ch_scales: Dict[str, Gtk.Scale] = {}
        self.ch_db_entries: Dict[str, Gtk.Entry] = {}
        self.ch_lock_btns: Dict[str, SkinImageButton] = {}

        for gkey, gtitle, k1, k2, l1, l2, gx in groups:
            gt = Gtk.Label(label=gtitle)
            gt.add_css_class("apo-text")
            c.put(gt, gx + 14, 62)

            for idx, (ch_key, ch_lbl) in enumerate([(k1, l1), (k2, l2)]):
                sx = gx + idx * 48
                sc = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, 0, 100, 1)
                sc.set_inverted(True)
                sc.set_draw_value(False)
                sc.add_css_class("eksa-slider")
                sc.set_size_request(28, 185)
                val = self.dsp.state["channel_vols"].get(ch_key, 100)
                sc.set_value(val)
                c.put(sc, sx, 88)
                self.ch_scales[ch_key] = sc

                tl = Gtk.Label(label=ch_lbl)
                tl.add_css_class("apo-text")
                c.put(tl, sx + 8, 280)

                ent = Gtk.Entry()
                ent.add_css_class("db-entry")
                ent.set_editable(False)
                ent.set_width_chars(5)
                db_v = -37.0 + (val * 37.0 / 100.0)
                ent.set_text(f"{db_v:.0f}dB")
                c.put(ent, sx - 6, 312)
                self.ch_db_entries[ch_key] = ent

                sc.connect("value-changed", lambda s, ck=ch_key, gk=gkey, pk=(k2 if ch_key == k1 else k1): self._on_channel_vol_changed(s, ck, gk, pk))

            lock_btn = SkinImageButton(
                "Resources/Res_Unlock_no.png", 21, 21, "Resources/Res_Lock_no.png",
                "Lock / Unlock Channel Balance"
            )
            lock_btn.set_checked(self.dsp.state["channel_locks"].get(gkey, True))
            lock_btn.connect("clicked", lambda _b, gk=gkey, lb=lock_btn: self._toggle_channel_lock(gk, lb))
            c.put(lock_btn, gx + 28, 280)
            self.ch_lock_btns[gkey] = lock_btn

    # -------------------------------------------------------------------------
    # 2. apoSpeakerSetting.cml (Channel Mode 2 / 4 / 5.1 / 7.1 + Interactive Speaker Test)
    # -------------------------------------------------------------------------
    def _build_page_speaker_setting(self) -> None:
        c = self._make_canvas("SpeakerSetting", "Speaker Settings & 7.1 Test")

        ch_modes = [
            (2, "Stereo (2 Channels)", 100),
            (4, "Quadraphonic (4 Channels)", 132),
            (6, "5.1 Surround Channels", 164),
            (8, "7.1 Virtual Surround Channels", 196),
        ]
        self.spk_ch_radios: Dict[int, Gtk.CheckButton] = {}
        group_leader = None
        for ch_num, ch_label, cy in ch_modes:
            rb = Gtk.CheckButton(label=ch_label)
            if group_leader:
                rb.set_group(group_leader)
            else:
                group_leader = rb
            rb.set_active(self.dsp.state.get("speaker_channels", 8) == ch_num)
            rb.connect("toggled", lambda b, n=ch_num: self._on_speaker_channel_mode_toggled(b, n))
            c.put(rb, 36, cy)
            self.spk_ch_radios[ch_num] = rb

        # Headphone Impedance Gain Amplifier (from apoHeadPhoneSetting.cml)
        lbl_amp = Gtk.Label(label="Headphone Amplifier Gain:")
        lbl_amp.add_css_class("apo-text")
        c.put(lbl_amp, 36, 245)

        self.combo_hp_gain = Gtk.DropDown.new_from_strings([
            "Normal Gain (0 dB for <64 ohms)",
            "High Gain (+3 dB for 64~150 ohms)",
            "Extra High Gain (+6 dB for 150~300 ohms)",
        ])
        self.combo_hp_gain.set_selected(self.dsp.state.get("hp_gain_mode", 0))
        self.combo_hp_gain.connect("notify::selected", self._on_hp_gain_changed)
        c.put(self.combo_hp_gain, 36, 268)

        # Interactive SoundField & 8 Clickable Speakers (Setting/SoundField.png)
        c.put(load_picture("Setting/SoundField.png", 340, 155), 255, 130)

        spk_coords = [
            ("L", "Setting/L_no.png", "Setting/L_glow.png", 340, 95, 48, 73),
            ("R", "Setting/R_no.png", "Setting/R_glow.png", 455, 95, 48, 73),
            ("C", "Setting/C_no.png", "Setting/C_Glow.png", 390, 82, 68, 48),
            ("W", "Setting/Bass_no.png", "Setting/Bass_Glow.png", 412, 118, 55, 48),
            ("Ls", "Setting/LS_no.png", "Setting/LS_Glow.png", 295, 152, 50, 80),
            ("Rs", "Setting/RS_no.png", "Setting/RS_Glow.png", 498, 152, 50, 80),
            ("Lb", "Setting/LB_no.png", "Setting/LB_Glow.png", 358, 205, 49, 79),
            ("Rb", "Setting/RB_no.png", "Setting/RB_Glow.png", 438, 205, 49, 79),
        ]
        self.setting_spk_btns: Dict[str, SkinImageButton] = {}
        for skey, norm_i, glow_i, sx, sy, sw, sh in spk_coords:
            sb = SkinImageButton(
                norm_i, sw, sh, glow_i,
                f"Click to test {DEFAULT_VSS_SPEAKERS[skey]['label']} ({DEFAULT_VSS_SPEAKERS[skey]['wav']})",
                on_click=lambda k=skey: self._trigger_single_speaker_test(k)
            )
            c.put(sb, sx, sy)
            self.setting_spk_btns[skey] = sb

        btn_autotest = SkinImageButton(
            "Setting/AutoTest_no.png", 65, 56, "Setting/AutoTest_glow.png",
            "Play 7.1 Surround Auto Speaker Test", self._trigger_auto_speaker_test
        )
        c.put(btn_autotest, 392, 295)
        self.btn_setting_autotest = btn_autotest

        lbl_hint = Gtk.Label(label="Click any speaker icon or the Play button to test 7.1 spatial audio")
        lbl_hint.add_css_class("apo-subtext")
        c.put(lbl_hint, 245, 360)

    # -------------------------------------------------------------------------
    # 3. apoSpeakerSamplingRate.cml (44.1 KHz / 48 KHz + 16/24 Bits + Diagrams)
    # -------------------------------------------------------------------------
    def _build_page_speaker_sample_rate(self) -> None:
        c = self._make_canvas("SpeakerSamplingRate", "Sample Rate")

        rb_44 = Gtk.CheckButton(label="44.1 KHz")
        rb_48 = Gtk.CheckButton(label="48 KHz")
        rb_48.set_group(rb_44)
        if self.hw.state.sample_rate == 44100:
            rb_44.set_active(True)
        else:
            rb_48.set_active(True)

        c.put(rb_44, 55, 95)
        c.put(rb_48, 55, 128)

        rb_16 = Gtk.CheckButton(label="16 Bits")
        rb_24 = Gtk.CheckButton(label="24 Bits (32-bit float PipeWire)")
        rb_24.set_group(rb_16)
        rb_16.set_active(True)
        c.put(rb_16, 365, 95)
        c.put(rb_24, 365, 128)

        self.pic_rate_diag = load_picture(
            "Resources/Res_Diagram_441KHz.png" if self.hw.state.sample_rate == 44100 else "Resources/Res_Diagram_48KHz.png",
            310, 125
        )
        self.pic_bits_diag = load_picture("Resources/Res_Diagram_16Bits.png", 145, 125)
        c.put(self.pic_rate_diag, 45, 195)
        c.put(self.pic_bits_diag, 385, 195)

        def _update_sr(_b):
            rate = 44100 if rb_44.get_active() else 48000
            bits = 16 if rb_16.get_active() else 24
            self.hw.set_sample_rate(rate, bits)
            rel_r = "Resources/Res_Diagram_441KHz.png" if rate == 44100 else "Resources/Res_Diagram_48KHz.png"
            rel_b = "Resources/Res_Diagram_16Bits.png" if bits == 16 else "Resources/Res_Diagram_24Bits.png"
            self.pic_rate_diag.set_filename(skin_path(rel_r))
            self.pic_bits_diag.set_filename(skin_path(rel_b))
            self.refresh_status_indicators()

        rb_44.connect("toggled", _update_sr)
        rb_48.connect("toggled", _update_sr)
        rb_16.connect("toggled", _update_sr)
        rb_24.connect("toggled", _update_sr)

    # -------------------------------------------------------------------------
    # 4. apoSpeakerEQ.cml (10-Band Equalizer + 12 Presets + Custom Save/Load/Delete)
    # -------------------------------------------------------------------------
    def _build_page_speaker_eq(self) -> None:
        c = self._make_canvas("SpeakerEQ", "Equalizer")
        self.btn_eq_enable = self._make_enable_row(c, 48, 48, "Enable Equalizer", "eq_enabled")

        # TickLines background (EQ/TickLines.png: Left=75, Top=92, Width=421, Height=169)
        c.put(load_picture("EQ/TickLines.png", 421, 169), 75, 92)

        for y_off, txt in [(86, "+20 dB"), (168, "0 dB"), (250, "-20 dB")]:
            l = Gtk.Label(label=txt)
            l.add_css_class("apo-subtext")
            c.put(l, 502, y_off)

        self.eq_sliders: List[Gtk.Scale] = []
        bands = self.dsp.state.get("eq_bands", [0.0] * 10)
        for idx, freq_lbl in enumerate(EQ_LABELS):
            sx = 92 + idx * 39
            sc = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, -20.0, 20.0, 0.5)
            sc.set_inverted(True)
            sc.set_draw_value(False)
            sc.add_css_class("eksa-slider")
            sc.set_size_request(28, 175)
            sc.set_value(float(bands[idx]) if idx < len(bands) else 0.0)
            sc.connect("value-changed", lambda s, i=idx: self._on_eq_band_changed(i, s.get_value()))
            c.put(sc, sx, 88)
            self.eq_sliders.append(sc)

            fl = Gtk.Label(label=freq_lbl)
            fl.add_css_class("apo-text")
            c.put(fl, sx + 2, 268)

        # 12 Preset Buttons + Manual in 3 rows (matching apoSpeakerEQ.cml coordinates)
        preset_grid = [
            ("Dance", 45, 300), ("Rap", 118, 300), ("Metal", 191, 300), ("Jazz", 264, 300), ("Manual", 345, 300),
            ("SoftRock", 45, 332), ("Rock", 118, 332), ("Live", 191, 332), ("Treble", 264, 332),
            ("Bass", 45, 364), ("Classic", 118, 364), ("Opera", 191, 364), ("Default", 264, 364),
        ]
        self.eq_preset_btns: Dict[str, Gtk.Button] = {}
        cur_p = self.dsp.state.get("eq_preset", "Default")
        for pname, px, py in preset_grid:
            b = Gtk.Button(label=pname)
            b.add_css_class("eq-preset-active" if pname == cur_p else "eq-preset-btn")
            b.connect("clicked", lambda _btn, p=pname: self._on_eq_preset_clicked(p))
            c.put(b, px, py)
            self.eq_preset_btns[pname] = b

        # User-defined preset Entry + Save + Delete (EQ/Save_no.png, EQ/Delete_no.png)
        self.entry_eq_name = Gtk.Entry()
        self.entry_eq_name.set_placeholder_text("Preset name...")
        self.entry_eq_name.set_size_request(145, 26)
        c.put(self.entry_eq_name, 430, 332)

        btn_save = SkinImageButton("EQ/Save_no.png", 27, 26, "EQ/Save_mo.png", "Save Custom EQ Preset", self._on_eq_save_custom)
        btn_del = SkinImageButton("EQ/Delete_no.png", 27, 26, "EQ/Delete_mo.png", "Delete Custom EQ Preset", self._on_eq_delete_custom)
        c.put(btn_save, 515, 364)
        c.put(btn_del, 548, 364)

    # -------------------------------------------------------------------------
    # 5. apoSpeakerEM.cml (27 Environment Effects + 4 Quick Icons + 3 Room Sizes)
    # -------------------------------------------------------------------------
    def _build_page_speaker_em(self) -> None:
        c = self._make_canvas("SpeakerEM", "Environment Effects")
        self.btn_em_enable = self._make_enable_row(c, 48, 48, "Enable Environment Effects", "em_enabled")

        lbl_env = Gtk.Label(label="Environment:")
        lbl_env.add_css_class("apo-text")
        c.put(lbl_env, 75, 88)

        self.combo_em = Gtk.DropDown.new_from_strings(ENVIRONMENT_LIST)
        cur_env = self.dsp.state.get("em_environment", "Concert Hall")
        if cur_env in ENVIRONMENT_LIST:
            self.combo_em.set_selected(ENVIRONMENT_LIST.index(cur_env))
        self.combo_em.set_size_request(185, 28)
        self.combo_em.connect("notify::selected", self._on_em_combo_changed)
        c.put(self.combo_em, 75, 112)

        # 4 Quick Environment Graphic Buttons: Concert Hall (Theater), Under Water, Bathroom (Shower), Psychotic (Bar)
        quick_envs = [
            ("Concert Hall", "EM/Theater_no.png", "EM/Theater_se.png", 105, 155),
            ("Under Water", "EM/Underwater_no.png", "EM/Underwater_se.png", 190, 155),
            ("Bathroom", "EM/Shower_no.png", "EM/Shower_se.png", 275, 155),
            ("Psychotic", "EM/Bar_no.png", "EM/Bar_se.png", 360, 155),
        ]
        self.em_quick_btns: Dict[str, SkinImageButton] = {}
        for ename, n_rel, s_rel, qx, qy in quick_envs:
            qb = SkinImageButton(
                n_rel, 67, 65, s_rel, ename,
                on_click=lambda e=ename: self._select_environment(e)
            )
            qb.set_checked(cur_env == ename)
            c.put(qb, qx, qy)
            self.em_quick_btns[ename] = qb

        lbl_rs = Gtk.Label(label="Room Size:")
        lbl_rs.add_css_class("apo-text")
        c.put(lbl_rs, 75, 240)

        rooms = [
            (0, "Small Room", "EM/SmallRoom_no.png", "EM/SmallRoom_se.png", 105, 268),
            (1, "Medium Room", "EM/MediumRoom_no.png", "EM/MediumRoom_se.png", 235, 268),
            (2, "Large Room", "EM/LargeRoom_no.png", "EM/LargeRoom_se.png", 365, 268),
        ]
        self.em_room_btns: Dict[int, SkinImageButton] = {}
        cur_rm = self.dsp.state.get("em_room_size", 1)
        for r_idx, r_tip, n_rel, s_rel, rx, ry in rooms:
            rb = SkinImageButton(
                n_rel, 106, 102, s_rel, r_tip,
                on_click=lambda idx=r_idx: self._select_em_room_size(idx)
            )
            rb.set_checked(cur_rm == r_idx)
            c.put(rb, rx, ry)
            self.em_room_btns[r_idx] = rb

    # -------------------------------------------------------------------------
    # 6. apoSpeakerVirtual.cml (Interactive 7.1 Virtual Speaker Shifter)
    # -------------------------------------------------------------------------
    def _build_page_speaker_virtual(self) -> None:
        c = self._make_canvas("SpeakerVirtual", "7.1 Virtual Speaker Shifter")
        self.btn_vss_enable = self._make_enable_row(c, 48, 44, "Enable 7.1 Virtual Speaker Shifter", "vss_enabled", lambda _v: self.vss_area.queue_draw())

        # Left 5 Mode Buttons from apoSpeakerVirtual.cml
        modes = [
            ("clockwise", "VirtualSpeaker/BtnClockwise_no.png", "VirtualSpeaker/BtnClockwise_se.png", 110, "Continuous Clockwise Rotation"),
            ("counter_clockwise", "VirtualSpeaker/BtnAnticlockwise_no.png", "VirtualSpeaker/BtnAnticlockwise_se.png", 156, "Continuous Counter-Clockwise Rotation"),
            ("manual_rotate", "VirtualSpeaker/BtnWiseArround_no.png", "VirtualSpeaker/BtnWiseArround_se.png", 202, "Manual Ring Rotation (Drag any speaker to rotate all)"),
            ("manual_shift", "VirtualSpeaker/BtnManual_no.png", "VirtualSpeaker/BtnManual_se.png", 248, "Manual Speaker Shifting (Drag any speaker or Head freely)"),
        ]
        self.vss_mode_btns: Dict[str, SkinImageButton] = {}
        cur_mode = self.dsp.state.get("vss_mode", "manual_shift")
        for mkey, n_rel, s_rel, my, mtip in modes:
            mb = SkinImageButton(n_rel, 43, 42, s_rel, mtip, on_click=lambda m=mkey: self._set_vss_mode(m))
            mb.set_checked(cur_mode == mkey)
            c.put(mb, 48, my)
            self.vss_mode_btns[mkey] = mb

        btn_reset = SkinImageButton(
            "VirtualSpeaker/BtnReset_no.png", 43, 42, "VirtualSpeaker/BtnReset_se.png",
            "Reset 7.1 Virtual Speaker Positions & dB Levels", self._reset_vss_positions
        )
        c.put(btn_reset, 48, 296)

        btn_test_vss = SkinImageButton(
            "Setting/AutoTest_no.png", 48, 42, "Setting/AutoTest_glow.png",
            "Play 7.1 Surround Sound Test", self._trigger_auto_speaker_test
        )
        c.put(btn_test_vss, 46, 346)

        # Interactive 320x320 SoundField Canvas (VirtualSpeaker/SoundField-Bg.png + Head + 8 Speakers)
        self._load_vss_pixbufs()
        self.vss_area = Gtk.DrawingArea()
        self.vss_area.set_size_request(320, 320)
        self.vss_area.set_draw_func(self._draw_vss_room)
        self.vss_area.set_tooltip_text("Drag any speaker (L, R, C, W, Ls, Rs, Lb, Rb) or Listener Head to adjust 3D soundstage in real-time! Double-click a speaker to test it.")
        c.put(self.vss_area, 108, 82)

        # Drag & Click controllers on VSS room
        drag = Gtk.GestureDrag.new()
        drag.connect("drag-begin", self._on_vss_drag_begin)
        drag.connect("drag-update", self._on_vss_drag_update)
        drag.connect("drag-end", self._on_vss_drag_end)
        self.vss_area.add_controller(drag)

        click = Gtk.GestureClick.new()
        click.connect("pressed", self._on_vss_clicked)
        self.vss_area.add_controller(click)

        # Right-side dB Trim Controls (-13 dB .. +4 dB)
        btn_sub_db = SkinImageButton(
            "VirtualSpeaker/BtnDecreaseDB_no.png", 20, 20, "VirtualSpeaker/BtnDecreaseDB_se.png",
            "Level Down (-1 dB for selected speaker)", lambda: self._adjust_selected_vss_db(-1.0)
        )
        btn_add_db = SkinImageButton(
            "VirtualSpeaker/BtnIncreaseDB_no.png", 20, 20, "VirtualSpeaker/BtnIncreaseDB_se.png",
            "Level Up (+1 dB for selected speaker)", lambda: self._adjust_selected_vss_db(1.0)
        )
        c.put(btn_sub_db, 445, 92)
        c.put(load_picture("VirtualSpeaker/Volume.png", 21, 15), 505, 95)
        c.put(btn_add_db, 565, 92)

        self.vss_db_Labels: Dict[str, Gtk.Label] = {}
        self.vss_db_bars: Dict[str, Gtk.LevelBar] = {}
        spk_order = ["L", "R", "Ls", "Rs", "Lb", "Rb", "C", "W"]
        for idx, skey in enumerate(spk_order):
            ry = 122 + idx * 32
            sl = Gtk.Label(label=skey)
            sl.add_css_class("apo-text")
            c.put(sl, 442, ry)

            bar = Gtk.LevelBar.new_for_interval(0.0, 17.0)
            bar.set_size_request(92, 12)
            db_v = float(self.dsp.state["vss_speakers"][skey]["db"])
            bar.set_value(max(0.0, min(17.0, db_v + 13.0)))
            c.put(bar, 468, ry + 3)
            self.vss_db_bars[skey] = bar

            dl = Gtk.Label(label=f"{db_v:+.0f} dB")
            dl.add_css_class("apo-subtext")
            c.put(dl, 566, ry)
            self.vss_db_Labels[skey] = dl

    def _load_vss_pixbufs(self) -> None:
        self.pb_vss_bg = GdkPixbuf.Pixbuf.new_from_file_at_scale(skin_path("VirtualSpeaker/SoundField-Bg.png"), 320, 320, False)
        self.pb_vss_head = GdkPixbuf.Pixbuf.new_from_file(skin_path("VirtualSpeaker/Head.png"))
        self.pb_vss_spks: Dict[str, GdkPixbuf.Pixbuf] = {}
        for k, fn in [("C", "C.png"), ("W", "W.png"), ("L", "L.png"), ("R", "R.png"), ("Ls", "Ls.png"), ("Rs", "Rs.png"), ("Lb", "Lb.png"), ("Rb", "Rb.png")]:
            self.pb_vss_spks[k] = GdkPixbuf.Pixbuf.new_from_file(skin_path(f"VirtualSpeaker/{fn}"))

    # -------------------------------------------------------------------------
    # 7. apoSpeakerXearSurroundHeadPhone.cml
    # -------------------------------------------------------------------------
    def _build_page_surround_headphone(self) -> None:
        c = self._make_canvas("SpeakerXearSurroundHeadPhone", "Xear Surround Headphone")
        self._make_enable_row(
            c, 48, 48, "Enable Xear Surround", "surround_hp_enabled",
            lambda on: self.pic_xhp_diag.set_filename(skin_path("XearSurroundEffect/Headphone_Diagram_On.png" if on else "XearSurroundEffect/Headphone_Diagram_Off.png"))
        )

        rb_mus = Gtk.CheckButton(label="Music / Gaming Mode")
        rb_mov = Gtk.CheckButton(label="Movie Mode")
        rb_mov.set_group(rb_mus)
        if self.dsp.state.get("surround_hp_mode", 0) == 0:
            rb_mus.set_active(True)
        else:
            rb_mov.set_active(True)
        rb_mus.connect("toggled", lambda b: self._set_state_key("surround_hp_mode", 0 if b.get_active() else 1))
        c.put(rb_mus, 55, 92)
        c.put(rb_mov, 55, 122)

        diag_rel = "XearSurroundEffect/Headphone_Diagram_On.png" if self.dsp.state.get("surround_hp_enabled", True) else "XearSurroundEffect/Headphone_Diagram_Off.png"
        self.pic_xhp_diag = load_picture(diag_rel, 390, 195)
        c.put(self.pic_xhp_diag, 195, 58)

        btn_test = SkinImageButton(
            "XearSurroundEffect/AutoTest_no.png", 60, 52, "XearSurroundEffect/AutoTest_glow.png",
            "Play 7.1 Headphone Surround Test", self._trigger_auto_speaker_test
        )
        c.put(btn_test, 515, 195)

        lbl_rm = Gtk.Label(label="Room Size:")
        lbl_rm.add_css_class("apo-text")
        c.put(lbl_rm, 48, 250)

        xhp_rooms = [
            (2, "Small Room", "XearSurroundEffect/SmallRoom_no.png", "XearSurroundEffect/SmallRoom_se.png", 105, 275),
            (1, "Medium Room", "XearSurroundEffect/MediumRoom_no.png", "XearSurroundEffect/MediumRoom_se.png", 235, 275),
            (0, "Large Room", "XearSurroundEffect/LargeRoom_no.png", "XearSurroundEffect/LargeRoom_se.png", 365, 275),
        ]
        self.xhp_room_btns: Dict[int, SkinImageButton] = {}
        cur_rm = self.dsp.state.get("surround_hp_room", 1)
        for r_val, r_tip, n_rel, s_rel, rx, ry in xhp_rooms:
            rb = SkinImageButton(n_rel, 106, 102, s_rel, r_tip, on_click=lambda v=r_val: self._select_xhp_room(v))
            rb.set_checked(cur_rm == r_val)
            c.put(rb, rx, ry)
            self.xhp_room_btns[r_val] = rb

    # -------------------------------------------------------------------------
    # 8. apoSpeakerXearSurroundSpeakers.cml
    # -------------------------------------------------------------------------
    def _build_page_surround_speakers(self) -> None:
        c = self._make_canvas("SpeakerXearSurroundSpeakers", "Xear Surround Speaker")
        self._make_enable_row(
            c, 48, 48, "Enable Xear Surround Speaker", "surround_spk_enabled",
            lambda on: self.pic_xspk_diag.set_filename(skin_path("XearSurroundEffect/Speaker_Diagram_On.png" if on else "XearSurroundEffect/Speaker_Diagram_Off.png"))
        )

        diag_rel = "XearSurroundEffect/Speaker_Diagram_On.png" if self.dsp.state.get("surround_spk_enabled", False) else "XearSurroundEffect/Speaker_Diagram_Off.png"
        self.pic_xspk_diag = load_picture(diag_rel, 390, 195)
        c.put(self.pic_xspk_diag, 195, 58)

        lbl_exp = Gtk.Label(label="Sound Field Expansion (Narrow -> Wide):")
        lbl_exp.add_css_class("apo-text")
        c.put(lbl_exp, 65, 275)

        sc_exp = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 3, 1)
        sc_exp.add_css_class("eksa-slider")
        sc_exp.set_size_request(200, 28)
        sc_exp.set_value(self.dsp.state.get("surround_spk_expansion", 2))
        sc_exp.connect("value-changed", lambda s: self._set_state_key("surround_spk_expansion", int(s.get_value())))
        c.put(sc_exp, 65, 302)

        lbl_ang = Gtk.Label(label="Physical Speaker Angle (5° -> 30°):")
        lbl_ang.add_css_class("apo-text")
        c.put(lbl_ang, 330, 275)

        sc_ang = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 5, 30, 5)
        sc_ang.add_css_class("eksa-slider")
        sc_ang.set_size_request(200, 28)
        sc_ang.set_value(self.dsp.state.get("surround_spk_angle", 15))
        sc_ang.connect("value-changed", lambda s: self._set_state_key("surround_spk_angle", int(s.get_value())))
        c.put(sc_ang, 330, 302)

    # -------------------------------------------------------------------------
    # 9. apoSpeakerSurroundMax.cml
    # -------------------------------------------------------------------------
    def _build_page_surround_max(self) -> None:
        c = self._make_canvas("SpeakerSurroundMax", "Xear Surround Max")
        self._make_enable_row(
            c, 48, 48, "Enable Xear Surround Max (Upmix Stereo to 7.1 Surround Field)", "surround_max_enabled",
            lambda on: self.pic_smx_diag.set_filename(skin_path("SurroundMax/SurroundMax_8.png" if on else "SurroundMax/SurroundMax_off.png"))
        )
        diag_rel = "SurroundMax/SurroundMax_8.png" if self.dsp.state.get("surround_max_enabled", False) else "SurroundMax/SurroundMax_off.png"
        self.pic_smx_diag = load_picture(diag_rel, 456, 240)
        c.put(self.pic_smx_diag, 80, 105)

    # -------------------------------------------------------------------------
    # 10. apoSpeakerKaraoke.cml (Xear SingFX: Key Shifting & Vocal Cancellation)
    # -------------------------------------------------------------------------
    def _build_page_speaker_karaoke(self) -> None:
        c = self._make_canvas("SpeakerKaraoke", "Xear SingFX (Karaoke)")

        self._make_enable_row(c, 75, 78, "Enable Key Shifting (-4 to +4 Semitones)", "keyshift_enabled")
        lbl_ks_low = Gtk.Label(label="Pitch Down (-4)")
        lbl_ks_low.add_css_class("apo-subtext")
        c.put(lbl_ks_low, 95, 118)
        lbl_ks_hi = Gtk.Label(label="Pitch Up (+4)")
        lbl_ks_hi.add_css_class("apo-subtext")
        c.put(lbl_ks_hi, 325, 118)

        self.sc_keyshift = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -4, 4, 1)
        self.sc_keyshift.add_css_class("eksa-slider")
        self.sc_keyshift.set_size_request(286, 30)
        self.sc_keyshift.set_value(self.dsp.state.get("keyshift_semitones", 0))
        c.put(self.sc_keyshift, 125, 140)

        self.ent_keyshift = Gtk.Entry()
        self.ent_keyshift.add_css_class("db-entry")
        self.ent_keyshift.set_editable(False)
        self.ent_keyshift.set_width_chars(4)
        self.ent_keyshift.set_text(f"{int(self.sc_keyshift.get_value()):+d}")
        c.put(self.ent_keyshift, 425, 142)

        btn_ks_rst = SkinImageButton("SingFX/Reset_no.png", 68, 28, "SingFX/Reset_mo.png", "Reset Key Shift", lambda: self.sc_keyshift.set_value(0))
        c.put(btn_ks_rst, 490, 140)

        self.sc_keyshift.connect("value-changed", lambda s: (
            self.ent_keyshift.set_text(f"{int(s.get_value()):+d}"),
            self._set_state_key("keyshift_semitones", int(s.get_value()))
        ))

        # Vocal Cancellation
        self._make_enable_row(c, 75, 215, "Enable Vocal Fading (Center Vocal Cancellation)", "vocal_cancel_enabled")
        lbl_vc_v = Gtk.Label(label="Voice (0%)")
        lbl_vc_v.add_css_class("apo-subtext")
        c.put(lbl_vc_v, 95, 255)
        lbl_vc_nv = Gtk.Label(label="No Voice (100%)")
        lbl_vc_nv.add_css_class("apo-subtext")
        c.put(lbl_vc_nv, 325, 255)

        self.sc_vocal = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.sc_vocal.add_css_class("eksa-slider")
        self.sc_vocal.set_size_request(286, 30)
        self.sc_vocal.set_value(self.dsp.state.get("vocal_cancel_level", 50))
        c.put(self.sc_vocal, 125, 278)

        self.ent_vocal = Gtk.Entry()
        self.ent_vocal.add_css_class("db-entry")
        self.ent_vocal.set_editable(False)
        self.ent_vocal.set_width_chars(4)
        self.ent_vocal.set_text(f"{int(self.sc_vocal.get_value())}%")
        c.put(self.ent_vocal, 425, 280)

        btn_vc_rst = SkinImageButton("SingFX/Reset_no.png", 68, 28, "SingFX/Reset_mo.png", "Reset Vocal Fading", lambda: self.sc_vocal.set_value(50))
        c.put(btn_vc_rst, 490, 278)

        self.sc_vocal.connect("value-changed", lambda s: (
            self.ent_vocal.set_text(f"{int(s.get_value())}%"),
            self._set_state_key("vocal_cancel_level", int(s.get_value()))
        ))

    # -------------------------------------------------------------------------
    # 11. apoSpeakerFlexBass.cml (Flex Bass II)
    # -------------------------------------------------------------------------
    def _build_page_flex_bass(self) -> None:
        c = self._make_canvas("SpeakerFlexBass", "Flex Bass II")
        self._make_enable_row(c, 48, 48, "Enable Flex Bass II Crossover Management", "flex_bass_enabled")

        lbl_cof = Gtk.Label(label="Bass Cutoff Frequency (50 - 250 Hz):")
        lbl_cof.add_css_class("apo-text")
        c.put(lbl_cof, 65, 88)

        sc_cof = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 50, 250, 5)
        sc_cof.add_css_class("eksa-slider")
        sc_cof.set_size_request(200, 28)
        sc_cof.set_value(self.dsp.state.get("flex_bass_cutoff", 120))
        sc_cof.connect("value-changed", lambda s: self._set_state_key("flex_bass_cutoff", int(s.get_value())))
        c.put(sc_cof, 65, 112)

        lbl_bl = Gtk.Label(label="Bass Level (-12 to +12 dB):")
        lbl_bl.add_css_class("apo-text")
        c.put(lbl_bl, 340, 88)

        sc_bl = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -12.0, 12.0, 0.5)
        sc_bl.add_css_class("eksa-slider")
        sc_bl.set_size_request(200, 28)
        sc_bl.set_value(self.dsp.state.get("flex_bass_level", 4.0))
        sc_bl.connect("value-changed", lambda s: self._set_state_key("flex_bass_level", float(s.get_value())))
        c.put(sc_bl, 340, 112)

        c.put(load_picture("FlexBass/SoundField.png", 330, 154), 36, 185)
        c.put(load_picture("FlexBass/Small_Woofer.png", 34, 33), 196, 187)
        c.put(load_picture("FlexBass/Large_L.png", 26, 52), 132, 165)
        c.put(load_picture("FlexBass/Large_R.png", 27, 52), 238, 165)
        c.put(load_picture("FlexBass/Small_C.png", 44, 28), 179, 156)
        c.put(load_picture("FlexBass/Small_LS.png", 27, 58), 93, 220)
        c.put(load_picture("FlexBass/Small_RS.png", 27, 58), 279, 220)
        c.put(load_picture("FlexBass/Small_LB.png", 28, 59), 150, 268)
        c.put(load_picture("FlexBass/Small_RB.png", 28, 58), 222, 269)

        for idx, (g_lbl, g_key) in enumerate([("L / R:", "LR"), ("Lb / Rb:", "LbRb"), ("Center:", "C"), ("Ls / Rs:", "LsRs")]):
            gy = 185 + idx * 38
            tl = Gtk.Label(label=g_lbl)
            tl.add_css_class("apo-text")
            c.put(tl, 380, gy + 4)
            dd = Gtk.DropDown.new_from_strings(["Small Speaker", "Large Full-Range"])
            dd.set_selected(self.dsp.state["flex_bass_sizes"].get(g_key, 0))
            dd.connect("notify::selected", lambda d, _p, k=g_key: (
                self.dsp.state["flex_bass_sizes"].__setitem__(k, d.get_selected()),
                self.dsp.apply_live()
            ))
            c.put(dd, 450, gy)

    # -------------------------------------------------------------------------
    # 12. apoSpeakerXearDynamicBass.cml
    # -------------------------------------------------------------------------
    def _build_page_dynamic_bass(self) -> None:
        c = self._make_canvas("SpeakerXearDynamicBass", "Xear Dynamic Bass")
        self._make_enable_row(c, 48, 48, "Enable Xear Dynamic Bass", "dynamic_bass_enabled")

        lbl_bl = Gtk.Label(label="Bass Level (0 - 10):")
        lbl_bl.add_css_class("apo-text")
        c.put(lbl_bl, 85, 105)

        sc_bl = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 10, 0.5)
        sc_bl.add_css_class("eksa-slider")
        sc_bl.set_size_request(240, 30)
        sc_bl.set_value(self.dsp.state.get("dynamic_bass_level", 5.0))
        c.put(sc_bl, 85, 132)

        ent_bl = Gtk.Entry()
        ent_bl.add_css_class("db-entry")
        ent_bl.set_editable(False)
        ent_bl.set_width_chars(4)
        ent_bl.set_text(f"{sc_bl.get_value():.1f}")
        c.put(ent_bl, 345, 134)

        btn_rst1 = SkinImageButton("SingFX/Reset_no.png", 68, 28, "SingFX/Reset_mo.png", "Reset Bass Level", lambda: sc_bl.set_value(5.0))
        c.put(btn_rst1, 420, 132)

        sc_bl.connect("value-changed", lambda s: (
            ent_bl.set_text(f"{s.get_value():.1f}"),
            self._set_state_key("dynamic_bass_level", float(s.get_value()))
        ))

        lbl_cf = Gtk.Label(label="Cutoff Frequency (100 - 400 Hz):")
        lbl_cf.add_css_class("apo-text")
        c.put(lbl_cf, 85, 205)

        sc_cf = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 100, 400, 10)
        sc_cf.add_css_class("eksa-slider")
        sc_cf.set_size_request(240, 30)
        sc_cf.set_value(self.dsp.state.get("dynamic_bass_cutoff", 150))
        c.put(sc_cf, 85, 232)

        ent_cf = Gtk.Entry()
        ent_cf.add_css_class("db-entry")
        ent_cf.set_editable(False)
        ent_cf.set_width_chars(5)
        ent_cf.set_text(f"{int(sc_cf.get_value())}Hz")
        c.put(ent_cf, 345, 234)

        btn_rst2 = SkinImageButton("SingFX/Reset_no.png", 68, 28, "SingFX/Reset_mo.png", "Reset Cutoff Frequency", lambda: sc_cf.set_value(150))
        c.put(btn_rst2, 420, 232)

        sc_cf.connect("value-changed", lambda s: (
            ent_cf.set_text(f"{int(s.get_value())}Hz"),
            self._set_state_key("dynamic_bass_cutoff", int(s.get_value()))
        ))

    # -------------------------------------------------------------------------
    # 13. apoSpeakerXearSmartVolume.cml
    # -------------------------------------------------------------------------
    def _build_page_smart_volume(self) -> None:
        c = self._make_canvas("SpeakerXearSmartVolume", "Xear Smart Volume")
        self.btn_svn_page_enable = self._make_enable_row(c, 48, 48, "Enable Xear Smart Volume Normalizer", "smart_vol_enabled")

        lbl_lv = Gtk.Label(label="Smart Volume Level (0 - 100):")
        lbl_lv.add_css_class("apo-text")
        c.put(lbl_lv, 85, 115)

        sc_lv = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        sc_lv.add_css_class("eksa-slider")
        sc_lv.set_size_request(280, 30)
        sc_lv.set_value(self.dsp.state.get("smart_vol_level", 75))
        c.put(sc_lv, 85, 142)

        ent_lv = Gtk.Entry()
        ent_lv.add_css_class("db-entry")
        ent_lv.set_editable(False)
        ent_lv.set_width_chars(4)
        ent_lv.set_text(f"{int(sc_lv.get_value())}")
        c.put(ent_lv, 385, 144)

        sc_lv.connect("value-changed", lambda s: (
            ent_lv.set_text(f"{int(s.get_value())}"),
            self._set_state_key("smart_vol_level", int(s.get_value()))
        ))

        lbl_md = Gtk.Label(label="Mode:")
        lbl_md.add_css_class("apo-text")
        c.put(lbl_md, 85, 210)

        dd_md = Gtk.DropDown.new_from_strings(["Music Mode", "Speech / Gaming Comms Mode"])
        dd_md.set_selected(self.dsp.state.get("smart_vol_mode", 0))
        dd_md.connect("notify::selected", lambda d, _p: self._set_state_key("smart_vol_mode", d.get_selected()))
        c.put(dd_md, 85, 236)

    # -------------------------------------------------------------------------
    # 14. apoSpeakerXearVoiceClarity.cml
    # -------------------------------------------------------------------------
    def _build_page_voice_clarity(self) -> None:
        c = self._make_canvas("SpeakerXearVoiceClarity", "Xear Voice Clarity")
        self._make_enable_row(c, 48, 48, "Enable Xear Voice Clarity", "voice_clarity_enabled")

        lbl_vc = Gtk.Label(label="Voice Clarity Level (0 - 6):")
        lbl_vc.add_css_class("apo-text")
        c.put(lbl_vc, 85, 105)

        sc_vc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 6, 1)
        sc_vc.add_css_class("eksa-slider")
        sc_vc.set_size_request(240, 30)
        sc_vc.set_value(self.dsp.state.get("voice_clarity_level", 4))
        c.put(sc_vc, 85, 132)

        ent_vc = Gtk.Entry()
        ent_vc.add_css_class("db-entry")
        ent_vc.set_editable(False)
        ent_vc.set_width_chars(4)
        ent_vc.set_text(str(int(sc_vc.get_value())))
        c.put(ent_vc, 345, 134)

        btn_rst1 = SkinImageButton("SingFX/Reset_no.png", 68, 28, "SingFX/Reset_mo.png", "Reset", lambda: sc_vc.set_value(4))
        c.put(btn_rst1, 420, 132)

        sc_vc.connect("value-changed", lambda s: (
            ent_vc.set_text(str(int(s.get_value()))),
            self._set_state_key("voice_clarity_level", int(s.get_value()))
        ))

        lbl_sp = Gtk.Label(label="Noise Suppression for Communication (0 - 20 dB):")
        lbl_sp.add_css_class("apo-text")
        c.put(lbl_sp, 85, 205)

        sc_sp = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 20, 1)
        sc_sp.add_css_class("eksa-slider")
        sc_sp.set_size_request(240, 30)
        sc_sp.set_value(self.dsp.state.get("voice_clarity_supp", 10))
        c.put(sc_sp, 85, 232)

        ent_sp = Gtk.Entry()
        ent_sp.add_css_class("db-entry")
        ent_sp.set_editable(False)
        ent_sp.set_width_chars(5)
        ent_sp.set_text(f"{int(sc_sp.get_value())}dB")
        c.put(ent_sp, 345, 234)

        btn_rst2 = SkinImageButton("SingFX/Reset_no.png", 68, 28, "SingFX/Reset_mo.png", "Reset", lambda: sc_sp.set_value(10))
        c.put(btn_rst2, 420, 232)

        sc_sp.connect("value-changed", lambda s: (
            ent_sp.set_text(f"{int(s.get_value())}dB"),
            self._set_state_key("voice_clarity_supp", int(s.get_value()))
        ))

    # -------------------------------------------------------------------------
    # 15. apoSpeakerXearAudioBrilliant.cml
    # -------------------------------------------------------------------------
    def _build_page_audio_brilliant(self) -> None:
        c = self._make_canvas("SpeakerXearAudioBrilliant", "Xear Audio Brilliant")
        self._make_enable_row(c, 48, 48, "Enable Xear Audio Brilliant (High-Frequency Detail Restoration)", "audio_brilliant_enabled")

        lbl_ab = Gtk.Label(label="Brilliant Level (0 - 6):")
        lbl_ab.add_css_class("apo-text")
        c.put(lbl_ab, 85, 125)

        sc_ab = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 6, 1)
        sc_ab.add_css_class("eksa-slider")
        sc_ab.set_size_request(300, 30)
        sc_ab.set_value(self.dsp.state.get("audio_brilliant_level", 4))
        c.put(sc_ab, 85, 155)

        ent_ab = Gtk.Entry()
        ent_ab.add_css_class("db-entry")
        ent_ab.set_editable(False)
        ent_ab.set_width_chars(4)
        ent_ab.set_text(str(int(sc_ab.get_value())))
        c.put(ent_ab, 405, 157)

        btn_rst = SkinImageButton("SingFX/Reset_no.png", 68, 28, "SingFX/Reset_mo.png", "Reset", lambda: sc_ab.set_value(4))
        c.put(btn_rst, 480, 155)

        sc_ab.connect("value-changed", lambda s: (
            ent_ab.set_text(str(int(s.get_value()))),
            self._set_state_key("audio_brilliant_level", int(s.get_value()))
        ))

    # -------------------------------------------------------------------------
    # 16. apoMicInVol.cml (Mic Capture Volume + Hardware Monitor/Sidetone + AGC)
    # -------------------------------------------------------------------------
    def _build_page_mic_vol(self) -> None:
        c = self._make_canvas("MicInVol", "Microphone Volume & Monitor Control")

        btn_agc = SkinImageButton("Resources/Res_CheckBox_no.png", 26, 25, "Resources/Res_CheckBox_se.png", "Enable Hardware Microphone Boost (ALSA AGC numid=9)")
        btn_agc.set_checked(self.hw.state.mic_agc)
        btn_agc.connect("clicked", lambda _b: (
            btn_agc.set_checked(not btn_agc.is_checked()),
            self.hw.set_mic_agc(btn_agc.is_checked())
        ))
        c.put(btn_agc, 48, 48)
        lbl_agc = Gtk.Label(label="Enable Microphone Boost (Hardware AGC)")
        lbl_agc.add_css_class("apo-text")
        c.put(lbl_agc, 80, 52)

        # Left group: Microphone Capture Volume (numid=7, 8)
        lbl_mv = Gtk.Label(label="Microphone Capture")
        lbl_mv.add_css_class("apo-text")
        c.put(lbl_mv, 105, 88)

        self.sc_mic_vol_l = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, 0, 100, 1)
        self.sc_mic_vol_l.set_inverted(True)
        self.sc_mic_vol_l.set_draw_value(False)
        self.sc_mic_vol_l.add_css_class("eksa-slider")
        self.sc_mic_vol_l.set_size_request(28, 185)
        self.sc_mic_vol_l.set_value(self.hw.state.mic_vol)
        c.put(self.sc_mic_vol_l, 125, 115)

        self.sc_mic_vol_r = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, 0, 100, 1)
        self.sc_mic_vol_r.set_inverted(True)
        self.sc_mic_vol_r.set_draw_value(False)
        self.sc_mic_vol_r.add_css_class("eksa-slider")
        self.sc_mic_vol_r.set_size_request(28, 185)
        self.sc_mic_vol_r.set_value(self.hw.state.mic_vol)
        c.put(self.sc_mic_vol_r, 175, 115)

        self.ent_mic_db = Gtk.Entry()
        self.ent_mic_db.add_css_class("db-entry")
        self.ent_mic_db.set_editable(False)
        self.ent_mic_db.set_width_chars(7)
        self.ent_mic_db.set_text(f"{self.hw.state.mic_db:+.1f} dB")
        c.put(self.ent_mic_db, 125, 310)

        self.btn_mic_mute = SkinImageButton("Resources/Res_Unmute_no.png", 22, 22, "Resources/Res_Mute_no.png", "Mute / UnMute Microphone")
        self.btn_mic_mute.set_checked(self.hw.state.mic_muted)
        self.btn_mic_mute.connect("clicked", lambda _b: (
            self.btn_mic_mute.set_checked(not self.btn_mic_mute.is_checked()),
            self.hw.set_mic_mute(self.btn_mic_mute.is_checked())
        ))
        c.put(self.btn_mic_mute, 152, 342)

        def _on_mic_sc(s):
            v = int(s.get_value())
            if self.sc_mic_vol_l.get_value() != v:
                self.sc_mic_vol_l.set_value(v)
            if self.sc_mic_vol_r.get_value() != v:
                self.sc_mic_vol_r.set_value(v)
            self.hw.set_mic_volume(v)
            self.ent_mic_db.set_text(f"{self.hw.state.mic_db:+.1f} dB")

        self.sc_mic_vol_l.connect("value-changed", _on_mic_sc)
        self.sc_mic_vol_r.connect("value-changed", _on_mic_sc)

        # Right group: Hardware Sidetone / Monitor Volume (numid=3, 4)
        lbl_mon = Gtk.Label(label="Monitor (Hardware Sidetone)")
        lbl_mon.add_css_class("apo-text")
        c.put(lbl_mon, 330, 88)

        self.sc_mon_vol_l = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, 0, 100, 1)
        self.sc_mon_vol_l.set_inverted(True)
        self.sc_mon_vol_l.set_draw_value(False)
        self.sc_mon_vol_l.add_css_class("eksa-slider")
        self.sc_mon_vol_l.set_size_request(28, 185)
        self.sc_mon_vol_l.set_value(self.hw.state.sidetone_vol)
        c.put(self.sc_mon_vol_l, 365, 115)

        self.sc_mon_vol_r = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, 0, 100, 1)
        self.sc_mon_vol_r.set_inverted(True)
        self.sc_mon_vol_r.set_draw_value(False)
        self.sc_mon_vol_r.add_css_class("eksa-slider")
        self.sc_mon_vol_r.set_size_request(28, 185)
        self.sc_mon_vol_r.set_value(self.hw.state.sidetone_vol)
        c.put(self.sc_mon_vol_r, 415, 115)

        self.ent_mon_db = Gtk.Entry()
        self.ent_mon_db.add_css_class("db-entry")
        self.ent_mon_db.set_editable(False)
        self.ent_mon_db.set_width_chars(7)
        self.ent_mon_db.set_text(f"{self.hw.state.sidetone_db:+.1f} dB")
        c.put(self.ent_mon_db, 365, 310)

        self.btn_mon_mute = SkinImageButton("Resources/Res_Unmute_no.png", 22, 22, "Resources/Res_Mute_no.png", "Mute / UnMute Hardware Sidetone Monitor")
        self.btn_mon_mute.set_checked(self.hw.state.sidetone_muted)
        self.btn_mon_mute.connect("clicked", lambda _b: (
            self.btn_mon_mute.set_checked(not self.btn_mon_mute.is_checked()),
            self.hw.set_sidetone_mute(self.btn_mon_mute.is_checked())
        ))
        c.put(self.btn_mon_mute, 392, 342)

        def _on_mon_sc(s):
            v = int(s.get_value())
            if self.sc_mon_vol_l.get_value() != v:
                self.sc_mon_vol_l.set_value(v)
            if self.sc_mon_vol_r.get_value() != v:
                self.sc_mon_vol_r.set_value(v)
            self.hw.set_sidetone_volume(v)
            self.ent_mon_db.set_text(f"{self.hw.state.sidetone_db:+.1f} dB")

        self.sc_mon_vol_l.connect("value-changed", _on_mon_sc)
        self.sc_mon_vol_r.connect("value-changed", _on_mon_sc)

    # -------------------------------------------------------------------------
    # 17. apoMicInSamplingRate.cml
    # -------------------------------------------------------------------------
    def _build_page_mic_sample_rate(self) -> None:
        c = self._make_canvas("MicInSamplingRate", "Microphone Sample Rate")
        rb_44 = Gtk.CheckButton(label="44.1 KHz (16 Bits)")
        rb_48 = Gtk.CheckButton(label="48 KHz (16 Bits)")
        rb_48.set_group(rb_44)
        rb_48.set_active(True)
        c.put(rb_44, 55, 95)
        c.put(rb_48, 55, 128)
        c.put(load_picture("Resources/Res_Diagram_48KHz.png", 310, 125), 45, 195)
        c.put(load_picture("Resources/Res_Diagram_16Bits.png", 145, 125), 385, 195)

    # -------------------------------------------------------------------------
    # 18. apoMicInKaraoke.cml & apoMicInXearMagicVoice.cml (Mic Echo + Magic Voice)
    # -------------------------------------------------------------------------
    def _build_page_mic_karaoke(self) -> None:
        c = self._make_canvas("MicInKaraoke", "Xear SingFX & Magic Voice")

        # Microphone Echo
        self._make_enable_row(c, 65, 58, "Microphone Echo", "mic_echo_enabled")

        sc_echo = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -12.0, 12.0, 1.0)
        sc_echo.add_css_class("eksa-slider")
        sc_echo.set_size_request(300, 30)
        sc_echo.set_value(self.dsp.state.get("mic_echo_level", 0.0))
        sc_echo.connect("value-changed", lambda s: self._set_state_key("mic_echo_level", float(s.get_value())))
        c.put(sc_echo, 105, 96)

        for lx, ltxt in [(105, "Low"), (240, "Default"), (380, "High")]:
            ll = Gtk.Label(label=ltxt)
            ll.add_css_class("apo-subtext")
            c.put(ll, lx, 130)

        btn_echo_rst = SkinImageButton("SingFX/Reset_no.png", 68, 28, "SingFX/Reset_mo.png", "Reset Echo Level", lambda: sc_echo.set_value(0.0))
        c.put(btn_echo_rst, 430, 96)

        # Magic Voice (Monster, Cartoon, Male, Female)
        self._make_enable_row(c, 65, 175, "Magic Voice (Real-Time Voice Changer)", "magic_voice_enabled")

        mv_items = [
            (0, "Monster", "SingFX/Monster_No.png", "SingFX/Monster_se.png", 105),
            (1, "Cartoon", "SingFX/Cartoon_No.png", "SingFX/Cartoon_se.png", 205),
            (2, "Male", "SingFX/Man_No.png", "SingFX/Man_se.png", 305),
            (3, "Female", "SingFX/Woman_No.png", "SingFX/Woman_se.png", 405),
        ]
        self.mv_btns: Dict[int, SkinImageButton] = {}
        cur_mv = self.dsp.state.get("magic_voice_preset", 0)
        for m_idx, m_lbl, n_rel, s_rel, mx in mv_items:
            mb = SkinImageButton(n_rel, 67, 65, s_rel, f"Magic Voice: {m_lbl}", on_click=lambda idx=m_idx: self._select_magic_voice(idx))
            mb.set_checked(cur_mv == m_idx)
            c.put(mb, mx, 215)
            self.mv_btns[m_idx] = mb

            ml = Gtk.Label(label=m_lbl)
            ml.add_css_class("apo-text")
            c.put(ml, mx + 8, 286)

        # Live "Listen to Magic Voice in Headphones" toggle so user can test immediately!
        btn_preview = SkinImageButton(
            "Resources/Res_CheckBox_no.png", 26, 25, "Resources/Res_CheckBox_se.png",
            "Hear your processed Magic Voice & Echo live in your headphones"
        )
        btn_preview.set_checked(self.dsp.state.get("mic_listen_preview", False))

        def _toggle_preview():
            nv = not btn_preview.is_checked()
            btn_preview.set_checked(nv)
            self.dsp.set_mic_listen_preview(nv)

        btn_preview.connect("clicked", lambda _b: _toggle_preview())
        c.put(btn_preview, 65, 335)
        lbl_prev = Gtk.Label(label="Listen to Processed Mic Live in Headphones (Test Magic Voice & Echo)")
        lbl_prev.add_css_class("apo-text")
        c.put(lbl_prev, 98, 339)

    # -------------------------------------------------------------------------
    # 19. apoMicInENC.cml (VoClear Environmental Noise Cancellation)
    # -------------------------------------------------------------------------
    def _build_page_mic_enc(self) -> None:
        c = self._make_canvas("MicInENC", "Environmental Noise Cancellation")
        self._make_enable_row(
            c, 48, 48, "Enable ENC (VoClear Environmental Noise Cancellation)", "mic_enc_enabled",
            lambda on: self.pic_enc_diag.set_filename(skin_path("ENC/Diagram_ENCOn.png" if on else "ENC/Diagram_ENCOff.png"))
        )
        diag_rel = "ENC/Diagram_ENCOn.png" if self.dsp.state.get("mic_enc_enabled", False) else "ENC/Diagram_ENCOff.png"
        self.pic_enc_diag = load_picture(diag_rel, 331, 259)
        c.put(self.pic_enc_diag, 145, 105)

    # -------------------------------------------------------------------------
    # 20. apoMicInNoiseReduction.cml (VoClear Noise Reduction + Suppression Slider)
    # -------------------------------------------------------------------------
    def _build_page_mic_nr(self) -> None:
        c = self._make_canvas("MicInNoiseReduction", "VoClear Noise Reduction")
        self._make_enable_row(
            c, 48, 44, "Enable Noise Reduction", "mic_nr_enabled",
            lambda on: self.pic_nr_diag.set_filename(skin_path("NR/Diagram_NROn.png" if on else "NR/Diagram_NROff.png"))
        )

        sc_nr = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 8, 20, 1)
        sc_nr.add_css_class("eksa-slider")
        sc_nr.set_size_request(300, 28)
        sc_nr.set_value(self.dsp.state.get("mic_nr_level", 14))
        sc_nr.connect("value-changed", lambda s: self._set_state_key("mic_nr_level", int(s.get_value())))
        c.put(sc_nr, 155, 85)

        diag_rel = "NR/Diagram_NROn.png" if self.dsp.state.get("mic_nr_enabled", False) else "NR/Diagram_NROff.png"
        self.pic_nr_diag = load_picture(diag_rel, 331, 259)
        c.put(self.pic_nr_diag, 145, 135)

    # -------------------------------------------------------------------------
    # 21. apoMicInBoost.cml (Software + Hardware Mic Boost)
    # -------------------------------------------------------------------------
    def _build_page_mic_boost(self) -> None:
        c = self._make_canvas("MicInBoost", "Microphone Boost")

        lbl_mb = Gtk.Label(label="Microphone Boost Gain (+0.0 dB to +20.0 dB):")
        lbl_mb.add_css_class("apo-text")
        c.put(lbl_mb, 115, 110)

        sc_mb = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 20, 1)
        sc_mb.add_css_class("eksa-slider")
        sc_mb.set_size_request(300, 30)
        sc_mb.set_value(self.dsp.state.get("mic_boost_db", 0))
        c.put(sc_mb, 115, 145)

        ent_mb = Gtk.Entry()
        ent_mb.add_css_class("db-entry")
        ent_mb.set_editable(False)
        ent_mb.set_width_chars(6)
        ent_mb.set_text(f"+{int(sc_mb.get_value())} dB")
        c.put(ent_mb, 435, 147)

        sc_mb.connect("value-changed", lambda s: (
            ent_mb.set_text(f"+{int(s.get_value())} dB"),
            self._set_state_key("mic_boost_db", int(s.get_value()))
        ))

    # -------------------------------------------------------------------------
    # 22. LEDLight (RGB Set using LED/Colorwheel_bk.png & Colour01..07)
    # -------------------------------------------------------------------------
    def _build_page_led_light(self) -> None:
        c = self._make_canvas("LEDLight", "EKSA RGB LED Lighting")
        self._make_enable_row(c, 48, 48, "Enable EKSA Headset LED Lighting", "led_enabled")

        c.put(load_picture("LED/Colorwheel_bk.png", 190, 190), 55, 105)

        colors = [
            (0, "LED/Colour01_no.png", "LED/Colour01_se.png", 280, 115),
            (1, "LED/Colour02_no.png", "LED/Colour02_se.png", 330, 115),
            (2, "LED/Colour03_no.png", "LED/Colour03_se.png", 380, 115),
            (3, "LED/Colour04_no.png", "LED/Colour04_se.png", 430, 115),
            (4, "LED/Colour05_no.png", "LED/Colour05_se.png", 280, 165),
            (5, "LED/Colour06_no.png", "LED/Colour06_se.png", 330, 165),
            (6, "LED/Colour07_no.png", "LED/Colour07_se.png", 380, 165),
        ]
        self.led_color_btns: Dict[int, SkinImageButton] = {}
        cur_c = self.dsp.state.get("led_color_idx", 0)
        for c_idx, n_rel, s_rel, cx, cy in colors:
            cb = SkinImageButton(n_rel, 38, 38, s_rel, f"Preset Color {c_idx + 1}", on_click=lambda idx=c_idx: self._select_led_color(idx))
            cb.set_checked(cur_c == c_idx)
            c.put(cb, cx, cy)
            self.led_color_btns[c_idx] = cb

        lbl_br = Gtk.Label(label="LED Brightness:")
        lbl_br.add_css_class("apo-text")
        c.put(lbl_br, 280, 230)

        sc_br = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        sc_br.add_css_class("eksa-slider")
        sc_br.set_size_request(220, 28)
        sc_br.set_value(self.dsp.state.get("led_brightness", 100))
        sc_br.connect("value-changed", lambda s: self._set_state_key("led_brightness", int(s.get_value())))
        c.put(sc_br, 280, 255)

    # =========================================================================
    # Interactive 7.1 Virtual Speaker Room Drawing & Dragging
    # =========================================================================
    def _draw_vss_room(self, _area, cr, width: int, height: int) -> None:
        Gdk.cairo_set_source_pixbuf(cr, self.pb_vss_bg, 0, 0)
        cr.paint()

        cx, cy = width / 2.0, height / 2.0
        max_r = 128.0
        st = self.dsp.state
        enabled = st.get("vss_enabled", True)

        # Draw concentric sonar rings when active
        if enabled:
            cr.set_source_rgba(0.0, 0.95, 0.82, 0.18)
            cr.set_line_width(1.2)
            for rad in (45, 85, 125):
                cr.arc(cx, cy, rad, 0, 2 * math.pi)
                cr.stroke()

        # Draw Listener Head
        hx_norm, hy_norm = st.get("vss_head", [0.0, 0.0])
        hx = cx + hx_norm * max_r
        hy = cy + hy_norm * max_r
        hw, hh = self.pb_vss_head.get_width(), self.pb_vss_head.get_height()
        Gdk.cairo_set_source_pixbuf(cr, self.pb_vss_head, hx - hw / 2.0, hy - hh / 2.0)
        cr.paint()

        # Draw 8 Virtual Speakers
        spks = st.get("vss_speakers", DEFAULT_VSS_SPEAKERS)
        for skey, info in spks.items():
            ang_rad = math.radians(float(info.get("angle", 0.0)))
            dist = float(info.get("dist", 0.68))
            sx = cx + dist * max_r * math.sin(ang_rad)
            sy = cy - dist * max_r * math.cos(ang_rad)

            # Highlight selected or currently testing speaker
            if skey == self._test_active_spk:
                cr.set_source_rgba(0.0, 1.0, 0.75, 0.55)
                cr.arc(sx, sy, 25, 0, 2 * math.pi)
                cr.fill()
            elif skey == self._vss_selected_spk:
                cr.set_source_rgba(0.75, 0.35, 1.0, 0.45)
                cr.arc(sx, sy, 22, 0, 2 * math.pi)
                cr.fill()

            pb = self.pb_vss_spks.get(skey)
            if pb:
                pw, ph = pb.get_width(), pb.get_height()
                Gdk.cairo_set_source_pixbuf(cr, pb, sx - pw / 2.0, sy - ph / 2.0)
                cr.paint_with_alpha(1.0 if enabled else 0.45)

    def _on_vss_clicked(self, _gesture, n_press: int, x: float, y: float) -> None:
        target = self._hit_test_vss(x, y)
        if target and target != "HEAD":
            self._vss_selected_spk = target
            self.vss_area.queue_draw()
            if n_press == 2:
                self._trigger_single_speaker_test(target)

    def _hit_test_vss(self, x: float, y: float) -> Optional[str]:
        cx, cy = 160.0, 160.0
        max_r = 128.0
        spks = self.dsp.state.get("vss_speakers", DEFAULT_VSS_SPEAKERS)
        for skey, info in spks.items():
            ang_rad = math.radians(float(info.get("angle", 0.0)))
            dist = float(info.get("dist", 0.68))
            sx = cx + dist * max_r * math.sin(ang_rad)
            sy = cy - dist * max_r * math.cos(ang_rad)
            if math.hypot(x - sx, y - sy) <= 24.0:
                return skey
        hx_n, hy_n = self.dsp.state.get("vss_head", [0.0, 0.0])
        if math.hypot(x - (cx + hx_n * max_r), y - (cy + hy_n * max_r)) <= 26.0:
            return "HEAD"
        return None

    def _on_vss_drag_begin(self, _gesture, start_x: float, start_y: float) -> None:
        self._vss_drag_start = (start_x, start_y)
        self._vss_drag_target = self._hit_test_vss(start_x, start_y)
        if self._vss_drag_target and self._vss_drag_target != "HEAD":
            self._vss_selected_spk = self._vss_drag_target

    def _on_vss_drag_update(self, _gesture, offset_x: float, offset_y: float) -> None:
        if not self._vss_drag_target:
            return
        sx = self._vss_drag_start[0] + offset_x
        sy = self._vss_drag_start[1] + offset_y
        cx, cy = 160.0, 160.0
        max_r = 128.0
        dx = (sx - cx) / max_r
        dy = (sy - cy) / max_r

        if self._vss_drag_target == "HEAD":
            r = math.hypot(dx, dy)
            if r > 0.45:
                dx, dy = dx * 0.45 / r, dy * 0.45 / r
            self.dsp.state["vss_head"] = [round(dx, 3), round(dy, 3)]
        else:
            new_ang = math.degrees(math.atan2(dx, -dy))
            new_dist = max(0.20, min(0.92, math.hypot(dx, dy)))
            spks = self.dsp.state["vss_speakers"]
            cur_info = spks[self._vss_drag_target]
            if self.dsp.state.get("vss_mode") == "manual_rotate":
                delta_ang = new_ang - float(cur_info["angle"])
                for k in spks:
                    spks[k]["angle"] = ((float(spks[k]["angle"]) + delta_ang + 180.0) % 360.0) - 180.0
            else:
                cur_info["angle"] = round(new_ang, 1)
                cur_info["dist"] = round(new_dist, 3)
                # Distance automatically updates dB trim (-13 .. +4 dB)
                db_auto = max(-13.0, min(4.0, round((0.68 - new_dist) * 22.0, 1)))
                cur_info["db"] = db_auto
                self._refresh_vss_db_bars()

        self.dsp.apply_live(save=False)
        self.vss_area.queue_draw()

    def _on_vss_drag_end(self, _gesture, _ox: float, _oy: float) -> None:
        self._vss_drag_target = None
        self.dsp.save_state()

    def _set_vss_mode(self, mode: str) -> None:
        self.dsp.state["vss_mode"] = mode
        for k, b in self.vss_mode_btns.items():
            b.set_checked(k == mode)
        self.dsp.save_state()

    def _reset_vss_positions(self) -> None:
        import copy
        self.dsp.state["vss_head"] = [0.0, 0.0]
        self.dsp.state["vss_speakers"] = copy.deepcopy(DEFAULT_VSS_SPEAKERS)
        self.dsp.state["vss_mode"] = "manual_shift"
        for k, b in self.vss_mode_btns.items():
            b.set_checked(k == "manual_shift")
        self._refresh_vss_db_bars()
        self.dsp.apply_live()
        self.vss_area.queue_draw()

    def _adjust_selected_vss_db(self, delta: float) -> None:
        skey = self._vss_selected_spk
        info = self.dsp.state["vss_speakers"].get(skey)
        if not info:
            return
        info["db"] = max(-13.0, min(4.0, round(float(info["db"]) + delta, 1)))
        self._refresh_vss_db_bars()
        self.dsp.apply_live()

    def _refresh_vss_db_bars(self) -> None:
        for skey, info in self.dsp.state["vss_speakers"].items():
            db_v = float(info["db"])
            if skey in self.vss_db_bars:
                self.vss_db_bars[skey].set_value(max(0.0, min(17.0, db_v + 13.0)))
            if skey in self.vss_db_Labels:
                self.vss_db_Labels[skey].set_label(f"{db_v:+.0f} dB")

    # =========================================================================
    # Live Peak Meter & Periodic Callbacks
    # =========================================================================
    def _draw_peak_meter(self, _area, cr, width: int, height: int) -> None:
        # Background bar frame
        cr.set_source_rgba(0.08, 0.03, 0.18, 0.85)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        # Draw 28 LED segments for Left and Right channels
        num_segs = 28
        seg_h = (height - 24) / num_segs
        pl = self.dsp.peak_l
        pr = self.dsp.peak_r

        for i in range(num_segs):
            norm = (num_segs - 1 - i) / float(num_segs)
            y = 6 + i * seg_h
            for ch_idx, p_val in enumerate((pl, pr)):
                x = 3 + ch_idx * 10
                lit = p_val >= norm
                if norm > 0.82:
                    cr.set_source_rgba(1.0, 0.2, 0.3, 0.95 if lit else 0.18)
                elif norm > 0.60:
                    cr.set_source_rgba(1.0, 0.85, 0.1, 0.95 if lit else 0.18)
                else:
                    cr.set_source_rgba(0.0, 0.98, 0.75, 0.95 if lit else 0.18)
                cr.rectangle(x, y, 8, max(2.0, seg_h - 2.0))
                cr.fill()

    def _on_tick_50ms(self) -> bool:
        # Decay peak meter smoothly when quiet
        self.dsp.peak_l = max(0.0, self.dsp.peak_l * 0.90)
        self.dsp.peak_r = max(0.0, self.dsp.peak_r * 0.90)
        self.peak_area.queue_draw()

        # Continuous rotation if VSS mode is clockwise or counter_clockwise
        if self.dsp.state.get("vss_enabled", False):
            vmode = self.dsp.state.get("vss_mode", "manual_shift")
            if vmode in ("clockwise", "counter_clockwise"):
                step = 2.0 if vmode == "clockwise" else -2.0
                for info in self.dsp.state["vss_speakers"].values():
                    info["angle"] = ((float(info["angle"]) + step + 180.0) % 360.0) - 180.0
                self.dsp.apply_live(save=False)
                if self.active_page_name == "SpeakerVirtual":
                    self.vss_area.queue_draw()
        return True

    def _on_hw_poll(self) -> bool:
        def _bg_poll():
            self.hw.refresh()
            self.dsp.route_desktop_streams_to_dsp()

        threading.Thread(target=_bg_poll, daemon=True).start()
        return True

    # =========================================================================
    # Control Event Handlers
    # =========================================================================
    def _set_state_key(self, key: str, val) -> None:
        self.dsp.state[key] = val
        self.dsp.apply_live()
        self.refresh_status_indicators()

    def _toggle_status_profile_panel(self) -> None:
        self.show_profile_panel = not self.show_profile_panel
        self.status_fixed.set_visible(not self.show_profile_panel)
        self.profile_fixed.set_visible(self.show_profile_panel)
        self.btn_panel_switch.set_checked(self.show_profile_panel)

    def _on_profile_selected(self, profile_name: str) -> None:
        self.dsp.apply_profile(profile_name)
        self._sync_ui_from_dsp_state()
        self.refresh_status_indicators()

    def _sync_ui_from_dsp_state(self) -> None:
        self._updating_ui = True
        st = self.dsp.state
        self.btn_eq_enable.set_checked(st.get("eq_enabled", False))
        self.btn_em_enable.set_checked(st.get("em_enabled", False))
        self.btn_vss_enable.set_checked(st.get("vss_enabled", False))
        bands = st.get("eq_bands", [0.0] * 10)
        for i, sc in enumerate(self.eq_sliders):
            if i < len(bands):
                sc.set_value(float(bands[i]))
        self._updating_ui = False

    def _on_top_vol_changed(self, scale: Gtk.Scale) -> None:
        if self._updating_ui:
            return
        v = int(scale.get_value())
        self.hw.set_speaker_volume(v, v)
        self._updating_ui = True
        self.spk_master_scale.set_value(v)
        self.entry_master_db.set_text(f"{self.hw.state.speaker_db_l:.1f}dB")
        self._updating_ui = False

    def _on_spk_master_vol_changed(self, scale: Gtk.Scale) -> None:
        if self._updating_ui:
            return
        v = int(scale.get_value())
        self.hw.set_speaker_volume(v, v)
        self._updating_ui = True
        self.top_vol_scale.set_value(v)
        self.entry_master_db.set_text(f"{self.hw.state.speaker_db_l:.1f}dB")
        self._updating_ui = False

    def _on_top_mute_clicked(self) -> None:
        new_m = not self.hw.state.speaker_muted
        self.hw.set_speaker_mute(new_m)
        self.btn_top_mute.set_checked(new_m)
        self.btn_spk_mute.set_checked(new_m)

    def _on_top_svn_clicked(self) -> None:
        nv = not self.dsp.state.get("smart_vol_enabled", False)
        self.dsp.state["smart_vol_enabled"] = nv
        self.btn_top_svn.set_checked(nv)
        self.btn_svn_page_enable.set_checked(nv)
        self.dsp.apply_live()
        self.refresh_status_indicators()

    def _on_top_gx_clicked(self) -> None:
        nv = not self.dsp.state.get("gx_enabled", False)
        self.dsp.state["gx_enabled"] = nv
        self.btn_top_gx.set_checked(nv)
        self.dsp.apply_live()
        self.refresh_status_indicators()

    def _on_top_asio_clicked(self) -> None:
        self.dsp.start_live_pipelines()
        self.btn_top_asio.set_checked(True)

    def _on_channel_vol_changed(self, scale: Gtk.Scale, ch_key: str, group_key: str, pair_key: str) -> None:
        if self._updating_ui:
            return
        val = int(scale.get_value())
        self.dsp.state["channel_vols"][ch_key] = val
        db_v = -37.0 + (val * 37.0 / 100.0)
        self.ch_db_entries[ch_key].set_text(f"{db_v:.0f}dB")

        if self.dsp.state["channel_locks"].get(group_key, True):
            self._updating_ui = True
            self.dsp.state["channel_vols"][pair_key] = val
            self.ch_scales[pair_key].set_value(val)
            self.ch_db_entries[pair_key].set_text(f"{db_v:.0f}dB")
            self._updating_ui = False

        if group_key == "Front":
            self.hw.set_speaker_volume(
                self.dsp.state["channel_vols"]["LF"],
                self.dsp.state["channel_vols"]["RF"],
            )
        self.dsp.apply_live()

    def _toggle_channel_lock(self, group_key: str, btn: SkinImageButton) -> None:
        nv = not btn.is_checked()
        btn.set_checked(nv)
        self.dsp.state["channel_locks"][group_key] = nv
        self.dsp.save_state()

    def _on_speaker_channel_mode_toggled(self, rb: Gtk.CheckButton, ch_num: int) -> None:
        if rb.get_active():
            self.dsp.state["speaker_channels"] = ch_num
            self.dsp.apply_live()
            self.refresh_status_indicators()

    def _on_hp_gain_changed(self, dd: Gtk.DropDown, _pspec) -> None:
        self.dsp.state["hp_gain_mode"] = dd.get_selected()
        self.dsp.apply_live()

    def _trigger_single_speaker_test(self, spk_key: str) -> None:
        self._test_active_spk = spk_key
        for k, b in self.setting_spk_btns.items():
            b.set_checked(k == spk_key)
        self.vss_area.queue_draw()

        def _done():
            self._test_active_spk = None
            for b in self.setting_spk_btns.values():
                b.set_checked(False)
            self.vss_area.queue_draw()

        self.dsp.play_test_sound(spk_key, on_done=_done)

    def _trigger_auto_speaker_test(self) -> None:
        def _on_step(active_key: Optional[str]):
            self._test_active_spk = active_key
            self.btn_setting_autotest.set_checked(active_key is not None)
            for k, b in self.setting_spk_btns.items():
                b.set_checked(k == active_key)
            self.vss_area.queue_draw()

        self.dsp.start_auto_speaker_test(_on_step)

    def _on_eq_band_changed(self, idx: int, val: float) -> None:
        if self._updating_ui:
            return
        self.dsp.state["eq_bands"][idx] = round(val, 1)
        self.dsp.state["eq_preset"] = "Manual"
        self._highlight_eq_preset("Manual")
        self.dsp.apply_live()

    def _on_eq_preset_clicked(self, preset_name: str) -> None:
        bands = self.dsp.apply_eq_preset(preset_name)
        self._updating_ui = True
        for i, sc in enumerate(self.eq_sliders):
            if i < len(bands):
                sc.set_value(float(bands[i]))
        self._updating_ui = False
        self._highlight_eq_preset(preset_name)

    def _highlight_eq_preset(self, active_name: str) -> None:
        for pname, b in self.eq_preset_btns.items():
            b.remove_css_class("eq-preset-active")
            b.remove_css_class("eq-preset-btn")
            b.add_css_class("eq-preset-active" if pname == active_name else "eq-preset-btn")

    def _on_eq_save_custom(self) -> None:
        name = self.entry_eq_name.get_text().strip()
        if name:
            self.dsp.save_custom_eq_preset(name)

    def _on_eq_delete_custom(self) -> None:
        name = self.entry_eq_name.get_text().strip()
        if name:
            self.dsp.delete_custom_eq_preset(name)
            self._on_eq_preset_clicked("Default")

    def _on_em_combo_changed(self, dd: Gtk.DropDown, _pspec) -> None:
        if self._updating_ui:
            return
        idx = dd.get_selected()
        if 0 <= idx < len(ENVIRONMENT_LIST):
            self._select_environment(ENVIRONMENT_LIST[idx], from_combo=True)

    def _select_environment(self, env_name: str, from_combo: bool = False) -> None:
        self.dsp.state["em_environment"] = env_name
        self.dsp.state["em_enabled"] = True
        self.btn_em_enable.set_checked(True)
        for k, b in self.em_quick_btns.items():
            b.set_checked(k == env_name)
        if not from_combo and env_name in ENVIRONMENT_LIST:
            self._updating_ui = True
            self.combo_em.set_selected(ENVIRONMENT_LIST.index(env_name))
            self._updating_ui = False
        self.dsp.apply_live()
        self.refresh_status_indicators()

    def _select_em_room_size(self, room_idx: int) -> None:
        self.dsp.state["em_room_size"] = room_idx
        for k, b in self.em_room_btns.items():
            b.set_checked(k == room_idx)
        self.dsp.apply_live()

    def _select_xhp_room(self, room_val: int) -> None:
        self.dsp.state["surround_hp_room"] = room_val
        for k, b in self.xhp_room_btns.items():
            b.set_checked(k == room_val)
        self.dsp.apply_live()

    def _select_magic_voice(self, preset_idx: int) -> None:
        self.dsp.state["magic_voice_preset"] = preset_idx
        self.dsp.state["magic_voice_enabled"] = True
        for k, b in self.mv_btns.items():
            b.set_checked(k == preset_idx)
        self.dsp.apply_live()
        self.refresh_status_indicators()

    def _select_led_color(self, color_idx: int) -> None:
        self.dsp.state["led_color_idx"] = color_idx
        for k, b in self.led_color_btns.items():
            b.set_checked(k == color_idx)
        self.dsp.save_state()

    # =========================================================================
    # DialogInfo.cml & Dialog_AppSetting.cml Popups
    # =========================================================================
    def _show_info_dialog(self) -> None:
        win = Gtk.Window(title="EKSA Audio Center - Information", transient_for=self, modal=True)
        win.set_default_size(520, 290)
        win.set_resizable(False)
        fixed = Gtk.Fixed()
        fixed.put(load_picture("DialogInfo/BG.png", 520, 290), 0, 0)

        info_lines = [
            f"Audio CODEC :   {self.hw.state.audio_codec} (USB { self.hw.state.usb_bus_dev or '0d8c:0012' })",
            f"Audio Driver Version :   {self.hw.state.driver_version}",
            f"Firmware Version :   {self.hw.state.firmware_version}",
            f"DSP Engine :   GStreamer 1.0 + PipeWire Real-Time APO (LFX/GFX)",
            f"CPL Version :   1.0.0.4 (FaceLift Linux Edition)",
            "Copyright © EKSA.INC - www.eksa.net",
        ]
        for idx, text in enumerate(info_lines):
            l = Gtk.Label(label=text)
            fixed.put(l, 45, 48 + idx * 28)

        btn_exit = Gtk.Button(label="Exit")
        btn_exit.add_css_class("eq-preset-btn")
        btn_exit.connect("clicked", lambda _b: win.close())
        fixed.put(btn_exit, 410, 235)
        win.set_child(fixed)
        win.present()

    def _show_setting_dialog(self) -> None:
        win = Gtk.Window(title="Application Setting", transient_for=self, modal=True)
        win.set_default_size(460, 260)
        win.set_resizable(False)
        fixed = Gtk.Fixed()
        fixed.put(load_picture("DialogAppSetting/bg.png", 460, 260), 0, 0)

        lbl_op = Gtk.Label(label="UI Opacity / Transparency:")
        fixed.put(lbl_op, 45, 65)
        sc_op = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 5, 10, 1)
        sc_op.set_size_request(180, 28)
        sc_op.set_value(10)
        sc_op.connect("value-changed", lambda s: self.set_opacity(s.get_value() / 10.0))
        fixed.put(sc_op, 230, 60)

        lbl_dev = Gtk.Label(label=f"Connected USB Hardware: {'YES (EKSA E900 Pro)' if self.hw.state.connected else 'Not Detected'}")
        fixed.put(lbl_dev, 45, 115)

        btn_ok = Gtk.Button(label="OK")
        btn_ok.add_css_class("eq-preset-btn")
        btn_ok.connect("clicked", lambda _b: win.close())
        fixed.put(btn_ok, 345, 200)
        win.set_child(fixed)
        win.present()


class EksaAudioCenterApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="net.eksa.AudioCenter")

    def do_activate(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(SKIN_CSS.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        win = self.props.active_window
        if not win:
            win = EksaApoWindow(self)
        win.present()


def main():
    app = EksaAudioCenterApp()
    sys.exit(app.run(sys.argv))


if __name__ == "__main__":
    main()
