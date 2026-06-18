#!/usr/bin/env python3
# Version: 0.4.6 (正本: .rulesync/metadata/sfx-generator.json)
"""OnGen: NumPy/SciPy ベースのMML・ABC音源合成ツール。"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from shutil import which
from typing import Iterable, Sequence

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

__version__ = "0.4.6"

SAMPLE_RATE = 44100
BIT_DEPTH = 16
OUTPUT_DIR = Path("output")
AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg"}
OUTPUT_FORMATS = ("wav", "mp3", "ogg", "all")
MIX_HEADROOM = 10.0 ** (-1.0 / 20.0)
SILENCE_THRESHOLD = 10.0 ** (-60.0 / 20.0)
CLIP_THRESHOLD = 0.999
LOUD_PEAK_DB = -0.5
QUIET_RMS_DB = -45.0
LONG_SILENCE_SEC = 0.5
MIN_NOTE_DURATION_SEC = 0.01
MAX_NOTE_DURATION_SEC = 8.0
MAX_NOTE_JUMP_SEMITONES = 24
NOTE_HARD_LOW_MIDI = 12
NOTE_HARD_HIGH_MIDI = 108
LOOP_EDGE_GAP_WARN = 0.25

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
NOTE_ALIASES = {
    "C": "C",
    "C+": "C#",
    "C#": "C#",
    "D": "D",
    "D-": "C#",
    "D+": "D#",
    "D#": "D#",
    "E": "E",
    "E-": "D#",
    "F": "F",
    "F+": "F#",
    "F#": "F#",
    "G": "G",
    "G-": "F#",
    "G+": "G#",
    "G#": "G#",
    "A": "A",
    "A-": "G#",
    "A+": "A#",
    "A#": "A#",
    "B": "B",
    "B-": "A#",
}


@dataclass
class ADSR:
    attack: float = 0.01
    decay: float = 0.05
    sustain: float = 0.6
    release: float = 0.08

    def envelope(self, num_samples: int, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
        if num_samples <= 0:
            return np.zeros(0, dtype=np.float64)

        total = num_samples
        env = np.zeros(total, dtype=np.float64)

        a = int(self.attack * sample_rate)
        d = int(self.decay * sample_rate)
        r = int(self.release * sample_rate)
        if a + d + r > total:
            scale = total / max(a + d + r, 1)
            a = int(a * scale)
            d = int(d * scale)
            r = total - a - d
        a = min(a, total)
        d = min(d, max(total - a, 0))
        r = min(r, max(total - a - d, 0))
        s_len = max(total - a - d - r, 0)

        idx = 0
        if a > 0:
            phase = np.linspace(0.0, np.pi, a, endpoint=False)
            env[idx : idx + a] = 0.5 - 0.5 * np.cos(phase)
            idx += a
        if d > 0:
            env[idx : idx + d] = np.linspace(1.0, self.sustain, d, endpoint=False)
            idx += d
        if s_len > 0:
            env[idx : idx + s_len] = self.sustain
            idx += s_len
        if r > 0:
            start = env[idx - 1] if idx > 0 else self.sustain
            env[idx : idx + r] = np.linspace(start, 0.0, r, endpoint=True)
            idx += r
        if idx < total:
            env[idx:] = 0.0
        return env[:num_samples]


@dataclass
class LFOConfig:
    enabled: bool = False
    rate: float = 5.0
    depth: float = 0.02
    target: str = "pitch"
    waveform: str = "sine"


@dataclass
class FMConfig:
    enabled: bool = False
    mod_ratio: float = 2.0
    mod_index: float = 2.0
    mod_waveform: str = "sine"


@dataclass
class SynthConfig:
    waveform: str = "square"
    duty: float = 0.5
    volume: float = 0.8
    anti_alias: bool = True
    noise_color: str = "white"
    filter_type: str = "none"
    cutoff: float = 8000.0
    adsr: ADSR = field(default_factory=ADSR)
    lfo: LFOConfig = field(default_factory=LFOConfig)
    fm: FMConfig = field(default_factory=FMConfig)
    sample_root: Path | None = None


@dataclass(frozen=True)
class MacroSequence:
    values: tuple[float, ...]
    loop_index: int | None = None


@dataclass
class MMLMacroBank:
    duty: dict[int, MacroSequence] = field(default_factory=dict)
    volume: dict[int, MacroSequence] = field(default_factory=dict)
    pitch: dict[int, MacroSequence] = field(default_factory=dict)
    note: dict[int, MacroSequence] = field(default_factory=dict)
    lfo: dict[int, MacroSequence] = field(default_factory=dict)


@dataclass
class NoteEvent:
    frequency: float | None
    duration: float
    volume: float = 1.0
    waveform: str | None = None
    duty: float | None = None
    sample_path: str | None = None
    sample_root_freq: float | None = None
    fm_index: float | None = None
    fm_ratio: float | None = None
    lfo_depth: float | None = None
    lfo_rate: float | None = None
    lfo_delay: float | None = None
    lfo_target: str | None = None
    event_adsr: ADSR | None = None
    glide_cents: float | None = None
    glide_duration: float | None = None
    volume_envelope: MacroSequence | None = None
    pitch_envelope: MacroSequence | None = None
    note_envelope: MacroSequence | None = None


@dataclass
class AudioIssue:
    level: str
    code: str
    message: str
    value: float | int | str | None = None


@dataclass
class AudioReport:
    status: str
    duration: float | None = None
    peak_db: float | None = None
    rms_db: float | None = None
    note_range: str | None = None
    issues: list[AudioIssue] = field(default_factory=list)


def midi_to_freq(midi: int) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def note_to_midi(name: str, octave: int) -> int:
    normalized = NOTE_ALIASES.get(name.upper(), name.upper())
    if normalized not in NOTE_NAMES:
        raise ValueError(f"未知の音名: {name}")
    return NOTE_NAMES.index(normalized) + (octave + 1) * 12


def note_name_to_freq(name: str, octave: int) -> float:
    return midi_to_freq(note_to_midi(name, octave))


def freq_to_midi(frequency: float) -> int:
    if frequency <= 0:
        raise ValueError("frequency must be positive")
    return int(round(69 + 12 * math.log2(frequency / 440.0)))


def midi_to_note_label(midi: int) -> str:
    name = NOTE_NAMES[midi % 12]
    octave = midi // 12 - 1
    return f"{name}{octave}"


def generate_square(phase: np.ndarray, duty: float = 0.5) -> np.ndarray:
    duty = min(max(duty, 0.01), 0.99)
    return np.where((phase % (2 * np.pi)) < (2 * np.pi * duty), 1.0, -1.0)


def poly_blep(phase_cycles: np.ndarray, phase_step: np.ndarray) -> np.ndarray:
    """Band-limit a waveform discontinuity around phase 0."""
    correction = np.zeros_like(phase_cycles, dtype=np.float64)
    step = np.clip(phase_step, 1e-12, 0.5)

    rising = phase_cycles < step
    x = phase_cycles[rising] / step[rising]
    correction[rising] = x + x - x * x - 1.0

    falling = phase_cycles > 1.0 - step
    x = (phase_cycles[falling] - 1.0) / step[falling]
    correction[falling] = x * x + x + x + 1.0
    return correction


def generate_bandlimited_square(
    phase: np.ndarray,
    phase_step: np.ndarray,
    duty: float | np.ndarray = 0.5,
) -> np.ndarray:
    duty = np.clip(duty, 0.01, 0.99)
    phase_cycles = (phase / (2.0 * np.pi)) % 1.0
    wave = np.where(phase_cycles < duty, 1.0, -1.0)
    wave += poly_blep(phase_cycles, phase_step)
    wave -= poly_blep((phase_cycles - duty) % 1.0, phase_step)
    return wave


def generate_sawtooth(phase: np.ndarray) -> np.ndarray:
    return 2.0 * (phase / (2 * np.pi) % 1.0) - 1.0


def generate_triangle(phase: np.ndarray) -> np.ndarray:
    return 2.0 * np.abs(2.0 * (phase / (2 * np.pi) % 1.0) - 1.0) - 1.0


def generate_white_noise(num_samples: int) -> np.ndarray:
    rng = np.random.default_rng()
    return rng.uniform(-1.0, 1.0, num_samples)


def generate_colored_noise(num_samples: int, color: str = "white") -> np.ndarray:
    if num_samples <= 0:
        return np.zeros(0, dtype=np.float64)
    if color == "white":
        return generate_white_noise(num_samples)

    rng = np.random.default_rng()
    spectrum = np.fft.rfft(rng.normal(size=num_samples))
    frequencies = np.fft.rfftfreq(num_samples, 1.0 / SAMPLE_RATE)
    exponent = 0.5 if color == "pink" else 1.0
    scale = np.ones_like(frequencies)
    scale[1:] = frequencies[1:] ** (-exponent)
    scale[0] = 0.0
    noise = np.fft.irfft(spectrum * scale, n=num_samples)
    peak = np.max(np.abs(noise))
    return noise / peak if peak > 0 else noise


def apply_audio_filter(
    audio: np.ndarray,
    filter_type: str,
    cutoff: float,
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    if audio.size == 0 or filter_type == "none":
        return audio
    nyquist = sample_rate / 2.0
    normalized_cutoff = min(max(cutoff, 20.0), nyquist * 0.99) / nyquist
    sos = butter(4, normalized_cutoff, btype=filter_type, output="sos")
    return sosfilt(sos, audio)


def generate_lfo_signal(
    num_samples: int,
    rate: float,
    waveform: str = "sine",
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    if num_samples <= 0:
        return np.zeros(0, dtype=np.float64)
    t = np.arange(num_samples, dtype=np.float64) / sample_rate
    phase = 2.0 * np.pi * rate * t
    if waveform == "square":
        return generate_square(phase, 0.5)
    if waveform == "sawtooth":
        return generate_sawtooth(phase)
    if waveform == "triangle":
        return generate_triangle(phase)
    return np.sin(phase)


def waveform_from_phase(waveform: str, phase: np.ndarray, duty: float = 0.5) -> np.ndarray:
    if waveform == "square":
        return generate_square(phase, duty).astype(np.float64)
    if waveform == "sawtooth":
        return generate_sawtooth(phase)
    if waveform == "triangle":
        return generate_triangle(phase)
    if waveform == "sine":
        return np.sin(phase)
    raise ValueError(f"未対応の波形: {waveform}")


def generate_waveform(
    waveform: str,
    num_samples: int,
    frequency: float,
    sample_rate: int = SAMPLE_RATE,
    duty: float = 0.5,
    phase_offset: float = 0.0,
) -> np.ndarray:
    if num_samples <= 0:
        return np.zeros(0, dtype=np.float64)

    if waveform == "noise":
        return generate_colored_noise(num_samples, config.noise_color)

    t = np.arange(num_samples, dtype=np.float64) / sample_rate
    phase = 2.0 * np.pi * frequency * t + phase_offset
    return waveform_from_phase(waveform, phase, duty)


def generate_fm_waveform(
    waveform: str,
    num_samples: int,
    carrier_freq: float,
    fm: FMConfig,
    sample_rate: int = SAMPLE_RATE,
    duty: float = 0.5,
) -> np.ndarray:
    if num_samples <= 0:
        return np.zeros(0, dtype=np.float64)
    if waveform == "noise":
        return generate_white_noise(num_samples)

    t = np.arange(num_samples, dtype=np.float64) / sample_rate
    mod_freq = max(carrier_freq * fm.mod_ratio, 0.0)
    mod_phase = 2.0 * np.pi * mod_freq * t
    modulator = waveform_from_phase(fm.mod_waveform, mod_phase)
    modulator *= fm.mod_index
    carrier_phase = 2.0 * np.pi * carrier_freq * t + modulator
    return waveform_from_phase(waveform, carrier_phase, duty)


def synthesize_oscillator(
    waveform: str,
    num_samples: int,
    frequency: float,
    duty: float,
    config: SynthConfig,
    event: NoteEvent,
) -> np.ndarray:
    fm = FMConfig(
        enabled=config.fm.enabled or event.fm_index is not None,
        mod_ratio=event.fm_ratio if event.fm_ratio is not None else config.fm.mod_ratio,
        mod_index=event.fm_index if event.fm_index is not None else config.fm.mod_index,
        mod_waveform=config.fm.mod_waveform,
    )
    lfo_depth = event.lfo_depth if event.lfo_depth is not None else config.lfo.depth
    lfo_rate = event.lfo_rate if event.lfo_rate is not None else config.lfo.rate
    lfo_delay = event.lfo_delay if event.lfo_delay is not None else 0.0
    lfo_target = event.lfo_target or config.lfo.target
    lfo_enabled = config.lfo.enabled or event.lfo_depth is not None

    if waveform == "noise":
        return generate_white_noise(num_samples)

    t = np.arange(num_samples, dtype=np.float64) / SAMPLE_RATE
    carrier_freq = np.full(num_samples, frequency, dtype=np.float64)

    def _event_lfo() -> np.ndarray:
        lfo = generate_lfo_signal(num_samples, lfo_rate, config.lfo.waveform)
        delay_samples = min(max(int(round(lfo_delay * SAMPLE_RATE)), 0), num_samples)
        if delay_samples > 0:
            lfo[:delay_samples] = 0.0
        return lfo

    if event.glide_cents is not None and event.glide_duration is not None:
        glide_samples = min(max(int(event.glide_duration * SAMPLE_RATE), 1), num_samples)
        glide_cents = np.zeros(num_samples, dtype=np.float64)
        glide_cents[:glide_samples] = np.linspace(
            event.glide_cents,
            0.0,
            glide_samples,
            endpoint=True,
        )
        carrier_freq *= 2.0 ** (glide_cents / 1200.0)

    if event.pitch_envelope is not None:
        pitch_steps = render_macro_sequence(event.pitch_envelope, num_samples)
        carrier_freq *= 2.0 ** (pitch_steps / 12.0)

    if event.note_envelope is not None:
        note_steps = render_macro_sequence(event.note_envelope, num_samples, interpolate=False)
        carrier_freq *= 2.0 ** (note_steps / 12.0)

    if lfo_enabled and lfo_depth > 0 and lfo_target == "pitch":
        lfo = _event_lfo()
        carrier_freq += frequency * lfo_depth * lfo

    if fm.enabled and fm.mod_index > 0:
        mod_freq = np.maximum(carrier_freq * fm.mod_ratio, 0.0)
        mod_phase = 2.0 * np.pi * np.cumsum(mod_freq) / SAMPLE_RATE
        modulator = waveform_from_phase(fm.mod_waveform, mod_phase) * fm.mod_index
        phase = 2.0 * np.pi * np.cumsum(carrier_freq) / SAMPLE_RATE + modulator
    else:
        phase = 2.0 * np.pi * np.cumsum(carrier_freq) / SAMPLE_RATE

    if waveform == "square":
        duty_values: float | np.ndarray = duty
        if lfo_enabled and lfo_depth > 0 and lfo_target == "duty":
            lfo = _event_lfo()
            duty_values = np.clip(duty + lfo_depth * lfo * 0.4, 0.05, 0.95)

        if config.anti_alias:
            phase_step = np.abs(np.diff(phase, prepend=phase[0])) / (2.0 * np.pi)
            phase_step[0] = max(frequency / SAMPLE_RATE, 1e-12)
            wave = generate_bandlimited_square(phase, phase_step, duty_values)
        else:
            phase_cycles = (phase / (2.0 * np.pi)) % 1.0
            wave = np.where(phase_cycles < duty_values, 1.0, -1.0)
    else:
        wave = waveform_from_phase(waveform, phase, duty)

    if lfo_enabled and lfo_depth > 0:
        lfo = _event_lfo()
        if lfo_target == "volume":
            wave *= 1.0 - lfo_depth + lfo_depth * (0.5 + 0.5 * lfo)

    return wave


def to_mono_float(audio: np.ndarray) -> np.ndarray:
    data = audio.astype(np.float64)
    if data.ndim == 1:
        mono = data
    else:
        mono = data.mean(axis=1)
    peak = np.max(np.abs(mono))
    if peak > 1.0:
        if peak <= np.iinfo(np.int16).max:
            mono /= np.iinfo(np.int16).max
        else:
            mono /= peak
    return mono


def resample_linear(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if audio.size == 0:
        return np.zeros(0, dtype=np.float64)
    if src_rate == dst_rate:
        return audio.astype(np.float64)

    src_times = np.arange(audio.size, dtype=np.float64) / src_rate
    dst_len = max(int(round(audio.size * dst_rate / src_rate)), 1)
    dst_times = np.arange(dst_len, dtype=np.float64) / dst_rate
    return np.interp(dst_times, src_times, audio).astype(np.float64)


def resolve_sample_path(path_text: str, sample_root: Path | None) -> Path:
    path = Path(path_text)
    if path.is_file():
        return path
    if sample_root is not None:
        candidate = sample_root / path_text
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"サンプル WAV が見つかりません: {path_text}")


def load_wav_sample(path: Path) -> tuple[np.ndarray, int]:
    rate, data = wavfile.read(str(path))
    return to_mono_float(data), int(rate)


def pitch_shift_audio(audio: np.ndarray, ratio: float) -> np.ndarray:
    if audio.size == 0 or abs(ratio - 1.0) < 1e-9:
        return audio
    src_times = np.arange(audio.size, dtype=np.float64)
    dst_len = max(int(round(audio.size / ratio)), 1)
    dst_times = np.linspace(0.0, audio.size - 1, dst_len)
    return np.interp(dst_times, src_times, audio).astype(np.float64)


def fit_audio_to_duration(audio: np.ndarray, num_samples: int) -> np.ndarray:
    if num_samples <= 0:
        return np.zeros(0, dtype=np.float64)
    if audio.size == num_samples:
        return audio
    if audio.size > num_samples:
        return audio[:num_samples]
    out = np.zeros(num_samples, dtype=np.float64)
    out[: audio.size] = audio
    return out


def macro_value_at(sequence: MacroSequence, frame_index: int) -> float:
    if not sequence.values:
        return 0.0
    if frame_index < len(sequence.values):
        return sequence.values[frame_index]
    if sequence.loop_index is not None:
        loop_start = min(max(sequence.loop_index, 0), len(sequence.values) - 1)
        loop_len = len(sequence.values) - loop_start
        return sequence.values[loop_start + ((frame_index - loop_start) % loop_len)]
    return sequence.values[-1]


def render_macro_sequence(
    sequence: MacroSequence,
    num_samples: int,
    frame_rate: int = 60,
    *,
    interpolate: bool = True,
) -> np.ndarray:
    if num_samples <= 0:
        return np.zeros(0, dtype=np.float64)
    samples_per_frame = max(int(round(SAMPLE_RATE / frame_rate)), 1)
    positions = np.arange(num_samples, dtype=np.float64) / samples_per_frame
    frame_indices = np.floor(positions).astype(np.int64)
    current = np.asarray(
        [macro_value_at(sequence, int(index)) for index in frame_indices],
        dtype=np.float64,
    )
    if not interpolate:
        return current
    fractions = positions - frame_indices
    next_values = np.asarray(
        [macro_value_at(sequence, int(index) + 1) for index in frame_indices],
        dtype=np.float64,
    )
    return current + (next_values - current) * fractions


def apply_volume_envelope(audio: np.ndarray, sequence: MacroSequence | None) -> np.ndarray:
    if sequence is None or audio.size == 0:
        return audio
    envelope = np.clip(render_macro_sequence(sequence, audio.size) / 15.0, 0.0, 1.0)
    return audio * envelope


def render_sample_note(event: NoteEvent, config: SynthConfig) -> np.ndarray:
    num_samples = int(round(max(event.duration, 0.0) * SAMPLE_RATE))
    if num_samples <= 0 or not event.sample_path:
        return np.zeros(0, dtype=np.float64)

    path = resolve_sample_path(event.sample_path, config.sample_root)
    audio, src_rate = load_wav_sample(path)
    audio = resample_linear(audio, src_rate, SAMPLE_RATE)

    if event.frequency and event.sample_root_freq and event.sample_root_freq > 0:
        audio = pitch_shift_audio(audio, event.frequency / event.sample_root_freq)

    audio = fit_audio_to_duration(audio, num_samples)
    env = config.adsr.envelope(num_samples)
    audio = audio * env * config.volume * event.volume
    return apply_volume_envelope(audio, event.volume_envelope)


def synthesize_note(event: NoteEvent, config: SynthConfig) -> np.ndarray:
    duration = max(event.duration, 0.0)
    num_samples = int(round(duration * SAMPLE_RATE))
    if num_samples <= 0:
        return np.zeros(0, dtype=np.float64)

    volume = config.volume * event.volume

    if event.sample_path:
        return render_sample_note(event, config)

    waveform = event.waveform or config.waveform
    duty = event.duty if event.duty is not None else config.duty

    if event.frequency is None:
        return np.zeros(num_samples, dtype=np.float64)

    wave = synthesize_oscillator(waveform, num_samples, event.frequency, duty, config, event)
    wave = apply_audio_filter(wave, config.filter_type, config.cutoff)
    wave = np.clip(wave, -1.0, 1.0)
    env = (event.event_adsr or config.adsr).envelope(num_samples)
    audio = wave * env * volume
    return apply_volume_envelope(audio, event.volume_envelope)


def synthesize_sequence(events: Sequence[NoteEvent], config: SynthConfig) -> np.ndarray:
    if not events:
        return np.zeros(0, dtype=np.float64)
    parts = [synthesize_note(event, config) for event in events]
    if not parts:
        return np.zeros(0, dtype=np.float64)
    return np.concatenate(parts)


def mix_tracks(tracks: Iterable[np.ndarray]) -> np.ndarray:
    track_list = [track for track in tracks if track.size > 0]
    if not track_list:
        return np.zeros(0, dtype=np.float64)

    max_len = max(track.size for track in track_list)
    mixed = np.zeros(max_len, dtype=np.float64)
    for track in track_list:
        mixed[: track.size] += track

    peak = np.max(np.abs(mixed))
    if peak > MIX_HEADROOM:
        mixed *= MIX_HEADROOM / peak
    return mixed


def mix_at_offset(
    base: np.ndarray,
    overlay: np.ndarray,
    offset_samples: int = 0,
    gain: float = 1.0,
) -> np.ndarray:
    if overlay.size == 0:
        return base
    offset = max(offset_samples, 0)
    total_len = max(base.size, offset + overlay.size)
    mixed = np.zeros(total_len, dtype=np.float64)
    if base.size > 0:
        mixed[: base.size] += base
    end = offset + overlay.size
    mixed[offset:end] += overlay * gain
    peak = np.max(np.abs(mixed))
    if peak > MIX_HEADROOM:
        mixed *= MIX_HEADROOM / peak
    return mixed


def apply_master_fade(audio: np.ndarray, fade_in: float = 0.005) -> np.ndarray:
    """Apply a short smooth fade-in to suppress playback-start transients."""
    if audio.size == 0 or fade_in <= 0:
        return audio
    fade_samples = min(int(round(fade_in * SAMPLE_RATE)), audio.size)
    if fade_samples <= 0:
        return audio
    result = audio.copy()
    phase = np.linspace(0.0, np.pi, fade_samples, endpoint=True)
    result[:fade_samples] *= 0.5 - 0.5 * np.cos(phase)
    return result


def parse_overlay_spec(spec: str, sample_root: Path | None) -> tuple[np.ndarray, int, float]:
    parts = spec.split(":")
    path_text = parts[0]
    offset_sec = float(parts[1]) if len(parts) > 1 and parts[1] else 0.0
    gain = float(parts[2]) if len(parts) > 2 and parts[2] else 1.0
    path = resolve_sample_path(path_text, sample_root)
    audio, src_rate = load_wav_sample(path)
    audio = resample_linear(audio, src_rate, SAMPLE_RATE)
    return audio, int(round(offset_sec * SAMPLE_RATE)), gain


def normalize_and_convert(audio: np.ndarray) -> np.ndarray:
    if audio.size == 0:
        return np.zeros(0, dtype=np.int16)
    clipped = np.clip(audio, -1.0, 1.0)
    return (clipped * (2 ** (BIT_DEPTH - 1) - 1)).astype(np.int16)


def dbfs(value: float) -> float | None:
    if value <= 0:
        return None
    return 20.0 * math.log10(value)


def report_status(issues: Sequence[AudioIssue]) -> str:
    if any(issue.level == "ERROR" for issue in issues):
        return "ERROR"
    if any(issue.level == "WARN" for issue in issues):
        return "WARN"
    return "OK"


def merge_reports(reports: Sequence[AudioReport]) -> AudioReport:
    issues: list[AudioIssue] = []
    duration: float | None = None
    peak_db: float | None = None
    rms_db: float | None = None
    note_range: str | None = None
    for report in reports:
        issues.extend(report.issues)
        duration = report.duration if report.duration is not None else duration
        peak_db = report.peak_db if report.peak_db is not None else peak_db
        rms_db = report.rms_db if report.rms_db is not None else rms_db
        note_range = report.note_range if report.note_range is not None else note_range
    return AudioReport(
        status=report_status(issues),
        duration=duration,
        peak_db=peak_db,
        rms_db=rms_db,
        note_range=note_range,
        issues=issues,
    )


def longest_silence_duration(audio: np.ndarray, sample_rate: int) -> float:
    if audio.size == 0:
        return 0.0
    silent = np.abs(audio) <= SILENCE_THRESHOLD
    longest = 0
    current = 0
    for is_silent in silent:
        if is_silent:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest / sample_rate


def analyze_audio_array(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> AudioReport:
    issues: list[AudioIssue] = []
    duration = audio.size / sample_rate if sample_rate > 0 else 0.0
    if audio.size == 0:
        issues.append(AudioIssue("ERROR", "empty_audio", "音声データが空です。", 0))
        return AudioReport(status=report_status(issues), duration=duration, issues=issues)

    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(np.square(audio))))
    peak_db = dbfs(peak)
    rms_db = dbfs(rms)
    clipped_count = int(np.count_nonzero(np.abs(audio) >= CLIP_THRESHOLD))
    silence_sec = longest_silence_duration(audio, sample_rate)
    loop_gap = float(abs(audio[0] - audio[-1])) if audio.size > 1 else 0.0

    if clipped_count > 0:
        issues.append(
            AudioIssue("ERROR", "clipping_detected", "クリップしているサンプルがあります。", clipped_count)
        )
    if peak_db is not None and peak_db > LOUD_PEAK_DB:
        issues.append(AudioIssue("WARN", "too_loud_peak", "ピーク音量が高すぎます。", round(peak_db, 2)))
    if rms_db is None or rms_db < QUIET_RMS_DB:
        issues.append(AudioIssue("WARN", "too_quiet_rms", "RMS音量が小さすぎます。", None if rms_db is None else round(rms_db, 2)))
    if silence_sec >= LONG_SILENCE_SEC:
        issues.append(AudioIssue("WARN", "too_long_silence", "長い無音区間があります。", round(silence_sec, 3)))
    if loop_gap >= LOOP_EDGE_GAP_WARN:
        issues.append(AudioIssue("WARN", "loop_click_risk", "先頭と末尾の差分が大きく、ループ時にクリックノイズが出る可能性があります。", round(loop_gap, 3)))

    return AudioReport(
        status=report_status(issues),
        duration=duration,
        peak_db=None if peak_db is None else round(peak_db, 2),
        rms_db=None if rms_db is None else round(rms_db, 2),
        issues=issues,
    )


def lint_note_events(events: Sequence[NoteEvent]) -> AudioReport:
    issues: list[AudioIssue] = []
    midi_values: list[int] = []
    previous_midi: int | None = None

    for index, event in enumerate(events):
        if event.duration < MIN_NOTE_DURATION_SEC:
            issues.append(AudioIssue("WARN", "note_too_short", f"#{index} の音長が短すぎます。", round(event.duration, 4)))
        if event.duration > MAX_NOTE_DURATION_SEC:
            issues.append(AudioIssue("WARN", "note_too_long", f"#{index} の音長が長すぎます。", round(event.duration, 3)))
        if event.frequency is None:
            continue
        if event.frequency <= 0:
            issues.append(AudioIssue("ERROR", "invalid_frequency", f"#{index} の周波数が不正です。", event.frequency))
            continue

        midi = freq_to_midi(event.frequency)
        midi_values.append(midi)
        if midi < NOTE_HARD_LOW_MIDI:
            issues.append(AudioIssue("ERROR", "note_below_hard_limit", f"#{index} の音域が低すぎます。", midi_to_note_label(midi)))
        if midi > NOTE_HARD_HIGH_MIDI:
            issues.append(AudioIssue("ERROR", "note_above_hard_limit", f"#{index} の音域が高すぎます。", midi_to_note_label(midi)))
        if previous_midi is not None and abs(midi - previous_midi) > MAX_NOTE_JUMP_SEMITONES:
            issues.append(
                AudioIssue(
                    "WARN",
                    "note_jump_too_large",
                    f"#{index - 1} から #{index} の音程ジャンプが大きすぎます。",
                    f"{midi_to_note_label(previous_midi)} -> {midi_to_note_label(midi)}",
                )
            )
        previous_midi = midi

    note_range = None
    if midi_values:
        note_range = f"{midi_to_note_label(min(midi_values))} - {midi_to_note_label(max(midi_values))}"

    return AudioReport(status=report_status(issues), note_range=note_range, issues=issues)


def audio_report_to_dict(report: AudioReport) -> dict[str, object]:
    return {
        "status": report.status,
        "duration": report.duration,
        "peak_db": report.peak_db,
        "rms_db": report.rms_db,
        "note_range": report.note_range,
        "issues": [
            {
                "level": issue.level,
                "code": issue.code,
                "message": issue.message,
                "value": issue.value,
            }
            for issue in report.issues
        ],
    }


def format_report_text(report: AudioReport) -> str:
    lines = ["OnGen Audio Lint Report", "", f"status: {report.status}"]
    if report.duration is not None:
        lines.append(f"duration: {report.duration:.2f} sec")
    if report.peak_db is not None:
        lines.append(f"peak_db: {report.peak_db:.2f} dB")
    if report.rms_db is not None:
        lines.append(f"rms_db: {report.rms_db:.2f} dB")
    if report.note_range is not None:
        lines.append(f"note_range: {report.note_range}")
    if report.issues:
        lines.append("issues:")
        for issue in report.issues:
            suffix = "" if issue.value is None else f" ({issue.value})"
            lines.append(f"  - {issue.level} {issue.code}: {issue.message}{suffix}")
    return "\n".join(lines)


def write_report_json(path: Path, report: AudioReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(audio_report_to_dict(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def resolve_output_path(path_text: str) -> Path:
    path = Path(path_text)
    if len(path.parts) == 1:
        return OUTPUT_DIR / path.name
    return path


def resolve_output_stem(path_text: str) -> Path:
    path = resolve_output_path(path_text)
    if path.suffix.lower() in AUDIO_EXTENSIONS:
        return path.with_suffix("")
    return path


def ensure_ffmpeg() -> None:
    if which("ffmpeg") is None:
        raise RuntimeError(
            "MP3/OGG 出力には ffmpeg が必要です。"
            " https://ffmpeg.org/download.html からインストールし、PATH に追加してください。"
        )


def run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "不明なエラー"
        raise RuntimeError(f"ffmpeg 変換に失敗: {detail}")


def ensure_ffplay() -> None:
    if which("ffplay") is None:
        raise RuntimeError(
            "--play での再生には ffplay が必要です。"
            " https://ffmpeg.org/download.html からffmpegをインストールし、PATH に追加してください。"
        )


def play_audio(wav_path: Path) -> None:
    result = subprocess.run(
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", str(wav_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "不明なエラー"
        raise RuntimeError(f"ffplay 再生に失敗: {detail}")


def export_mp3_from_wav(wav_path: Path, mp3_path: Path, bitrate: int) -> None:
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-i",
            str(wav_path),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            f"{bitrate}k",
            str(mp3_path),
        ]
    )


def export_ogg_from_wav(wav_path: Path, ogg_path: Path, quality: int) -> None:
    ogg_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-i",
            str(wav_path),
            "-codec:a",
            "libvorbis",
            "-q:a",
            str(quality),
            str(ogg_path),
        ]
    )


def write_wav(path: Path, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(str(path), SAMPLE_RATE, normalize_and_convert(audio))


def write_audio_files(
    audio: np.ndarray,
    stem: Path,
    output_format: str,
    bitrate: int,
    ogg_quality: int,
) -> list[Path]:
    targets = ["wav", "mp3", "ogg"] if output_format == "all" else [output_format]
    written: list[Path] = []
    temp_wav_path: Path | None = None

    try:
        if "wav" in targets:
            wav_path = stem.with_suffix(".wav")
            write_wav(wav_path, audio)
            written.append(wav_path)
            source_wav = wav_path
        elif "mp3" in targets or "ogg" in targets:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.close()
            temp_wav_path = Path(tmp.name)
            write_wav(temp_wav_path, audio)
            source_wav = temp_wav_path
        else:
            source_wav = stem.with_suffix(".wav")

        if "mp3" in targets or "ogg" in targets:
            ensure_ffmpeg()
            if "mp3" in targets:
                mp3_path = stem.with_suffix(".mp3")
                export_mp3_from_wav(source_wav, mp3_path, bitrate)
                written.append(mp3_path)
            if "ogg" in targets:
                ogg_path = stem.with_suffix(".ogg")
                export_ogg_from_wav(source_wav, ogg_path, ogg_quality)
                written.append(ogg_path)
    finally:
        if temp_wav_path is not None and temp_wav_path.exists():
            temp_wav_path.unlink()

    return written


# ---------------------------------------------------------------------------
# MML parser (minimal)
# ---------------------------------------------------------------------------

MML_TOKEN_RE = re.compile(
    r"""
    (?P<loop_start>\[) |
    (?P<loop_end>\]) |
    (?P<octave_up>>) |
    (?P<octave_down><) |
    (?P<tie>&) |
    (?P<gate_cut>@Q\d+) |
    (?P<gate>Q\d+(?:,[+-]?\d+)?) |
    (?P<volume_env>@V\d+) |
    (?P<pitch_env>EP\d+) |
    (?P<note_env>EN\d+) |
    (?P<mp_env>MP\d+) |
    (?P<transpose>K[+-]?\d+) |
    (?P<note_num>N\d+(?:,\d+)?) |
    (?P<fm_pct>%\d+) |
    (?P<fm_mul>\*\d+) |
    (?P<lfo_cmd>~\d+) |
    (?P<sample>W\([^)]+\)) |
    (?P<cmd>[OTLV@][+-]?\d*) |
    (?P<rest>R(?:\d+)?) |
    (?P<note>[A-G][+#-]?\d*\.*)
    """,
    re.VERBOSE | re.IGNORECASE,
)

PPMCK_NOTE_ZERO_MIDI = 36
PPMCK_TRANSPOSE_MIN = -127
PPMCK_TRANSPOSE_MAX = 126
PPMCK_DIRECT_NOTE_MAX = 95
PPMCK_TRACK_LETTERS = frozenset("ABCDE")
PPMCK_PULSE_DUTY: dict[int, float] = {
    0: 0.125,
    1: 0.25,
    2: 0.5,
    3: 0.75,
}
PPMCK_CHANNEL_MAP: dict[str, dict[str, object]] = {
    "A": {"waveform": "square", "duty": 0.5},
    "B": {"waveform": "square", "duty": 0.5},
    "C": {"waveform": "triangle"},
    "D": {"waveform": "noise", "noise_color": "white"},
    "E": {"waveform": "noise", "noise_color": "white"},
}
PPMCK_CHANNEL_ORDER = "ABCDE"
PPMCK_INLINE_TRACK_HEADER_RE = re.compile(
    r"(?<=\s)"
    r"(?:"
    r"([A-E]{2,})"
    r"|"
    r"([A-E])(?=\s+(?:[OTLVQRK@%*\[~]|W\())"
    r")"
    r"(?=\s|$)",
    re.IGNORECASE,
)
PPMCK_CLEAR_TRACK_CONTENT_RE = re.compile(
    r"(?:[OTLVQK@%*\[~]|W\()",
    re.IGNORECASE,
)
MML_MACRO_DEF_RE = re.compile(
    r"^@(?P<kind>V|EP|EN|MP)?(?P<index>\d+)\s*=\s*\{(?P<body>[^}]*)\}\s*$",
    re.IGNORECASE,
)
MML_MACRO_DEF_SCAN_RE = re.compile(
    r"@(?P<kind>V|EP|EN|MP)?(?P<index>\d+)\s*=\s*\{(?P<body>[^}]*)\}",
    re.IGNORECASE,
)


@dataclass
class ParsedMMLTrack:
    channel: str
    events: list[NoteEvent]
    synth_overrides: dict[str, object]
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class MMLState:
    octave: int = 4
    length: int = 4
    tempo: int = 120
    volume: int = 12
    waveform: str | None = None
    duty: float | None = None
    fm_index: float | None = None
    fm_ratio: float | None = None
    lfo_depth: float | None = None
    lfo_rate: float | None = None
    lfo_delay: float | None = None
    lfo_target: str | None = None
    sample_path: str | None = None
    transpose: int = 0
    gate: int = 8
    gate_denom: int = 8
    gate_adjust_frames: int = 0
    gate_cut_frames: int = 0
    volume_envelope: MacroSequence | None = None
    pitch_envelope: MacroSequence | None = None
    note_envelope: MacroSequence | None = None


def mml_length_to_seconds(length: int, dotted: int, tempo: int) -> float:
    beat = 60.0 / tempo
    unit = beat * 4.0 / max(length, 1)
    multiplier = 1.0
    for _ in range(dotted):
        multiplier += 0.5 * (0.5 ** _)
    return unit * multiplier


def parse_mml_meter(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", value)
    if not match:
        raise ValueError(f"MML拍子メタ情報の形式が不正です: {value}")
    numerator = int(match.group(1))
    denominator = int(match.group(2))
    if numerator <= 0 or denominator <= 0:
        raise ValueError(f"MML拍子メタ情報は正の値を指定してください: {value}")
    return numerator, denominator


def mml_measure_duration_seconds(meter: str, tempo: int) -> float:
    numerator, denominator = parse_mml_meter(meter)
    quarter = 60.0 / max(tempo, 1)
    return numerator * quarter * (4.0 / denominator)


def parse_mml_metadata(text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.split(";", 1)[0].strip()
        if not line.startswith("#"):
            continue
        match = re.match(r"#([A-Za-z][A-Za-z0-9_-]*)\s*(.*)$", line)
        if not match:
            continue
        key = match.group(1).upper()
        value = match.group(2).strip()
        if key in {"METER", "TIME"}:
            parse_mml_meter(value)
            metadata["meter"] = value.replace(" ", "")
        elif key == "TITLE" and value:
            metadata["title"] = value
    return metadata


def parse_macro_sequence(body: str) -> MacroSequence:
    values: list[float] = []
    loop_index: int | None = None
    tokens = [token for token in re.split(r"[\s,]+", body.strip()) if token]
    for token in tokens:
        if token == "|":
            if loop_index is not None:
                raise ValueError("MMLマクロ定義のループ記号 | は1回だけ指定できます")
            loop_index = len(values)
            continue
        values.append(float(token))
    if not values:
        raise ValueError("MMLマクロ定義には1つ以上の値が必要です")
    if loop_index is not None and loop_index >= len(values):
        raise ValueError("MMLマクロ定義の | の後ろにはループ対象値が必要です")
    return MacroSequence(tuple(values), loop_index)


def parse_mml_macro_definitions(text: str) -> MMLMacroBank:
    bank = MMLMacroBank()
    uncommented = "\n".join(raw_line.split(";", 1)[0] for raw_line in text.splitlines())
    for match in MML_MACRO_DEF_SCAN_RE.finditer(uncommented):
        kind = (match.group("kind") or "DUTY").upper()
        index = int(match.group("index"))
        sequence = parse_macro_sequence(match.group("body"))
        if kind == "DUTY":
            bank.duty[index] = sequence
        elif kind == "V":
            bank.volume[index] = sequence
        elif kind == "EP":
            bank.pitch[index] = sequence
        elif kind == "EN":
            bank.note[index] = sequence
        elif kind == "MP":
            bank.lfo[index] = sequence
    return bank


def is_mml_macro_definition(line: str) -> bool:
    return MML_MACRO_DEF_RE.match(line.strip()) is not None


def mml_volume_to_gain(volume: int) -> float:
    return min(max(volume, 0), 15) / 15.0


def mml_scale_to_fm_index(value: int) -> float:
    return (min(max(value, 0), 15) / 15.0) * 8.0


def mml_scale_to_lfo_depth(value: int) -> float:
    return (min(max(value, 0), 15) / 15.0) * 0.08


def apply_mml_pitch_lfo_macro(state: MMLState, sequence: MacroSequence, index: int) -> None:
    if len(sequence.values) < 3:
        raise ValueError(f"@MP{index} には delay, speed, depth の3値が必要です")
    delay_frames, speed, depth = sequence.values[:3]
    state.lfo_delay = max(delay_frames, 0.0) / 60.0
    state.lfo_rate = max(speed, 0.0)
    state.lfo_depth = mml_scale_to_lfo_depth(int(round(depth)))
    state.lfo_target = "pitch"


def preprocess_mml_text(text: str) -> str:
    text = MML_MACRO_DEF_SCAN_RE.sub("", text)
    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split(";", 1)[0].strip()
        if not line:
            continue
        if is_mml_macro_definition(line):
            continue
        if line.startswith("#"):
            if line.upper().startswith("#GATE-DENOM"):
                cleaned_lines.append(line)
            continue
        cleaned_lines.append(line)
    return " ".join(cleaned_lines)


def iter_mml_source_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split(";", 1)[0].strip()
        if not line:
            continue
        if line.startswith("#") and not line.upper().startswith("#GATE-DENOM"):
            continue
        lines.append(line)
    return lines


def _read_track_header_at(line: str, pos: int) -> tuple[list[str], int] | None:
    header_match = re.match(r"[A-E]+", line[pos:])
    if not header_match:
        return None
    header = header_match.group(0)
    if header != header.upper() or not set(header).issubset(PPMCK_TRACK_LETTERS):
        return None

    end = pos + header_match.end()
    if end < len(line) and not line[end].isspace():
        return None

    return list(header), end


def _split_line_track_chunks(line: str) -> list[tuple[list[str], str]]:
    chunks: list[tuple[list[str], str]] = []
    pos = 0
    length = len(line)

    while pos < length:
        while pos < length and line[pos].isspace():
            pos += 1
        if pos >= length:
            break

        header = _read_track_header_at(line, pos)
        if header is None:
            if not chunks:
                return []
            break
        track_ids, pos = header

        while pos < length and line[pos].isspace():
            pos += 1

        content_start = pos
        next_header = PPMCK_INLINE_TRACK_HEADER_RE.search(line[content_start:])
        if next_header:
            header_text = next_header.group(1) or next_header.group(2)
            candidate_pos = content_start + next_header.start()
            if (
                header_text == header_text.upper()
                and _read_track_header_at(line, candidate_pos) is not None
            ):
                content_end = content_start + next_header.start()
                content = line[content_start:content_end].strip()
                chunks.append((track_ids, content))
                pos = candidate_pos
                continue

        content = line[content_start:].strip()
        chunks.append((track_ids, content))
        break

    return chunks


def _has_clear_ppmck_track_headers(lines: list[str]) -> bool:
    channels: set[str] = set()
    for line in lines:
        if line.upper().startswith("#GATE-DENOM") or is_mml_macro_definition(line):
            continue
        chunks = _split_line_track_chunks(line)
        for track_ids, content in chunks:
            channels.update(track_ids)
            if len(track_ids) > 1 or PPMCK_CLEAR_TRACK_CONTENT_RE.match(content):
                return True
    return len(channels) > 1


def split_ppmck_tracks(text: str) -> dict[str, str] | None:
    lines = iter_mml_source_lines(text)
    if not lines:
        return None
    if not _has_clear_ppmck_track_headers(lines):
        return None

    global_directives: list[str] = []
    common_prefix: list[str] = []
    track_parts: dict[str, list[str]] = {}
    active_tracks: list[str] = []
    saw_header = False

    for line in lines:
        if line.upper().startswith("#GATE-DENOM"):
            global_directives.append(line)
            continue
        if is_mml_macro_definition(line):
            global_directives.append(line)
            continue

        chunks = _split_line_track_chunks(line)
        if not chunks:
            if not active_tracks:
                common_prefix.append(line)
                continue
            for track_id in active_tracks:
                track_parts.setdefault(track_id, []).append(line)
            continue

        for track_ids, content in chunks:
            saw_header = True
            active_tracks = track_ids
            if content:
                for track_id in active_tracks:
                    track_parts.setdefault(track_id, []).append(content)

    if not saw_header:
        return None

    prefix = " ".join([*global_directives, *common_prefix])
    ordered = [track_id for track_id in PPMCK_CHANNEL_ORDER if track_id in track_parts]
    result: dict[str, str] = {}
    prefix_joiner = "\n" if any(is_mml_macro_definition(line) for line in global_directives) else " "
    for track_id in ordered:
        body = " ".join(track_parts[track_id])
        result[track_id] = f"{prefix}{prefix_joiner}{body}".strip() if prefix else body
    return result


def has_ppmck_track_headers(text: str) -> bool:
    return split_ppmck_tracks(text) is not None


def apply_ppmck_channel_defaults(state: MMLState, channel: str | None) -> None:
    if not channel:
        return
    defaults = PPMCK_CHANNEL_MAP.get(channel)
    if not defaults:
        return
    if "waveform" in defaults:
        state.waveform = str(defaults["waveform"])
    if "duty" in defaults:
        state.duty = float(defaults["duty"])


def apply_synth_overrides(config: SynthConfig, overrides: dict[str, object]) -> SynthConfig:
    if not overrides:
        return config
    kwargs: dict[str, object] = {}
    for key, value in overrides.items():
        if hasattr(config, key):
            kwargs[key] = value
    return replace(config, **kwargs) if kwargs else config


def parse_mml_source(
    text: str,
    default_config: SynthConfig | None = None,
    *,
    dialect: str = "ppmck",
    max_repeat: int = 2,
    pyxel_multipart: bool = False,
) -> list[ParsedMMLTrack]:
    default_config = default_config or SynthConfig()
    metadata = parse_mml_metadata(text)
    if dialect.lower() == "pyxel":
        if pyxel_multipart:
            parts = split_pyxel_multipart_lines(text)
            if not parts:
                raise ValueError("Pyxelマルチパートとして解釈できるMML行がありません")
            return [
                ParsedMMLTrack(
                    channel=str(index),
                    events=parse_pyxel_mml(part, default_config, max_repeat=max_repeat),
                    synth_overrides={},
                    metadata=metadata,
                )
                for index, part in enumerate(parts, start=1)
            ]
        return [
            ParsedMMLTrack(
                channel="",
                events=parse_pyxel_mml(text, default_config, max_repeat=max_repeat),
                synth_overrides={},
                metadata=metadata,
            )
        ]

    split = split_ppmck_tracks(text)
    if split is None:
        return [
            ParsedMMLTrack(
                channel="",
                events=parse_mml(text, default_config),
                synth_overrides={},
                metadata=metadata,
            )
        ]

    tracks: list[ParsedMMLTrack] = []
    for channel in split:
        overrides = dict(PPMCK_CHANNEL_MAP.get(channel, {}))
        tracks.append(
            ParsedMMLTrack(
                channel=channel,
                events=parse_mml(split[channel], default_config, channel=channel),
                synth_overrides=overrides,
                metadata=metadata,
            )
        )
    return tracks


def split_pyxel_multipart_lines(text: str) -> list[str]:
    parts: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.lower().startswith(("http://", "https://")):
            continue
        parts.append(line)
    return parts


def mml_apply_gate(full_duration: float, state: MMLState) -> tuple[float, float]:
    denom = state.gate_denom
    if denom < 1 or not 0 <= state.gate <= denom:
        raise ValueError(f"PPMCKクオンタイズ値の範囲外です: q{state.gate} (分母 {denom})")
    sound = full_duration * (state.gate / denom) + state.gate_adjust_frames / 60.0
    if state.gate_cut_frames > 0:
        sound = max(0.0, sound - state.gate_cut_frames / 60.0)
    if sound <= 0.0 or sound > full_duration:
        raise ValueError(
            "PPMCKクオンタイズ後の発音時間は0秒より長く、音長以下である必要があります"
        )
    rest = max(0.0, full_duration - sound)
    return sound, rest


def mml_freq_from_note_number(note_num: int, transpose: int) -> float:
    if not 0 <= note_num <= PPMCK_DIRECT_NOTE_MAX:
        raise ValueError(f"PPMCK直接ノート番号の範囲外です: n{note_num}")
    # PPMCK uses 16 slots per octave; 13 through 15 alias A through B one octave down.
    octave, pitch = divmod(note_num, 16)
    if pitch == 12:
        raise ValueError(f"PPMCK直接ノート番号の未定義値です: n{note_num}")
    semitone = pitch if pitch < 12 else pitch - 16
    return midi_to_freq(PPMCK_NOTE_ZERO_MIDI + octave * 12 + semitone + transpose)


def mml_freq_from_name(name: str, octave: int, transpose: int) -> float:
    return midi_to_freq(note_to_midi(name, octave) + transpose)


def make_note_event(
    *,
    state: MMLState,
    default_config: SynthConfig,
    duration: float,
    frequency: float | None,
) -> NoteEvent:
    return NoteEvent(
        frequency=frequency,
        duration=duration,
        volume=mml_volume_to_gain(state.volume),
        waveform=state.waveform or default_config.waveform,
        duty=state.duty,
        sample_path=state.sample_path,
        fm_index=state.fm_index,
        fm_ratio=state.fm_ratio,
        lfo_depth=state.lfo_depth,
        lfo_rate=state.lfo_rate,
        lfo_delay=state.lfo_delay,
        lfo_target=state.lfo_target,
        volume_envelope=state.volume_envelope,
        pitch_envelope=state.pitch_envelope,
        note_envelope=state.note_envelope,
    )


def parse_mml(
    text: str,
    default_config: SynthConfig | None = None,
    *,
    channel: str | None = None,
) -> list[NoteEvent]:
    default_config = default_config or SynthConfig()
    state = MMLState()
    apply_ppmck_channel_defaults(state, channel)
    macro_bank = parse_mml_macro_definitions(text)
    events: list[NoteEvent] = []
    loop_stack: list[tuple[int, MMLState]] = []

    sample_paths: dict[str, str] = {}

    def _stash_sample(match: re.Match[str]) -> str:
        key = f"__S{len(sample_paths)}__"
        sample_paths[key] = match.group(1)
        return f"W({key})"

    preprocessed = preprocess_mml_text(text)
    gate_denom_match = re.search(r"#GATE-DENOM\s+([+-]?\d+)", preprocessed, re.IGNORECASE)
    if gate_denom_match:
        gate_denom = int(gate_denom_match.group(1))
        if gate_denom <= 0:
            raise ValueError(f"PPMCK #GATE-DENOM値の範囲外です: {gate_denom}")
        state.gate_denom = gate_denom
        preprocessed = re.sub(
            r"#GATE-DENOM\s+[+-]?\d+", "", preprocessed, flags=re.IGNORECASE
        )

    normalized = re.sub(r"W\(([^)]+)\)", _stash_sample, preprocessed, flags=re.IGNORECASE)
    compact = re.sub(r"\s+", "", normalized.upper())
    for key, path in sample_paths.items():
        compact = compact.replace(f"W({key.upper()})", f"W({path})")

    tie_pending = False
    last_pitched_event: NoteEvent | None = None
    last_gate_rest: NoteEvent | None = None
    last_pitched_full_duration = 0.0

    def emit(event: NoteEvent) -> None:
        nonlocal tie_pending, last_pitched_event, last_gate_rest, last_pitched_full_duration
        if tie_pending and events:
            events[-1].duration += event.duration
        else:
            events.append(event)
        tie_pending = False
        last_pitched_event = None
        last_gate_rest = None
        last_pitched_full_duration = 0.0

    def emit_pitched(full_duration: float, frequency: float) -> None:
        nonlocal tie_pending, last_pitched_event, last_gate_rest, last_pitched_full_duration
        if tie_pending and last_pitched_event is not None:
            if not math.isclose(last_pitched_event.frequency or 0.0, frequency):
                raise ValueError("PPMCKの & で接続できるのは同じ音程の音符だけです")
            if last_gate_rest is not None and events and events[-1] is last_gate_rest:
                events.pop()
            combined_duration = last_pitched_full_duration + full_duration
            sound, rest = mml_apply_gate(combined_duration, state)
            last_pitched_event.duration = sound
            last_pitched_full_duration = combined_duration
            last_gate_rest = None
            if rest > 0:
                last_gate_rest = make_note_event(
                    state=state,
                    default_config=default_config,
                    duration=rest,
                    frequency=None,
                )
                events.append(last_gate_rest)
            tie_pending = False
            return
        if tie_pending:
            raise ValueError("PPMCKの & の前後には同じ音程の音符が必要です")

        sound, rest = mml_apply_gate(full_duration, state)
        pitched_event = make_note_event(
            state=state,
            default_config=default_config,
            duration=sound,
            frequency=frequency,
        )
        if sound > 0:
            events.append(pitched_event)
        last_pitched_event = pitched_event
        last_pitched_full_duration = full_duration
        last_gate_rest = None
        if rest > 0:
            last_gate_rest = make_note_event(
                state=state,
                default_config=default_config,
                duration=rest,
                frequency=None,
            )
            events.append(last_gate_rest)
        tie_pending = False

    def emit_rest(full_duration: float) -> None:
        emit(
            make_note_event(
                state=state,
                default_config=default_config,
                duration=full_duration,
                frequency=None,
            )
        )

    pos = 0
    while pos < len(compact):
        match = MML_TOKEN_RE.match(compact, pos)
        if not match:
            raise ValueError(
                f"未対応のMMLトークンです: {compact[pos:pos + 10]!r} (位置 {pos})"
            )

        pos = match.end()
        if match.group("loop_start"):
            loop_stack.append((len(events), MMLState(**vars(state))))
            continue

        if match.group("loop_end"):
            direct_match = re.match(r"(\d+)", compact[pos:])
            pipe_match = re.match(r"\|(\d+)", compact[pos:])
            if direct_match:
                repeat = int(direct_match.group(1))
                pos += direct_match.end()
            elif pipe_match:
                repeat = int(pipe_match.group(1))
                pos += pipe_match.end()
            else:
                repeat = 2
            if not loop_stack:
                continue
            start_idx, saved_state = loop_stack.pop()
            segment = events[start_idx:]
            events = events[:start_idx]
            for _ in range(repeat):
                events.extend(segment)
            state = saved_state
            continue

        if match.group("tie"):
            tie_pending = True
            continue

        if match.group("gate_cut"):
            gate_cut_frames = int(match.group("gate_cut")[2:])
            if not 0 <= gate_cut_frames <= 65535:
                raise ValueError(f"PPMCK @q値の範囲外です: @q{gate_cut_frames}")
            state.gate_cut_frames = gate_cut_frames
            continue

        if match.group("gate"):
            token = match.group("gate")[1:]
            if "," in token:
                gate_text, adjust_text = token.split(",", 1)
                state.gate = int(gate_text)
                state.gate_adjust_frames = int(adjust_text)
            else:
                state.gate = int(token)
                state.gate_adjust_frames = 0
            if not 0 <= state.gate <= state.gate_denom:
                raise ValueError(
                    f"PPMCKクオンタイズ値の範囲外です: q{state.gate} (分母 {state.gate_denom})"
                )
            continue

        if match.group("volume_env"):
            index = int(match.group("volume_env")[2:])
            if index not in macro_bank.volume:
                raise ValueError(f"未定義の音量エンベロープです: @v{index}")
            state.volume_envelope = macro_bank.volume[index]
            continue

        if match.group("pitch_env"):
            index = int(match.group("pitch_env")[2:])
            if index not in macro_bank.pitch:
                raise ValueError(f"未定義のピッチエンベロープです: @EP{index}")
            state.pitch_envelope = macro_bank.pitch[index]
            continue

        if match.group("note_env"):
            index = int(match.group("note_env")[2:])
            if index not in macro_bank.note:
                raise ValueError(f"未定義のノートエンベロープです: @EN{index}")
            state.note_envelope = macro_bank.note[index]
            continue

        if match.group("mp_env"):
            index = int(match.group("mp_env")[2:])
            if index not in macro_bank.lfo:
                raise ValueError(f"未定義のピッチLFOマクロです: @MP{index}")
            apply_mml_pitch_lfo_macro(state, macro_bank.lfo[index], index)
            continue

        if match.group("transpose"):
            token = match.group("transpose")[1:]
            transpose = int(token)
            if not PPMCK_TRANSPOSE_MIN <= transpose <= PPMCK_TRANSPOSE_MAX:
                raise ValueError(f"PPMCKトランスポーズ値の範囲外です: K{token}")
            state.transpose = transpose
            continue

        if match.group("note_num"):
            token = match.group("note_num")[1:]
            if "," in token:
                num_text, len_text = token.split(",", 1)
                note_num = int(num_text)
                length = int(len_text)
            else:
                note_num = int(token)
                length = state.length
            full_duration = mml_length_to_seconds(length, 0, state.tempo)
            emit_pitched(full_duration, mml_freq_from_note_number(note_num, state.transpose))
            continue

        if match.group("cmd"):
            cmd = match.group("cmd")
            kind = cmd[0]
            value = cmd[1:]
            if not value:
                continue
            number = int(value)
            if kind == "O":
                state.octave = number
            elif kind == "L":
                state.length = max(number, 1)
            elif kind == "T":
                state.tempo = max(number, 1)
            elif kind == "V":
                state.volume = min(max(number, 0), 15)
            elif kind == "@":
                if channel in ("A", "B") and 0 <= number <= 3:
                    state.waveform = "square"
                    state.duty = PPMCK_PULSE_DUTY[number]
                else:
                    preset = WAVEFORM_PRESETS.get(number)
                    if preset:
                        state.waveform = preset.get("waveform", state.waveform)
                        state.duty = preset.get("duty", state.duty)
            continue

        if match.group("octave_up"):
            state.octave += 1
            continue

        if match.group("octave_down"):
            state.octave -= 1
            continue

        if match.group("fm_pct"):
            state.fm_index = mml_scale_to_fm_index(int(match.group("fm_pct")[1:]))
            continue

        if match.group("fm_mul"):
            state.fm_ratio = max(int(match.group("fm_mul")[1:]), 1) / 2.0
            continue

        if match.group("lfo_cmd"):
            state.lfo_depth = mml_scale_to_lfo_depth(int(match.group("lfo_cmd")[1:]))
            state.lfo_target = "pitch"
            continue

        if match.group("sample"):
            sample_token = match.group("sample")
            state.sample_path = sample_token[2:-1]
            duration = mml_length_to_seconds(state.length, 0, state.tempo)
            emit_rest(duration)
            state.sample_path = None
            continue

        if match.group("rest"):
            token = match.group("rest")
            length = state.length
            length_match = re.fullmatch(r"R(\d+)", token, re.IGNORECASE)
            if length_match:
                length = int(length_match.group(1))
            full_duration = mml_length_to_seconds(length, 0, state.tempo)
            emit_rest(full_duration)
            continue

        if match.group("note"):
            token = match.group("note")
            note_match = re.match(r"([A-G](?:\+|#|-)?)(\d*)(\.*)", token, re.IGNORECASE)
            if not note_match:
                continue
            name = note_match.group(1)
            length_text = note_match.group(2)
            dots = note_match.group(3) or ""
            length = int(length_text) if length_text else state.length
            full_duration = mml_length_to_seconds(length, len(dots), state.tempo)
            emit_pitched(
                full_duration,
                mml_freq_from_name(name, state.octave, state.transpose),
            )

    return events


# ---------------------------------------------------------------------------
# Pyxel MML parser (2.4+ dialect)
# ---------------------------------------------------------------------------

PYXEL_TEMPO_MIN = 1
PYXEL_TEMPO_MAX = 900
PYXEL_OCTAVE_MIN = -1
PYXEL_OCTAVE_MAX = 9
PYXEL_LENGTH_MIN = 1
PYXEL_LENGTH_MAX = 192
PYXEL_VOLUME_MAX = 127
PYXEL_GATE_MAX = 100
PYXEL_TICKS_PER_QUARTER = 48
PYXEL_DEFAULT_MAX_REPEAT = 2

PYXEL_TONE_MAP: dict[int, dict[str, object]] = {
    0: {"waveform": "triangle"},
    1: {"waveform": "square", "duty": 0.5},
    2: {"waveform": "square", "duty": 0.25},
    3: {"waveform": "noise", "noise_color": "white"},
}

PYXEL_MML_TOKEN_RE = re.compile(
    r"""
    (?P<loop_start>\[) |
    (?P<loop_end>\]) |
    (?P<octave_up>>) |
    (?P<octave_down><) |
    (?P<tie_ext>&\d+) |
    (?P<tie>&) |
    (?P<env_macro>@ENV\d*\{[^}]*\}) |
    (?P<env_slot>@ENV\d+) |
    (?P<vib_macro>@VIB\d*\{[^}]*\}) |
    (?P<vib_slot>@VIB\d+) |
    (?P<gli_macro>@GLI(?:\d+|\*)\{[^}]*\}) |
    (?P<gli_slot>@GLI(?:\d+|\*)) |
    (?P<gate>Q\d+) |
    (?P<detune>Y[+-]?\d+) |
    (?P<transpose>K[+-]?\d+) |
    (?P<cmd>[OTLV][+-]?\d*) |
    (?P<tone>@[0-3]) |
    (?P<rest>R(?:\d+)?) |
    (?P<note>[A-G][+#-]?\d*\.*)
    """,
    re.VERBOSE | re.IGNORECASE,
)

PYXEL_UNSUPPORTED_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"%\d+", "OnGen 独自の % コマンド"),
    (r"\*\d+", "OnGen 独自の * コマンド"),
    (r"W\(", "OnGen 独自の W(...) サンプル"),
    (r"N\d+", "PPMCK 流の直接ノート番号 N"),
    (r"#GATE-DENOM", "PPMCK の #GATE-DENOM"),
    (r"@Q\d+", "PPMCK の @Q フレーム短縮"),
    (r"(?<![A-Z])Q\d+,\d+", "PPMCK の Q<num>,<frames> 形式"),
)


@dataclass
class PyxelMMLState:
    octave: int = 4
    length: int = 4
    tempo: int = 120
    volume: int = 100
    gate_percent: int = 80
    transpose: int = 0
    detune_cents: int = 0
    waveform: str | None = "triangle"
    duty: float | None = None
    noise_color: str = "white"
    env_adsr: ADSR | None = None
    vib_rate: float | None = None
    vib_depth: float | None = None
    gli_cents: float | None = None
    gli_duration: float | None = None


def preprocess_pyxel_mml_text(text: str) -> str:
    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split(";", 1)[0].strip()
        if line:
            cleaned_lines.append(line)
    return " ".join(cleaned_lines)


def pyxel_tick_to_seconds(ticks: int, tempo: int) -> float:
    quarter = 60.0 / max(tempo, 1)
    return quarter * (ticks / PYXEL_TICKS_PER_QUARTER)


def pyxel_length_to_seconds(length: int, dotted: int, tempo: int) -> float:
    return mml_length_to_seconds(length, dotted, tempo)


def pyxel_volume_to_gain(volume: int) -> float:
    return min(max(volume, 0), PYXEL_VOLUME_MAX) / PYXEL_VOLUME_MAX


def pyxel_apply_gate(full_duration: float, gate_percent: int) -> tuple[float, float]:
    ratio = min(max(gate_percent, 0), PYXEL_GATE_MAX) / 100.0
    sound = full_duration * ratio
    rest = max(0.0, full_duration - sound)
    return sound, rest


def pyxel_freq_from_name(name: str, octave: int, transpose: int, detune_cents: int) -> float:
    freq = mml_freq_from_name(name, octave, transpose)
    if detune_cents:
        freq *= 2.0 ** (detune_cents / 1200.0)
    return freq


def apply_pyxel_tone(state: PyxelMMLState, tone: int) -> None:
    if tone not in PYXEL_TONE_MAP:
        raise ValueError(f"Pyxel音色の範囲外です: @{tone}")
    defaults = PYXEL_TONE_MAP[tone]
    state.waveform = str(defaults["waveform"])
    state.duty = float(defaults["duty"]) if "duty" in defaults else None
    state.noise_color = str(defaults.get("noise_color", "white"))


def pyxel_parse_macro_numbers(body: str) -> list[float]:
    values: list[float] = []
    for token in body.split(","):
        token = token.strip()
        if not token:
            continue
        if token == "*":
            values.append(float("nan"))
        else:
            values.append(float(token))
    return values


def pyxel_env_from_macro(values: list[float], tempo: int) -> ADSR:
    if not values:
        raise ValueError("Pyxel @ENV マクロの引数が空です")
    init_vol = min(max(values[0], 0.0), PYXEL_VOLUME_MAX) / PYXEL_VOLUME_MAX
    decay = 0.05
    sustain = init_vol
    if len(values) >= 3:
        decay = pyxel_tick_to_seconds(int(values[1]), tempo)
        sustain = min(max(values[2], 0.0), PYXEL_VOLUME_MAX) / PYXEL_VOLUME_MAX
    return ADSR(attack=0.002, decay=max(decay, 0.001), sustain=sustain, release=0.04)


def pyxel_vib_from_macro(values: list[float], tempo: int) -> tuple[float, float]:
    if len(values) < 3:
        raise ValueError("Pyxel @VIB マクロには delay, period, depth が必要です")
    period_ticks = int(values[1])
    depth_cents = float(values[2])
    period_sec = max(pyxel_tick_to_seconds(max(period_ticks, 1), tempo), 0.01)
    rate = 1.0 / period_sec
    depth = min(abs(depth_cents) / 1200.0, 0.12)
    return rate, depth


def pyxel_gli_from_macro(values: list[float], tempo: int) -> tuple[float, float]:
    if len(values) < 2:
        raise ValueError("Pyxel @GLI マクロには offset, duration が必要です")
    if math.isnan(values[0]):
        cents = 0.0
    else:
        cents = float(values[0])
    if math.isnan(values[1]):
        duration = 0.0
    else:
        duration = pyxel_tick_to_seconds(max(int(values[1]), 0), tempo)
    return cents, duration


def make_pyxel_note_event(
    *,
    state: PyxelMMLState,
    default_config: SynthConfig,
    duration: float,
    frequency: float | None,
) -> NoteEvent:
    return NoteEvent(
        frequency=frequency,
        duration=duration,
        volume=pyxel_volume_to_gain(state.volume),
        waveform=state.waveform or default_config.waveform,
        duty=state.duty,
        lfo_depth=state.vib_depth,
        lfo_rate=state.vib_rate,
        lfo_target="pitch" if state.vib_depth else None,
        event_adsr=state.env_adsr,
        glide_cents=state.gli_cents,
        glide_duration=state.gli_duration,
    )


def expand_pyxel_repeats(text: str, max_repeat: int) -> str:
    def expand_section(start: int, *, nested: bool) -> tuple[str, int]:
        parts: list[str] = []
        pos = start
        while pos < len(text):
            char = text[pos]
            if char == "[":
                expanded, pos = expand_section(pos + 1, nested=True)
                count_match = re.match(r"\d+", text[pos:])
                if count_match:
                    repeat = int(count_match.group(0))
                    if repeat < 1:
                        raise ValueError("Pyxelのリピート回数は1以上を指定してください")
                    pos += count_match.end()
                else:
                    repeat = max_repeat
                parts.append(expanded * repeat)
                continue
            if char == "]":
                if not nested:
                    raise ValueError("Pyxelのリピート終端 ] に対応する [ がありません")
                return "".join(parts), pos + 1
            parts.append(char)
            pos += 1
        if nested:
            raise ValueError("Pyxelのリピート開始 [ が閉じられていません")
        return "".join(parts), pos

    expanded, _ = expand_section(0, nested=False)
    return expanded


def report_pyxel_compat_issues(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", preprocess_pyxel_mml_text(text).upper())
    issues: list[str] = []
    for pattern, message in PYXEL_UNSUPPORTED_PATTERNS:
        if re.search(pattern, compact, re.IGNORECASE):
            issues.append(message)
    if split_ppmck_tracks(text):
        issues.append("PPMCK 流の A〜E トラック宣言（Pyxel は Sound 単位の MML）")
    return issues


def parse_pyxel_mml(
    text: str,
    default_config: SynthConfig | None = None,
    *,
    max_repeat: int = PYXEL_DEFAULT_MAX_REPEAT,
) -> list[NoteEvent]:
    if max_repeat < 1:
        raise ValueError("--max-repeat は正の整数を指定してください")

    default_config = default_config or SynthConfig()
    state = PyxelMMLState()
    events: list[NoteEvent] = []
    env_slots: dict[int, ADSR] = {}
    vib_slots: dict[int, tuple[float, float]] = {}
    gli_slots: dict[int, tuple[float, float]] = {}

    compact = re.sub(r"\s+", "", preprocess_pyxel_mml_text(text).upper())
    compact = expand_pyxel_repeats(compact, max_repeat)

    tie_pending = False
    legato_pending = False
    last_pitched_event: NoteEvent | None = None
    last_gate_rest: NoteEvent | None = None
    last_pitched_full_duration = 0.0
    last_pitched_frequency: float | None = None
    last_extend_kind: str | None = None
    last_rest_event: NoteEvent | None = None

    def emit_rest(full_duration: float) -> None:
        nonlocal tie_pending, legato_pending, last_extend_kind, last_rest_event
        tie_pending = False
        legato_pending = False
        rest_event = make_pyxel_note_event(
            state=state,
            default_config=default_config,
            duration=full_duration,
            frequency=None,
        )
        events.append(rest_event)
        last_extend_kind = "rest"
        last_rest_event = rest_event

    def emit_pitched(full_duration: float, frequency: float) -> None:
        nonlocal tie_pending, legato_pending, last_extend_kind, last_rest_event
        nonlocal last_pitched_event, last_gate_rest, last_pitched_full_duration
        nonlocal last_pitched_frequency

        effective_duration = full_duration

        if tie_pending and last_pitched_event is not None:
            if math.isclose(last_pitched_frequency or 0.0, frequency, rel_tol=0.0, abs_tol=1e-6):
                if last_gate_rest is not None and events and events[-1] is last_gate_rest:
                    events.pop()
                combined_duration = last_pitched_full_duration + effective_duration
                sound, rest = pyxel_apply_gate(combined_duration, state.gate_percent)
                last_pitched_event.duration = sound
                last_pitched_full_duration = combined_duration
                last_gate_rest = None
                if rest > 0:
                    last_gate_rest = make_pyxel_note_event(
                        state=state,
                        default_config=default_config,
                        duration=rest,
                        frequency=None,
                    )
                    events.append(last_gate_rest)
            else:
                if last_gate_rest is not None and events and events[-1] is last_gate_rest:
                    events.pop()
                if last_pitched_event is not None:
                    last_pitched_event.duration = last_pitched_full_duration
                    last_gate_rest = None
                sound, rest = pyxel_apply_gate(effective_duration, state.gate_percent)
                if sound > 0:
                    pitched_event = make_pyxel_note_event(
                        state=state,
                        default_config=default_config,
                        duration=sound,
                        frequency=frequency,
                    )
                    events.append(pitched_event)
                    last_pitched_event = pitched_event
                else:
                    last_pitched_event = None
                last_pitched_full_duration = effective_duration
                if rest > 0:
                    last_gate_rest = make_pyxel_note_event(
                        state=state,
                        default_config=default_config,
                        duration=rest,
                        frequency=None,
                    )
                    events.append(last_gate_rest)
                last_pitched_frequency = frequency
            tie_pending = False
            legato_pending = False
            last_extend_kind = "pitched"
            last_rest_event = None
            return

        if tie_pending:
            raise ValueError("Pyxelの & の後に音符または休符が必要です")

        sound, rest = pyxel_apply_gate(effective_duration, state.gate_percent)
        pitched_event = make_pyxel_note_event(
            state=state,
            default_config=default_config,
            duration=sound,
            frequency=frequency,
        )
        if sound > 0:
            events.append(pitched_event)
        last_pitched_event = pitched_event if sound > 0 else None
        last_pitched_full_duration = effective_duration
        last_pitched_frequency = frequency
        last_gate_rest = None
        if rest > 0:
            last_gate_rest = make_pyxel_note_event(
                state=state,
                default_config=default_config,
                duration=rest,
                frequency=None,
            )
            events.append(last_gate_rest)
        tie_pending = False
        legato_pending = False
        last_extend_kind = "pitched"
        last_rest_event = None

    pos = 0
    while pos < len(compact):
        match = PYXEL_MML_TOKEN_RE.match(compact, pos)
        if not match:
            raise ValueError(
                f"未対応のPyxel MMLトークンです: {compact[pos:pos + 12]!r} (位置 {pos})"
            )
        pos = match.end()

        if match.group("tie_ext"):
            length = int(match.group("tie_ext")[1:])
            extra_duration = pyxel_length_to_seconds(length, 0, state.tempo)
            if last_extend_kind == "pitched" and last_pitched_event is not None:
                if last_gate_rest is not None and events and events[-1] is last_gate_rest:
                    events.pop()
                last_pitched_full_duration += extra_duration
                sound, rest = pyxel_apply_gate(last_pitched_full_duration, state.gate_percent)
                last_pitched_event.duration = sound
                last_gate_rest = None
                if rest > 0:
                    last_gate_rest = make_pyxel_note_event(
                        state=state,
                        default_config=default_config,
                        duration=rest,
                        frequency=None,
                    )
                    events.append(last_gate_rest)
            elif last_extend_kind == "rest" and last_rest_event is not None:
                last_rest_event.duration += extra_duration
            else:
                raise ValueError("Pyxelの &<length> の前に音符または休符が必要です")
            continue

        if match.group("tie"):
            tie_pending = True
            continue

        if match.group("env_macro"):
            token = match.group("env_macro").upper()
            body_match = re.search(r"\{([^}]*)\}", token)
            if not body_match:
                continue
            slot_match = re.match(r"@ENV(\d+)", token)
            slot = int(slot_match.group(1)) if slot_match else 0
            if slot < 1:
                raise ValueError("Pyxel @ENV マクロのスロットは1以上を指定してください")
            state.env_adsr = pyxel_env_from_macro(
                pyxel_parse_macro_numbers(body_match.group(1)),
                state.tempo,
            )
            env_slots[slot] = state.env_adsr
            continue

        if match.group("env_slot"):
            slot = int(match.group("env_slot")[4:] or "0")
            if slot == 0:
                state.env_adsr = None
            elif slot in env_slots:
                state.env_adsr = env_slots[slot]
            else:
                raise ValueError(f"未定義のPyxel @ENVスロットです: {slot}")
            continue

        if match.group("vib_macro"):
            token = match.group("vib_macro").upper()
            body_match = re.search(r"\{([^}]*)\}", token)
            if not body_match:
                continue
            slot_match = re.match(r"@VIB(\d+)", token)
            slot = int(slot_match.group(1)) if slot_match else 0
            if slot < 1:
                raise ValueError("Pyxel @VIB マクロのスロットは1以上を指定してください")
            rate, depth = pyxel_vib_from_macro(
                pyxel_parse_macro_numbers(body_match.group(1)),
                state.tempo,
            )
            state.vib_rate = rate
            state.vib_depth = depth
            vib_slots[slot] = (rate, depth)
            continue

        if match.group("vib_slot"):
            slot = int(match.group("vib_slot")[4:] or "0")
            if slot == 0:
                state.vib_rate = None
                state.vib_depth = None
            elif slot in vib_slots:
                state.vib_rate, state.vib_depth = vib_slots[slot]
            else:
                raise ValueError(f"未定義のPyxel @VIBスロットです: {slot}")
            continue

        if match.group("gli_macro"):
            token = match.group("gli_macro").upper()
            body_match = re.search(r"\{([^}]*)\}", token)
            if not body_match:
                continue
            slot_match = re.match(r"@GLI(\d+)", token)
            slot = int(slot_match.group(1)) if slot_match else 0
            if slot < 1:
                raise ValueError("Pyxel @GLI マクロのスロットは1以上を指定してください")
            state.gli_cents, state.gli_duration = pyxel_gli_from_macro(
                pyxel_parse_macro_numbers(body_match.group(1)),
                state.tempo,
            )
            gli_slots[slot] = (state.gli_cents, state.gli_duration)
            continue

        if match.group("gli_slot"):
            slot_text = match.group("gli_slot")[4:]
            if slot_text in ("", "0", "*"):
                state.gli_cents = None
                state.gli_duration = None
            else:
                slot = int(slot_text)
                if slot not in gli_slots:
                    raise ValueError(f"未定義のPyxel @GLIスロットです: {slot}")
                state.gli_cents, state.gli_duration = gli_slots[slot]
            continue

        if match.group("gate"):
            gate_percent = int(match.group("gate")[1:])
            if not 0 <= gate_percent <= PYXEL_GATE_MAX:
                raise ValueError(f"Pyxel Q値の範囲外です: Q{gate_percent}")
            state.gate_percent = gate_percent
            continue

        if match.group("detune"):
            cents = int(match.group("detune")[1:])
            state.detune_cents = cents
            continue

        if match.group("transpose"):
            state.transpose = int(match.group("transpose")[1:])
            continue

        if match.group("cmd"):
            cmd = match.group("cmd")
            kind = cmd[0]
            value = cmd[1:]
            if not value:
                continue
            number = int(value)
            if kind == "O":
                if not PYXEL_OCTAVE_MIN <= number <= PYXEL_OCTAVE_MAX:
                    raise ValueError(f"Pyxel O値の範囲外です: O{number}")
                state.octave = number
            elif kind == "L":
                if not PYXEL_LENGTH_MIN <= number <= PYXEL_LENGTH_MAX:
                    raise ValueError(f"Pyxel L値の範囲外です: L{number}")
                state.length = number
            elif kind == "T":
                if not PYXEL_TEMPO_MIN <= number <= PYXEL_TEMPO_MAX:
                    raise ValueError(f"Pyxel T値の範囲外です: T{number}")
                state.tempo = number
            elif kind == "V":
                if not 0 <= number <= PYXEL_VOLUME_MAX:
                    raise ValueError(f"Pyxel V値の範囲外です: V{number}")
                state.volume = number
            continue

        if match.group("tone"):
            apply_pyxel_tone(state, int(match.group("tone")[1:]))
            continue

        if match.group("octave_up"):
            state.octave = min(state.octave + 1, PYXEL_OCTAVE_MAX)
            continue

        if match.group("octave_down"):
            state.octave = max(state.octave - 1, PYXEL_OCTAVE_MIN)
            continue

        if match.group("rest"):
            token = match.group("rest")
            length = state.length
            length_match = re.fullmatch(r"R(\d+)", token, re.IGNORECASE)
            if length_match:
                length = int(length_match.group(1))
            full_duration = pyxel_length_to_seconds(length, 0, state.tempo)
            emit_rest(full_duration)
            continue

        if match.group("note"):
            token = match.group("note")
            note_match = re.match(r"([A-G](?:\+|#|-)?)(\d*)(\.*)", token, re.IGNORECASE)
            if not note_match:
                continue
            name = note_match.group(1)
            length_text = note_match.group(2)
            dots = note_match.group(3) or ""
            length = int(length_text) if length_text else state.length
            full_duration = pyxel_length_to_seconds(length, len(dots), state.tempo)
            emit_pitched(
                full_duration,
                pyxel_freq_from_name(name, state.octave, state.transpose, state.detune_cents),
            )

    return events


def parse_mml_by_dialect(
    text: str,
    default_config: SynthConfig | None = None,
    *,
    dialect: str = "ppmck",
    max_repeat: int = PYXEL_DEFAULT_MAX_REPEAT,
    channel: str | None = None,
) -> list[NoteEvent]:
    normalized = dialect.lower()
    if normalized == "pyxel":
        return parse_pyxel_mml(text, default_config, max_repeat=max_repeat)
    if normalized == "ppmck":
        return parse_mml(text, default_config, channel=channel)
    raise ValueError(f"未対応の MML 方言です: {dialect}")


# ---------------------------------------------------------------------------
# ABC parser (minimal)
# ---------------------------------------------------------------------------

ABC_HEADER_RE = re.compile(r"^([A-Za-z]):\s*(.*)$")

NOTE_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# シャープ/フラット系の調号で変化記号が付く音名の順序
SHARP_ORDER = "FCGDAEB"
FLAT_ORDER = "BEADGCF"

# 長調の調号（シャープ/フラットの数）
MAJOR_SHARPS = {"C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7}
MAJOR_FLATS = {"C": 0, "F": 1, "BB": 2, "EB": 3, "AB": 4, "DB": 5, "GB": 6, "CB": 7}

# 短調（Am 等）から平行長調への変換
MINOR_TO_MAJOR = {
    "A": "C", "E": "G", "B": "D", "F#": "A", "C#": "E", "G#": "B", "D#": "F#",
    "D": "F", "G": "BB", "C": "EB", "F": "AB", "BB": "DB", "EB": "GB", "AB": "CB",
}

ABC_ACCIDENTAL_OFFSETS = {"^^": 2, "^": 1, "=": 0, "_": -1, "__": -2}


def abc_default_unit_from_meter(meter: str) -> float:
    """Return ABC's implicit L: value for the given meter."""
    normalized = meter.strip().upper()
    if normalized in {"C", "C|"}:
        meter_value = 1.0
    elif "/" in normalized:
        num, den = normalized.split("/", 1)
        try:
            meter_value = int(num.strip()) / max(int(den.strip()), 1)
        except ValueError:
            meter_value = 1.0
    else:
        meter_value = 1.0
    return 1.0 / 16.0 if meter_value < 0.75 else 1.0 / 8.0


def abc_length_multiplier(length_text: str) -> float:
    """Parse an ABC note-length suffix such as 2, /, /2, //, or 3/2."""
    if not length_text:
        return 1.0
    if "/" not in length_text:
        return float(int(length_text))

    match = re.fullmatch(r"(\d*)(/+)(\d*)", length_text)
    if not match:
        raise ValueError(f"不正な ABC 音長: {length_text}")

    numerator = int(match.group(1)) if match.group(1) else 1
    slash_count = len(match.group(2))
    explicit_denominator = int(match.group(3)) if match.group(3) else 2
    denominator = explicit_denominator * (2 ** (slash_count - 1))
    return numerator / max(denominator, 1)


def abc_quarter_note_tempo(q_header: str, fallback: int = 120) -> float:
    """Convert an ABC Q: declaration to quarter-note beats per minute."""
    match = re.search(r"(?:(\d+)\s*/\s*(\d+)\s*)?=\s*(\d+)", q_header)
    if match:
        numerator = int(match.group(1) or 1)
        denominator = int(match.group(2) or 4)
        bpm = int(match.group(3))
        return bpm * 4.0 * numerator / max(denominator, 1)

    trailing_bpm = re.search(r"(\d+)\s*$", q_header)
    return float(int(trailing_bpm.group(1))) if trailing_bpm else float(fallback)


def key_signature_offsets(key: str) -> dict[str, int]:
    """K: ヘッダ（例: "G", "Bm", "F#", "Bb"）から音名ごとの半音オフセットを求める。"""
    key = key.strip()
    if not key:
        return {}
    match = re.match(r"^([A-Ga-g])(#|b)?\s*(.*)$", key)
    if not match:
        return {}
    letter = match.group(1).upper()
    accidental = (match.group(2) or "").upper()
    mode = match.group(3).strip().lower()

    key_name = letter + accidental

    if mode.startswith("m") and not mode.startswith("maj"):
        key_name = MINOR_TO_MAJOR.get(key_name, "C")

    offsets = {letter: 0 for letter in "ABCDEFG"}
    sharps = MAJOR_SHARPS.get(key_name, 0)
    if sharps:
        for letter in SHARP_ORDER[:sharps]:
            offsets[letter] = 1
        return offsets

    flats = MAJOR_FLATS.get(key_name, 0)
    if flats:
        for letter in FLAT_ORDER[:flats]:
            offsets[letter] = -1
    return offsets


def parse_abc_note_body(
    body: str,
    tempo: float,
    default_unit: float,
    key: str,
    default_volume: float = 0.8,
) -> list[NoteEvent]:
    events: list[NoteEvent] = []
    key_offsets = key_signature_offsets(key)
    measure_accidentals: dict[tuple[str, int], int] = {}
    token_re = re.compile(
        r"""
        (?P<bar>\|+) |
        (?P<rest>z(?:\d+(?:/\d*)?|/+\d*)?) |
        (?P<acc>\^\^|__|\^|_|=)?(?P<note>[A-Ga-g])(?P<octmark>[,']*)(?P<length>\d+(?:/\d*)?|/+\d*)?
        """,
        re.VERBOSE,
    )

    pos = 0
    while pos < len(body):
        match = token_re.match(body, pos)
        if not match:
            pos += 1
            continue
        pos = match.end()

        if match.group("bar"):
            measure_accidentals.clear()
            continue

        length_text = match.group("length") or ""
        if match.group("rest"):
            length_text = match.group("rest")[1:]
        length_value = abc_length_multiplier(length_text)

        duration = (60.0 / tempo) * (4.0 * default_unit) * length_value

        if match.group("rest"):
            events.append(NoteEvent(frequency=None, duration=duration, volume=default_volume))
            continue

        note_token = match.group("note")
        if not note_token:
            continue

        letter = note_token.upper()
        base_octave = 4 if note_token.isupper() else 5
        octmark = match.group("octmark") or ""
        octave_shift = octmark.count("'") - octmark.count(",")
        octave = base_octave + octave_shift

        acc_token = match.group("acc")
        accidental_key = (letter, octave)
        if acc_token is not None:
            offset = ABC_ACCIDENTAL_OFFSETS[acc_token]
            measure_accidentals[accidental_key] = offset
        elif accidental_key in measure_accidentals:
            offset = measure_accidentals[accidental_key]
        else:
            offset = key_offsets.get(letter, 0)

        midi = (octave + 1) * 12 + NOTE_SEMITONES[letter] + offset
        freq = midi_to_freq(midi)
        events.append(
            NoteEvent(
                frequency=freq,
                duration=duration,
                volume=default_volume,
            )
        )

    return events


def parse_abc(text: str, default_config: SynthConfig | None = None) -> list[NoteEvent]:
    default_config = default_config or SynthConfig()
    headers: dict[str, str] = {}
    body_lines: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.split("%", 1)[0].strip()
        if not line:
            continue
        if line.startswith("%"):
            continue
        header_match = ABC_HEADER_RE.match(line)
        if header_match and not body_lines:
            headers[header_match.group(1).upper()] = header_match.group(2).strip()
            continue
        body_lines.append(line)

    tempo = abc_quarter_note_tempo(headers.get("Q", "120"))

    default_unit = 0.125
    if "L" in headers:
        try:
            if "/" in headers["L"]:
                num, den = headers["L"].split("/", 1)
                default_unit = int(num.strip() or 1) / max(int(den.strip()), 1)
            else:
                default_unit = 1.0 / max(int(headers["L"]), 1)
        except ValueError:
            pass
    elif "M" in headers:
        default_unit = abc_default_unit_from_meter(headers["M"])

    body = " ".join(body_lines)
    events = parse_abc_note_body(
        body,
        tempo=tempo,
        default_unit=default_unit,
        key=headers.get("K", "C"),
        default_volume=default_config.volume,
    )
    for event in events:
        if event.waveform is None:
            event.waveform = default_config.waveform
    return events


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

WAVEFORM_PRESETS: dict[int, dict[str, float | str]] = {
    1: {"waveform": "square", "duty": 0.5},
    2: {"waveform": "square", "duty": 0.25},
    3: {"waveform": "square", "duty": 0.125},
    4: {"waveform": "triangle"},
    5: {"waveform": "sawtooth"},
    6: {"waveform": "sine"},
    7: {"waveform": "noise"},
}

FM_TONE_PRESETS: dict[str, dict[str, object]] = {
    "bell": {
        "waveform": "sine",
        "fm": FMConfig(enabled=True, mod_ratio=2.0, mod_index=5.0),
        "adsr": ADSR(0.001, 0.8, 0.08, 0.8),
    },
    "e-piano": {
        "waveform": "sine",
        "fm": FMConfig(enabled=True, mod_ratio=1.0, mod_index=2.2),
        "adsr": ADSR(0.005, 0.45, 0.3, 0.5),
    },
    "bass": {
        "waveform": "sine",
        "fm": FMConfig(enabled=True, mod_ratio=0.5, mod_index=1.8),
        "adsr": ADSR(0.005, 0.18, 0.45, 0.12),
    },
}

SFX_PRESETS: dict[str, dict[str, str | SynthConfig]] = {
    "jump": {
        "description": "上昇音で表現するジャンプ",
        "format": "mml",
        "mml": "T240 L16 V15 O4 C E G >C",
        "config": SynthConfig(waveform="square", duty=0.25, adsr=ADSR(0.002, 0.04, 0.35, 0.04)),
    },
    "coin": {
        "description": "明るく短いコイン取得音",
        "format": "mml",
        "mml": "T300 L16 V14 O6 <B >E B",
        "config": SynthConfig(
            waveform="sine",
            adsr=ADSR(0.001, 0.08, 0.1, 0.12),
            fm=FMConfig(enabled=True, mod_ratio=2.0, mod_index=3.5),
        ),
    },
    "hit": {
        "description": "短い打撃音",
        "format": "mml",
        "mml": "T240 L16 V15 O4 C",
        "config": SynthConfig(
            waveform="noise",
            volume=0.65,
            noise_color="pink",
            filter_type="highpass",
            cutoff=900.0,
            adsr=ADSR(0.001, 0.06, 0.0, 0.025),
        ),
    },
    "explosion": {
        "description": "低域の強い爆発音",
        "format": "mml",
        "mml": "T100 L2 V15 O3 C",
        "config": SynthConfig(
            waveform="noise",
            noise_color="brown",
            filter_type="lowpass",
            cutoff=1800.0,
            adsr=ADSR(0.001, 0.4, 0.08, 0.45),
        ),
    },
    "laser": {
        "description": "FM変調された下降レーザー",
        "format": "mml",
        "mml": "T300 L32 V13 O7 C <B G E C <G",
        "config": SynthConfig(
            waveform="sawtooth",
            filter_type="lowpass",
            cutoff=7000.0,
            adsr=ADSR(0.001, 0.04, 0.45, 0.03),
            fm=FMConfig(enabled=True, mod_ratio=2.5, mod_index=3.0),
            lfo=LFOConfig(enabled=True, rate=12.0, depth=0.012, target="pitch"),
        ),
    },
    "powerup": {
        "description": "段階的に上昇するパワーアップ",
        "format": "mml",
        "mml": "T280 L16 V14 O4 C E G >C E G >C",
        "config": SynthConfig(waveform="square", duty=0.25, adsr=ADSR(0.002, 0.03, 0.65, 0.05)),
    },
    "select": {
        "description": "控えめなUI選択音",
        "format": "mml",
        "mml": "T300 L32 V11 O6 C",
        "config": SynthConfig(waveform="sine", adsr=ADSR(0.001, 0.025, 0.25, 0.035)),
    },
    "confirm": {
        "description": "肯定感のあるUI決定音",
        "format": "mml",
        "mml": "T240 L16 V13 O5 C E G >C",
        "config": SynthConfig(
            waveform="sine",
            adsr=ADSR(0.002, 0.08, 0.25, 0.1),
            fm=FMConfig(enabled=True, mod_ratio=2.0, mod_index=1.2),
        ),
    },
    "damage": {
        "description": "低く濁ったダメージ音",
        "format": "mml",
        "mml": "T220 L16 V15 O4 A F D <A",
        "config": SynthConfig(
            waveform="sawtooth",
            filter_type="lowpass",
            cutoff=2500.0,
            adsr=ADSR(0.001, 0.09, 0.15, 0.08),
        ),
    },
    "victory": {
        "description": "短い勝利ファンファーレ",
        "format": "mml",
        "mml": "T200 L8 V14 O4 C E G >C R16 <G >C E G >C.",
        "config": SynthConfig(waveform="square", duty=0.25, adsr=ADSR(0.004, 0.06, 0.55, 0.1)),
    },
}


def load_preset(name: str) -> tuple[list[NoteEvent], SynthConfig]:
    preset = SFX_PRESETS.get(name.lower())
    if preset is None:
        available = ", ".join(sorted(SFX_PRESETS))
        raise ValueError(f"未知のプリセット: {name}（利用可能: {available}）")

    config = preset.get("config")
    if not isinstance(config, SynthConfig):
        config = SynthConfig()

    if preset.get("format") == "abc":
        events = parse_abc(str(preset.get("abc", "")), config)
    else:
        events = parse_mml(str(preset.get("mml", "")), config)
    return events, config


def build_config_from_args(args: argparse.Namespace) -> SynthConfig:
    adsr = ADSR(
        attack=args.attack,
        decay=args.decay,
        sustain=args.sustain,
        release=args.release,
    )
    lfo = LFOConfig(
        enabled=args.lfo,
        rate=args.lfo_rate,
        depth=args.lfo_depth,
        target=args.lfo_target,
        waveform=args.lfo_wave,
    )
    fm = FMConfig(
        enabled=args.fm,
        mod_ratio=args.fm_ratio,
        mod_index=args.fm_index,
        mod_waveform=args.fm_wave,
    )
    sample_root = Path(args.sample_root) if args.sample_root else None
    config = SynthConfig(
        waveform=args.style,
        duty=args.duty,
        volume=args.volume,
        anti_alias=args.anti_alias,
        noise_color=args.noise_color,
        filter_type=args.filter,
        cutoff=args.cutoff,
        adsr=adsr,
        lfo=lfo,
        fm=fm,
        sample_root=sample_root,
    )
    if args.fm_preset:
        preset = FM_TONE_PRESETS[args.fm_preset]
        config.waveform = str(preset["waveform"])
        config.fm = preset["fm"]  # type: ignore[assignment]
        config.adsr = preset["adsr"]  # type: ignore[assignment]
    return config


def read_input_text(args: argparse.Namespace) -> str:
    if args.input_file:
        return Path(args.input_file).read_text(encoding="utf-8")
    if args.input:
        return args.input
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def resolve_events(args: argparse.Namespace, config: SynthConfig) -> list[NoteEvent]:
    if args.preset:
        events, preset_config = load_preset(args.preset)
        config.waveform = preset_config.waveform
        config.duty = preset_config.duty
        config.volume = preset_config.volume
        config.noise_color = preset_config.noise_color
        config.filter_type = preset_config.filter_type
        config.cutoff = preset_config.cutoff
        config.adsr = preset_config.adsr
        config.fm = preset_config.fm
        config.lfo = preset_config.lfo
        return events

    text = read_input_text(args)
    if args.abc:
        text = args.abc
        fmt = "abc"
    elif args.format:
        fmt = args.format.lower()
    else:
        fmt = "mml"

    if not text.strip():
        raise ValueError("入力が空です。--input / --abc / --preset / 標準入力を指定してください。")

    if fmt == "abc":
        return parse_abc(text, config)
    if fmt == "mml":
        return parse_mml_by_dialect(
            text,
            config,
            dialect=getattr(args, "mml_dialect", "ppmck"),
            max_repeat=getattr(args, "max_repeat", PYXEL_DEFAULT_MAX_REPEAT),
        )
    raise ValueError(f"未対応のフォーマット: {fmt}")


def _mml_kwargs_from_args(args: argparse.Namespace) -> dict[str, object]:
    return {
        "dialect": getattr(args, "mml_dialect", "ppmck"),
        "max_repeat": getattr(args, "max_repeat", PYXEL_DEFAULT_MAX_REPEAT),
        "pyxel_multipart": getattr(args, "pyxel_multipart", False),
    }


def resolve_track_specs(
    args: argparse.Namespace,
    config: SynthConfig,
) -> list[tuple[list[NoteEvent], SynthConfig]]:
    if args.preset:
        events = resolve_events(args, config)
        return [(events, config)]

    text = read_input_text(args)
    if args.abc:
        text = args.abc
        fmt = "abc"
    elif args.format:
        fmt = args.format.lower()
    else:
        fmt = "mml"

    if not text.strip():
        raise ValueError("入力が空です。--input / --abc / --preset / 標準入力を指定してください。")

    specs: list[tuple[list[NoteEvent], SynthConfig]] = []

    if fmt == "mml":
        mml_kwargs = _mml_kwargs_from_args(args)
        parsed_tracks = parse_mml_source(text, config, **mml_kwargs)
        if len(parsed_tracks) > 1 or (parsed_tracks and parsed_tracks[0].channel):
            for parsed in parsed_tracks:
                track_config = apply_synth_overrides(config, parsed.synth_overrides)
                specs.append((parsed.events, track_config))
        elif mml_kwargs["dialect"] == "pyxel":
            specs.append((parsed_tracks[0].events, config))
    else:
        specs.append((parse_abc(text, config), config))

    if not specs:
        specs.append((resolve_events(args, config), config))

    main_fmt = "abc" if fmt == "abc" else "mml"
    extra_index = 0
    for extra_text in args.track:
        track_config = config
        style_index = extra_index
        if style_index < len(args.track_style):
            track_config = replace(config, waveform=args.track_style[style_index])
        specs.append((parse_track_text(extra_text, main_fmt, config, args), track_config))
        extra_index += 1

    for path_text in args.track_file:
        path = Path(path_text)
        extra_text = path.read_text(encoding="utf-8")
        extra_fmt = "abc" if path.suffix.lower() == ".abc" else main_fmt
        track_config = config
        style_index = extra_index
        if style_index < len(args.track_style):
            track_config = replace(config, waveform=args.track_style[style_index])
        specs.append((parse_track_text(extra_text, extra_fmt, config, args), track_config))
        extra_index += 1

    return specs


def parse_track_text(
    text: str,
    fmt: str,
    config: SynthConfig,
    args: argparse.Namespace | None = None,
) -> list[NoteEvent]:
    if fmt == "abc":
        return parse_abc(text, config)
    if args is not None:
        return parse_mml_by_dialect(
            text,
            config,
            dialect=getattr(args, "mml_dialect", "ppmck"),
            max_repeat=getattr(args, "max_repeat", PYXEL_DEFAULT_MAX_REPEAT),
        )
    return parse_mml(text, config)


def resolve_extra_tracks(args: argparse.Namespace, config: SynthConfig) -> list[list[NoteEvent]]:
    main_fmt = "abc" if (args.abc or (args.format and args.format.lower() == "abc")) else "mml"
    track_event_lists: list[list[NoteEvent]] = []

    for text in args.track:
        track_event_lists.append(parse_track_text(text, main_fmt, config))

    for path_text in args.track_file:
        path = Path(path_text)
        text = path.read_text(encoding="utf-8")
        fmt = "abc" if path.suffix.lower() == ".abc" else main_fmt
        track_event_lists.append(parse_track_text(text, fmt, config))

    return track_event_lists


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OnGen - NumPy/SciPy ベースの MML/ABC 音源合成ツール",
    )
    parser.add_argument("--input", "-i", help="MML 文字列")
    parser.add_argument("--input-file", "-f", help="MML/ABC テキストファイル")
    parser.add_argument("--abc", help="ABC 記譜テキスト")
    parser.add_argument("--format", choices=["mml", "abc"], default="mml", help="入力フォーマット")
    parser.add_argument(
        "--mml-dialect",
        choices=["ppmck", "pyxel"],
        default="ppmck",
        help="MML 方言（既定: ppmck。pyxel は Pyxel 2.4+ 記法）",
    )
    parser.add_argument(
        "--max-repeat",
        type=int,
        default=PYXEL_DEFAULT_MAX_REPEAT,
        help="Pyxel 方言で [ ] 回数省略時の展開回数（正の整数、既定: 2）",
    )
    parser.add_argument(
        "--pyxel-compat-report",
        action="store_true",
        help="Pyxel 方言で非推奨・未対応トークンの警告を stderr に出力",
    )
    parser.add_argument(
        "--pyxel-multipart",
        action="store_true",
        help="Pyxel 方言の入力を1行1パートとして同時演奏（空行・コメント行・共有URLは除外）",
    )
    parser.add_argument("--preset", "-p", choices=sorted(SFX_PRESETS), help="内蔵 SFX プリセット")
    parser.add_argument(
        "--output",
        "-o",
        default="output",
        help="出力ファイル名（拡張子省略可。ファイル名のみの場合は output/ に保存）",
    )
    parser.add_argument(
        "--output-format",
        choices=OUTPUT_FORMATS,
        default="wav",
        help="出力フォーマット: wav / mp3 / ogg / all（MP3+OGG 一括）",
    )
    parser.add_argument(
        "--bitrate",
        type=int,
        default=192,
        help="MP3 ビットレート kbps（SFX: 128-192 推奨）",
    )
    parser.add_argument(
        "--ogg-quality",
        type=int,
        default=5,
        choices=range(0, 11),
        metavar="0-10",
        help="OGG Vorbis 品質（0=低〜10=高、既定: 5）",
    )
    parser.add_argument(
        "--style",
        choices=["square", "sawtooth", "triangle", "sine", "noise"],
        default="square",
        help="基本波形",
    )
    parser.add_argument("--duty", type=float, default=0.5, help="矩形波デューティ比 (0-1)")
    parser.add_argument(
        "--no-anti-alias",
        action="store_false",
        dest="anti_alias",
        help="矩形波のアンチエイリアスを無効化し、荒い波形を生成",
    )
    parser.add_argument("--volume", type=float, default=0.8, help="全体音量 (0-1)")
    parser.add_argument(
        "--fade-in",
        type=float,
        default=0.005,
        help="出力全体の冒頭フェード秒数（既定: 0.005、0で無効）",
    )
    parser.add_argument(
        "--noise-color",
        choices=["white", "pink", "brown"],
        default="white",
        help="ノイズ波形の色",
    )
    parser.add_argument(
        "--filter",
        choices=["none", "lowpass", "highpass"],
        default="none",
        help="出力へ適用するフィルター",
    )
    parser.add_argument("--cutoff", type=float, default=8000.0, help="フィルターのカットオフ周波数 Hz")
    parser.add_argument("--attack", type=float, default=0.01, help="ADSR Attack 秒")
    parser.add_argument("--decay", type=float, default=0.05, help="ADSR Decay 秒")
    parser.add_argument("--sustain", type=float, default=0.6, help="ADSR Sustain (0-1)")
    parser.add_argument("--release", type=float, default=0.08, help="ADSR Release 秒")
    parser.add_argument("--fm", action="store_true", help="FM 合成を有効化")
    parser.add_argument(
        "--fm-preset",
        choices=sorted(FM_TONE_PRESETS),
        help="2オペレーターFM音色プリセット",
    )
    parser.add_argument("--fm-ratio", type=float, default=2.0, help="FM モジュレータ倍率")
    parser.add_argument("--fm-index", type=float, default=2.0, help="FM 変調指数")
    parser.add_argument(
        "--fm-wave",
        choices=["square", "sawtooth", "triangle", "sine"],
        default="sine",
        help="FM モジュレータ波形",
    )
    parser.add_argument("--lfo", action="store_true", help="LFO 変調を有効化")
    parser.add_argument("--lfo-rate", type=float, default=5.0, help="LFO 周波数 (Hz)")
    parser.add_argument("--lfo-depth", type=float, default=0.02, help="LFO 深度")
    parser.add_argument(
        "--lfo-target",
        choices=["pitch", "volume", "duty"],
        default="pitch",
        help="LFO 変調対象",
    )
    parser.add_argument(
        "--lfo-wave",
        choices=["square", "sawtooth", "triangle", "sine"],
        default="sine",
        help="LFO 波形",
    )
    parser.add_argument("--sample-root", help="WAV サンプル検索ディレクトリ")
    parser.add_argument(
        "--track",
        action="append",
        default=[],
        metavar="TEXT",
        help="追加トラックの MML/ABC テキスト（メインと同時に鳴らしてミックス、複数指定可）",
    )
    parser.add_argument(
        "--track-file",
        action="append",
        default=[],
        metavar="FILE",
        help="追加トラックの MML/ABC ファイル（拡張子 .abc は ABC として解釈、複数指定可）",
    )
    parser.add_argument(
        "--track-style",
        action="append",
        default=[],
        choices=["square", "sawtooth", "triangle", "sine", "noise"],
        metavar="WAVEFORM",
        help="追加トラックごとの波形（--track / --track-file を並べた順に対応。未指定分は--styleを使用、複数指定可）",
    )
    parser.add_argument(
        "--overlay-sample",
        action="append",
        default=[],
        metavar="SPEC",
        help="合成音に重ねる WAV。形式: path[:offset秒[:gain]]",
    )
    parser.add_argument("--list-presets", action="store_true", help="プリセット一覧を表示")
    parser.add_argument("--lint", action="store_true", help="生成前の楽譜イベント列を検査")
    parser.add_argument("--analyze", action="store_true", help="生成後の波形を検査")
    parser.add_argument("--report-json", help="Lint/解析レポートをJSONで保存")
    parser.add_argument("--fail-on-warn", action="store_true", help="WARN以上の検査結果があれば終了コードを1にする")
    parser.add_argument("--fail-on-error", action="store_true", help="ERROR以上の検査結果があれば終了コードを1にする")
    parser.add_argument(
        "--play",
        action="store_true",
        help="生成した音声をその場で再生（ffplay が必要。ffmpegに同梱）",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.list_presets:
        print("利用可能なプリセット:")
        for name in sorted(SFX_PRESETS):
            description = SFX_PRESETS[name].get("description", "")
            print(f"  - {name}: {description}")
        return 0

    try:
        if args.max_repeat < 1:
            raise ValueError("--max-repeat は正の整数を指定してください")
        if args.pyxel_multipart and args.mml_dialect != "pyxel":
            raise ValueError("--pyxel-multipart は --mml-dialect pyxel と併用してください")

        config = build_config_from_args(args)
        input_text = read_input_text(args)
        if args.pyxel_compat_report and input_text.strip():
            for issue in report_pyxel_compat_issues(input_text):
                print(f"Pyxel互換警告: {issue}", file=sys.stderr)

        track_specs = resolve_track_specs(args, config)
        track_audios = [
            synthesize_sequence(track_events, track_config)
            for track_events, track_config in track_specs
        ]
        audio = mix_tracks(track_audios) if len(track_audios) > 1 else track_audios[0]
        total_events = sum(len(track_events) for track_events, _ in track_specs)
        extra_tracks = max(0, len(track_specs) - 1)

        for spec in args.overlay_sample:
            overlay, offset, gain = parse_overlay_spec(spec, config.sample_root)
            audio = mix_at_offset(audio, overlay, offset, gain)
        audio = apply_master_fade(audio, args.fade_in)
        reports: list[AudioReport] = []
        if args.lint:
            all_events = [
                event
                for track_events, _ in track_specs
                for event in track_events
            ]
            reports.append(lint_note_events(all_events))
        if args.analyze:
            reports.append(analyze_audio_array(audio, SAMPLE_RATE))
        report = merge_reports(reports) if reports else None
        output_stem = resolve_output_stem(args.output)
        written = write_audio_files(
            audio,
            output_stem,
            args.output_format,
            args.bitrate,
            args.ogg_quality,
        )
        duration_sec = audio.size / SAMPLE_RATE
        extras = []
        if config.fm.enabled:
            extras.append("FM")
        if config.lfo.enabled:
            extras.append("LFO")
        if args.overlay_sample:
            extras.append(f"overlay×{len(args.overlay_sample)}")
        if extra_tracks:
            extras.append(f"track×{len(track_specs)}")
        if args.output_format != "wav":
            extras.append(args.output_format)
        if args.play:
            extras.append("再生")
        suffix = f" [{', '.join(extras)}]" if extras else ""
        files_text = ", ".join(str(path) for path in written)
        print(f"出力完了: {files_text} ({duration_sec:.2f}s, {total_events} イベント){suffix}")
        if report is not None:
            print(format_report_text(report))
        if args.report_json:
            if report is None:
                report = analyze_audio_array(audio, SAMPLE_RATE)
            write_report_json(Path(args.report_json), report)

        if args.play:
            ensure_ffplay()
            wav_path = next((path for path in written if path.suffix.lower() == ".wav"), None)
            if wav_path is not None:
                play_audio(wav_path)
            else:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    temp_wav_path = Path(tmp.name)
                try:
                    write_wav(temp_wav_path, audio)
                    play_audio(temp_wav_path)
                finally:
                    temp_wav_path.unlink(missing_ok=True)

        if report is not None:
            if args.fail_on_warn and report.status in {"WARN", "ERROR"}:
                return 1
            if args.fail_on_error and report.status == "ERROR":
                return 1
        return 0
    except Exception as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
