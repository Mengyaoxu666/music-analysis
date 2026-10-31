# 1.0.0 验收记录

## 验证范围

本机 Windows 11 x64 执行，所有源码检查位于经确认的 `music-analysis` conda 环境。
安装版与便携版另起独立进程，PATH只保留Windows系统目录，并去除CONDA/PYTHON/Qt开发环境变量。
不是只验证解释器里的代码，也不以构建成功代替EXE运行测试。

| 验证项 | 结果 |
|---|---|
| Ruff静态检查 | All checks passed |
| pytest数值+GUI回归 | 33 passed，11.67秒；无警告 |
| 纯源码GUI离屏冒烟 | 通过，2首演示，归一化/差值/语谱图/导出 |
| 便携ZIP解压后直接运行EXE，清洁PATH | 通过，GUI冒烟3.33秒 |
| 安装器静默安装、安装后运行EXE，清洁PATH | 通过，GUI冒烟2.47秒 |
| 安装后卸载 | 通过，主EXE不残留 |
| 完整发布包安装/运行/卸载流程 | 26.73秒 |
| 原始待公开文件扫描 | 无命中的机器绝对路径、常见令牌、私钥或被禁二进制/音乐 |

## 33项回归包含

- 单窗PSD与SciPy独立Welch实现逐点核对，容差 `rtol=1e-12`。
- 全曲重叠分段与SciPy Welch对照。
- 已知正弦积分功率：幅度0.5、均方0.125、RMS约−9.0309 dBFS。
- 1/2/6声道，包含反相立体声，语谱图不抵消。
- 8/44.1/48/96 kHz采样率，功率标定一致。
- 已知0.5倍幅度变化：差值−6.0206 dB；功率归一化后的差值约0。
- WAV/FLAC/MP3/OGG及中文目录解码。
- **301秒** FLAC完整分析，末尾一秒独立高频能量在Welch和语谱图均可检出。
- 4/17/100/255样本短文件、静音、NaN、缺失/损坏文件。
- 取消协议、GUI真实事件循环、错误文件隔离、重复导入、勾选/移除后的索引映射。
- 重名歌曲分目录导出，报告无来源绝对路径。

## 真实音频本机检查

另对一首约250秒FLAC和一首约247秒MP3做了完整分析，均通过。
仅记录非识别性指标，未复制音频、真实文件名或源路径到本仓库/发布附件。
该检查不作为外部可重现的数值基准；公开的数值基准全部为合成信号。

## 验收边界

- 未在全新Windows虚拟机或其他实体机上测试；清洁PATH验证不等同于全新系统兼容性认证。
- 安装器/应用未商业代码签名，可能触发SmartScreen。
- AAC/M4A不在支持范围内。
- GUI操作验证为离屏真实Qt组件与回调，截图已人工检查中文、布局和曲线。
- 未使用MATLAB GUI或Runtime作为成品运行依赖。

## 复现命令

```powershell
conda run -n music-analysis python -m ruff check .
conda run -n music-analysis python -m pytest -q
conda run -n music-analysis python main.py --smoke-test local/smoke
conda run -n music-analysis python scripts/check_public.py
conda run -n music-analysis python scripts/verify_windows.py
```

最后一个命令要求已生成便携ZIP和安装EXE，并会创建独立测试目录。
如果当前用户已安装日常版本，脚本会拒绝安装测试，以免覆盖其卸载注册信息。
