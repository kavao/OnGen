#!/usr/bin/env python3
"""OnGen: NumPy/SciPy ベースのMML・ABC音源合成ツール。"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from shutil import which
from typing import Iterable, Sequence

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

SAMPLE_RATE = 44100
BIT_DEPTH = 16
OUTPUT_DIR = Path("output")
AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg"}
OUTPUT_FORMATS = ("wav", "mp3", "ogg", "all")
MIX_HEADROOM = 10.0 ** (-1.0 / 20.0)

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
    lfo_target: str | None = None


def midi_to_freq(midi: int) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def note_to_midi(name: str, octave: int) -> int:
    normalized = NOTE_ALIASES.get(name.upper(), name.upper())
    if normalized not in NOTE_NAMES:
        raise ValueError(f"未知の音名: {name}")
    return NOTE_NAMES.index(normalized) + (octave + 1) * 12


def note_name_to_freq(name: str, octave: int) -> float:
    return midi_to_freq(note_to_midi(name, octave))


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
    lfo_target = event.lfo_target or config.lfo.target
    lfo_enabled = config.lfo.enabled or event.lfo_depth is not None

    if waveform == "noise":
        return generate_white_noise(num_samples)

    t = np.arange(num_samples, dtype=np.float64) / SAMPLE_RATE
    carrier_freq = np.full(num_samples, frequency, dtype=np.float64)

    if lfo_enabled and lfo_depth > 0 and lfo_target == "pitch":
        lfo = generate_lfo_signal(num_samples, config.lfo.rate, config.lfo.waveform)
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
            lfo = generate_lfo_signal(num_samples, config.lfo.rate, config.lfo.waveform)
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
        lfo = generate_lfo_signal(num_samples, config.lfo.rate, config.lfo.waveform)
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
    return audio * env * config.volume * event.volume


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
    env = config.adsr.envelope(num_samples)
    return wave * env * volume


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
    (?P<loop_count>\|\s*\d+) |
    (?P<fm_pct>%\d+) |
    (?P<fm_mul>\*\d+) |
    (?P<lfo_cmd>~\d+) |
    (?P<sample>W\([^)]+\)) |
    (?P<cmd>[OTLVR@][+-]?\d*) |
    (?P<rest>R(?:\d+)?) |
    (?P<note>[A-G][+#-]?(?:-?\d+)?(?:\.*)?)
    """,
    re.VERBOSE | re.IGNORECASE,
)


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
    sample_path: str | None = None


def mml_length_to_seconds(length: int, dotted: int, tempo: int) -> float:
    beat = 60.0 / tempo
    unit = beat * 4.0 / max(length, 1)
    multiplier = 1.0
    for _ in range(dotted):
        multiplier += 0.5 * (0.5 ** _)
    return unit * multiplier


def mml_volume_to_gain(volume: int) -> float:
    return min(max(volume, 0), 15) / 15.0


def mml_scale_to_fm_index(value: int) -> float:
    return (min(max(value, 0), 15) / 15.0) * 8.0


def mml_scale_to_lfo_depth(value: int) -> float:
    return (min(max(value, 0), 15) / 15.0) * 0.08


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
    )


