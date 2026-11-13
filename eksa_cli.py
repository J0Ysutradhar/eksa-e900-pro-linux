#!/usr/bin/env python3
"""
EKSA E900 Pro Audio Center CLI for Fedora Linux
Controls ALSA hardware mixer, PipeWire sample rate, and real-time DSP state.
"""

import argparse
import os
import sys
from eksa_hardware import EksaHardwareController
from eksa_dsp import (
    EksaDspEngine,
    EQ_FREQS,
    BUILTIN_EQ_PRESETS,
    ENVIRONMENT_PRESETS,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="eksa-cli",
        description="EKSA E900 Pro Gaming Headset Control CLI (Hardware + Real-Time Xear DSP)",
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Show EKSA E900 Pro hardware & DSP status")
    sub.add_parser("presets", help="List built-in 10-band EQ and 27 Environment presets")

    p_vol = sub.add_parser("volume", help="Set speaker volume (0-100) or mute/unmute")
    p_vol.add_argument("level", nargs="?", type=int, help="Volume percentage 0..100")
    p_vol.add_argument("--left", type=int, help="Left channel 0..100")
    p_vol.add_argument("--right", type=int, help="Right channel 0..100")
    p_vol.add_argument("--mute", choices=["on", "off"], help="Mute or unmute speaker")

    p_mic = sub.add_parser("mic", help="Set microphone capture volume (0-100), mute, or AGC")
    p_mic.add_argument("level", nargs="?", type=int, help="Mic volume percentage 0..100")
    p_mic.add_argument("--mute", choices=["on", "off"], help="Mute or unmute microphone")
    p_mic.add_argument("--agc", choices=["on", "off"], help="Hardware AGC / Mic Boost switch")

    p_st = sub.add_parser("sidetone", help="Set hardware zero-latency microphone sidetone/monitor")
    p_st.add_argument("level", nargs="?", type=int, help="Sidetone volume 0..100")
    p_st.add_argument("--enable", choices=["on", "off"], help="Enable or disable hardware sidetone")

    p_eq = sub.add_parser("eq", help="Configure 10-band Equalizer preset or enable/disable")
    p_eq.add_argument("--enable", choices=["on", "off"], help="Enable or disable Equalizer")
    p_eq.add_argument("--preset", type=str, help="Select EQ preset name (e.g. Bass, Dance, Rock, Metal)")
    p_eq.add_argument("--bands", nargs=10, type=float, metavar="DB", help="10 band gains in dB (-12..+12)")

    p_env = sub.add_parser("env", help="Configure Xear Environment Reverb")
    p_env.add_argument("--enable", choices=["on", "off"], help="Enable or disable Environment Effects")
    p_env.add_argument("--preset", type=str, help="Environment preset name (e.g. 'Concert Hall', 'Under Water')")
    p_env.add_argument("--room", type=int, choices=[0, 1, 2], help="Room size (0=Small, 1=Medium, 2=Large)")

    p_sur = sub.add_parser("surround", help="Configure 7.1 Virtual Speaker Shifter, Surround Headphone & 3D EX")
    p_sur.add_argument("--vss", choices=["on", "off"], help="7.1 Virtual Speaker Shifter")
    p_sur.add_argument("--headphone", choices=["on", "off"], help="Xear Surround Headphone")
    p_sur.add_argument("--max", choices=["on", "off"], help="Xear Surround Max")
    p_sur.add_argument("--gx", choices=["on", "off"], help="EKSA 3D EX gaming audio engine")

    p_fx = sub.add_parser("fx", help="Configure Xear Smart Volume, Dynamic Bass, Voice Clarity, Brilliant, SingFX, Magic Voice, ENC")
    p_fx.add_argument("--svn", choices=["on", "off"], help="Xear Smart Volume")
    p_fx.add_argument("--dyn-bass", choices=["on", "off"], help="Xear Dynamic Bass")
    p_fx.add_argument("--flex-bass", choices=["on", "off"], help="Flex Bass II")
    p_fx.add_argument("--clarity", choices=["on", "off"], help="Xear Voice Clarity")
    p_fx.add_argument("--brilliant", choices=["on", "off"], help="Xear Audio Brilliant")
    p_fx.add_argument("--magic-voice", choices=["off", "monster", "cartoon", "male", "female"], help="Xear Magic Voice preset")
    p_fx.add_argument("--enc", choices=["on", "off"], help="VoClear Environmental Noise Cancellation")

    sub.add_parser("reset", help="Reset all DSP parameters to factory defaults")

    args = parser.parse_args()
    hw = EksaHardwareController()
    assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    dsp = EksaDspEngine(hw, assets_dir)

    if not args.cmd or args.cmd == "status":
        hw.refresh()
        st = hw.state
        print("=== EKSA E900 Pro Hardware Status (ALSA / USB 0d8c:0012) ===")
        print(f"  Connected       : {st.connected} (ALSA card {st.card_index}: {st.card_id})")
        print(f"  Speaker Volume  : L={st.speaker_vol_l}% ({st.speaker_db_l:.1f} dB), R={st.speaker_vol_r}% ({st.speaker_db_r:.1f} dB) | Muted={st.speaker_muted}")
        print(f"  Mic Capture Vol : {st.mic_vol}% ({st.mic_db:.1f} dB) | Muted={st.mic_muted} | HW AGC={st.mic_agc}")
        print(f"  HW Sidetone     : {st.sidetone_vol}% ({st.sidetone_db:.1f} dB) | Muted={st.sidetone_muted}")
        print(f"  Sample Rate     : {st.sample_rate} Hz ({st.bit_depth}-bit)")
        print("\n=== EKSA Xear Real-Time DSP State ===")
        s = dsp.state
        print(f"  7.1 Virtual Spk : {s.get('vss_enabled')} (Mode: {s.get('vss_mode')})")
        print(f"  Xear Surround   : HP={s.get('surround_hp_enabled')}, Max={s.get('surround_max_enabled')}, 3D EX={s.get('gx_enabled')}")
        print(f"  Equalizer (10B) : {s.get('eq_enabled')} (Preset: {s.get('eq_preset')}, Gains: {s.get('eq_bands')})")
        print(f"  Environment FX  : {s.get('em_enabled')} (Preset: {s.get('em_environment')}, Room: {s.get('em_room_size')})")
        print(f"  SingFX          : KeyShift={s.get('singfx_enable_pitch')} ({s.get('singfx_pitch_semitones')} st), VocalFade={s.get('singfx_enable_vocal_fade')} ({s.get('singfx_vocal_fade')}%)")
        print(f"  Bass & Clarity  : FlexBassII={s.get('flex_bass_enabled')}, DynBass={s.get('dyn_bass_enabled')}, SVN={s.get('svn_enabled')}, Clarity={s.get('voice_clarity_enabled')}, Brilliant={s.get('brilliant_enabled')}")
        print(f"  Mic APO         : ENC={s.get('enc_enabled')}, NR={s.get('nr_enabled')}, Echo={s.get('mic_echo_enabled')}, MagicVoice={s.get('magic_voice_enabled')} (type={s.get('magic_voice_type')})")
        return 0

    if args.cmd == "presets":
        print("10-Band EQ Frequencies (Hz):", EQ_FREQS)
        print("\nBuilt-in EQ Presets:")
        for k, v in BUILTIN_EQ_PRESETS.items():
            print(f"  {k:12s}: {v}")
        print("\n27 Environment Presets:")
        for idx, k in enumerate(ENVIRONMENT_PRESETS.keys(), 1):
            print(f"  {idx:2d}. {k}")
        return 0

    if args.cmd == "volume":
        if args.level is not None:
            hw.set_speaker_volume(args.level, args.level)
        elif args.left is not None or args.right is not None:
            hw.refresh()
            l = args.left if args.left is not None else hw.state.speaker_vol_l
            r = args.right if args.right is not None else hw.state.speaker_vol_r
            hw.set_speaker_volume(l, r)
        if args.mute is not None:
            hw.set_speaker_mute(args.mute == "on")
        print("Updated speaker volume.")
        return 0

    if args.cmd == "mic":
        if args.level is not None:
            hw.set_mic_volume(args.level)
        if args.mute is not None:
            hw.set_mic_mute(args.mute == "on")
        if args.agc is not None:
            hw.set_agc(args.agc == "on")
        print("Updated microphone hardware settings.")
        return 0

    if args.cmd == "sidetone":
        if args.level is not None:
            hw.set_sidetone_volume(args.level)
        if args.enable is not None:
            hw.set_sidetone_mute(args.enable == "off")
        print("Updated hardware sidetone.")
        return 0

    if args.cmd == "eq":
        if args.enable is not None:
            dsp.state["eq_enabled"] = (args.enable == "on")
        if args.preset is not None:
            if args.preset not in BUILTIN_EQ_PRESETS and args.preset not in dsp.custom_eq_presets:
                print(f"Unknown EQ preset: {args.preset}", file=sys.stderr)
                return 1
            dsp.state["eq_preset"] = args.preset
            bands = BUILTIN_EQ_PRESETS.get(args.preset) or dsp.custom_eq_presets[args.preset]
            dsp.state["eq_bands"] = list(bands)
            dsp.state["eq_enabled"] = True
        if args.bands is not None:
            dsp.state["eq_bands"] = [max(-12.0, min(12.0, float(x))) for x in args.bands]
            dsp.state["eq_enabled"] = True
        dsp.save_state()
        print("Saved EQ settings.")
        return 0

    if args.cmd == "env":
        if args.enable is not None:
            dsp.state["em_enabled"] = (args.enable == "on")
        if args.preset is not None:
            if args.preset not in ENVIRONMENT_PRESETS:
                print(f"Unknown Environment preset: {args.preset}", file=sys.stderr)
                return 1
            dsp.state["em_environment"] = args.preset
            dsp.state["em_enabled"] = True
        if args.room is not None:
            dsp.state["em_room_size"] = args.room
        dsp.save_state()
        print("Saved Environment settings.")
        return 0

    if args.cmd == "surround":
        if args.vss is not None:
            dsp.state["vss_enabled"] = (args.vss == "on")
        if args.headphone is not None:
            dsp.state["surround_hp_enabled"] = (args.headphone == "on")
        if args.max is not None:
            dsp.state["surround_max_enabled"] = (args.max == "on")
        if args.gx is not None:
            dsp.state["gx_enabled"] = (args.gx == "on")
        dsp.save_state()
        print("Saved Surround settings.")
        return 0

    if args.cmd == "fx":
        if args.svn is not None:
            dsp.state["svn_enabled"] = (args.svn == "on")
        if args.dyn_bass is not None:
            dsp.state["dyn_bass_enabled"] = (args.dyn_bass == "on")
        if args.flex_bass is not None:
            dsp.state["flex_bass_enabled"] = (args.flex_bass == "on")
        if args.clarity is not None:
            dsp.state["voice_clarity_enabled"] = (args.clarity == "on")
        if args.brilliant is not None:
            dsp.state["brilliant_enabled"] = (args.brilliant == "on")
        if args.magic_voice is not None:
            mv_map = {"monster": 1, "cartoon": 2, "male": 3, "female": 4}
            if args.magic_voice == "off":
                dsp.state["magic_voice_enabled"] = False
            else:
                dsp.state["magic_voice_enabled"] = True
                dsp.state["magic_voice_type"] = mv_map[args.magic_voice]
        if args.enc is not None:
            dsp.state["enc_enabled"] = (args.enc == "on")
        dsp.save_state()
        print("Saved FX settings.")
        return 0

    if args.cmd == "reset":
        dsp.reset_defaults()
        print("Reset all DSP settings to factory defaults.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
