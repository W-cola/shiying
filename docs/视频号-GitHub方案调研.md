> 2026-10-08 后续更新：拾影 v1.4.2 已接入一个公开免登录的第三方解析服务，用户视频实测成功。下面保留此前 GitHub 调研；元宝登录方案属于另一条路径，用户登录不是实现下载的必经步骤。

# 视频号 GitHub 方案调研

核对日期：2026-10-08。此文件是技术调研记录，不表示这些方案已接入拾影 APK，也不表示用户的视频已通过登录路径下载。

## 结论

GitHub 存在完整的视频号处理实现。对拾影安卓应用，优先验证用户在本机登录腾讯元宝、取得正常播放信息的路径；系统相册保存及已公开播放参数对应的格式处理，可以复用现有原生实现。

普通 sph 分享页仅有封面，并不能证明其他带有效播放参数的访问方式也无法取得视频。当前缺少的关键环节是短链转换和授权播放信息获取。

## 候选项目

| 项目 | 已核对的处理方式 | 与安卓应用的关系 |
| --- | --- | --- |
| [ltaoo/wx_channels_download](https://github.com/ltaoo/wx_channels_download) | 桌面微信代理及播放数据读取；另有 sph Worker 部署。最新发布页显示 v260907，包含 Worker 凭证配置变更 | 桌面流程不能作为普通 APK 直接运行；短链服务流程可参考 |
| [oliver-zch/wx-video-channel-download](https://github.com/oliver-zch/wx-video-channel-download) | 源码通过已登录元宝解析短链，再向视频号请求媒体信息；提供下载和格式处理 | 适合参考接口流程，再用原生 Java 实现；不能直接照搬 Go 服务为 APK |
| [jianminggan/wechat-video-subtitle](https://github.com/jianminggan/wechat-video-subtitle) | 项目文档描述普通视频使用元宝浏览器登录；直播回放另需 Windows 微信播放记录 | 普通视频流程可参考；项目本身是电脑端 Python/Playwright 工具，尚未运行验证 |
| [cexll/wx-channels-skill](https://github.com/cexll/wx-channels-skill) | Python 客户端将短链发给在线解析服务，再下载返回的媒体 URL | 本身不独立解决解析；依赖服务在线及访问凭证 |
| [putyy/res-downloader](https://github.com/putyy/res-downloader) | 桌面代理抓取资源，文档包含视频号格式处理 | 电脑辅助路线，需证书、代理及实际播放；不能直接替代手机短链解析 |

## 已核对的源码

- [oliver 的 sph.go](https://github.com/oliver-zch/wx-video-channel-download/blob/main/internal/service/sph.go)：元宝请求、播放页参数及视频号媒体接口的数据流。
- [cexll 的下载脚本](https://github.com/cexll/wx-channels-skill/blob/main/scripts/wx_channels_download.py)：依赖在线解析端点，读取 H.264/H.265 媒体字段。
- [dys-cq 的双路径实现](https://github.com/dys-cq/video-extractor/blob/main/scripts/wechat_channels.py)：在线解析服务和元宝登录路径；仅作为源码参考，没有执行其脚本。
- [ltaoo 的 sph 部署文档](https://github.com/ltaoo/wx_channels_download/blob/main/docs/cli/sph.md)及[最新发布说明](https://github.com/ltaoo/wx_channels_download/releases)：自行部署服务需要 Cloudflare 配置和元宝登录状态，新版本还调整了凭证设置。

## 当前实测边界

1. 前一轮已用用户自己的三个分享短链读取正常公开预览数据，作者、标题和封面一致，没有公开视频 URL。
2. 前一轮对腾讯元宝解析端点做匿名测试，HTTP 401；没有登录后的成功结果。
3. 本轮仅用 cexll README 自带的公开示例测试在线 Worker，HTTP 401，返回 unauthorized。未向这个第三方服务提交用户的视频链接、账号或 Cookie。
4. 本轮没有安装、执行任何 GitHub 仓库的程序，没有修改系统证书、代理或用户登录配置。GitHub API 检索受限后改读仓库网页和原始源码。

## 推荐的后续验证顺序

先验证本机正常元宝登录会话是否能取得用户短链对应的播放页；取得后严格绑定原分享链接和目标作品，检查媒体地址及完整文件。验证成功再移植到 APK，复用现有下载、格式处理、取消删除及 MediaStore 相册发布。

第三方解析服务需要先证明可用性及凭证来源，适合作为明确选择的备用服务；不能依据旧脚本中的“无需登录”说明默认接入。当前 APK 仍为 v1.4.1。
