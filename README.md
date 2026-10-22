# 拾影 · 视频、图文与原声

Windows 桌面版与原生 Android 应用。粘贴分享链接，收藏视频、整组图文与独立音频。源码仓库：https://github.com/W-cola/shiying 。

## Windows 桌面版 v1.7.1

双击项目根目录的 `启动拾影.cmd`，或 `dist/ShiYing/拾影.exe`。便携版解压后直接打开 `拾影.exe`；保留同目录的 `_internal` 文件夹，无需安装 Python。

v1.7.1 统一画质、分类、倍速选择器及弹出列表，重绘播放器滑块、复选框和菜单。桌面、任务栏、应用内品牌使用同一套「书签＋播放」图标，EXE 内嵌 16–256 像素的 9 个尺寸；矢量源文件为 `assets/app.svg`。

运行 `tools/create_desktop_shortcut.ps1` 可在当前用户桌面创建「拾影」快捷方式，直接启动 EXE 并使用配套图标。迁移程序文件夹后重新创建快捷方式即可；`.cmd` 启动脚本仍保留作为备用入口。

1. 粘贴一条完整分享文字，点击「解析内容」。支持抖音、小红书、B站、快手、视频号，以及 yt-dlp 支持的其他单个视频和图片直链。
2. 选择画质或「全部图片 / 第 N 张」，可在应用内播放、预览，或保存到所选文件夹。
3. 「只收下声音」将原声音轨保存为独立 M4A；已有视频也能从「我的片段」提取原声。AAC 优先无损封装，其他可处理编码转成 AAC。无音轨会明确失败。
4. 「我的片段」支持全部 / 视频 / 图文 / 音频分类，按标题或作者搜索。图文每次保存为一个独立文件夹，含原顺序图片与 UTF-8 正文，不会散成重复记录。
5. 双击片段在应用内播放或预览。视频支持暂停、拖动进度、前后跳转 15 秒、0.5–2× 倍速、循环、全屏、画面旋转、音量与亮度调节。全屏轻触显示控制，播放时 3 秒后隐藏，Esc 先退出全屏；空格暂停，方向键跳转。画面左右拖动调进度，左半屏上下拖动调亮度，右半屏上下拖动调音量。
6. 图文支持左右拖动、方向键和上一张 / 下一张，保留张数、顺序及正文。可以复制文件到聊天窗口或其他文件夹，也可打开原位置、重新解析。
7. 删除前会确认，删除所选批次的文件和记录；其他批次保留。预览窗口打开时需先关闭再删除。原 v1.0 的本地下载记录继续可用。

在线播放采用临时下载缓存，不新增下载记录或公开保存文件；关闭播放器清理缓存，下次预览清理超过 24 小时的遗留缓存。临时媒体上限 1 GiB。Windows 轮子自带 FFmpeg，无需另配音频工具。

## 平台能力与边界

| 平台 | 已接入内容 | 验证范围 |
| --- | --- | --- |
| 抖音 | 视频、图文 / 图集、短链及 video/note/slides 页面 | 真实视频保存、完整解码与音频提取；图文数据回归 |
| 小红书 | 视频、图文、单张 / 多张图片、正文 | 目标编号、视频流、图片顺序的数据回归；真实网站可能要求登录与验证 |
| B站 | BV/AV、b23.tv、当前分 P、DASH 音视频整理、动态与专栏图文 | 真实公开视频音视频保存、完整解码与音频提取；分 P、图文和受保护片段拒绝回归 |
| 快手 | 视频、图集、Apollo 网页状态及分享短链 | 真实 10 张图文与正文完整保存；视频与引用结构回归 |
| 视频号 | sph 分享视频、可访问网页提供的视频和图文 | 真实 sph 视频保存、完整解码与音频提取；网页数据与格式参数回归 |
| 直链 / 其他网页 | 常见图片、视频直链及 yt-dlp 支持的单个录播视频 | 本地 HTTP 下载、续传、错误内容、取消回归 |

视频号 sph 使用与安卓版相同的公开在线解析服务 `https://v.mtotech.com/api/resolve`，仅发送粘贴的分享 URL，不发送本机 Cookie；服务可用性由第三方决定。

需要登录或验证码时，点击「浏览器辅助解析」，在应用专用 Edge / Chrome 中手动完成。浏览器状态保存在本机，按 Cookie 域隔离，不读取日常浏览器配置。抖音浏览器路径只接受匹配目标编号的数据，不会把 `currentSrc` 的加载动画直接认作视频。

实际画质与可访问内容由网站决定，不保证无水印或所有链接都成功；不移除水印，不支持直播、私密、删除、区域限制或 DRM 内容，也不会将受保护试看当作完整视频。Android 的系统分享、媒体库相册路径等按 Windows 的文件夹、剪贴板和应用内播放器对应实现。

## 本机数据与升级

打包版的设置、历史和独立浏览器状态保存在 exe 同目录 `data/`；默认保存到同目录 `downloads/`。源码运行使用项目根目录，或设置 `CLIPHARBOR_DATA` 指向独立数据目录。用户文件不进入 Git。

`tools/build.py` 先输出到 `build/desktop-dist/ShiYing`。关闭旧版后运行 `tools/install_desktop.py`，仅更新程序文件，保留 `dist/ShiYing/data` 与 `downloads`。不要用清空应用文件夹的方式升级。

## 安卓版

[安卓版说明](android/README.md) 与 [交互设计](android/DESIGN.md) 保留。安卓 v1.7.0 的源码位于 `android/`；APK、签名、模拟器和本机会话不上传 GitHub。安卓本机预览 `http://127.0.0.1:8787/` 是模拟器操作面板，尚非独立网页产品。

## 开发与验证

Python 3.12+，Windows 10/11：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools\gui_smoke.py
```

若没有 Edge / Chrome，可安装 Playwright Chromium：

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

构建、关闭旧版后安装、打包：

```powershell
.\.venv\Scripts\python.exe tools\build.py
.\.venv\Scripts\python.exe tools\install_desktop.py
.\.venv\Scripts\python.exe tools\package.py
```

`requirements-lock.txt` 记录验证环境的依赖版本。`tools/verify_desktop_live.py` 为可选联网验证，会实际访问样本、保存测试媒体并提取音频，结果写入 `.tmp/desktop-live/report.json`。其结果只代表对应样本在测试时成功。

## 源码结构与网页改造

- `clipharbor/engine.py`：统一解析、下载、进度、续传和取消入口。
- `clipharbor/platforms.py`、`douyin.py`：各平台目标编号、正常网页数据与独立浏览器解析。
- `clipharbor/media.py`、`channels_codec.py`：整组图文、正文、音视频整理、音频提取及临时缓存。
- `clipharbor/player.py`、`gui.py`：Qt 应用内播放器、图文预览与界面。
- `clipharbor/store.py`：本地设置、分类搜索、旧记录兼容与准确删除。
- `tests/`：Windows 桌面版测试；`android/tests/`：独立安卓测试，不由 pytest 自动收集。
- [网页版交接](docs/网页版交接.md)：供网页开发平台阅读的入口与改造边界。

仅用于自己的内容、已获授权内容和合法研究用途；下载不改变内容的版权或使用权限。第三方依赖与许可证见 [THIRD_PARTY.md](THIRD_PARTY.md)。
