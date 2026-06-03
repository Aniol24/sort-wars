"""
T4 — Audio Engine

Top algorithm (A) → high-pitched tones  (500–1500 Hz)
Bottom algorithm (B) → low-pitched tones (60–300 Hz)

Pitch is proportional to the value of the element being processed.
Phase is tracked across frames so tones are continuous with no clicks.
"""

import subprocess
from pathlib import Path

import numpy as np
from scipy.io import wavfile

SAMPLE_RATE = 44100
FPS         = 60
SPF         = SAMPLE_RATE // FPS       # samples per frame ≈ 735

PITCH_A_MIN = 500.0                    # Hz — top algo (high)
PITCH_A_MAX = 1500.0
PITCH_B_MIN = 60.0                     # Hz — bottom algo (low)
PITCH_B_MAX = 300.0

AMPLITUDE   = 0.40                     # per-tone amplitude before mixing


def _freq(value: int, max_val: int, lo: float, hi: float) -> float:
    return lo + (hi - lo) * (value / max_val)


def generate_audio(
    states_a: list,
    states_b: list,
    n_celebration_frames: int = FPS * 3,
    output_wav: str = "output/audio.wav",
) -> str:
    total    = max(len(states_a), len(states_b))
    n_frames = total + n_celebration_frames
    audio    = np.zeros(n_frames * SPF, dtype=np.float64)
    t_frame  = np.arange(SPF) / SAMPLE_RATE

    phases_a: dict = {}
    phases_b: dict = {}

    for f in range(total):
        sa = states_a[min(f, len(states_a) - 1)]
        sb = states_b[min(f, len(states_b) - 1)]

        arr_a, _, _, active_a = sa
        arr_b, _, _, active_b = sb
        max_val = max(max(arr_a), max(arr_b), 1)

        frame = np.zeros(SPF)
        n_act = max(1, len(active_a) + len(active_b))
        amp   = AMPLITUDE / (n_act ** 0.5)

        new_pa: dict = {}
        for i in set(active_a):
            freq = _freq(arr_a[i], max_val, PITCH_A_MIN, PITCH_A_MAX)
            ph   = phases_a.get(i, 0.0)
            frame += amp * np.sin(2 * np.pi * freq * t_frame + ph)
            new_pa[i] = (ph + 2 * np.pi * freq * SPF / SAMPLE_RATE) % (2 * np.pi)
        phases_a = new_pa

        new_pb: dict = {}
        for i in set(active_b):
            freq = _freq(arr_b[i], max_val, PITCH_B_MIN, PITCH_B_MAX)
            ph   = phases_b.get(i, 0.0)
            frame += amp * np.sin(2 * np.pi * freq * t_frame + ph)
            new_pb[i] = (ph + 2 * np.pi * freq * SPF / SAMPLE_RATE) % (2 * np.pi)
        phases_b = new_pb

        np.clip(frame, -1.0, 1.0, out=frame)
        audio[f * SPF : (f + 1) * SPF] = frame

    # Fade out over last 0.5s
    fade = min(SAMPLE_RATE // 2, len(audio))
    audio[-fade:] *= np.linspace(1.0, 0.0, fade)

    Path(output_wav).parent.mkdir(parents=True, exist_ok=True)
    stereo = np.stack([audio, audio], axis=-1)
    wavfile.write(output_wav, SAMPLE_RATE, (stereo * 32767).astype(np.int16))
    print(f"Audio: {output_wav}")
    return output_wav


def merge_video_audio(video_path: str, audio_path: str, output_path: str) -> str:
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Merged: {output_path}")
    return output_path
