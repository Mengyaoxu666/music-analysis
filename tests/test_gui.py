"""离屏驱动真实 Qt 回调；不弹窗，也不关闭用户的其他应用。"""

import os
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from music_analysis.gui import create_window


def test_gui_workflow(tmp_path):
    app = QApplication.instance() or QApplication([])
    ui = create_window(visible=False)
    try:
        ui["demo_button"].click()
        assert ui["list"].count() == 2
        ui["start_button"].click()
        deadline = time.monotonic() + 45
        while ui["state"]["busy"] and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.02)
        assert not ui["state"]["busy"]
        assert not ui["state"]["errors"]
        assert len(ui["results"]) == 2
        assert not ui["window"].isVisible()
        ui["mode"].setCurrentIndex(1)
        ui["difference"].setChecked(True)
        assert len(ui["spectrum_figure"].axes[0].lines) == 2
        ui["list"].item(0).setCheckState(Qt.CheckState.Unchecked)
        ui["export"](tmp_path)
        assert (tmp_path / "comparison.png").exists()
        assert len(list(tmp_path.glob("*/report.json"))) == 1
        ui["list"].setCurrentRow(0)
        ui["remove"]()
        assert ui["list"].count() == 1
        assert 0 in ui["results"]
        assert ui["results"][0]["name"].endswith(".flac")
    finally:
        ui["cancel"]()
        if ui["state"]["worker"]:
            ui["state"]["worker"].join(timeout=5)
        ui["timer"].stop()
        ui["window"].close()
        ui["temp"].cleanup()


def test_gui_bad_file_and_cancel(tmp_path):
    app = QApplication.instance() or QApplication([])
    ui = create_window(visible=False)
    try:
        bad = tmp_path / "broken.wav"
        bad.write_bytes(b"not a music file")
        ui["add_paths"]([bad, bad])
        assert ui["list"].count() == 1  # 同路径不重复加入。
        ui["load_demo"]()
        ui["analyze"]()
        deadline = time.monotonic() + 45
        while ui["state"]["busy"] and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.02)
        assert not ui["state"]["busy"]
        assert len(ui["results"]) == 2 and len(ui["state"]["errors"]) == 1
        ui["analyze"]()
        ui["cancel"]()
        deadline = time.monotonic() + 15
        while ui["state"]["busy"] and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.02)
        assert not ui["state"]["busy"]
        assert not ui["window"].isVisible()
    finally:
        ui["cancel"]()
        if ui["state"]["worker"]:
            ui["state"]["worker"].join(timeout=5)
        ui["timer"].stop()
        ui["window"].close()
        ui["temp"].cleanup()
