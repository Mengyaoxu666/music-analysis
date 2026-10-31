"""提交前只检查Git候选文件；不读取用户音乐、环境或凭据存储。"""

from pathlib import Path
import re
import subprocess
import sys


def main():
    output = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    names = sorted(set(name.decode("utf-8") for name in output.split(b"\0") if name))
    forbidden = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".pem", ".key", ".pfx", ".p12", ".exe", ".zip", ".log"}
    patterns = {
        "machine_absolute_path": re.compile(r"\b[A-Za-z]:[\\/]"),
        "github_token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
        "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "cloud_key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    }
    failures = []
    for name in names:
        path = Path(name)
        if path.suffix.lower() in forbidden or path.name.startswith(".env"):
            failures.append((name, "forbidden_file_type"))
        if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".ico"}:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            failures.append((name, "unexpected_binary"))
            continue
        for label, pattern in patterns.items():
            if pattern.search(text):
                failures.append((name, label))
    # 仅报告文件/类别，不把匹配的敏感内容打印到日志。
    for name, label in failures:
        print(f"BLOCKED {name}: {label}")
    print(f"Public candidate scan: {len(names)} files, {len(failures)} findings")
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
