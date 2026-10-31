# 项目约定

- 本项目交付独立 Windows 11 x64 EXE，不要求终端用户安装 MATLAB/Python/conda。
- 开发与测试使用经用户确认的 conda 环境 `music-analysis`。
- 检查：`conda run -n music-analysis python -m pytest -q`；
  `conda run -n music-analysis python -m ruff check .`。
- 隐藏 GUI 检查：`conda run -n music-analysis python main.py --smoke-test local/smoke`。
- 打包：`conda run -n music-analysis python scripts/build_windows.py`。
- 不使用子 agent。保留函数式数值核心；界面使用 Qt 内置组件，无需自定义类。
- 禁止上传本地音乐、凭据、真实音乐文件名、用户目录及开发机绝对路径。
- 公共测试和截图只用程序生成的合成信号；二进制附件上传 GitHub Releases。
