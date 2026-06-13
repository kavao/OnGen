import math
import unittest
from pathlib import Path

import numpy as np

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
    generate_colored_noise,
    mix_tracks,
    load_preset,
    note_name_to_freq,
    parse_abc,
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


if __name__ == "__main__":
    unittest.main()
