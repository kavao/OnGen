import importlib.util
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PATH = ROOT / "tools" / "sound" / "sfx_generator.py"


def _load_canonical():
    spec = importlib.util.spec_from_file_location("ongen_sound_sfx_generator", CANONICAL_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"正本を読み込めません: {CANONICAL_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["ongen_sound_sfx_generator"] = module
    spec.loader.exec_module(module)
    return module


sg = _load_canonical()

ADSR = sg.ADSR
FMConfig = sg.FMConfig
FM_TONE_PRESETS = sg.FM_TONE_PRESETS
LFOConfig = sg.LFOConfig
MIX_HEADROOM = sg.MIX_HEADROOM
NoteEvent = sg.NoteEvent
SFX_PRESETS = sg.SFX_PRESETS
SynthConfig = sg.SynthConfig
abc_default_unit_from_meter = sg.abc_default_unit_from_meter
abc_length_multiplier = sg.abc_length_multiplier
abc_quarter_note_tempo = sg.abc_quarter_note_tempo
apply_master_fade = sg.apply_master_fade
apply_audio_filter = sg.apply_audio_filter
build_config_from_args = sg.build_config_from_args
create_parser = sg.create_parser
generate_colored_noise = sg.generate_colored_noise
main = sg.main
mix_tracks = sg.mix_tracks
load_preset = sg.load_preset
note_name_to_freq = sg.note_name_to_freq
parse_abc = sg.parse_abc
parse_mml = sg.parse_mml
parse_pyxel_mml = sg.parse_pyxel_mml
parse_mml_by_dialect = sg.parse_mml_by_dialect
parse_mml_source = sg.parse_mml_source
report_pyxel_compat_issues = sg.report_pyxel_compat_issues
PYXEL_TONE_MAP = sg.PYXEL_TONE_MAP
resolve_track_specs = sg.resolve_track_specs
split_ppmck_tracks = sg.split_ppmck_tracks
has_ppmck_track_headers = sg.has_ppmck_track_headers
PPMCK_CHANNEL_MAP = sg.PPMCK_CHANNEL_MAP
play_audio = sg.play_audio
synthesize_note = sg.synthesize_note
synthesize_sequence = sg.synthesize_sequence
__version__ = sg.__version__


class SfxGeneratorVersionTests(unittest.TestCase):
    def test_version_matches_rulesync_metadata(self) -> None:
        meta_path = ROOT / ".rulesync" / "metadata" / "sfx-generator.json"
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertEqual(__version__, metadata["version"])
        header = CANONICAL_PATH.read_text(encoding="utf-8").splitlines()[1]
        self.assertIn(metadata["version"], header)
        self.assertIn("Version:", header)


class PitchTests(unittest.TestCase):
    def test_equal_temperament_reference_pitches(self) -> None:
        self.assertAlmostEqual(note_name_to_freq("A", 4), 440.0, places=10)
        self.assertAlmostEqual(note_name_to_freq("C", 4), 261.625565, places=5)


class AudioQualityTests(unittest.TestCase):
    def test_square_anti_alias_softens_discontinuities(self) -> None:
        event = NoteEvent(frequency=440.0, duration=0.1)
        smooth = synthesize_note(event, SynthConfig(waveform="square", anti_alias=True))
        raw = synthesize_note(event, SynthConfig(waveform="square", anti_alias=False))
        self.assertLess(np.max(np.abs(np.diff(smooth))), np.max(np.abs(np.diff(raw))))

    def test_track_mix_keeps_headroom(self) -> None:
        mixed = mix_tracks([np.ones(10), np.ones(10)])
        self.assertAlmostEqual(float(np.max(np.abs(mixed))), MIX_HEADROOM)

    def test_master_fade_starts_at_zero_and_reaches_original_level(self) -> None:
        source = np.ones(441)
        faded = apply_master_fade(source, 0.005)
        self.assertEqual(faded[0], 0.0)
        self.assertAlmostEqual(faded[220], 1.0)
        self.assertTrue(np.array_equal(faded[221:], source[221:]))

    def test_duty_lfo_changes_square_pulse_width_over_time(self) -> None:
        config = SynthConfig(
            waveform="square",
            anti_alias=False,
            adsr=ADSR(0, 0, 1, 0),
            lfo=LFOConfig(enabled=True, rate=2.0, depth=0.5, target="duty"),
        )
        audio = synthesize_note(NoteEvent(frequency=440.0, duration=1.0), config)
        chunks = np.array_split(audio, 8)
        positive_ratios = [float(np.mean(chunk > 0)) for chunk in chunks]
        self.assertGreater(max(positive_ratios) - min(positive_ratios), 0.15)

    def test_fm_and_duty_lfo_can_be_combined(self) -> None:
        base = SynthConfig(
            waveform="square",
            anti_alias=False,
            adsr=ADSR(0, 0, 1, 0),
            lfo=LFOConfig(enabled=True, rate=2.0, depth=0.5, target="duty"),
        )
        with_fm = SynthConfig(
            waveform="square",
            anti_alias=False,
            adsr=base.adsr,
            lfo=base.lfo,
            fm=FMConfig(enabled=True, mod_ratio=2.0, mod_index=3.0),
        )
        event = NoteEvent(frequency=440.0, duration=0.25)
        self.assertFalse(np.array_equal(synthesize_note(event, base), synthesize_note(event, with_fm)))

    def test_noise_colors_have_increasing_low_frequency_bias(self) -> None:
        def low_high_ratio(color: str) -> float:
            spectrum = np.abs(np.fft.rfft(generate_colored_noise(44100, color))) ** 2
            frequencies = np.fft.rfftfreq(44100, 1 / 44100)
            low = spectrum[(frequencies >= 100) & (frequencies < 1000)].mean()
            high = spectrum[(frequencies >= 5000) & (frequencies < 10000)].mean()
            return float(low / high)

        white = low_high_ratio("white")
        pink = low_high_ratio("pink")
        brown = low_high_ratio("brown")
        self.assertLess(white, pink)
        self.assertLess(pink, brown)

    def test_lowpass_and_highpass_attenuate_expected_bands(self) -> None:
        t = np.arange(44100) / 44100
        low = np.sin(2 * np.pi * 200 * t)
        high = np.sin(2 * np.pi * 8000 * t)
        source = low + high
        lowpassed = apply_audio_filter(source, "lowpass", 1000)
        highpassed = apply_audio_filter(source, "highpass", 1000)
        self.assertGreater(abs(np.vdot(lowpassed, low)), abs(np.vdot(lowpassed, high)))
        self.assertGreater(abs(np.vdot(highpassed, high)), abs(np.vdot(highpassed, low)))

    def test_fm_tone_presets_are_enabled_two_operator_configs(self) -> None:
        self.assertEqual(set(FM_TONE_PRESETS), {"bass", "bell", "e-piano"})
        for preset in FM_TONE_PRESETS.values():
            self.assertTrue(preset["fm"].enabled)

    def test_all_sfx_presets_render_without_clipping(self) -> None:
        expected = {
            "jump", "coin", "hit", "explosion", "laser",
            "powerup", "select", "confirm", "damage", "victory",
        }
        self.assertEqual(set(SFX_PRESETS), expected)
        for name, preset in SFX_PRESETS.items():
            self.assertTrue(preset.get("description"))
            events, config = load_preset(name)
            audio = synthesize_sequence(events, config)
            self.assertGreater(audio.size, 0)
            self.assertLess(float(np.max(np.abs(audio))), 0.99)


class TrackStyleTests(unittest.TestCase):
    def test_track_style_parses_in_declared_order(self) -> None:
        parser = create_parser()
        args = parser.parse_args(
            ["--track-style", "sine", "--track-style", "triangle"]
        )
        self.assertEqual(args.track_style, ["sine", "triangle"])

    def test_track_style_overrides_waveform_for_that_track(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = str(Path(tmpdir) / "track_style_sample")
            exit_code = main(
                [
                    "--input", "O4 L4 T120 C E G C",
                    "--style", "square",
                    "--track", "O4 L4 T120 C E G C",
                    "--track-style", "sine",
                    "-o", output,
                ]
            )
            self.assertEqual(exit_code, 0)
            _, audio = wavfile.read(output + ".wav")
            self.assertGreater(audio.size, 0)


class PlaybackTests(unittest.TestCase):
    def test_play_flag_defaults_to_false(self) -> None:
        parser = create_parser()
        args = parser.parse_args(["--input", "O4 L4 T120 C"])
        self.assertFalse(args.play)

    def test_play_flag_parses(self) -> None:
        parser = create_parser()
        args = parser.parse_args(["--input", "O4 L4 T120 C", "--play"])
        self.assertTrue(args.play)

    def test_play_reports_error_when_ffplay_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = str(Path(tmpdir) / "play_sample")
            with patch.object(sg, "which", return_value=None):
                exit_code = main(
                    ["--input", "O4 L4 T120 C", "--play", "-o", output]
                )
            self.assertEqual(exit_code, 1)

    def test_play_audio_raises_on_ffplay_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "sample.wav"
            wavfile.write(str(wav_path), 44100, np.zeros(10, dtype=np.int16))
            fake_result = type(
                "Result", (), {"returncode": 1, "stderr": "boom", "stdout": ""}
            )()
            with patch.object(sg, "subprocess") as mock_subprocess:
                mock_subprocess.run.return_value = fake_result
                with self.assertRaises(RuntimeError):
                    play_audio(wav_path)


class AbcTimingTests(unittest.TestCase):
    def test_q_header_uses_declared_beat_unit(self) -> None:
        self.assertEqual(abc_quarter_note_tempo("1/4=120"), 120.0)
        self.assertEqual(abc_quarter_note_tempo("1/8=120"), 60.0)

    def test_default_length_follows_abc_standard(self) -> None:
        self.assertEqual(abc_default_unit_from_meter("2/4"), 1.0 / 16.0)
        self.assertEqual(abc_default_unit_from_meter("3/4"), 1.0 / 8.0)
        self.assertEqual(abc_default_unit_from_meter("C"), 1.0 / 8.0)

    def test_fractional_length_forms(self) -> None:
        self.assertEqual(abc_length_multiplier("/"), 0.5)
        self.assertEqual(abc_length_multiplier("//"), 0.25)
        self.assertEqual(abc_length_multiplier("/2"), 0.5)
        self.assertEqual(abc_length_multiplier("3/2"), 1.5)


class TulipBenchmarkTests(unittest.TestCase):
    def test_tulip_score_has_expected_pitch_and_timing(self) -> None:
        events = parse_abc((ROOT / "scores" / "tulip.abc").read_text(encoding="utf-8"))
        expected_notes = (
            "C D E C D E G E D C D E D "
            "C D E C D E G E D C D E C "
            "G G E G A A G E E D D C"
        ).split()

        self.assertEqual(len(events), len(expected_notes))
        for event, note in zip(events, expected_notes):
            self.assertIsNotNone(event.frequency)
            self.assertTrue(math.isclose(event.frequency, note_name_to_freq(note, 4), rel_tol=1e-12))

        self.assertAlmostEqual(sum(event.duration for event in events), 12.0)
        self.assertAlmostEqual(events[0].duration, 0.25)
        self.assertAlmostEqual(events[2].duration, 0.5)
        self.assertAlmostEqual(events[-1].duration, 1.0)

    def test_inline_comment_does_not_create_notes(self) -> None:
        events = parse_abc("X:1\nL:1/4\nK:C\nC % BAD should not become notes")
        self.assertEqual(len(events), 1)


class FastPlaybackBenchmarkTests(unittest.TestCase):
    def test_fur_elise_fast_sample_uses_short_notes_and_correct_accidentals(self) -> None:
        events = parse_abc(
            (ROOT / "scores" / "fur_elise_fast_sample.abc").read_text(encoding="utf-8")
        )
        self.assertEqual(len(events), 41)
        self.assertAlmostEqual(events[0].duration, 0.25)
        self.assertAlmostEqual(events[0].frequency, note_name_to_freq("E", 5))
        self.assertAlmostEqual(events[1].frequency, note_name_to_freq("D#", 5))
        self.assertAlmostEqual(events[6].frequency, note_name_to_freq("D", 5))
        self.assertAlmostEqual(events[27].frequency, note_name_to_freq("D", 5))
        self.assertEqual(sum(event.frequency is None for event in events), 6)
        self.assertAlmostEqual(sum(event.duration for event in events), 12.0)


class StarSpangledBannerBenchmarkTests(unittest.TestCase):
    def test_verified_opening_pitch_and_rhythm(self) -> None:
        events = parse_abc(
            (ROOT / "scores" / "star_spangled_banner_sample.abc").read_text(encoding="utf-8")
        )
        expected_notes = ["G", "E", "C", "E", "G", "C", "E", "D", "C", "E", "F#", "G"]
        expected_octaves = [4, 4, 4, 4, 4, 5, 5, 5, 5, 4, 4, 4]
        sounding = [event for event in events if event.frequency is not None]

        self.assertEqual(len(sounding), len(expected_notes))
        for event, note, octave in zip(sounding, expected_notes, expected_octaves):
            self.assertAlmostEqual(event.frequency, note_name_to_freq(note, octave))

        sixteenth = 60.0 / 87 / 4
        self.assertAlmostEqual(events[0].duration, sixteenth * 3)
        self.assertAlmostEqual(events[1].duration, sixteenth)
        self.assertAlmostEqual(events[5].duration, sixteenth * 8)
        self.assertIsNone(events[-1].frequency)
        self.assertAlmostEqual(sum(event.duration for event in events), (60.0 / 87) * 13)


class AmazingGraceBenchmarkTests(unittest.TestCase):
    def test_new_britain_melody_pitch_and_rhythm(self) -> None:
        events = parse_abc((ROOT / "scores" / "amazing_grace.abc").read_text(encoding="utf-8"))
        expected = (
            "D G B G B A G E D D "
            "G B G B A B D D B "
            "D B G B A G E D D "
            "G B G B A G G"
        ).split()
        expected_octaves = [5 if note == "D" and index in {16, 17, 19} else 4
                            for index, note in enumerate(expected)]

        self.assertEqual(len(events), len(expected))
        for event, note, octave in zip(events, expected, expected_octaves):
            self.assertAlmostEqual(event.frequency, note_name_to_freq(note, octave))

        quarter = 60.0 / 80
        self.assertAlmostEqual(events[0].duration, quarter)
        self.assertAlmostEqual(events[1].duration, quarter * 2)
        self.assertAlmostEqual(events[2].duration, quarter / 2)
        self.assertAlmostEqual(sum(event.duration for event in events), 36.0)


class CanonInDBenchmarkTests(unittest.TestCase):
    def test_ground_bass_pitch_and_timing(self) -> None:
        events = parse_mml((ROOT / "scores" / "canon_in_d_bass.mml").read_text(encoding="utf-8"))
        expected_notes = "D A B F# G D G A D A B F# G D G A".split()

        self.assertEqual(len(events), len(expected_notes))
        for event, note in zip(events, expected_notes):
            self.assertAlmostEqual(event.frequency, note_name_to_freq(note, 3))

        quarter = 60.0 / 96
        for event in events:
            self.assertAlmostEqual(event.duration, quarter)

    def test_round_voices_form_canon_with_bass(self) -> None:
        bass = parse_mml((ROOT / "scores" / "canon_in_d_bass.mml").read_text(encoding="utf-8"))
        voice1 = parse_mml((ROOT / "scores" / "canon_in_d_round1.mml").read_text(encoding="utf-8"))
        voice2 = parse_mml((ROOT / "scores" / "canon_in_d_round2.mml").read_text(encoding="utf-8"))
        expected_notes = "D A B F# G D G A D A B F# G D G A".split()

        self.assertEqual(len(voice1), len(expected_notes))
        for event, note in zip(voice1, expected_notes):
            self.assertAlmostEqual(event.frequency, note_name_to_freq(note, 4))

        # voice2はバスより2拍子(2小節)遅れて同じ旋律を演奏するカノン構造。
        self.assertEqual(len(voice2), 2 + 8)
        self.assertIsNone(voice2[0].frequency)
        self.assertIsNone(voice2[1].frequency)
        for event, note in zip(voice2[2:], expected_notes[:8]):
            self.assertAlmostEqual(event.frequency, note_name_to_freq(note, 4))

        self.assertAlmostEqual(
            sum(event.duration for event in bass),
            sum(event.duration for event in voice1),
        )
        self.assertAlmostEqual(
            sum(event.duration for event in voice1),
            sum(event.duration for event in voice2),
        )


class MmlNoteLengthTests(unittest.TestCase):
    def test_note_without_digit_uses_default_length(self) -> None:
        events = parse_mml("O4 L8 T120 C")
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].frequency, note_name_to_freq("C", 4))
        self.assertAlmostEqual(events[0].duration, 0.25)

    def test_note_with_digit_overrides_length(self) -> None:
        events = parse_mml("O4 L8 T120 C4")
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].frequency, note_name_to_freq("C", 4))
        self.assertAlmostEqual(events[0].duration, 0.5)

    def test_dotted_note_with_length_override(self) -> None:
        events = parse_mml("O4 T120 C4.")
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].duration, 0.75)

    def test_relative_octave_commands_shift_pitch(self) -> None:
        events = parse_mml("O4 T120 L4 C >C <<C")
        self.assertEqual(len(events), 3)
        self.assertAlmostEqual(events[0].frequency, note_name_to_freq("C", 4))
        self.assertAlmostEqual(events[1].frequency, note_name_to_freq("C", 5))
        self.assertAlmostEqual(events[2].frequency, note_name_to_freq("C", 3))

    def test_tie_combines_durations_into_single_event(self) -> None:
        events = parse_mml("O4 T120 L4 C&C")
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].frequency, note_name_to_freq("C", 4))
        self.assertAlmostEqual(events[0].duration, 60.0 / 120 * 2)

    def test_tie_chain_combines_multiple_durations(self) -> None:
        events = parse_mml("O4 T120 L4 C&C&C8")
        self.assertEqual(len(events), 1)
        quarter = 60.0 / 120
        self.assertAlmostEqual(events[0].duration, quarter * 2 + quarter / 2)

    def test_loop_with_direct_repeat_count(self) -> None:
        events = parse_mml("O4 T120 L4 [CD]3")
        self.assertEqual(len(events), 6)
        for index, (name, octave) in enumerate([("C", 4), ("D", 4)] * 3):
            self.assertAlmostEqual(events[index].frequency, note_name_to_freq(name, octave))

    def test_rest_with_explicit_length_creates_silent_event(self) -> None:
        events = parse_mml("O4 T120 L4 C R8 C")
        self.assertEqual(len(events), 3)
        self.assertIsNone(events[1].frequency)
        eighth = 60.0 / 120 / 2
        self.assertAlmostEqual(events[1].duration, eighth)

    def test_bare_rest_uses_default_length(self) -> None:
        events = parse_mml("O4 T120 L4 R")
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0].frequency)
        quarter = 60.0 / 120
        self.assertAlmostEqual(events[0].duration, quarter)

    def test_unsupported_token_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_mml("O4 T120 L4 C Z")

    def test_semicolon_comment_is_stripped_before_parsing(self) -> None:
        events = parse_mml("O4 T120 L4 C4; trailing comment")
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].frequency, note_name_to_freq("C", 4))

    def test_preset_pitch_sequences_match_expected_notes(self) -> None:
        expected_by_preset = {
            "jump": [("C", 4), ("E", 4), ("G", 4), ("C", 5)],
            "coin": [("B", 5), ("E", 6), ("B", 6)],
            "powerup": [("C", 4), ("E", 4), ("G", 4), ("C", 5), ("E", 5), ("G", 5), ("C", 6)],
            "damage": [("A", 4), ("F", 4), ("D", 4), ("A", 3)],
            # R16 は休符イベント(frequency=None)を生成する。
            "victory": [
                ("C", 4), ("E", 4), ("G", 4), ("C", 5), None,
                ("G", 4), ("C", 5), ("E", 5), ("G", 5), ("C", 6),
            ],
        }
        for preset_name, expected_notes in expected_by_preset.items():
            events = parse_mml(SFX_PRESETS[preset_name]["mml"])
            self.assertEqual(len(events), len(expected_notes))
            for event, expected in zip(events, expected_notes):
                if expected is None:
                    self.assertIsNone(event.frequency)
                    continue
                name, octave = expected
                self.assertAlmostEqual(event.frequency, note_name_to_freq(name, octave))


