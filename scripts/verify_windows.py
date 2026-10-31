"""独立进程验证发布包：清除开发环境路径，安装、运行、导出、卸载。

所有测试文件在local下，本脚本不枚举或修改用户已有安装。
运行命令：conda run -n music-analysis python scripts/verify_windows.py
"""

import json
import os
from pathlib import Path
import subprocess
import time
import zipfile


def run_application(executable, output, env):
    """不调用Python解释器，直接运行待交付EXE。"""
    subprocess.run([str(executable), "--smoke-test", str(output)], cwd=output.parent,
                   env=env, check=True, timeout=120)
    report = json.loads((output / "smoke.json").read_text(encoding="utf-8"))
    assert report["passed"] and report["songs"] == 2
    assert (output / "export" / "comparison.png").is_file()
    return report


def main():
    import winreg

    # 防止同AppId安装测试覆盖日常已安装版本的注册信息。
    key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{93F5899D-B7AF-4677-8759-90B1E6576C5B}_is1"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key):
            raise RuntimeError("已存在日常安装，请勿在同一用户下运行安装/卸载测试")
    except FileNotFoundError:
        pass
    root = Path(__file__).resolve().parents[1]
    # 每次使用独立测试目录，不覆盖日常使用者安装或导出文件。
    work = root / "local" / f"package-check-{time.time_ns()}"
    work.mkdir(parents=True)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("CONDA", "PYTHON", "QT_", "MPL"))}
    system = Path(os.environ["SystemRoot"])
    env["PATH"] = str(system / "System32") + os.pathsep + str(system)
    started = time.monotonic()
    archive = root / "release" / "MusicAnalysis-1.0.0-Windows-x64-portable.zip"
    with zipfile.ZipFile(archive) as stream:
        stream.extractall(work / "portable")
    app_dir = work / "portable" / "MusicAnalysis"
    assert (app_dir / "_internal" / "third_party_licenses" / "Qt" / "LGPL-3.0-only.txt").is_file()
    portable = run_application(app_dir / "MusicAnalysis.exe", work / "portable-evidence", env)
    installer = root / "release" / "MusicAnalysis-1.0.0-Windows-x64-Setup.exe"
    target = work / "installed"
    subprocess.run([str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
                    f"/DIR={target}", "/CURRENTUSER", f"/LOG={work / 'setup.log'}"],
                   env=env, check=True, timeout=180)
    try:
        installed = run_application(target / "MusicAnalysis.exe", work / "installed-evidence", env)
    finally:
        uninstaller = target / "unins000.exe"
        if uninstaller.exists():
            subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                           env=env, check=True, timeout=90)
    assert not (target / "MusicAnalysis.exe").exists(), "卸载后仍残留主程序"
    report = {"passed": True, "platform": "Windows 11 x64", "clean_path": True,
              "portable": portable, "installed": installed, "uninstall": True,
              "seconds": round(time.monotonic() - started, 2)}
    destination = root / "local" / "package-validation.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
