"""独立 Qt 桌面界面；无自定义类，函数回调和共享局部状态。

数值计算在线程中运行，只用队列与界面通信；所有Qt/绘图操作在主线程。
取消和关闭采用协作终止，工作线程不访问已销毁的控件。
"""

from pathlib import Path
import os
import queue
import tempfile
import threading

import matplotlib
import numpy as np
from matplotlib import font_manager
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QFileDialog, QComboBox, QCheckBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QTabWidget,
)

from .analysis import analyze_file, display_spectrum, difference_spectrum, new_cancel_event
from .demo import make_demo
from .export import export_results

COLORS = ["#087f8c", "#df7351", "#6c60ac", "#348a45", "#c7497a", "#406ac6", "#928224", "#566975"]


def create_window(visible=True):
    """构造窗口并返回测试/启动接口；首次显示后不自动扫描用户目录。"""
    # 中文字体来自运行系统；不复制用户字体到发布包中。
    installed = {font.name for font in font_manager.fontManager.ttflist}
    for font in ("Microsoft YaHei", "Microsoft YaHei UI", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"):
        if font in installed:
            matplotlib.rcParams["font.family"] = font
            break
    matplotlib.rcParams["axes.unicode_minus"] = False
    matplotlib.rcParams["font.size"] = 9
    # Qt的Windows离屏插件默认没有字体库，显式注册系统字体供隐藏检查使用。
    # 仅读取系统自带字体，不随成品分发；正常桌面平台则直接使用系统字体库。
    if not QFontDatabase.families():
        font_dir = Path(os.environ.get("WINDIR", "")) / "Fonts"
        for filename in ("msyh.ttc", "seguiemj.ttf", "segoeui.ttf"):
            font_file = font_dir / filename
            if font_file.is_file():
                QFontDatabase.addApplicationFont(str(font_file))
    qt_fonts = QFontDatabase.families()
    qt_family = next((name for name in ("Microsoft YaHei", "Microsoft YaHei UI", "Noto Sans SC", "Segoe UI") if name in qt_fonts), "Sans Serif")
    window = QWidget()
    window.setWindowTitle("Music Analysis · 音乐频谱对比 1.0")
    window.resize(1400, 920)
    window.setMinimumSize(1000, 700)
    window.setFont(QFont(qt_family, 10))
    window.setStyleSheet("""
        QWidget { background: #f4f6f9; color: #20304a; }
        QLabel#brand { font-size: 25px; font-weight: 700; color: #13243c; }
        QLabel#muted { color: #60728c; }
        QPushButton { background: white; border: 1px solid #d5dfe9; border-radius: 6px; padding: 9px 12px; }
        QPushButton:hover { border-color: #087f8c; background: #eff9f9; }
        QPushButton:disabled { color: #9aa8b8; background: #eaf0f4; }
        QPushButton#primary { background: #087f8c; color: white; border: none; font-weight: 600; }
        QListWidget, QTableWidget { background: white; border: 1px solid #dde5ed; border-radius: 6px; }
        QListWidget::item { padding: 9px 3px; }
        QListWidget::item:selected { background: #ddf1f1; color: #153b45; }
        QComboBox { background: white; padding: 6px; border: 1px solid #d5dfe9; border-radius: 4px; }
        QTabWidget::pane { background: white; border: 1px solid #dde5ed; }
        QTabBar::tab { padding: 9px 24px; background: #e8eef4; }
        QTabBar::tab:selected { color: #087f8c; background: white; }
        QHeaderView::section { background: #edf2f7; padding: 6px; border: none; font-weight: 600; }
        QProgressBar { background: #e2eaf0; border: none; border-radius: 4px; height: 7px; }
        QProgressBar::chunk { background: #087f8c; border-radius: 4px; }
    """)
    root = QVBoxLayout(window)
    root.setContentsMargins(24, 18, 24, 16)
    title = QLabel("MUSIC ANALYSIS  /  音乐频谱对比")
    title.setObjectName("brand")
    root.addWidget(title)
    subtitle = QLabel("整首分析 · 多声道功率平均 · 完全离线 · 无需 MATLAB")
    subtitle.setObjectName("muted")
    root.addWidget(subtitle)
    splitter = QSplitter(Qt.Orientation.Horizontal)
    root.addWidget(splitter, 1)
    side = QWidget()
    side.setMinimumWidth(280)
    side.setMaximumWidth(360)
    left = QVBoxLayout(side)
    left.setContentsMargins(0, 10, 14, 0)
    left.addWidget(QLabel("01  音乐库"))
    add_button = QPushButton("＋ 添加音乐（可多选）")
    add_button.setObjectName("primary")
    left.addWidget(add_button)
    track_list = QListWidget()
    track_list.setWordWrap(True)
    left.addWidget(track_list, 1)
    demo_button = QPushButton("加载合成演示")
    remove_button = QPushButton("移除当前条目")
    left.addWidget(demo_button)
    left.addWidget(remove_button)
    left.addSpacing(12)
    left.addWidget(QLabel("02  分析设置"))
    left.addWidget(QLabel("Welch 窗口（秒）"))
    segment = QComboBox()
    segment.addItems(["0.25", "0.5", "1.0", "2.0"])
    segment.setCurrentText("1.0")
    left.addWidget(segment)
    fft_check = QCheckBox("同时计算整曲 FFT（更慢）")
    left.addWidget(fft_check)
    start_button = QPushButton("开始分析勾选音乐")
    start_button.setObjectName("primary")
    cancel_button = QPushButton("取消计算")
    cancel_button.setEnabled(False)
    left.addWidget(start_button)
    left.addWidget(cancel_button)
    progress_bar = QProgressBar()
    progress_bar.setTextVisible(False)
    left.addWidget(progress_bar)
    note = QLabel("勾选条目：叠加对比\n单击条目：查看该曲语谱图\n窗口/FFT设置改变后需重新分析")
    note.setObjectName("muted")
    left.addWidget(note)
    splitter.addWidget(side)
    right = QWidget()
    body = QVBoxLayout(right)
    body.setContentsMargins(6, 10, 0, 0)
    controls = QHBoxLayout()
    mode = QComboBox()
    mode.addItems(["绝对电平（PSD）", "归一化音色（共同频段）"])
    smoothing = QCheckBox("对数频带平滑")
    smoothing.setChecked(True)
    difference = QCheckBox("两曲差值 B − A")
    export_button = QPushButton("导出图片 / 数据")
    controls.addWidget(mode)
    controls.addWidget(smoothing)
    controls.addWidget(difference)
    controls.addStretch()
    controls.addWidget(export_button)
    body.addLayout(controls)
    tabs = QTabWidget()
    body.addWidget(tabs, 1)
    spectrum_figure = Figure(figsize=(9, 4.4), facecolor="white", layout="constrained")
    spectrum_canvas = FigureCanvasQTAgg(spectrum_figure)
    spectrum_tab = QWidget()
    spectrum_layout = QVBoxLayout(spectrum_tab)
    spectrum_layout.addWidget(NavigationToolbar2QT(spectrum_canvas, spectrum_tab))
    spectrum_layout.addWidget(spectrum_canvas, 1)
    tabs.addTab(spectrum_tab, "频谱叠加")
    spec_figure = Figure(figsize=(9, 4.4), facecolor="white", layout="constrained")
    spec_canvas = FigureCanvasQTAgg(spec_figure)
    spec_tab = QWidget()
    spec_layout = QVBoxLayout(spec_tab)
    spec_layout.addWidget(NavigationToolbar2QT(spec_canvas, spec_tab))
    spec_layout.addWidget(spec_canvas, 1)
    tabs.addTab(spec_tab, "全曲语谱图")
    help_label = QLabel(
        "比较口径\n\n"
        "• 绝对电平：PSD = 单边功率 / Hz，参考 1 FS²/Hz，不是声压级 SPL。\n"
        "• 归一化：按所有勾选歌曲共有频段的功率积分归一化，排除音量差。\n"
        "• 差值：恰好勾选两首时，显示列表中 B 减 A（dB）。\n"
        "• 语谱图：所有声道先平方再平均；固定色标，不会因反相抵消消失。\n"
        "• 不同 FFT 窗长的峰高不可直接比较；谱峰相近不代表算法已验证。\n"
        "• RMS dBFS 参考样本幅值1：满幅正弦为 −3.01 dBFS，不是 LUFS。\n"
        "• 整首均参与分析；语谱图只在计算后压缩为最多720个时间功率平均列。\n"
        "• 不读取标签/封面，不联网，不上传音乐，不保存源绝对路径。\n\n"
        "支持 WAV、MP3、FLAC、OGG、AIFF；AAC/M4A 暂不支持，请先转为 WAV/FLAC。"
    )
    help_label.setWordWrap(True)
    help_label.setMargin(24)
    help_label.setAlignment(Qt.AlignmentFlag.AlignTop)
    tabs.addTab(help_label, "口径与帮助")
    metrics = QTableWidget(0, 7)
    metrics.setHorizontalHeaderLabels(["音乐", "采样率", "声道 / 格式", "时长", "RMS dBFS", "质心 Hz", "Welch段数"])
    metrics.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    metrics.horizontalHeader().setStretchLastSection(True)
    metrics.setMaximumHeight(180)
    metrics.setMinimumHeight(125)
    metrics.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    body.addWidget(metrics)
    splitter.addWidget(right)
    splitter.setStretchFactor(1, 1)
    status = QLabel("就绪 · 添加音乐或加载合成演示，点击开始分析。")
    status.setObjectName("muted")
    status.setWordWrap(True)
    root.addWidget(status)

    # 仅保存在进程内，退出时不持久化源路径；结果与队列分别维护。
    paths, results = [], {}
    messages = queue.Queue()
    cancel = new_cancel_event()
    state = {"busy": False, "errors": [], "worker": None, "closed": False}
    demo_directory = tempfile.TemporaryDirectory(prefix="music-analysis-demo-")

    def selected_indices():
        return [i for i in range(track_list.count()) if track_list.item(i).checkState() == Qt.CheckState.Checked]

    def checked_results():
        return [results[index] for index in selected_indices() if index in results]

    def style_axis(axis):
        axis.set_facecolor("white")
        axis.grid(True, color="#dce4eb", alpha=0.7, linewidth=0.6)
        axis.spines[["top", "right"]].set_visible(False)
        axis.tick_params(colors="#53647a")

    def refresh(*_):
        """缓存展示，切换显示口径时不重新解码、FFT。"""
        chosen = checked_results()
        spectrum_figure.clear()
        axis = spectrum_figure.add_subplot(111)
        style_axis(axis)
        normalized = mode.currentIndex() == 1
        high = min([20000.0] + [result["sample_rate"] / 2 for result in chosen])
        if chosen:
            for index, result in enumerate(chosen):
                freq, level = display_spectrum(result, normalized, smoothing.isChecked(), high=high)
                axis.semilogx(freq, level, color=COLORS[index % len(COLORS)], linewidth=1.5, label=result["name"])
                if result["fft_psd"].size:
                    freq, level = display_spectrum(result, normalized, True, high=high, full=True)
                    axis.semilogx(freq, level, color=COLORS[index % len(COLORS)], linewidth=0.7, alpha=0.4, linestyle="--")
            if difference.isChecked() and len(chosen) == 2:
                axis.clear()
                style_axis(axis)
                freq, delta = difference_spectrum(chosen[0], chosen[1], normalized)
                axis.semilogx(freq, delta, color=COLORS[0], linewidth=1.6)
                axis.axhline(0, color="#8b96a5", linewidth=0.7)
                axis.set_title("B − A  |  " + chosen[1]["name"] + " − " + chosen[0]["name"], fontsize=10)
                axis.set_ylabel("PSD 差值 (dB)")
            else:
                axis.legend(loc="upper right", fontsize=8, frameon=False)
                axis.set_title("整首音乐 · Welch 功率谱密度" + ("（虚线：整曲 FFT）" if any(r["fft_psd"].size for r in chosen) else ""), loc="left", fontsize=11)
                axis.set_ylabel("相对功率密度 (dB/Hz)" if normalized else "PSD (dB re 1 FS²/Hz)")
            axis.set_xlim(20, high)
            if not (difference.isChecked() and len(chosen) == 2):
                levels = [line.get_ydata() for line in axis.lines if len(line.get_ydata())]
                if levels:
                    top = max(float(np.max(level)) for level in levels)
                    axis.set_ylim(max(-160, top - 105), max(top + 10, -110))
        else:
            axis.text(0.5, 0.53, "比较音乐，从添加文件开始", transform=axis.transAxes, ha="center", fontsize=16, color="#8a9aae")
            axis.text(0.5, 0.44, "也可以加载两段合成演示，先体验频谱对比", transform=axis.transAxes, ha="center", color="#8a9aae")
            axis.set_xlim(20, 20000)
            axis.set_xscale("log")
        axis.set_xlabel("频率 (Hz)")
        spectrum_canvas.draw_idle()
        metrics.setRowCount(len(chosen))
        for row, result in enumerate(chosen):
            values = [result["name"], f"{result['sample_rate'] / 1000:g} kHz", f"{result['channels']} / {result['subtype']}",
                      f"{result['duration'] / 60:.2f} min", f"{result['rms_dbfs']:.2f}", f"{result['centroid']:.1f}", str(result["segments"])]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setForeground(QColor(COLORS[row % len(COLORS)]))
                metrics.setItem(row, col, item)
        spec_figure.clear()
        spec_axis = spec_figure.add_subplot(111)
        active = results.get(track_list.currentRow())
        if active:
            freq = active["spec_frequency"]
            edges_f = np.linspace(0, active["sample_rate"] / 2, len(freq) + 1)
            mesh = spec_axis.pcolormesh(active["spec_edges"] / 60, edges_f / 1000,
                                       10 * np.log10(np.maximum(active["spec_psd"], 1e-20)),
                                       cmap="magma", vmin=-110, vmax=-20, shading="flat", rasterized=True)
            spec_figure.colorbar(mesh, ax=spec_axis, label="PSD (dB re 1 FS²/Hz)")
            spec_axis.set_ylim(0, min(20000, active["sample_rate"] / 2) / 1000)
            spec_axis.set_title(active["name"] + " · 全曲语谱图", loc="left", fontsize=11)
        else:
            spec_axis.text(0.5, 0.5, "单击已分析音乐，查看全曲语谱图", transform=spec_axis.transAxes, ha="center", color="#8a9aae")
        spec_axis.set_xlabel("时间 (min)")
        spec_axis.set_ylabel("频率 (kHz)")
        spec_canvas.draw_idle()
        export_button.setEnabled(bool(chosen) and not state["busy"])

    def add_paths(new_paths):
        if state["busy"]:
            return
        for path in new_paths:
            path = Path(path).resolve()
            if path in paths:
                continue
            paths.append(path)
            item = QListWidgetItem(path.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            track_list.addItem(item)
        if track_list.currentRow() < 0 and paths:
            track_list.setCurrentRow(0)
        status.setText(f"已添加 {len(paths)} 首 · 勾选需要比较的音乐，然后开始分析。")

    def browse():
        names, _ = QFileDialog.getOpenFileNames(window, "选择音乐（可多选）", "", "音频 (*.wav *.mp3 *.flac *.ogg *.aif *.aiff);;所有文件 (*)")
        add_paths(names)

    def load_demo():
        add_paths(make_demo(demo_directory.name))

    def remove():
        index = track_list.currentRow()
        if index < 0 or state["busy"]:
            return
        paths.pop(index)
        track_list.takeItem(index)
        remaining = {i - (i > index): value for i, value in results.items() if i != index}
        results.clear()
        results.update(remaining)
        refresh()

    def set_busy(busy):
        state["busy"] = busy
        for control in [add_button, demo_button, remove_button, start_button, segment, fft_check]:
            control.setEnabled(not busy)
        cancel_button.setEnabled(busy)
        export_button.setEnabled(not busy and bool(checked_results()))

    def analyze():
        indices = selected_indices()
        if state["busy"]:
            return
        if not indices:
            status.setText("请先添加并勾选至少一首音乐。")
            return
        set_busy(True)
        cancel.clear()
        state["errors"].clear()
        # 在主线程读取设置；工作线程不碰Qt控件。
        seconds, full = float(segment.currentText()), fft_check.isChecked()
        jobs = [(index, paths[index]) for index in indices]
        for index in indices:
            results.pop(index, None)  # 失败/取消时不将旧参数结果冒充本轮新结果。
        progress_bar.setValue(0)

        def worker():
            for position, (index, path) in enumerate(jobs):
                if cancel.is_set():
                    break
                messages.put(("status", f"正在完整分析 {position + 1}/{len(jobs)} · {path.name}"))
                try:
                    result = analyze_file(path, seconds, full, cancel,
                                          lambda part, pos=position: messages.put(("progress", int(100 * (pos + part) / len(jobs)))))
                    messages.put(("result", (index, result)))
                except InterruptedError:
                    break
                except Exception as exc:
                    # 不显示解码器内部路径/堆栈，不因一个文件损坏而丢掉其他结果。
                    messages.put(("error", f"{path.name}：{type(exc).__name__} · {str(exc)[:160]}"))
            messages.put(("done", None))

        state["worker"] = threading.Thread(target=worker, daemon=True, name="audio-analysis")
        state["worker"].start()

    def consume():
        while not messages.empty():
            event, value = messages.get_nowait()
            if event == "result":
                index, result = value
                results[index] = result
            elif event == "progress":
                progress_bar.setValue(value)
            elif event == "status":
                status.setText(value)
            elif event == "error":
                state["errors"].append(value)
            elif event == "done":
                set_busy(False)
                refresh()
                if state["errors"]:
                    status.setText("部分文件未完成：" + "；".join(state["errors"]))
                elif cancel.is_set():
                    status.setText("已取消 · 已完成的结果仍保留。")
                else:
                    progress_bar.setValue(100)
                    status.setText(f"分析完成 · {len(checked_results())} 首 · 切换归一化 / 差值，或导出结果。")

    def export_to(directory):
        chosen = checked_results()
        if not chosen:
            raise ValueError("没有可导出的分析结果")
        spectrum_canvas.draw()
        spec_canvas.draw()
        return export_results(chosen, directory, spectrum_figure, spec_figure,
                              "normalized" if mode.currentIndex() else "absolute")

    def choose_export():
        directory = QFileDialog.getExistingDirectory(window, "选择结果保存文件夹")
        if directory:
            try:
                export_to(directory)
                status.setText("导出成功 · 比较图、CSV及每曲报告已保存（不含源绝对路径）。")
            except Exception:
                status.setText("导出失败 · 请确认目录可写或更换保存目录。")

    def request_cancel():
        cancel.set()
        status.setText("正在取消，请等待当前计算步骤结束……")

    timer = QTimer(window)
    timer.setInterval(80)
    timer.timeout.connect(consume)
    timer.start()
    # 删除窗口/退出时只通知后台停止，不等待导致界面阻塞。
    window.destroyed.connect(lambda: cancel.set())
    add_button.clicked.connect(browse)
    demo_button.clicked.connect(load_demo)
    remove_button.clicked.connect(remove)
    start_button.clicked.connect(analyze)
    cancel_button.clicked.connect(request_cancel)
    export_button.clicked.connect(choose_export)
    track_list.itemChanged.connect(refresh)
    track_list.currentRowChanged.connect(refresh)
    mode.currentIndexChanged.connect(refresh)
    smoothing.toggled.connect(refresh)
    difference.toggled.connect(refresh)
    refresh()
    if visible:
        window.show()
    # 供冒烟测试驱动真实按钮和事件循环，不用替代界面假实现。
    return {"window": window, "load_demo": load_demo, "add_paths": add_paths,
            "analyze": analyze, "cancel": request_cancel, "remove": remove,
            "state": state, "results": results, "list": track_list,
            "mode": mode, "difference": difference, "smoothing": smoothing,
            "fft_check": fft_check, "tabs": tabs, "export": export_to,
            "start_button": start_button, "demo_button": demo_button,
            "spectrum_figure": spectrum_figure, "spec_figure": spec_figure,
            "timer": timer, "temp": demo_directory}