class MmlPhase2CompatTests(unittest.TestCase):
    def test_gate_shortens_sound_and_inserts_rest(self) -> None:
        events = parse_mml("O4 T120 L4 Q4 C4")
        quarter = 60.0 / 120
        self.assertEqual(len(events), 2)
        self.assertAlmostEqual(events[0].frequency, note_name_to_freq("C", 4))
        self.assertAlmostEqual(events[0].duration, quarter / 2)
        self.assertIsNone(events[1].frequency)
        self.assertAlmostEqual(events[1].duration, quarter / 2)

    def test_gate_frame_adjustment_is_added_after_ratio(self) -> None:
        events = parse_mml("O4 T120 L4 Q4,6 C4")
        quarter = 60.0 / 120
        self.assertEqual(len(events), 2)
        self.assertAlmostEqual(events[0].duration, quarter / 2 + 0.1)
        self.assertAlmostEqual(events[1].duration, quarter / 2 - 0.1)

    def test_gate_denominator_directive_changes_ratio(self) -> None:
        events = parse_mml("#GATE-DENOM 4\nO4 T120 L4 Q2 C4")
        quarter = 60.0 / 120
        self.assertAlmostEqual(events[0].duration, quarter / 2)
        self.assertAlmostEqual(events[1].duration, quarter / 2)

    def test_gate_and_tie_are_applied_to_combined_duration(self) -> None:
        events = parse_mml("O4 T120 L4 Q4 C&C")
        quarter = 60.0 / 120
        self.assertEqual(len(events), 2)
        self.assertAlmostEqual(events[0].frequency, note_name_to_freq("C", 4))
        self.assertAlmostEqual(events[0].duration, quarter)
        self.assertIsNone(events[1].frequency)
        self.assertAlmostEqual(events[1].duration, quarter)

    def test_tie_rejects_different_pitch_or_rest(self) -> None:
        for mml in ("C&D", "R&C"):
            with self.subTest(mml=mml), self.assertRaises(ValueError):
                parse_mml(mml)

    def test_invalid_gate_values_raise_value_error(self) -> None:
        for mml in (
            "Q9 C4",
            "Q4,-60 C4",
            "Q8,1 C4",
            "#GATE-DENOM 0\nC4",
            "#GATE-DENOM -1\nC4",
        ):
            with self.subTest(mml=mml), self.assertRaises(ValueError):
                parse_mml(mml)

    def test_transpose_shifts_pitch(self) -> None:
        events = parse_mml("O4 T120 L4 K+12 C4")
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].frequency, note_name_to_freq("C", 5))

    def test_invalid_transpose_values_raise_value_error(self) -> None:
        for mml in ("K-128 C4", "K127 C4"):
            with self.subTest(mml=mml), self.assertRaises(ValueError):
                parse_mml(mml)

    def test_direct_note_number_matches_ppmck_convention(self) -> None:
        events = parse_mml("T120 L4 N32,4")
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].frequency, note_name_to_freq("C", 4))
        self.assertAlmostEqual(events[0].duration, 0.5)

    def test_direct_note_number_uses_sixteen_values_per_octave(self) -> None:
        events = parse_mml("T120 L4 N0 N11 N13 N16")
        self.assertAlmostEqual(events[0].frequency, note_name_to_freq("C", 2))
        self.assertAlmostEqual(events[1].frequency, note_name_to_freq("B", 2))
        self.assertAlmostEqual(events[2].frequency, note_name_to_freq("A", 1))
        self.assertAlmostEqual(events[3].frequency, note_name_to_freq("C", 3))

    def test_invalid_direct_note_numbers_raise_value_error(self) -> None:
        for mml in ("N12", "N96"):
            with self.subTest(mml=mml), self.assertRaises(ValueError):
                parse_mml(mml)

    def test_hash_directive_lines_are_skipped(self) -> None:
        events = parse_mml("#TITLE sample\nO4 T120 L4 C4")
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].frequency, note_name_to_freq("C", 4))

    def test_comment_or_metadata_only_input_is_empty(self) -> None:
        self.assertEqual(parse_mml("; comment only"), [])
        self.assertEqual(parse_mml("#TITLE metadata only"), [])

    def test_at_q_shortens_sound_by_frames(self) -> None:
        events = parse_mml("T120 L4 @Q15 N32,4")
        self.assertEqual(len(events), 2)
        self.assertAlmostEqual(events[0].duration, 0.5 - (15 / 60.0))
        self.assertIsNone(events[1].frequency)
        self.assertAlmostEqual(events[1].duration, 15 / 60.0)

    def test_invalid_at_q_value_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_mml("@Q65536 C4")

    def test_ppmck_phase2_sample_score(self) -> None:
        events = parse_mml(
            (ROOT / "scores" / "ppmck_phase2_sample.mml").read_text(encoding="utf-8")
        )
        quarter = 60.0 / 120
        self.assertEqual(len(events), 6)
        self.assertAlmostEqual(events[0].frequency, note_name_to_freq("C", 4))
        self.assertAlmostEqual(events[0].duration, quarter / 2 + 0.1)
        self.assertIsNone(events[1].frequency)
        self.assertAlmostEqual(events[2].frequency, note_name_to_freq("C", 5))
        self.assertAlmostEqual(events[3].frequency, note_name_to_freq("C", 4))
        self.assertAlmostEqual(events[4].frequency, note_name_to_freq("C", 3))
        self.assertAlmostEqual(events[4].duration, quarter / 2 - 0.05)
        self.assertIsNone(events[5].frequency)


