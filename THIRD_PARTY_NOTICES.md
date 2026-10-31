# 第三方组件与运行时

本程序使用 Python、NumPy、SciPy、matplotlib、SoundFile/libsndfile、PySide6/Qt、
shiboken6 及其依赖。打包脚本会从已安装发行包提取实际许可证，放入便携包的
`_internal/third_party_licenses/`。用户可直接阅读这些文本。

- Python: https://www.python.org/psf/license/
- NumPy: https://github.com/numpy/numpy (BSD)
- SciPy: https://github.com/scipy/scipy (BSD及所含第三方声明)
- matplotlib: https://github.com/matplotlib/matplotlib
- SoundFile: https://github.com/bastibe/python-soundfile (BSD)
- libsndfile: https://github.com/libsndfile/libsndfile (LGPL-2.1-or-later)
- PySide6 / shiboken: https://code.qt.io/pyside/pyside-setup.git/ (LGPL-3.0/GPL/商业多许可，参见随包许可证)
- Qt: https://code.qt.io/cgit/qt/ (各模块具体许可见随包文本)
- Qt开源许可说明: https://www.qt.io/licensing/open-source-lgpl-obligations
- Qt 6.9.1源码: https://download.qt.io/archive/qt/6.9/6.9.1/

发行使用目录式动态库打包，不加密或静态链接Qt/libsndfile，不限制用户为调试这些库
而进行的修改、共享库替换或逆向工程（受相应第三方许可证保护的范围内）。
构建源码和步骤公开在本仓库。安装器仅复制/删除应用文件，不包含遥测或下载器。
PyInstaller引导器遵循GPL附带bootloader例外，安装器由Inno Setup编译。

字体使用系统已安装字体，未将开发机中文字体复制进安装包。
演示音频是数学合成信号，不包含音乐采样或商业歌曲。
