"""纯函数/过程式数值核心：全曲、逐声道功率平均，不创建任何窗口。

PSD 单位为 FS²/Hz：满幅峰值为 1；满幅正弦积分均方值为 0.5。
因此不能把这个 PSD 的单个频点误称为幅度 dBFS，也不把补零间隔当分辨率。
"""

from pathlib import Path
import math
import re
import threading

import numpy as np
import soundfile as sf
from scipy.fft import rfft, rfftfreq


def frame_starts(total, window, hop):
    """帧起点（0 基）；补上最后完整窗口，保证尾部不被丢弃。"""
    last = max(0, total - window)
    starts = list(range(0, last + 1, hop))
    if starts[-1] != last:
        starts.append(last)
    return starts


def check_cancel(cancel):
    """仅在计算边界取消，避免把不完整结果误报为成功。"""
    if cancel is not None and cancel.is_set():
        raise InterruptedError("分析已取消")


def frame_psd(samples, window, fs, nfft=None):
    """单边 PSD；每声道独立去均值和 FFT，平方后才跨声道平均。"""
    centered = samples - samples.mean(axis=0, keepdims=True)
    transform = rfft(centered * window[:, None], n=nfft, axis=0)
    power = np.mean(np.abs(transform) ** 2, axis=1)
    power /= fs * np.sum(window**2)
    fft_size = len(window) if nfft is None else nfft
    power[1 : -1 if fft_size % 2 == 0 else None] *= 2
    return power


