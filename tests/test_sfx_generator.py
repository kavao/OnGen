import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from sfx_generator import (
    ADSR,
    FMConfig,
    FM_TONE_PRESETS,
    LFOConfig,
    MIX_HEADROOM,
    NoteEvent,
    SFX_PRESETS,
    SynthConfig,
    abc_default_unit_from_meter,
    abc_length_multiplier,
    abc_quarter_note_tempo,
    apply_master_fade,
    apply_audio_filter,
    create_parser,
    generate_colored_noise,
    main,
    mix_tracks,
    load_preset,
    note_name_to_freq,
    parse_abc,
    parse_mml,
    synthesize_note,
    synthesize_sequence,
)


ROOT = Path(__file__).resolve().parents[1]


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
            parse_mml("O4 T120 L4 C;D")

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


if __name__ == "__main__":
    unittest.main()