def parse_mml(text: str, default_config: SynthConfig | None = None) -> list[NoteEvent]:
    default_config = default_config or SynthConfig()
    state = MMLState()
    events: list[NoteEvent] = []
    loop_stack: list[tuple[int, MMLState]] = []

    sample_paths: dict[str, str] = {}

    def _stash_sample(match: re.Match[str]) -> str:
        key = f"__S{len(sample_paths)}__"
        sample_paths[key] = match.group(1)
        return f"W({key})"

    normalized = re.sub(r"W\(([^)]+)\)", _stash_sample, text, flags=re.IGNORECASE)
    compact = re.sub(r"\s+", "", normalized.upper())
    for key, path in sample_paths.items():
        compact = compact.replace(f"W({key.upper()})", f"W({path})")

    pos = 0
    while pos < len(compact):
        match = MML_TOKEN_RE.match(compact, pos)
        if not match:
            pos += 1
            continue

        pos = match.end()
        if match.group("loop_start"):
            loop_stack.append((len(events), MMLState(**vars(state))))
            continue

        if match.group("loop_end"):
            count_match = re.match(r"\|(\d+)", compact[pos:])
            repeat = int(count_match.group(1)) if count_match else 2
            if count_match:
                pos += count_match.end()
            if not loop_stack:
                continue
            start_idx, saved_state = loop_stack.pop()
            segment = events[start_idx:]
            events = events[:start_idx]
            for _ in range(repeat):
                events.extend(segment)
            state = saved_state
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
            elif kind == "R":
                pass
            elif kind == "@":
                preset = WAVEFORM_PRESETS.get(number)
                if preset:
                    state.waveform = preset.get("waveform", state.waveform)
                    state.duty = preset.get("duty", state.duty)
            continue

        if match.group("fm_pct"):
            state.fm_index = mml_scale_to_fm_index(int(match.group("fm_pct")[1:]))
            continue

        if match.group("fm_mul"):
            state.fm_ratio = max(int(match.group("fm_mul")[1:]), 1) / 2.0
            continue

        if match.group("lfo_cmd"):
            state.lfo_depth = mml_scale_to_lfo_depth(int(match.group("lfo_cmd")[1:]))
            continue

        if match.group("sample"):
            sample_token = match.group("sample")
            state.sample_path = sample_token[2:-1]
            duration = mml_length_to_seconds(state.length, 0, state.tempo)
            events.append(
                make_note_event(
                    state=state,
                    default_config=default_config,
                    duration=duration,
                    frequency=None,
                )
            )
            state.sample_path = None
            continue

        if match.group("rest"):
            token = match.group("rest")
            length = state.length
            length_match = re.fullmatch(r"R(\d+)", token, re.IGNORECASE)
            if length_match:
                length = int(length_match.group(1))
            duration = mml_length_to_seconds(length, 0, state.tempo)
            events.append(
                make_note_event(
                    state=state,
                    default_config=default_config,
                    duration=duration,
                    frequency=None,
                )
            )
            continue

        if match.group("note"):
            token = match.group("note")
            note_match = re.match(r"([A-G](?:\+|#|-)?)(-?\d*)((\.*)*)", token, re.IGNORECASE)
            if not note_match:
                continue
            name = note_match.group(1)
            octave_text = note_match.group(2)
            dots = note_match.group(3) or ""
            length = state.length
            octave = int(octave_text) if octave_text else state.octave
            freq = note_name_to_freq(name, octave)
            duration = mml_length_to_seconds(length, len(dots), state.tempo)
            events.append(
                make_note_event(
                    state=state,
                    default_config=default_config,
                    duration=duration,
                    frequency=freq,
                )
            )

    return events


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
        "mml": "T240 L16 V15 O4 C4 E4 G4 C5",
        "config": SynthConfig(waveform="square", duty=0.25, adsr=ADSR(0.002, 0.04, 0.35, 0.04)),
    },
    "coin": {
        "description": "明るく短いコイン取得音",
        "format": "mml",
        "mml": "T300 L16 V14 O6 B5 E6 B6",
        "config": SynthConfig(
            waveform="sine",
            adsr=ADSR(0.001, 0.08, 0.1, 0.12),
            fm=FMConfig(enabled=True, mod_ratio=2.0, mod_index=3.5),
        ),
    },
    "hit": {
        "description": "短い打撃音",
        "format": "mml",
        "mml": "T240 L16 V15 O4 C4",
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
        "mml": "T100 L2 V15 O3 C3",
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
        "mml": "T300 L32 V13 O7 C7 B6 G6 E6 C6 G5",
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
        "mml": "T280 L16 V14 O4 C4 E4 G4 C5 E5 G5 C6",
        "config": SynthConfig(waveform="square", duty=0.25, adsr=ADSR(0.002, 0.03, 0.65, 0.05)),
    },
    "select": {
        "description": "控えめなUI選択音",
        "format": "mml",
        "mml": "T300 L32 V11 O6 C6",
        "config": SynthConfig(waveform="sine", adsr=ADSR(0.001, 0.025, 0.25, 0.035)),
    },
    "confirm": {
        "description": "肯定感のあるUI決定音",
        "format": "mml",
        "mml": "T240 L16 V13 O5 C5 E5 G5 C6",
        "config": SynthConfig(
            waveform="sine",
            adsr=ADSR(0.002, 0.08, 0.25, 0.1),
            fm=FMConfig(enabled=True, mod_ratio=2.0, mod_index=1.2),
        ),
    },
    "damage": {
        "description": "低く濁ったダメージ音",
        "format": "mml",
        "mml": "T220 L16 V15 O4 A4 F4 D4 A3",
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
        "mml": "T200 L8 V14 O4 C4 E4 G4 C5 R16 G4 C5 E5 G5 C6.",
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
        return parse_mml(text, config)
    raise ValueError(f"未対応のフォーマット: {fmt}")


def parse_track_text(text: str, fmt: str, config: SynthConfig) -> list[NoteEvent]:
    if fmt == "abc":
        return parse_abc(text, config)
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
        "--overlay-sample",
        action="append",
        default=[],
        metavar="SPEC",
        help="合成音に重ねる WAV。形式: path[:offset秒[:gain]]",
    )
    parser.add_argument("--list-presets", action="store_true", help="プリセット一覧を表示")
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
        config = build_config_from_args(args)
        events = resolve_events(args, config)
        audio = synthesize_sequence(events, config)

        extra_tracks = resolve_extra_tracks(args, config)
        total_events = len(events)
        if extra_tracks:
            track_audios = [audio]
            for track_events in extra_tracks:
                total_events += len(track_events)
                track_audios.append(synthesize_sequence(track_events, config))
            audio = mix_tracks(track_audios)

        for spec in args.overlay_sample:
            overlay, offset, gain = parse_overlay_spec(spec, config.sample_root)
            audio = mix_at_offset(audio, overlay, offset, gain)
        audio = apply_master_fade(audio, args.fade_in)
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
            extras.append(f"track×{len(extra_tracks) + 1}")
        if args.output_format != "wav":
            extras.append(args.output_format)
        suffix = f" [{', '.join(extras)}]" if extras else ""
        files_text = ", ".join(str(path) for path in written)
        print(f"出力完了: {files_text} ({duration_sec:.2f}s, {total_events} イベント){suffix}")
        return 0
    except Exception as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