def analyze_file(path, window_seconds=1.0, full_fft=False, cancel=None, progress=None):
    """读取整首 WAV/MP3/FLAC/OGG/AIFF，返回已校验的数值结果。

    Welch/STFT 采用有限长度读取，峰值/RMS/DC 逐块累计，空间不随时长线性
    增长（输出语谱图最多 720 列）。可选整曲 FFT 需要整曲内存，提前检查预算。
    progress 为可选的 (0..1) 回调，核心不依赖 GUI 或 matplotlib。
    """
    path = Path(path)
    if not math.isfinite(window_seconds) or not 0.05 <= window_seconds <= 8:
        raise ValueError("分析窗口必须在 0.05～8 秒之间")
    check_cancel(cancel)
    # 统一转换解码器错误，不把绝对路径或底层堆栈带入可导出结果。
    try:
        audio = sf.SoundFile(str(path))
    except (sf.LibsndfileError, OSError) as exc:
        raise ValueError("无法解码音频；请使用 WAV、MP3、FLAC、OGG 或 AIFF") from exc
    with audio:
        fs, total, channels = audio.samplerate, len(audio), audio.channels
        subtype = audio.subtype
        if total < 4 or fs < 80 or channels < 1:
            raise ValueError("音频过短或采样率无效")
        # 窗长按秒配置，PSD 按 Hz 归一化，不同采样率下仍可比较。
        window_len = min(total, 2 ** round(math.log2(window_seconds * fs)))
        window_len = max(4, window_len)
        window = np.hanning(window_len + 1)[:-1]
        hop = max(1, window_len // 4)
        starts = frame_starts(total, window_len, hop)
        power_sum = np.zeros(window_len // 2 + 1)
        for index, start in enumerate(starts):
            check_cancel(cancel)
            audio.seek(start)
            samples = audio.read(window_len, dtype="float64", always_2d=True)
            if len(samples) != window_len or not np.isfinite(samples).all():
                raise ValueError("解码样本数不一致或包含 NaN/Inf")
            power_sum += frame_psd(samples, window, fs)
            if progress and index % 32 == 0:
                progress(0.45 * (index + 1) / len(starts))
        psd = power_sum / len(starts)
        frequency = rfftfreq(window_len, 1 / fs)

        # 用全部原始声道样本做统计，不先混合，避免反相抵消。
        audio.seek(0)
        square_sum = np.zeros(channels)
        dc_sum = np.zeros(channels)
        peak, clipped, actual = 0.0, 0, 0
        for samples in audio.blocks(blocksize=65536, dtype="float64", always_2d=True):
            check_cancel(cancel)
            if not np.isfinite(samples).all():
                raise ValueError("音频包含 NaN/Inf")
            actual += len(samples)
            square_sum += np.sum(samples**2, axis=0)
            dc_sum += samples.sum(axis=0)
            peak = max(peak, float(np.max(np.abs(samples))))
            clipped += int(np.count_nonzero(np.abs(samples) >= 0.999))
        if actual != total:
            raise ValueError("实际解码长度与文件长度不一致")
        mean_square = float(np.mean(square_sum / total))
        rms_db = 10 * math.log10(max(mean_square, 1e-30))

        # STFT 所有帧都计算，再把时间邻域的线性功率平均到最多720列。
        # 所有音乐固定相同色标；不会逐曲自动拉高静音或微弱信号。
        spec_len = min(total, 2048)
        spec_window = np.hanning(spec_len + 1)[:-1]
        spec_starts = frame_starts(total, spec_len, max(1, spec_len // 2))
        columns = min(720, len(spec_starts))
        spec_power = np.zeros((spec_len // 2 + 1, columns), dtype=np.float64)
        counts = np.zeros(columns)
        for index, start in enumerate(spec_starts):
            check_cancel(cancel)
            audio.seek(start)
            samples = audio.read(spec_len, dtype="float64", always_2d=True)
            column = min(columns - 1, int((start + spec_len / 2) / total * columns))
            spec_power[:, column] += frame_psd(samples, spec_window, fs)
            counts[column] += 1
            if progress and index % 64 == 0:
                progress(0.45 + 0.4 * (index + 1) / len(spec_starts))
        populated = counts > 0
        spec_power[:, populated] /= counts[populated]

        # 可选全长 FFT：PSD 同单位归一化，但窗长/平滑尺度不同，不能逐峰判定成功。
        fft_frequency, fft_psd = np.array([]), np.array([])
        if full_fft:
            nfft = 1 << (total - 1).bit_length()
            # 包含读入样本、窗、复数FFT和中间数组，保守上限1.5 GiB。
            estimated = total * (channels * 8 + 32) + nfft * 48
            if estimated > 1.5 * 1024**3:
                raise ValueError("整曲 FFT 预计超过 1.5 GiB；请取消勾选整曲 FFT 后分析")
            check_cancel(cancel)
            audio.seek(0)
            whole = audio.read(dtype="float64", always_2d=True)
            whole_window = np.hanning(total + 1)[:-1]
            # 按声道顺序处理，避免同时分配所有声道的复数FFT。
            whole_psd = np.zeros(nfft // 2 + 1)
            for channel in range(channels):
                check_cancel(cancel)
                whole_psd += frame_psd(whole[:, channel : channel + 1], whole_window, fs, nfft)
            whole_psd /= channels
            # 仅显示/缓存降采样，主 Welch 数值及积分不做显示降采样。
            whole_freq = rfftfreq(nfft, 1 / fs)
            fft_frequency, fft_psd = log_average(whole_freq, whole_psd, points=1800)
        if progress:
            progress(1.0)

    integral = float(np.sum(psd) * (fs / window_len))
    centroid = float(np.sum(frequency * psd) / np.sum(psd)) if integral > 1e-25 else 0.0
    # 仅保留文件名；结果、截图、导出报告都不包含来源绝对路径。
    result = {
        "name": path.name, "sample_rate": fs, "channels": channels,
        "subtype": subtype, "samples": total, "duration": total / fs,
        "frequency": frequency, "psd": psd, "window_samples": window_len,
        "segments": len(starts), "bin_hz": fs / window_len,
        "enbw_hz": float(fs * np.sum(window**2) / np.sum(window)**2),
        "rms_dbfs": rms_db, "peak_dbfs": 20 * math.log10(max(peak, 1e-15)),
        "clipped_percent": clipped / (total * channels) * 100,
        "dc": float(np.mean(dc_sum / total)), "centroid": centroid,
        "integrated_power": integral, "fft_frequency": fft_frequency, "fft_psd": fft_psd,
        "spec_frequency": rfftfreq(spec_len, 1 / fs),
        "spec_edges": np.linspace(0, total / fs, columns + 1),
        "spec_psd": spec_power.astype(np.float32),
    }
    if not np.isfinite(psd).all() or np.any(psd < 0) or not np.isfinite(spec_power).all():
        raise ValueError("数值校验失败：频谱非有限或负功率")
    return result


def log_average(frequency, power, points=400, low=20.0, high=20000.0):
    """显示用对数频带线性功率平均；不取最大值，不改变原始分析数组。"""
    high = min(high, float(frequency[-1]))
    if high <= low:
        return np.array([]), np.array([])
    edges = np.geomspace(low, high, points + 1)
    bands = np.clip(np.searchsorted(edges, frequency, side="right") - 1, 0, points - 1)
    valid = (frequency >= low) & (frequency <= high)
    sums = np.bincount(bands[valid], weights=power[valid], minlength=points)
    counts = np.bincount(bands[valid], minlength=points)
    keep = counts > 0
    return np.sqrt(edges[:-1] * edges[1:])[keep], sums[keep] / counts[keep]


def display_spectrum(result, normalize=False, smooth=True, low=20.0, high=20000.0, full=False):
    """按共同频段积分归一化，比较音色而不被响度差主导；Nyquist以上不外推。"""
    frequency = result["fft_frequency" if full else "frequency"]
    power = result["fft_psd" if full else "psd"].copy()
    if normalize:
        main_f, main_p = result["frequency"], result["psd"]
        mask = (main_f >= low) & (main_f <= high)
        reference = float(main_p[mask].sum() * result["bin_hz"])
        power /= max(reference, 1e-30)
    if smooth:
        frequency, power = log_average(frequency, power, low=low, high=high)
    mask = (frequency >= low) & (frequency <= high)
    return frequency[mask], 10 * np.log10(np.maximum(power[mask], 1e-20))


def difference_spectrum(first, second, normalize=False):
    """在两首歌曲共有频段上插值，返回第二首减第一首，不跨 Nyquist 外推。"""
    high = min(20000.0, first["sample_rate"] / 2, second["sample_rate"] / 2)
    f1, p1 = display_spectrum(first, normalize, low=20, high=high)
    f2, p2 = display_spectrum(second, normalize, low=20, high=high)
    low, top = max(f1[0], f2[0]), min(f1[-1], f2[-1])
    grid = np.geomspace(low, top, 400)
    return grid, np.interp(grid, f2, p2) - np.interp(grid, f1, p1)


def safe_stem(name):
    """合法、短的 Windows 目录名；导出不沿用绝对源路径。"""
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(name).stem).strip(" .")[:80]
    if not stem or stem.upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(10)], *[f"LPT{i}" for i in range(10)]}:
        stem = "audio_" + stem
    return stem


def new_cancel_event():
    """方便界面和批量脚本使用同一取消协议。"""
    return threading.Event()
