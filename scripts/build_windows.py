"""在确认的开发环境运行，生成可替换DLL的便携包，随后由Inno Setup生成安装包。"""

from importlib import metadata
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    release = root / "release"
    release.mkdir(exist_ok=True)
    # 复制第三方实际许可证，而非仅列出包名。保留Qt/LGPL替换共享库的权利。
    notices = root / "build" / "notices"
    notices.mkdir(parents=True, exist_ok=True)
    shutil.copytree(root / "third_party_licenses", notices, dirs_exist_ok=True)
    for name in ["numpy", "scipy", "soundfile", "matplotlib", "PySide6-Essentials", "shiboken6", "cffi", "pillow", "contourpy", "kiwisolver", "cycler", "fonttools", "pyparsing", "python-dateutil", "six", "pyinstaller"]:
        dist = metadata.distribution(name)
        for entry in dist.files or []:
            if "license" in str(entry).lower() or "copying" in str(entry).lower():
                source = Path(dist.locate_file(entry))
                if source.is_file():
                    target = notices / name / str(entry).replace("/", "_").replace("\\", "_")
                    target.parent.mkdir(exist_ok=True)
                    shutil.copy2(source, target)
    python_license = Path(sys.base_prefix) / "LICENSE_PYTHON.txt"
    if python_license.is_file():
        shutil.copy2(python_license, notices / "LICENSE_PYTHON.txt")
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
               "--onedir", "--name", "MusicAnalysis", "--collect-data", "_soundfile_data",
               "--add-data", f"{notices};third_party_licenses", "--add-data", "THIRD_PARTY_NOTICES.md;.",
               "--exclude-module", "tkinter", "--exclude-module", "pytest", "main.py"]
    subprocess.run(command, cwd=root, check=True)
    app_dir = root / "dist" / "MusicAnalysis"
    for filename in ["README.md", "THIRD_PARTY_NOTICES.md"]:
        shutil.copy2(root / filename, app_dir / filename)
    shutil.make_archive(str(release / "MusicAnalysis-1.0.0-Windows-x64-portable"), "zip", root / "dist", "MusicAnalysis")
    print("便携包已生成。运行 Inno Setup 编译 installer/windows.iss 后，重新生成 SHA256SUMS.txt。")
    write_checksums(release)


def write_checksums(directory):
    rows = []
    for path in sorted(Path(directory).glob("*")):
        if path.suffix.lower() in {".zip", ".exe"}:
            rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    (Path(directory) / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="ascii")


if __name__ == "__main__":
    main()