class MmlPhase3CompatTests(unittest.TestCase):
    def test_split_line_start_track_headers(self) -> None:
        split = split_ppmck_tracks("A T120 C4\nB T120 E4")
        self.assertIsNotNone(split)
        assert split is not None
        self.assertEqual(set(split.keys()), {"A", "B"})
        self.assertIn("T120 C4", split["A"])
        self.assertIn("T120 E4", split["B"])

    def test_split_inline_track_switch(self) -> None:
        split = split_ppmck_tracks("A C4\nB D4")
        self.assertIsNotNone(split)
        assert split is not None
        self.assertEqual(split["A"], "C4")
        self.assertEqual(split["B"], "D4")

    def test_split_inline_plural_header(self) -> None:
        split = split_ppmck_tracks("AB C4 E4")
        self.assertIsNotNone(split)
        assert split is not None
        self.assertEqual(split["A"], "C4 E4")
        self.assertEqual(split["B"], "C4 E4")

    def test_split_continues_across_lines_without_header(self) -> None:
        split = split_ppmck_tracks("A T120\nC4 D4")
        self.assertIsNotNone(split)
        assert split is not None
        self.assertEqual(split["A"], "T120 C4 D4")

    def test_single_track_without_headers_returns_none(self) -> None:
        self.assertIsNone(split_ppmck_tracks("O4 T120 L4 C4 D4"))
        self.assertIsNone(split_ppmck_tracks("A C4 D4 E4"))
        self.assertIsNone(split_ppmck_tracks("C D E F"))

    def test_single_clear_track_header_is_detected(self) -> None:
        self.assertEqual(split_ppmck_tracks("A @1 C4"), {"A": "@1 C4"})

    def test_lines_before_first_track_header_apply_to_every_track(self) -> None:
        split = split_ppmck_tracks("T120 L8\nA c4\nB e4")
        self.assertEqual(split, {"A": "T120 L8 c4", "B": "T120 L8 e4"})

    def test_parse_mml_source_returns_single_track_without_headers(self) -> None:
        tracks = parse_mml_source("O4 T120 L4 C4")
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0].channel, "")
        self.assertEqual(len(tracks[0].events), 1)

    def test_parse_mml_source_assigns_channel_defaults(self) -> None:
        tracks = parse_mml_source("A C4\nC O2 L2 C2\nD R16")
        by_channel = {track.channel: track for track in tracks}
        self.assertEqual(by_channel["A"].synth_overrides["waveform"], "square")
        self.assertEqual(by_channel["C"].synth_overrides["waveform"], "triangle")
        self.assertEqual(by_channel["D"].synth_overrides["waveform"], "noise")
        self.assertAlmostEqual(by_channel["A"].events[0].frequency, note_name_to_freq("C", 4))
        self.assertAlmostEqual(by_channel["C"].events[0].frequency, note_name_to_freq("C", 2))

    def test_pulse_duty_on_channel_a_uses_ppmck_mapping(self) -> None:
        for token, expected in (("@0", 0.125), ("@1", 0.25), ("@2", 0.5), ("@3", 0.75)):
            with self.subTest(token=token):
                event = parse_mml_source(f"A {token} C4")[0].events[0]
                self.assertEqual(event.waveform, "square")
                self.assertAlmostEqual(event.duty, expected)

    def test_track_style_still_targets_cli_extra_tracks(self) -> None:
        parser = create_parser()
        args = parser.parse_args(
            [
                "--input-file",
                str(ROOT / "scores" / "ppmck_phase3_sample.mml"),
                "--track",
                "O4 C4",
                "--track-style",
                "sine",
            ]
        )
        config = build_config_from_args(args)
        specs = resolve_track_specs(args, config)
        self.assertEqual(len(specs), 5)
        self.assertEqual(specs[-1][1].waveform, "sine")
        self.assertEqual(specs[0][1].waveform, "square")

    def test_ppmck_phase3_sample_score(self) -> None:
        tracks = parse_mml_source(
            (ROOT / "scores" / "ppmck_phase3_sample.mml").read_text(encoding="utf-8")
        )
        self.assertEqual([track.channel for track in tracks], ["A", "B", "C", "D"])
        by_channel = {track.channel: track for track in tracks}
        self.assertEqual(len(by_channel["A"].events), 4)
        self.assertEqual(len(by_channel["B"].events), 3)
        self.assertEqual(len(by_channel["C"].events), 3)
        self.assertEqual(len(by_channel["D"].events), 4)
        self.assertAlmostEqual(by_channel["A"].events[0].frequency, note_name_to_freq("C", 4))
        self.assertAlmostEqual(by_channel["B"].events[0].frequency, note_name_to_freq("E", 4))
        self.assertAlmostEqual(by_channel["C"].events[0].frequency, note_name_to_freq("C", 3))

    def test_embedded_tracks_cli_mixes_without_track_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = str(Path(tmpdir) / "phase3_embedded")
            result = main(
                [
                    "--input-file",
                    str(ROOT / "scores" / "ppmck_phase3_sample.mml"),
                    "-o",
                    output,
                ]
            )
            self.assertEqual(result, 0)
            wav_path = Path(f"{output}.wav")
            self.assertTrue(wav_path.exists())
            _, audio = wavfile.read(wav_path)
            self.assertGreater(audio.size, 0)


