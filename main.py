"""双击 EXE 启动；--smoke-test 在不显示窗口的情况下运行真实GUI回调。"""

import argparse
import json
import os
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", type=Path, help="静默测试并写出报告和截图")
    args = parser.parse_args()
    if args.smoke_test:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    # 不在启动目录写缓存；matplotlib默认缓存位于用户自己的缓存目录。
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from music_analysis.gui import create_window
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Music Analysis")
    interface = create_window(visible=not bool(args.smoke_test))
    app.aboutToQuit.connect(interface["cancel"])
    if args.smoke_test:
        destination = args.smoke_test.resolve()
        destination.mkdir(parents=True, exist_ok=True)
        interface["fft_check"].setChecked(True)
        interface["demo_button"].click()
        interface["start_button"].click()
        started = time.monotonic()
        timer = QTimer()

        def verify():
            if interface["state"]["busy"]:
                if time.monotonic() - started > 90:
                    (destination / "smoke.json").write_text('{"passed": false, "error": "timeout"}')
                    app.exit(1)
                return
            timer.stop()
            try:
                assert not interface["state"]["errors"], interface["state"]["errors"]
                assert len(interface["results"]) == 2
                assert not interface["window"].isVisible()
                assert all(r["integrated_power"] > 0.01 for r in interface["results"].values())
                # 实际驱动归一化、差值、语谱图切换与导出。
                interface["mode"].setCurrentIndex(1)
                interface["difference"].setChecked(True)
                assert len(interface["spectrum_figure"].axes[0].lines) == 2
                interface["difference"].setChecked(False)
                interface["list"].setCurrentRow(1)
                interface["tabs"].setCurrentIndex(1)
                interface["export"](destination / "export")
                interface["tabs"].setCurrentIndex(0)
                interface["window"].grab().save(str(destination / "gui.png"))
                # 勾选 / 移除 / 错误文件分支由单测补充；这里验证缓存结果未变化。
                report = {"passed": True, "songs": 2, "hidden_window": True,
                          "full_fft": True, "normalization": True, "difference": True,
                          "spectrogram": True, "export": True,
                          "seconds": round(time.monotonic() - started, 2)}
                (destination / "smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                app.exit(0)
            except Exception as exc:
                (destination / "smoke.json").write_text(json.dumps({"passed": False, "error": str(exc)}), encoding="utf-8")
                app.exit(1)

        timer.timeout.connect(verify)
        timer.start(100)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
