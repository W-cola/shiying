# 拾影 · 视频下载工具

安卓应用已升级至 v1.7.0：保留一个分享链接输入框和原视频解析结果，新增独立音频保存（M4A，音乐/拾影）与应用内音频播放；已保存的视频也能直接提取原声。统一升级片段卡、底部详情面板、图标、文字对比和过渡动画，片段库新增分类、搜索，并保留图文整组滑动预览、相册保存与正确方向的沉浸式全屏。电脑可在 Codex 右侧打开 [真实 APK 预览](http://127.0.0.1:8787/)，修改源码后点击按钮重新编译安装。重启预览运行 `android/启动安卓预览.cmd`。详情见 [安卓说明](android/README.md) 和 [交互调研](android/DESIGN.md)，安装包为 `dist/拾影-安卓版-v1.7.0.apk`，原签名可覆盖安装保留记录。以下为原有 Windows 桌面版说明，其功能未随 APK 一起升级。

本地运行的 Windows 桌面应用。粘贴抖音整段分享文字，解析视频，选择画质与保存位置，然后下载。也支持 yt-dlp 能解析的其他单个视频网页和视频直链。

## 直接使用

1. 双击项目中的 `启动拾影.cmd`，或 `dist/ShiYing/拾影.exe`。
2. 粘贴整段分享文字，点击「解析视频」。
3. 选择解析到的画质和保存文件夹，点击「下载视频」。
4. 下载完成后点击「打开保存文件夹」。下载记录保存在「下载记录」页面。

不需要安装 Python。复制或分发时，请保留整个 `dist/ShiYing` 文件夹，包含 `_internal`；不能只复制 exe。

抖音要求登录或验证码时，点击「浏览器辅助解析」，在弹出的独立浏览器中手动完成，并播放目标视频。应用等待最多 3 分钟，读到视频后自动关闭浏览器并返回。请留在目标视频页面。需要本机已安装 Microsoft Edge 或 Chrome。

## 功能与实际边界

- 自动提取分享文字中的 http/https 链接，展开抖音短链接。
- 优先读取正常分享页的公开播放信息；没有信息时用 Playwright 加载真实浏览器，并读取目标视频的页面数据或播放器地址。
- 校验目标视频编号，避免从推荐列表中误选其他视频。下载标题为空时使用视频编号命名。
- 选择页面实际提供的画质；并不保证每条链接都有原画、多种画质或无水印版本。不会额外处理或移除水印。
- 流式下载、进度、速度、取消、HTTP Range 续传、同名文件保护、下载历史。取消和网络中断会保留 `.part` 临时文件；同一个有效地址再次下载可续传。地址刷新后可能重新下载。
- 下载器检查 HTTP 状态、返回内容类型和文件长度，不会把登录页面当作 MP4。
- 当前针对单个录播视频；不支持直播、图集、主页或批量合集。私密、删除、区域限制及 DRM 视频可能无法下载。
- 网站接口可能变化。抖音没有为本应用提供稳定的官方下载 API；真实浏览器与解析器也无法保证所有视频永远成功。
- 通用网站优先提供包含音频的视频格式；本机有 FFmpeg 时还提供自动合并的最佳画质。FFmpeg 是可选项，普通抖音 MP4 下载不需要它。

应用与会话数据保存在 exe 同目录的 `data/`，默认下载目录为同目录的 `downloads/`。源码运行时位于项目根目录。请放在可写目录中使用。浏览器使用本应用独立的 `data/browser-profile/`，不会读取日常浏览器的个人配置。登录会话属于敏感数据，请勿把 `data/` 或浏览器配置发给别人。关闭应用后可删除 `data/browser-profile/` 和 `data/browser-state.json` 来清除会话。

适用于自己的视频、已获授权的视频和合法研究用途。下载不改变内容的版权或使用权限。

## 本次真实测试

测试链接：`https://v.douyin.com/78nnhuQHT8k/`

- 展开后的目标视频编号：`7693840282563565674`
- 作者：口罩哥研报60秒
- 分享页提供的播放画质：854×480
- 实际保存：10,749,131 字节 MP4
- FFprobe 检查：H.264 视频、AAC 音频，文件时长约 86.75 秒；分享页声明约 83.73 秒，以下载文件为准。
- 浏览器备用路径正确匹配相同视频，并读取到 8 个可用视频源。
- 16 项自动测试通过，完成整个视频的 FFmpeg 解码检查；打包版也完成实际下载和界面渲染验证。

本次结果仅代表此链接在测试时成功；访问状态和可用画质由平台决定。

## 开发运行

Python 3.12+，Windows 10/11。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe main.py
```

`requirements-lock.txt` 记录本次实际安装的完整版本；重现依赖可安装该文件。开发环境若没有 Edge/Chrome，可安装 Playwright Chromium：

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

命令行解析与下载：

```powershell
.\.venv\Scripts\python.exe main.py --url "https://v.douyin.com/78nnhuQHT8k/" --download --output ".\downloads"
```

测试与打包：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools\build.py
```

更新解析依赖后需重新测试并打包：

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade -r requirements.txt
```

## 项目结构

- `clipharbor/gui.py`：PySide6 界面与后台任务。
- `clipharbor/douyin.py`：分享页、页面数据、独立浏览器解析。
- `clipharbor/engine.py`：通用解析、流式下载、续传。
- `clipharbor/store.py`：本地设置和下载历史。
- `tests/`：分享文本、目标视频选择、下载、续传、错误内容、取消和 Cookie 域隔离测试。

参考：[yt-dlp 官方项目](https://github.com/yt-dlp/yt-dlp)、[Playwright 浏览器支持](https://playwright.dev/python/docs/browsers)。