class SfxMmlSampleTests(unittest.TestCase):
    SFX_SAMPLES: list[tuple[str, int, str | None]] = [
        ("sfx_jump_sample.mml", 4, "square"),
        ("sfx_coin_sample.mml", 3, "sine"),
        ("sfx_laser_sample.mml", 6, "sawtooth"),
        ("sfx_ui_sample.mml", 5, "sine"),
    ]

    def test_sfx_sample_scores_parse_and_render(self) -> None:
        for filename, min_pitched, expected_waveform in self.SFX_SAMPLES:
            with self.subTest(filename=filename):
                text = (ROOT / "scores" / filename).read_text(encoding="utf-8")
                tracks = parse_mml_source(text)
                pitched = [
                    event
                    for track in tracks
                    for event in track.events
                    if event.frequency is not None
                ]
                self.assertGreaterEqual(len(pitched), min_pitched)
                self.assertEqual(pitched[0].waveform, expected_waveform)
                audio = synthesize_sequence(pitched, SynthConfig())
                self.assertGreater(audio.size, 0)
                self.assertLessEqual(np.max(np.abs(audio)), MIX_HEADROOM)

    def test_sfx_hit_sample_uses_noise_channel(self) -> None:
        tracks = parse_mml_source(
            (ROOT / "scores" / "sfx_hit_sample.mml").read_text(encoding="utf-8")
        )
        self.assertEqual([track.channel for track in tracks], ["D"])
        pitched = [event for event in tracks[0].events if event.frequency is not None]
        self.assertEqual(len(pitched), 1)
        self.assertEqual(pitched[0].waveform, "noise")

    def test_sfx_kick_sample_mixes_body_and_click(self) -> None:
        tracks = parse_mml_source(
            (ROOT / "scores" / "sfx_kick_sample.mml").read_text(encoding="utf-8")
        )
        self.assertEqual([track.channel for track in tracks], ["A", "D"])
        by_channel = {track.channel: track for track in tracks}
        body = [event for event in by_channel["A"].events if event.frequency is not None][0]
        click = [event for event in by_channel["D"].events if event.frequency is not None][0]
        self.assertEqual(body.waveform, "sine")
        self.assertEqual(click.waveform, "noise")
        self.assertGreater(body.duration, click.duration)

    def test_sfx_explosion_sample_layers_impact_and_noise_tail(self) -> None:
        tracks = parse_mml_source(
            (ROOT / "scores" / "sfx_explosion_sample.mml").read_text(encoding="utf-8")
        )
        self.assertEqual([track.channel for track in tracks], ["A", "B", "D"])
        by_channel = {track.channel: track for track in tracks}
        impact = [event for event in by_channel["A"].events if event.frequency is not None][0]
        crackle = [event for event in by_channel["B"].events if event.frequency is not None][0]
        tail = [event for event in by_channel["D"].events if event.frequency is not None][0]
        self.assertEqual(impact.waveform, "square")
        self.assertEqual(crackle.waveform, "square")
        self.assertEqual(tail.waveform, "noise")
        self.assertLess(impact.duration, crackle.duration)
        self.assertLess(crackle.duration, tail.duration)
        self.assertAlmostEqual(tail.duration, 1.2, places=2)

    def test_cli_sfx_explosion_sample_generates_wav(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "explosion"
            argv = [
                "sfx_generator.py",
                "--input-file",
                str(ROOT / "scores" / "sfx_explosion_sample.mml"),
                "--noise-color",
                "brown",
                "--filter",
                "lowpass",
                "--cutoff",
                "2000",
                "--attack",
                "0.001",
                "--decay",
                "0.35",
                "--sustain",
                "0.05",
                "--release",
                "0.3",
                "--fade-in",
                "0",
                "-o",
                str(out),
            ]
            with patch.object(sys, "argv", argv):
                main()
            wav_path = out.with_suffix(".wav")
            self.assertTrue(wav_path.exists())
            rate, audio = wavfile.read(wav_path)
            self.assertGreater(audio.size, 0)
            self.assertAlmostEqual(audio.size / rate, 1.2, delta=0.15)

    def test_cli_sfx_jump_sample_generates_wav(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "jump"
            with patch.object(sys, "argv", ["sfx_generator.py", "--input-file", str(ROOT / "scores" / "sfx_jump_sample.mml"), "-o", str(out)]):
                main()
            wav_path = out.with_suffix(".wav")
            self.assertTrue(wav_path.exists())
            _, audio = wavfile.read(wav_path)
            self.assertGreater(audio.size, 0)


class EineKleineNachtmusikBenchmarkTests(unittest.TestCase):
    def test_eine_kleine_nachtmusik_sample_score(self) -> None:
        tracks = parse_mml_source(
            (ROOT / "scores" / "eine_kleine_nachtmusik_sample.mml").read_text(encoding="utf-8")
        )
        self.assertEqual([track.channel for track in tracks], ["A", "C"])
        by_channel = {track.channel: track for track in tracks}
        a_pitched = [event for event in by_channel["A"].events if event.frequency is not None]
        c_pitched = [event for event in by_channel["C"].events if event.frequency is not None]
        self.assertEqual(len(a_pitched), 18)
        self.assertEqual(len(c_pitched), 12)
        self.assertAlmostEqual(a_pitched[0].frequency, note_name_to_freq("C", 4))
        self.assertAlmostEqual(
            sum(event.duration for event in by_channel["A"].events),
            sum(event.duration for event in by_channel["C"].events),
            places=3,
        )

    def test_eine_kleine_nachtmusik_cli_generates_wav(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = str(Path(tmpdir) / "nachtmusik")
            result = main(
                [
                    "--input-file",
                    str(ROOT / "scores" / "eine_kleine_nachtmusik_sample.mml"),
                    "-o",
                    output,
                ]
            )
            self.assertEqual(result, 0)
            rate, audio = wavfile.read(f"{output}.wav")
            self.assertAlmostEqual(audio.size / rate, 5.33, delta=0.5)


class MmlPyxelCompatTests(unittest.TestCase):
    def test_q_gate_percent_inserts_rest(self) -> None:
        events = parse_pyxel_mml("T120 Q50 @1 O4 L8 C4")
        quarter = 60.0 / 120
        self.assertEqual(len(events), 2)
        self.assertAlmostEqual(events[0].duration, quarter / 2)
        self.assertIsNone(events[1].frequency)

    def test_volume_maps_0_to_127(self) -> None:
        events = parse_pyxel_mml("T120 Q100 V127 @1 O4 L8 C4")
        self.assertAlmostEqual(events[0].volume, 1.0)
        quiet = parse_pyxel_mml("T120 Q100 V0 @1 O4 L8 C4")
        self.assertAlmostEqual(quiet[0].volume, 0.0)

    def test_tone_map_assigns_waveforms(self) -> None:
        self.assertEqual(PYXEL_TONE_MAP[0]["waveform"], "triangle")
        self.assertEqual(PYXEL_TONE_MAP[3]["waveform"], "noise")
        events = parse_pyxel_mml("T120 Q100 @2 O4 L8 C4")
        self.assertEqual(events[0].waveform, "square")
        self.assertAlmostEqual(events[0].duty, 0.25)

    def test_legato_connects_different_pitches(self) -> None:
        events = parse_pyxel_mml("T120 Q50 @1 O4 L8 C4&D4")
        quarter = 60.0 / 120
        pitched = [event for event in events if event.frequency is not None]
        self.assertEqual(len(pitched), 2)
        self.assertAlmostEqual(pitched[0].duration, quarter)

    def test_tie_combines_same_pitch(self) -> None:
        events = parse_pyxel_mml("T120 Q100 @1 O4 L8 C4&C")
        quarter = 60.0 / 120
        pitched = [event for event in events if event.frequency is not None]
        self.assertEqual(len(pitched), 1)
        self.assertAlmostEqual(pitched[0].duration, quarter * 1.5)

    def test_length_only_tie_extends_previous_note(self) -> None:
        events = parse_pyxel_mml("T120 Q100 L16 C16&16 D16")
        pitched = [event for event in events if event.frequency is not None]
        self.assertEqual(len(pitched), 2)
        self.assertAlmostEqual(pitched[0].duration, 0.25)
        self.assertAlmostEqual(pitched[1].duration, 0.125)

    def test_length_only_tie_extends_previous_rest(self) -> None:
        events = parse_pyxel_mml("T120 Q100 L16 R16&16 C16")
        self.assertIsNone(events[0].frequency)
        self.assertAlmostEqual(events[0].duration, 0.25)
        self.assertAlmostEqual(events[1].duration, 0.125)

    def test_chained_length_only_ties_extend_previous_note(self) -> None:
        events = parse_pyxel_mml("T120 Q100 L16 C16&16&16&16 D16")
        pitched = [event for event in events if event.frequency is not None]
        self.assertAlmostEqual(pitched[0].duration, 0.5)
        self.assertAlmostEqual(pitched[1].duration, 0.125)

    def test_length_only_tie_recalculates_gate(self) -> None:
        events = parse_pyxel_mml("T120 Q50 L16 C16&16 D16")
        self.assertAlmostEqual(events[0].duration, 0.125)
        self.assertIsNone(events[1].frequency)
        self.assertAlmostEqual(events[1].duration, 0.125)

    def test_implicit_repeat_uses_max_repeat(self) -> None:
        events = parse_pyxel_mml("T120 @1 O4 L8 [C4 D4]", max_repeat=3)
        pitched = [event for event in events if event.frequency is not None]
        self.assertEqual(len(pitched), 6)

    def test_explicit_repeat_ignores_max_repeat(self) -> None:
        events = parse_pyxel_mml("T120 @1 O4 L8 [C4 D4]2", max_repeat=5)
        pitched = [event for event in events if event.frequency is not None]
        self.assertEqual(len(pitched), 4)

    def test_repeat_reexecutes_state_commands(self) -> None:
        events = parse_pyxel_mml("T120 Q100 O4 [>C4]2 C4")
        frequencies = [event.frequency for event in events if event.frequency is not None]
        self.assertEqual(
            frequencies,
            [
                note_name_to_freq("C", 5),
                note_name_to_freq("C", 6),
                note_name_to_freq("C", 6),
            ],
        )

    def test_repeat_events_do_not_share_tie_mutations(self) -> None:
        events = parse_pyxel_mml("T120 Q100 O4 [C4]2 &C4")
        pitched = [event for event in events if event.frequency is not None]
        self.assertEqual(len(pitched), 2)
        self.assertIsNot(pitched[0], pitched[1])
        self.assertAlmostEqual(pitched[0].duration, 0.5)
        self.assertAlmostEqual(pitched[1].duration, 1.0)

    def test_max_repeat_zero_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_pyxel_mml("[C4]", max_repeat=0)

    def test_env_and_vib_macros_parse(self) -> None:
        events = parse_pyxel_mml(
            "T128 Q100 @2 @ENV1{127,6,96} @VIB1{36,18,25} O4 L8 C4"
        )
        pitched = [event for event in events if event.frequency is not None]
        self.assertEqual(len(pitched), 1)
        self.assertIsNotNone(pitched[0].event_adsr)
        self.assertIsNotNone(pitched[0].lfo_depth)
        self.assertIsNotNone(pitched[0].lfo_rate)

    def test_effect_slots_can_be_disabled_and_reselected(self) -> None:
        events = parse_pyxel_mml(
            "T120 Q100 "
            "@ENV1{127,6,96} @VIB1{0,12,100} @GLI1{100,12} C4 "
            "@ENV0 @VIB0 @GLI0 D4 "
            "@ENV1 @VIB1 @GLI1 E4"
        )
        pitched = [event for event in events if event.frequency is not None]
        self.assertIsNotNone(pitched[0].event_adsr)
        self.assertIsNotNone(pitched[0].lfo_depth)
        self.assertEqual(pitched[0].glide_cents, 100.0)
        self.assertIsNone(pitched[1].event_adsr)
        self.assertIsNone(pitched[1].lfo_depth)
        self.assertIsNone(pitched[1].glide_cents)
        self.assertIs(pitched[2].event_adsr, pitched[0].event_adsr)
        self.assertEqual(pitched[2].lfo_depth, pitched[0].lfo_depth)
        self.assertEqual(pitched[2].glide_cents, pitched[0].glide_cents)

    def test_ppmck_token_rejected_in_pyxel_mode(self) -> None:
        with self.assertRaises(ValueError):
            parse_pyxel_mml("T120 N32")

    def test_compat_report_lists_ppmck_tokens(self) -> None:
        issues = report_pyxel_compat_issues("T120 %12 *4 W(kick.wav) N32")
        self.assertTrue(any("N32" in issue or "直接ノート" in issue for issue in issues))
        self.assertTrue(any("%" in issue for issue in issues))

    def test_pyxel_core_sample_score(self) -> None:
        events = parse_pyxel_mml(
            (ROOT / "scores" / "pyxel_core_sample.mml").read_text(encoding="utf-8")
        )
        pitched = [event for event in events if event.frequency is not None]
        self.assertEqual(len(pitched), 4)
        self.assertAlmostEqual(pitched[0].frequency, note_name_to_freq("C", 5))

    def test_cli_max_repeat_zero_exits_with_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = str(Path(tmpdir) / "bad_repeat")
            result = main(
                [
                    "--mml-dialect",
                    "pyxel",
                    "--max-repeat",
                    "0",
                    "--input",
                    "C4",
                    "-o",
                    output,
                ]
            )
            self.assertEqual(result, 1)

    def test_cli_pyxel_dialect_generates_wav(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = str(Path(tmpdir) / "pyxel_cli")
            result = main(
                [
                    "--mml-dialect",
                    "pyxel",
                    "--input-file",
                    str(ROOT / "scores" / "pyxel_core_sample.mml"),
                    "-o",
                    output,
                ]
            )
            self.assertEqual(result, 0)
            self.assertTrue(Path(f"{output}.wav").exists())

    def test_pyxel_multiline_stays_single_part_by_default(self) -> None:
        tracks = parse_mml_source(
            "T120 Q100 O4 C4\nD4",
            dialect="pyxel",
        )
        self.assertEqual(len(tracks), 1)
        self.assertEqual(len([e for e in tracks[0].events if e.frequency is not None]), 2)

    def test_pyxel_multipart_uses_each_mml_line_and_ignores_share_url(self) -> None:
        tracks = parse_mml_source(
            "T120 Q100 O4 C4\n"
            "T120 Q100 O3 G4\n"
            "\n"
            "; exported by composer\n"
            "https://example.com/share",
            dialect="pyxel",
            pyxel_multipart=True,
        )
        self.assertEqual(len(tracks), 2)
        self.assertEqual([track.channel for track in tracks], ["1", "2"])

    def test_cli_pyxel_multipart_composer_file_generates_wav(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = str(Path(tmpdir) / "pyxel_multipart")
            source = Path(tmpdir) / "composer.txt"
            source.write_text(
                "T120 Q100 O4 C4\nT120 Q100 O3 G4\n\nhttps://example.com/share\n",
                encoding="utf-8",
            )
            result = main(
                [
                    "--mml-dialect",
                    "pyxel",
                    "--pyxel-multipart",
                    "--input-file",
                    str(source),
                    "-o",
                    output,
                ]
            )
            self.assertEqual(result, 0)
            rate, audio = wavfile.read(f"{output}.wav")
            self.assertAlmostEqual(audio.size / rate, 0.5, places=2)

    def test_cli_pyxel_multipart_requires_pyxel_dialect(self) -> None:
        result = main(["--pyxel-multipart", "--input", "C4"])
        self.assertEqual(result, 1)

    def test_pyxel_composer_sample_score(self) -> None:
        text = (ROOT / "scores" / "pyxel_composer_sample.mml").read_text(encoding="utf-8")
        tracks = parse_mml_source(text, dialect="pyxel", pyxel_multipart=True)
        self.assertEqual(len(tracks), 4)
        self.assertEqual([track.channel for track in tracks], ["1", "2", "3", "4"])
        for track in tracks:
            pitched = [event for event in track.events if event.frequency is not None]
            self.assertGreater(len(pitched), 8)

    def test_cli_pyxel_composer_sample_generates_wav(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = str(Path(tmpdir) / "pyxel_composer_sample")
            result = main(
                [
                    "--mml-dialect",
                    "pyxel",
                    "--pyxel-multipart",
                    "--input-file",
                    str(ROOT / "scores" / "pyxel_composer_sample.mml"),
                    "-o",
                    output,
                ]
            )
            self.assertEqual(result, 0)
            rate, audio = wavfile.read(f"{output}.wav")
            self.assertAlmostEqual(audio.size / rate, 32.0, delta=1.0)

    def test_detune_y_shifts_frequency(self) -> None:
        base = parse_pyxel_mml("T120 Q100 @1 O4 L8 C4")[0].frequency
        detuned = parse_pyxel_mml("T120 Q100 Y50 @1 O4 L8 C4")[0].frequency
        self.assertIsNotNone(base)
        self.assertIsNotNone(detuned)
        self.assertAlmostEqual(detuned, base * (2.0 ** (50 / 1200.0)))

    def test_sharp_note_matches_plus(self) -> None:
        sharp = parse_pyxel_mml("T120 Q100 @1 O4 L8 C#4")[0].frequency
        plus = parse_pyxel_mml("T120 Q100 @1 O4 L8 C+4")[0].frequency
        self.assertAlmostEqual(sharp, plus)
        self.assertAlmostEqual(sharp, note_name_to_freq("C#", 4))

    def test_l12_sets_triplet_quarter_length(self) -> None:
        events = parse_pyxel_mml("T120 Q100 @1 O4 L12 C")
        quarter = 60.0 / 120
        self.assertAlmostEqual(events[0].duration, quarter / 3)

    def test_gli_macro_adds_pitch_envelope(self) -> None:
        base_event = parse_pyxel_mml("T120 Q100 @1 O4 L8 C4")[0]
        gli = parse_pyxel_mml("T120 Q100 @1 @GLI1{100,6} O4 L8 C4")[0]
        self.assertIsNotNone(base_event.frequency)
        self.assertAlmostEqual(gli.frequency, base_event.frequency)
        self.assertEqual(gli.glide_cents, 100.0)
        self.assertAlmostEqual(gli.glide_duration, (60.0 / 120) * (6 / 48))
        config = SynthConfig(waveform="sine")
        self.assertFalse(
            np.allclose(synthesize_note(gli, config), synthesize_note(base_event, config))
        )

    def test_pyxel_effects_sample_score(self) -> None:
        events = parse_pyxel_mml(
            (ROOT / "scores" / "pyxel_effects_sample.mml").read_text(encoding="utf-8")
        )
        pitched = [event for event in events if event.frequency is not None]
        self.assertGreaterEqual(len(pitched), 4)
        self.assertIsNotNone(pitched[0].event_adsr)
        self.assertIsNotNone(pitched[0].lfo_depth)

    def test_pyxel_legato_sample_score(self) -> None:
        events = parse_pyxel_mml(
            (ROOT / "scores" / "pyxel_legato_sample.mml").read_text(encoding="utf-8")
        )
        pitched = [event for event in events if event.frequency is not None]
        self.assertGreaterEqual(len(pitched), 3)


if __name__ == "__main__":
    unittest.main()
