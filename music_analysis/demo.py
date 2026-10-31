"""只生成合成信号；不随程序携带或下载任何版权音乐。"""

from pathlib import Path

import numpy as np
import soundfile as sf


def make_demo(directory, seconds=12, fs=44100):
    """低频温暖/高频明亮两段合成信号，包络随时间变化，方便验证对比功能。"""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    t = np.arange(round(seconds * fs)) / fs
    envelope = 0.65 + 0.35 * np.sin(2 * np.pi * 0.17 * t) ** 2
    warm = envelope * (0.50 * np.sin(2 * np.pi * 220 * t) + 0.18 * np.sin(2 * np.pi * 880 * t))
    bright = envelope * (0.20 * np.sin(2 * np.pi * 220 * t) + 0.42 * np.sin(2 * np.pi * 3600 * t))
    paths = []
    for name, samples in [("Demo A - Warm.wav", warm), ("Demo B - Bright.flac", bright)]:
        path = directory / name
        sf.write(path, np.column_stack([samples, -samples]), fs, subtype="PCM_24")
        paths.append(path)
    return paths
