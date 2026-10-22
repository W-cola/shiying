# 第三方组件

应用使用开源组件，打包文件中的 `_internal` 保留其随包提供的许可与元数据。

| 组件 | 用途 | 上游与许可 |
| --- | --- | --- |
| Python | 应用运行时 | https://www.python.org/ · PSF License |
| PySide6 / Qt Essentials 与 Addons | 桌面界面、QtMultimedia 应用内播放，动态链接 DLL | https://www.qt.io/qt-for-python · LGPLv3/GPLv3 或商业许可；本项目采用 LGPLv3 路径 |
| imageio-ffmpeg / FFmpeg | 独立音频提取与音视频整理；Windows 轮子内置 FFmpeg | https://github.com/imageio/imageio-ffmpeg · Python 包 BSD-2-Clause；FFmpeg 可执行文件遵循随包提供的 GPLv3 许可及构建说明，见 licenses/imageio-ffmpeg |
| Playwright | 浏览器加载与页面数据读取 | https://github.com/microsoft/playwright-python · Apache-2.0 |
| yt-dlp | 通用视频解析与下载 | https://github.com/yt-dlp/yt-dlp · Unlicense；部分依赖有各自许可 |
| Requests | HTTP 流式下载 | https://github.com/psf/requests · Apache-2.0 |
| PyInstaller | 应用打包 | https://github.com/pyinstaller/pyinstaller · GPL-2.0-or-later，带分发例外 |
| sherpa-onnx 1.13.8 | CPU 离线语音识别及字词时间戳 | https://github.com/k2-fsa/sherpa-onnx · Apache-2.0 |
| SenseVoice Small int8 2024-07-17 | 离线多语言识别模型 | https://github.com/FunAudioLLM/SenseVoice · 代码 MIT；模型权重按模型卡所列 FunASR Model License，见 licenses/sensevoice-model.txt；固定导出及摘要见 assets/speech/model.json |
| Silero VAD | 本地讲话片段检测 | https://github.com/snakers4/silero-vad · MIT |
| ONNX Runtime | 本地模型推理运行库 | https://github.com/microsoft/onnxruntime · MIT |
| NumPy | 本地 PCM 音频处理 | https://numpy.org/ · BSD-3-Clause |

其他传递依赖按各自元数据许可分发。未打包 Microsoft Edge 或 Google Chrome，它们由用户机器提供。FFmpeg 由 imageio-ffmpeg 提供，也可通过 IMAGEIO_FFMPEG_EXE 指定兼容程序；许可与源码构建入口随包保留。

本项目完整源码随项目交付。Qt/PySide6 DLL 位于 `_internal`，可替换相容的动态链接版本。Qt 对应版本的源代码与许可见 https://download.qt.io/official_releases/qt/ 和 https://code.qt.io/；PySide6 源代码见 https://code.qt.io/cgit/pyside/pyside-setup.git/ 。
