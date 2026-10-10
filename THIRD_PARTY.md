# 第三方组件

应用使用开源组件，打包文件中的 `_internal` 保留其随包提供的许可与元数据。

| 组件 | 用途 | 上游与许可 |
| --- | --- | --- |
| Python | 应用运行时 | https://www.python.org/ · PSF License |
| PySide6 / Qt Essentials | 桌面界面，动态链接 DLL | https://www.qt.io/qt-for-python · LGPLv3/GPLv3 或商业许可；本项目采用 LGPLv3 路径 |
| Playwright | 浏览器加载与页面数据读取 | https://github.com/microsoft/playwright-python · Apache-2.0 |
| yt-dlp | 通用视频解析与下载 | https://github.com/yt-dlp/yt-dlp · Unlicense；部分依赖有各自许可 |
| Requests | HTTP 流式下载 | https://github.com/psf/requests · Apache-2.0 |
| PyInstaller | 应用打包 | https://github.com/pyinstaller/pyinstaller · GPL-2.0-or-later，带分发例外 |

其他传递依赖按各自元数据许可分发。未打包 Microsoft Edge、Google Chrome 或 FFmpeg，它们由用户机器提供。

本项目完整源码随项目交付。Qt/PySide6 DLL 位于 `_internal`，可替换相容的动态链接版本。Qt 对应版本的源代码与许可见 https://download.qt.io/official_releases/qt/ 和 https://code.qt.io/；PySide6 源代码见 https://code.qt.io/cgit/pyside/pyside-setup.git/ 。
