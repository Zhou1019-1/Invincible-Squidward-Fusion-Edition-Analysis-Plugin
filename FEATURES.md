# 功能介绍与使用说明

> 无敌章鱼哥融合版解析插件（Fusion Edition）
> 主体框架来自 drdon1234 的 `astrbot_plugin_media_parser`，融合了 zhiyu1998 的 `rconsole-plugin`（R 插件）8 项能力。
> 每个功能下标注了来源：【媒体解析】= 原聚合解析插件，【R 插件】= rconsole-plugin 移植。

## 目录

- [触发方式](#触发方式)
- [各平台解析用法](#各平台解析用法)
  - [B站](#b站)
  - [抖音](#抖音)
  - [TikTok](#tiktok)
  - [快手](#快手)
  - [微博](#微博)
  - [小红书](#小红书)
  - [闲鱼](#闲鱼)
  - [今日头条](#今日头条)
  - [小黑盒](#小黑盒)
  - [Steam](#steam)
  - [Twitter / X](#twitter--x)
  - [Pixiv](#pixiv)
- [融合增强功能（来自 R 插件）](#融合增强功能来自-r-插件)
- [通用能力](#通用能力)
- [功能来源总表](#功能来源总表)

---

## 触发方式

| 方式 | 用法 | 配置项 |
|---|---|---|
| 自动解析 | 群里/私聊直接发送含链接的消息，插件自动识别并解析 | `trigger.auto_parse`（默认开） |
| 关键词触发 | 关闭自动解析后，消息含关键词才解析，如「视频解析 <链接>」 | `trigger.keywords`（默认：视频解析 / 解析视频） |
| 回复触发 | 引用一条含链接的消息，回复关键词即可解析 | `trigger.reply_trigger` |
| ZIP 归档 | 引用含链接的消息，单独发送自定义归档命令，把解析详情和媒体打包成 ZIP | `message.archive.command` |
| 清理缓存 | 管理员发送「清理媒体」清除所有媒体缓存 | `admin.clean_cache_keyword` |
| 更新 B站 Cookie | 管理员私聊发送「B站更新Cookie」，扫码重新登录 | `bilibili_enhanced.admin_assist.command` |

每个平台可在 `parsers.*` 单独设置输出模式：**全部发送 / 仅文本 / 仅富媒体 / 关闭**。

---

## 各平台解析用法

### B站

**来源：【媒体解析】为主体，直播/专栏/AI总结/在线人数/CDN优选/编码降档来自【R 插件】**

支持的链接：

- 视频：`bilibili.com/video/BV...`、`av...`、短链 `b23.tv/...`
- 番剧：`bilibili.com/bangumi/play/ep...` / `ss...`
- 动态：`t.bilibili.com/...`、`bilibili.com/opus/...`（图片动态、视频动态、转发视频均支持）
- 直播：`live.bilibili.com/...`（需开启直播解析，见[融合增强功能](#融合增强功能来自-r-插件)）
- 专栏：`bilibili.com/read/cv...`（见融合增强功能）

能解析出：标题、作者、发布时间、简介、封面、视频（含分 P）、动态图片、热评。

用法要点：

1. 直接发链接即可；番剧遇会员/地区/付费限制时会提示受限原因。
2. 在「B站增强 → 携带 Cookie 解析」填入 Cookie 可获得更高画质；`max_quality` 可限制最高画质（4K ~ 360P）。
3. 开启「管理员协助登录」后，Cookie 失效会自动私聊管理员，扫码完成续期。
4. 热评：「附加内容：热评」中把条数设为大于 0 并打开 B站开关。

### 抖音

**来源：【媒体解析】为主体，直播解析/BGM 附带/热评来自【R 插件】**

支持的链接：

- 短链 `v.douyin.com/...`
- 视频 `douyin.com/video/...`、图文笔记 `/note/...`、混排 slides `/slides/...`
- 直播 `live.douyin.com/...`（需开启，见融合增强功能）

能解析出：无水印视频、图集图片、标题、作者、发布时间、简介。

用法要点：

1. 直接发分享链接或口令中的链接即可。
2. 热评在「附加内容：热评」中开启抖音开关（来自 R 插件）。
3. BGM 附带：开启 `douyin_enhanced.send_bgm` 后，视频/图集的背景音乐会以语音消息一并发送（来自 R 插件）。

### TikTok

**来源：【媒体解析】**

支持的链接：`tiktok.com/@用户/video/...`、短链 `vm.tiktok.com/...`、`vt.tiktok.com/...`

能解析出：视频、图集、标题、作者。

用法要点：国内网络需在「代理设置」填代理地址并打开 `proxy.tiktok` 开关。

### 快手

**来源：【媒体解析】**

支持的链接：短链 `v.kuaishou.com/...`、`kuaishou.com/...`、`gifshow.com/...`、`chenzhongtech.com/...`

能解析出：视频、完整图集（多图）、标题、作者。

### 微博

**来源：【媒体解析】**

支持的链接：

- 桌面链接 `weibo.com/...`
- 移动链接 `m.weibo.cn/...`
- 视频页 `video.weibo.com/show/...`、`weibo.com/tv/show/...`

能解析出：视频、图片（含 GIF）、正文、作者；热评可在「附加内容：热评」中开启。

### 小红书

**来源：【媒体解析】**

支持的链接：短链 `xhslink.com/...` / `xhslink.cn/...`、笔记页 `xiaohongshu.com/...`

能解析出：无水印视频（优先 H.264 高画质）、图文图片、正文、作者；热评可在「附加内容：热评」中开启。

### 闲鱼

**来源：【媒体解析】**

支持的链接：短链 `m.tb.cn/...`、商品页 `h5.m.goofish.com/item...`、`www.goofish.com/item...`

能解析出：商品标题、价格、正文、卖家昵称、商品图片；商品带视频时一并解析（一个商品最多一个视频）。

### 今日头条

**来源：【媒体解析】**

支持的链接：

- 文章/视频页 `www.toutiao.com/article|video/...`
- 微头条 `m.toutiao.com/w/...`
- 短链 `m.toutiao.com/is/...`
- QQ 小程序卡片（自动从卡片提取链接）

能解析出：文章正文与插图、微头条图文、视频（多码率候选）、标题、来源、发布时间。

### 小黑盒

**来源：【媒体解析】**

支持的链接：

- 帖子 `xiaoheihe.cn` BBS/link 分享链接
- 游戏详情页 `share_game_detail?appid=...`、`/app/topic/game/...`

能解析出：帖子正文（富文本转纯文本）、图片、视频；游戏页的评分、价格、标签、在线人数、截图和预览视频。

### Steam

**来源：【媒体解析】**

支持的链接：`store.steampowered.com/app/{appid}/...`

能解析出：游戏标题、简介、发行日期、开发商/发行商、价格、截图、预告片视频。

用法要点：

- 开启 `steam.use_xiaoheihe` 后改走小黑盒接口，额外获得小黑盒评分、实时在线人数、销量排行、平均游戏时间。
- 国内网络可在 `proxy.steam` 分别控制解析/图片/视频是否走代理。

### Twitter / X

**来源：【媒体解析】**

支持的链接：`twitter.com/.../status/...`、`x.com/.../status/...`

能解析出：推文正文（长文优先）、作者、图片原图、视频/动图（高质量 MP4）、引用推文内容。

用法要点：优先走 FxTwitter 公共接口，服务不可用时回退官方 Guest GraphQL；国内网络需配置 `proxy.twitter`。

### Pixiv

**来源：【媒体解析】**

支持的链接：`pixiv.net/artworks/{id}`、`pixiv.net/i/{id}`（含 `/en/` 前缀）

能解析出：插画标题、作者、标签（含 R-18 / AI 生成标记）、多页原图（原图失败自动降级分辨率）。

用法要点：

- 公开作品无需 Cookie；登录/年龄限制作品需在 `pixiv.cookie` 填含 `PHPSESSID` 的完整 Cookie。
- 国内网络需开启 `proxy.pixiv`；图片必须经本地缓存后发送。

---

## 融合增强功能（来自 R 插件）

以下 8 项能力移植自 zhiyu1998 的 rconsole-plugin，**默认全部关闭**，在 WebUI 插件配置中按需开启。

### 1. B站直播解析

- 配置：`bilibili_enhanced.live_parse`（开）、`live_clip_seconds`（录制秒数）
- 用法：发送 `live.bilibili.com/房间号` 链接，返回直播间标题、分区、主播、封面和直播状态；`live_clip_seconds` 设大于 0（建议 10–30）且直播进行中时，额外录制指定秒数的直播片段发送（有 ffmpeg 自动转 MP4，否则发 FLV）。
- 关闭时直播链接保持跳过，不影响其他 B站解析。

### 2. B站专栏解析

- 配置：随 B站解析器启用，无独立开关。
- 用法：发送 `bilibili.com/read/cv...` 链接，返回专栏标题、作者和全部原图。

### 3. B站 AI 视频总结

- 配置：`bilibili_enhanced.ai_summary`（开），**前置条件**：已开启「携带 Cookie 解析」且 Cookie 有效。
- 用法：解析 B站视频时自动调用 B站官方 AI 总结接口，在简介后附加摘要与分段大纲。

### 4. B站实时在线人数

- 配置：`bilibili_enhanced.show_online`（开）
- 用法：解析视频时在简介中附加当前正在观看的人数。

### 5. B站 CDN 优选

- 配置：`bilibili_enhanced.cdn_mode`
  - `0` = 自动避开慢速 mCDN（推荐）
  - `1` = 关闭优选
  - `2` = 将 P2P/慢速域名替换为官方镜像域名
- 用法：开启后下载 B站视频自动挑选可用高速 CDN，解决部分 mCDN/P2P 节点极慢或超时的问题。

### 6. 编码偏好与自动降档

- 配置：`bilibili_enhanced.video_codec`（auto/av1/hevc/avc）、`file_size_limit_mb`（预估上限 MB，0 不限）
- 用法：同画质下按编码偏好选 DASH 流（av1 体积更小；老设备兼容性差选 avc）；设置大小上限后，按「码率 × 时长」预估文件大小，超限自动降低画质档位，避免视频过大发不出去。

### 7. 抖音增强

- 直播解析：`douyin_enhanced.live_parse` + `live_clip_seconds`，用法同 B站直播（发送 `live.douyin.com/...` 链接）。
- BGM 附带：`douyin_enhanced.send_bgm` 开启后，作品背景音乐以语音消息发送。
- 热评：`hot_comments.douyin`（条数需大于 0）。

### 8. 超限转文件

- 配置：`download.oversize_as_file`（开）
- 用法：超过 `max_video_size_mb` 的视频原本会被丢弃，开启后仍会下载并作为**文件消息**发送，需要可用的媒体缓存目录。

---

## 通用能力

**来源：【媒体解析】**（除特别标注外）

- **每平台输出模式**：全部发送 / 仅文本 / 仅富媒体 / 关闭，互不影响。
- **文本元数据控制**：标题、作者、时间、原始链接、简介均可单独开关；可设置只让文本引用用户消息。
- **文本渲染为图片**：`render_to_image` 开启后，摘要、热评、翻译合并渲染成一张图发送，支持 4 种风格、5 种字体、字号 16–42。
- **视频仅发封面**：`video_cover_only` 开启后不发视频，改发封面或截取首帧（需 ffmpeg）。
- **热评**：支持 B站 / 微博 / 小红书 / 抖音（抖音热评来自【R 插件】），按点赞排序。
- **消息聚合**：合并转发发送，支持「不聚合 / 全部聚合 / 按条件聚合」（按图片数、视频数、节点数阈值触发）；NapCat 兼容性按需开启。
- **LLM 翻译**：翻译标题/正文为 10 种目标语言；可用 AstrBot 内置提供商，也可自定义 OpenAI 兼容接口（DeepSeek、Kimi、通义、GLM、豆包、OpenRouter、SiliconFlow、Ollama 等预设）。翻译失败不影响媒体解析。
- **下载控制**：最大并发、视频大小上限（预检 + 下载后兜底）、大视频单独发送阈值。
- **媒体中转**：Bot 与消息平台跨服务器部署时，由 AstrBot HTTP 服务中转本地缓存媒体，可配回调地址和有效期。
- **权限控制**：管理员 ID + 用户/群组黑白名单，优先级：管理员 > 个人白名单 > 个人黑名单 > 群组白名单 > 群组黑名单。
- **解析频率限制**：同链接、同用户两个维度的时间窗限流，记录持久化并自动裁剪。
- **代理**：按平台独立开关（TikTok、小黑盒视频、Steam、Pixiv、Twitter），支持 http/socks5。
- **调试模式**：`admin.debug` 输出完整工作流日志。

---

## 功能来源总表

| 功能 | 来源 |
|---|---|
| 12 平台聚合解析框架（B站/抖音/TikTok/快手/微博/小红书/闲鱼/头条/小黑盒/Steam/Twitter/Pixiv） | [astrbot_plugin_media_parser](https://github.com/drdon1234/astrbot_plugin_media_parser)（drdon1234） |
| 输出模式、消息聚合、ZIP 归档、LLM 翻译、文本渲染图片、媒体中转、权限、限流、代理 | 同上 |
| B站 Cookie 扫码登录与失效续期、番剧/动态/受限检测 | 同上 |
| B站直播解析与片段录制 | [rconsole-plugin](https://github.com/zhiyu1998/rconsole-plugin)（zhiyu1998） |
| B站专栏解析 | 同上 |
| B站 AI 视频总结 | 同上 |
| B站实时在线人数 | 同上 |
| B站 CDN 优选 | 同上 |
| 编码偏好与按大小自动降档 | 同上 |
| 抖音直播解析与片段录制、BGM 附带、抖音热评 | 同上 |
| 超限视频转文件发送 | 同上 |

> 融合过程中参考了 R 插件的 AstrBot 移植版 `astrbot_plugin_rconsole`（作者 daphne）。
