"""导出本地分析结果；不写入源绝对路径、音频内容或机器信息。"""

from pathlib import Path
import csv
import json

import numpy as np

from .analysis import safe_stem


def export_results(results, directory, spectrum_figure=None, spectrogram_figure=None, mode="absolute"):
    """按歌曲分目录保存原始Welch PSD/可选FFT显示数据；支持重名歌曲。"""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, result in enumerate(results, 1):
        song_dir = directory / f"{index:02d}_{safe_stem(result['name'])}"
        song_dir.mkdir(exist_ok=True)
        np.savetxt(song_dir / "welch_psd.csv", np.column_stack([
            result["frequency"], result["psd"], 10 * np.log10(np.maximum(result["psd"], 1e-20))]),
            delimiter=",", header="Frequency_Hz,PSD_FS2_per_Hz,PSD_dB_re_1_FS2_per_Hz", comments="")
        if result["fft_psd"].size:
            np.savetxt(song_dir / "full_fft_display.csv", np.column_stack([
                result["fft_frequency"], result["fft_psd"]]), delimiter=",",
                header="Frequency_Hz,LogBand_Mean_PSD_FS2_per_Hz", comments="")
        metadata = {key: value for key, value in result.items() if not isinstance(value, np.ndarray)}
        metadata["units"] = "PSD: FS^2/Hz; RMS dBFS: 20log10(rms/1); display mode: " + mode
        metadata["notes"] = "Welch and full FFT have different ENBW; peak agreement alone is not validation."
        (song_dir / "report.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        rows.append([result["name"], result["sample_rate"], result["channels"], result["subtype"],
                     result["duration"], result["rms_dbfs"], result["centroid"], result["segments"]])
    with (directory / "comparison.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(["File", "SampleRate_Hz", "Channels", "Subtype", "Duration_s", "RMS_dBFS", "Centroid_Hz", "Segments"])
        writer.writerows(rows)
    for figure, name in [(spectrum_figure, "comparison"), (spectrogram_figure, "spectrogram")]:
        if figure is not None:
            figure.savefig(directory / f"{name}.png", dpi=160, facecolor="white")
    return directory
