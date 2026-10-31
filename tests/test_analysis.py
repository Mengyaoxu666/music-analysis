"""全合成数值回归；不依赖任何私人音乐文件或网络。"""

import json
import threading

import numpy as np
import pytest
import soundfile as sf
from scipy.signal import welch

from music_analysis.analysis import (
    analyze_file, frame_starts, frame_psd, display_spectrum, difference_spectrum, safe_stem,
)
from music_analysis.export import export_results


def tone(tmp_path, name="tone.wav", fs=16000, seconds=3, amplitude=0.5, channels=1):
    t = np.arange(round(fs * seconds)) / fs
    x = amplitude * np.sin(2 * np.pi * 1000 * t)
    samples = np.column_stack([x * (-1 if i % 2 else 1) for i in range(channels)])
    path = tmp_path / name
    sf.write(path, samples, fs, subtype="FLOAT" if path.suffix == ".wav" else None)
    return path, samples


@pytest.mark.parametrize("total,window,hop", [(5001, 1024, 256), (1024, 1024, 256), (70, 70, 17)])
def test_tail_coverage(total, window, hop):
    starts = frame_starts(total, window, hop)
    assert starts[0] == 0 and starts[-1] + window == total
    covered = np.zeros(total, bool)
    for start in starts:
        covered[start : start + window] = True
    assert covered.all()


def test_psd_matches_scipy():
    samples = np.random.default_rng(42).normal(size=(2048, 3))
    window = np.hanning(2049)[:-1]
    ours = frame_psd(samples, window, 48000)
    _, reference = welch(samples, fs=48000, window=window, nperseg=2048,
                         noverlap=0, detrend="constant", axis=0, scaling="density")
    np.testing.assert_allclose(ours, reference.mean(axis=1), rtol=1e-12, atol=1e-15)


@pytest.mark.parametrize("channels", [1, 2, 6])
def test_antiphase_channels(tmp_path, channels):
    path, _ = tone(tmp_path, channels=channels)
    result = analyze_file(path, full_fft=True)
    assert result["channels"] == channels
    assert result["integrated_power"] == pytest.approx(0.125, rel=0.003)
    assert result["rms_dbfs"] == pytest.approx(-9.0309, abs=0.01)
    assert result["centroid"] == pytest.approx(1000, abs=1)
    assert result["spec_psd"].max() > 0.001
    assert abs(result["fft_frequency"][np.argmax(result["fft_psd"])] - 1000) < 10


@pytest.mark.parametrize("fs", [8000, 44100, 48000, 96000])
def test_sample_rates_consistent_power(tmp_path, fs):
    path, _ = tone(tmp_path, fs=fs, seconds=2)
    result = analyze_file(path)
    assert result["sample_rate"] == fs
    assert result["integrated_power"] == pytest.approx(0.125, rel=0.01)
    assert result["centroid"] == pytest.approx(1000, abs=1)


def test_gain_and_normalization(tmp_path):
    rng = np.random.default_rng(12)
    samples = rng.normal(0, 0.1, (48000, 2))
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    sf.write(a, samples, 16000, subtype="FLOAT")
    sf.write(b, samples * 0.5, 16000, subtype="FLOAT")
    r1, r2 = analyze_file(a), analyze_file(b)
    _, delta = difference_spectrum(r1, r2)
    np.testing.assert_allclose(delta, -6.020599913, atol=1e-4)
    _, delta_normalized = difference_spectrum(r1, r2, normalize=True)
    np.testing.assert_allclose(delta_normalized, 0, atol=1e-4)
    f1, _ = display_spectrum(r1, high=8000)
    assert f1.max() <= 8000


def test_welch_matches_scipy_whole(tmp_path):
    samples = np.random.default_rng(1).normal(0, 0.1, (16384, 2))
    path = tmp_path / "random.wav"
    sf.write(path, samples, 8192, subtype="DOUBLE")
    result = analyze_file(path, window_seconds=0.5)
    _, reference = welch(samples, fs=8192, window="hann", nperseg=4096,
                         noverlap=3072, detrend="constant", axis=0, scaling="density")
    np.testing.assert_allclose(result["psd"], reference.mean(axis=1), rtol=1e-12, atol=1e-16)


