import importlib.util
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
create_parser = sg.create_parser
generate_colored_noise = sg.generate_colored_noise
main = sg.main
mix_tracks = sg.mix_tracks
load_preset = sg.load_preset
note_name_to_freq = sg.note_name_to_freq
parse_abc = sg.parse_abc
parse_mml = sg.parse_mml
play_audio = sg.play_audio
synthesize_note = sg.synthesize_note
synthesize_sequence = sg.synthesize_sequence


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


if __name__ == "__main__":
    unittest.main()
