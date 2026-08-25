# 无敌章鱼哥融合版解析插件

> **本插件由 无敌章鱼哥 重制（Fusion Edition）**
> 在原 12 平台聚合解析插件的基础上，融合了 R 插件的 8 项独有能力，一个插件即可覆盖两大插件的全部功能。

一款 AstrBot 流媒体聚合解析插件：自动识别消息中的链接，解析为媒体直链并发送视频/图集/直播间信息。

## 功能总览

### 支持平台（12 个）

B站 · 抖音 · TikTok · 快手 · 微博 · 小红书 · 闲鱼 · 今日头条 · 小黑盒 · Steam · Twitter/X · Pixiv

### 融合新增能力（来自 R 插件）

| 能力 | 说明 | 配置项 |
|---|---|---|
| B站直播解析 | 直播间标题/分区/封面/直播状态，可选录制 FLV 片段发送 | `bilibili_enhanced.live_parse` / `live_clip_seconds` |
| B站专栏解析 | `read/cv` 专栏文章标题/作者/全部原图 | 随 B站解析器启用 |
| B站 AI 视频总结 | 官方 AI 摘要 + 分段大纲（需 Cookie） | `bilibili_enhanced.ai_summary` |
| B站在线人数 | 实时观看人数附加到简介 | `bilibili_enhanced.show_online` |
| B站 CDN 优选 | 自动避开慢速 mCDN / P2P 域名替换官方镜像 | `bilibili_enhanced.cdn_mode` |
| 编码偏好与降档 | av1/hevc/avc 选流偏好，按预估文件大小自动降画质 | `bilibili_enhanced.video_codec` / `file_size_limit_mb` |
| 抖音增强 | 热评、BGM 语音附带、直播间解析与片段录制 | `douyin_enhanced.*` / `hot_comments.douyin` |
| 超限转文件 | 超过大小限制的视频不再丢弃，作为文件消息发送 | `download.oversize_as_file` |

### 原有核心能力

- 每平台独立输出模式（全部/仅文本/仅富媒体/关闭）
- 消息聚合发送、LLM 翻译（OpenAI 兼容/Ollama）、文本元数据渲染为图片
- B站 Cookie 扫码登录与失效自动续期、番剧/动态/充电专属受限检测
- 解析结果导出 ZIP、媒体文件中转（跨服务器部署）、解析频率限制
- 直播片段录制采用 `liveclip:` 自定义协议，ffmpeg 转封装 MP4（无 ffmpeg 时保留 FLV）

## 安装

**方式一（推荐）**：AstrBot WebUI → 插件管理 → 安装插件 → 仓库地址填：

```
https://github.com/Zhou1019-1/Invincible-Squidward-Fusion-Edition-Analysis-Plugin
```

**方式二**：下载 Release/仓库 zip，在插件管理中本地上传安装。

依赖（安装时自动装）：`aiohttp`、`cryptography`、`qrcode[pil]`、`pillow`。直播片段录制/DASH 合并需要系统可用的 `ffmpeg`。

## 配置说明

所有融合新增能力**默认关闭**，在 WebUI 插件配置中按需开启：

- **B站增强**：CDN 优选模式（0 自动避慢 / 1 关闭 / 2 P2P 替换）、编码偏好、文件大小预估上限、在线人数、AI 总结、直播解析与录制秒数
- **抖音增强**：直播解析与录制秒数、BGM 附带发送；热评在「附加内容：热评」中开启抖音开关
- **下载与缓存**：超限视频转为文件发送

> AI 视频总结需要先在「携带 Cookie 解析」中配置有效 B站 Cookie；录制片段需配置可用的媒体缓存目录。

## 测试

`integration_test/` 内置两套可重复执行的受控测试：

- `run_tests.py`：两来源插件的签名算法一致性（WBI/SM3/a_bogus）、契约适配等 9 项
- `run_migration_tests.py`：融合后功能回归 13 项（CDN/编码/降档/直播门控/下载路由/配置注入/真实网络冒烟）

## 致谢与来源

本插件为融合重制版，站在两位原作者的肩膀上：

| 来源 | 原作者 | 仓库 |
|---|---|---|
| 主体框架：AstrBot 流媒体聚合解析插件 | **drdon1234** | [astrbot_plugin_media_parser](https://github.com/drdon1234/astrbot_plugin_media_parser) |
| 融合能力来源：R-plugin（Yunzai-Bot 插件） | **zhiyu1998** | [rconsole-plugin](https://github.com/zhiyu1998/rconsole-plugin) |

> 融合过程中参考了 R 插件的 AstrBot 移植版 `astrbot_plugin_rconsole`（作者 daphne）。

感谢原作者们的开源工作。若本插件对你有帮助，请同样去给原仓库点个 Star。

## 许可

遵循主体框架原作者的开源协议，详见 [LICENSE](LICENSE)。