@pytest.mark.parametrize("name,subtype", [("tone.wav", "PCM_16"), ("tone.flac", "PCM_24"), ("tone.ogg", "VORBIS"), ("tone.mp3", "MPEG_LAYER_III")])
def test_formats_and_unicode(tmp_path, name, subtype):
    folder = tmp_path / "合成音频"
    folder.mkdir()
    fs = 44100
    x = 0.5 * np.sin(2 * np.pi * 1000 * np.arange(fs * 2) / fs)
    path = folder / name
    sf.write(path, x, fs, subtype=subtype)
    result = analyze_file(path)
    assert result["sample_rate"] == fs
    assert result["centroid"] == pytest.approx(1000, abs=20)


def test_five_minutes_and_tail(tmp_path):
    fs = 16000
    path = tmp_path / "five_minutes.flac"
    # 分块生成301秒音频；最后一秒含独立高频，检查尾部也参与分析。
    t = np.arange(fs) / fs
    with sf.SoundFile(path, "w", samplerate=fs, channels=2, subtype="PCM_24") as audio:
        for second in range(301):
            signal = 0.3 * np.sin(2 * np.pi * (3000 if second == 300 else 200) * t)
            audio.write(np.column_stack([signal, -signal]))
    result = analyze_file(path)
    assert result["duration"] == 301
    assert result["samples"] == fs * 301
    assert result["spec_psd"].shape[1] <= 720
    assert result["integrated_power"] == pytest.approx(0.045, rel=0.03)
    high = (result["frequency"] > 2900) & (result["frequency"] < 3100)
    assert result["psd"][high].sum() * result["bin_hz"] > 0.00003
    high_spec = (result["spec_frequency"] > 2900) & (result["spec_frequency"] < 3100)
    assert result["spec_psd"][high_spec, -1].max() > 0.00001


def test_silence(tmp_path):
    path = tmp_path / "silent.wav"
    sf.write(path, np.zeros((8000, 2)), 8000)
    result = analyze_file(path, full_fft=True)
    assert result["integrated_power"] == 0
    assert result["centroid"] == 0
    assert np.isfinite(result["spec_psd"]).all()


def test_cancel_and_errors(tmp_path):
    path, _ = tone(tmp_path)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(InterruptedError):
        analyze_file(path, cancel=cancel)
    with pytest.raises(ValueError, match="窗口"):
        analyze_file(path, window_seconds=0)
    with pytest.raises(ValueError, match="解码"):
        analyze_file(tmp_path / "missing.wav")
    invalid = tmp_path / "broken.wav"
    invalid.write_bytes(b"not audio")
    with pytest.raises(ValueError, match="解码"):
        analyze_file(invalid)


def test_export_no_absolute_path_and_duplicate_names(tmp_path):
    path, _ = tone(tmp_path)
    result = analyze_file(path, full_fft=True)
    destination = export_results([result, result], tmp_path / "export")
    assert (destination / "01_tone" / "welch_psd.csv").exists()
    assert (destination / "02_tone" / "welch_psd.csv").exists()
    report = (destination / "01_tone" / "report.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in report
    assert json.loads(report)["samples"] == 48000
    assert (destination / "01_tone" / "full_fft_display.csv").exists()


@pytest.mark.parametrize("name", ["CON.wav", "NUL.wav", "../../test.wav", 'a:b?c.wav', "   .wav"])
def test_safe_names(name):
    stem = safe_stem(name)
    assert stem and not any(char in stem for char in '<>:"/\\|?*')


def test_nonfinite_data(tmp_path):
    path = tmp_path / "nan.wav"
    samples = np.zeros(16000)
    samples[100] = np.nan
    sf.write(path, samples, 8000, subtype="FLOAT")
    with pytest.raises(ValueError, match="NaN"):
        analyze_file(path)


@pytest.mark.parametrize("length", [4, 17, 100, 255])
def test_short_files_do_not_overrun(tmp_path, length):
    path = tmp_path / "short.wav"
    sf.write(path, np.linspace(-0.2, 0.2, length), 8000, subtype="FLOAT")
    result = analyze_file(path, full_fft=True)
    assert result["samples"] == length
    assert result["window_samples"] <= length
    assert np.isfinite(result["psd"]).all()
