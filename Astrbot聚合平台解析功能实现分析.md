# astrbot_plugin_media_parser 解析功能实现分析

> 分析对象：`astrbot_plugin_media_parser` v1.1.0（https://github.com/drdon1234/astrbot_plugin_media_parser）
> 分析日期：2026-08-25
> 分析范围：插件内全部 12 个平台的链接解析实现，以及支撑解析的框架基础设施

---

## 目录

- [一、总架构：四层流水线](#一总架构四层流水线)
- [二、框架基础设施](#二框架基础设施)
- [三、各平台解析实现](#三各平台解析实现)
  - [3.1 B 站（bilibili）](#31-b-站bilibili)
  - [3.2 抖音（douyin）](#32-抖音douyin)
  - [3.3 TikTok](#33-tiktok)
  - [3.4 快手（kuaishou）](#34-快手kuaishou)
  - [3.5 微博（weibo）](#35-微博weibo)
  - [3.6 小红书（xiaohongshu）](#36-小红书xiaohongshu)
  - [3.7 今日头条（toutiao）](#37-今日头条toutiao)
  - [3.8 闲鱼（xianyu）](#38-闲鱼xianyu)
  - [3.9 小黑盒（xiaoheihe）](#39-小黑盒xiaoheihe)
  - [3.10 Steam](#310-steam)
  - [3.11 Twitter / X](#311-twitter--x)
  - [3.12 Pixiv](#312-pixiv)
- [四、横向对比与共性设计](#四横向对比与共性设计)

---

## 一、总架构：四层流水线

```
消息事件 → LinkRouter（提链/去重）→ ParserManager（并发解析）
→ DownloadManager（决策下载）→ NodeBuilder/Sender（构建发送）
```

| 层 | 文件 | 职责 |
|---|---|---|
| 入口调度 | `main.py` | 事件过滤、QQ 卡片提链、频率限制、建 session、触发解析/翻译/下载/发送 |
| 链接路由 | `core/parser/router.py` | 从文本提取链接、过滤直播、排序去重、匹配解析器 |
| 并发调度 | `core/parser/manager.py` | `asyncio.gather` 全并发解析、错误分类兜底 |
| 平台解析 | `core/parser/platform/*.py` | 12 个平台解析器，均继承 `BaseVideoParser` |
| 数据契约 | `core/types.py` | `MediaMetadata` TypedDict 贯穿解析→下载→发送全流程 |

关键约定：

- **一个 session 贯穿全程**：入口创建 `aiohttp.ClientSession(timeout=30s)`（`core/constants.py` 的 `DEFAULT_TIMEOUT`），解析与下载共享。
- **解析器抛出、管理器兜底**：`parse()` 失败直接抛异常；`ParserManager` 分类处理——`CancelledError` 重抛、`SkipParse`（直播等业务性跳过）静默丢弃、其他异常生成带 `error` 字段的占位元数据，**单链接失败绝不影响其他链接**。
- **多候选直链结构**：`video_urls`/`image_urls` 均为 `List[List[str]]`，每个媒体元素对应一组候选直链，下载时按序尝试。
- **协议前缀**：直链可加 `range:`（Range 分块下载）、`dash:`（DASH 音视频分离，`||` 分隔）、`m3u8:`（HLS）前缀，由下载层分流处理。
- **ID 一致性校验**：各平台普遍校验"接口返回的是不是请求的那个作品"，防止缓存/重定向导致串数据。

---

## 二、框架基础设施

### 2.1 BaseVideoParser 抽象基类（`core/parser/platform/base.py`）

三个核心接口：

| 方法 | 职责 |
|---|---|
| `can_parse(url) -> bool` | 纯判断"此 URL 是否归我解析"，供路由逐个询问 |
| `extract_links(text) -> List[str]` | 从消息文本提取本平台链接（含各平台正则、规范化、去重） |
| `parse(session, url) -> Optional[MediaMetadata]` | 核心解析，session 由调用方注入，失败抛异常 |

辅助方法 `_add_range_prefix_to_video_urls`：为视频直链统一加 `range:` 前缀，兼容 `dash:`（逐段加）和已带前缀的 URL（跳过）。

### 2.2 LinkRouter 链接路由（`core/parser/router.py`）

`extract_links_with_parser` 流程：

1. 遍历所有解析器调用 `extract_links`，单个解析器异常被隔离跳过；
2. 用 `is_live_url`（`core/parser/utils.py`）过滤直播域名链接；
3. 用 `text.find(link)` 定位链接在原文中的位置；若解析器把链接规范化导致原文找不到，则排到尾部追加，保证不丢失；
4. 按位置排序 + `seen_links` 集合去重，保留首次出现的 `(link, parser)` 对。

注意：**短链展开不在路由层**，而在各解析器 `parse` 内做（HEAD 跟随重定向，失败回退 GET）。

### 2.3 ParserManager 并发调度（`core/parser/manager.py`）

- 二次去重后，`asyncio.gather(*tasks, return_exceptions=True)` 全并发执行；
- 超时依靠入口 session 的 30s 总超时，Manager 内不单独实现；
- `_normalize_metadata` 为成功结果补齐 `platform`/`parser_name`/`source_url`；`_error_metadata` 为失败链接构造占位元数据，使失败也能进入统一展示流程。

### 2.4 MediaMetadata 数据契约（`core/types.py`）

`MediaMetadata(TypedDict, total=False)`，按产出阶段分三组：

- **解析阶段**（解析器产出）：`url`、`title`、`author`、`desc`、`timestamp`、`video_urls`、`image_urls`、`video_headers`、`image_headers`、`video_force_download`、`hot_comments`、`access_status`（受限/试看标记）、`use_*_proxy`、`proxy_url`、`error` 等；
- **下载阶段**（DownloadManager 回填）：`file_paths`、`video_sizes`、`has_valid_media`、`use_local_files`、各媒体状态码与跳过原因等；
- **中转阶段**（文件 Token 服务回填）：`use_file_token_service`、`file_token_urls`。

### 2.5 共享工具

- `core/parser/utils.py`：`build_request_headers`（区分图/视频两套默认头，支持 referer/UA 合并）、`is_live_url`（直播域名识别，含重定向 query 里嵌套的直播 URL）、`extract_url_from_card_data`（QQ 小程序卡片提取 `meta.detail_1.qqdocurl` / `meta.news.jumpUrl`）、`SkipParse` 异常。
- `core/parser/platform/short_video_shared.py`：`ShortVideoParserMixin`，提供域名后缀匹配、URL 清洗（剥离中英文尾随标点）、时间戳格式化、**嵌套 JSON 递归挖直链**（最深 4 层，按 `urlList/playAddr/downloadAddr` 等 19 个优先键）、**HTML 内嵌 JSON 提取**（`window._ROUTER_DATA` 大括号栈配平、按 script id 提取）、深度优先遍历。被抖音和 TikTok 复用。

---

## 三、各平台解析实现

### 3.1 B 站（bilibili）

文件：`core/parser/platform/bilibili.py`（约 2780 行，全插件最复杂）+ `core/parser/runtime_manager/bilibili/auth.py`（Cookie 运行时）+ `core/interaction/platform/bilibili/cookie_assist.py`（管理员协助登录）

**链接形式**（`can_parse` 按优先级匹配）：

- b23.tv 短链（GET 跟随重定向展开，失败静默返回原 URL）
- BV 号 / av 号（av 用本地 BV_TABLE + XOR 算法转 BV，失败退回 aid 调 API）
- 番剧 ep / ss（ss 通过 season 接口取首个 ep_id）
- opus 图文动态、t.bilibili.com 动态
- 裸 BV/av 号（检查前后 50 字符上下文，附近有 http 则跳过避免重复）
- QQ 小程序卡片（消息层提取，通常是 b23 短链）
- **显式拒绝**：直播（live.bilibili.com）、个人空间；域名信任校验仅接受 bilibili.com 及子域

**API 端点**：

| 端点 | 用途 |
|---|---|
| `x/web-interface/nav` | Cookie 校验 + 获取 WBI 密钥 |
| `x/web-interface/view` | UGC 视频元信息 |
| `x/player/pagelist` | 分 P 列表（取 cid） |
| `x/player/wbi/playurl` | UGC 播放地址（WBI 签名） |
| `pgc/player/web/v2/playurl` | PGC 番剧播放地址（未签名） |
| `pgc/view/web/season` | 番剧季度信息 / ep↔ss 互查 |
| `x/polymer/web-dynamic/v1/detail` | 动态/图文详情 |
| `x/v2/reply/wbi/main` | 热评（WBI 签名） |

**WBI 签名**：nav 接口取 `wbi_img` 的 img_key/sub_key → 按 64 位 `MIXIN_KEY_ENC_TAB` 重排表混排取前 32 字符得 mixin_key（带锁缓存 6 小时）→ 参数加 `wts` 时间戳、按 key 排序、过滤 `!'()*` → `md5(query + mixin_key)` 得 `w_rid`。

**画质三段式策略**（`FNVAL_MP4=1` / `FNVAL_DASH=4048`）：

1. 探测：`qn=120, fnval=4048`，从 `accept_quality` 选不超过用户上限的最大画质（兜底 qn=80）；
2. MP4 优先：以目标 qn + `fnval=1` 请求，有 `durl` 直接取单文件 MP4；
3. DASH 回退：无 durl 则 `fnval=4048`，按 `(画质id, 带宽)` 降序选流，拼自定义协议 `dash:{视频流}||{音频流}`，交下载器分离下载后合并。

**动态解析**：兼容两套结构——

- 新版 polymer：富文本节点拼正文、转发动态合并原作者信息（`转发内容 (原作者信息)`）、major 含视频时递归解析内嵌视频并合并元数据；图文兼容 `major.draw/opus/article/common` 四种形态；
- 旧版 card：`desc.type==8` 视频动态、`type==1 && orig_type==8` 转发视频动态，无视频按图文从 `item.pictures` 提取。

**热评**：`x/v2/reply/wbi/main`（WBI 签名，`mode=3` 热度排序），oid 视频用 aid（type=1）、动态优先从 opus 页面 HTML 的 `__INITIAL_STATE__` 提取 `comment_id_str/comment_type`（失败退回 `int(opus_id)`, type=17）；合并置顶+普通评论按 rpid 去重、点赞降序截取；**失败仅 warning，绝不影响主解析**。

**Cookie 体系**（auth.py + cookie_assist.py）：

- 凭据优先级：扫码登录的运行时凭据（持久化 JSON，原子写入 + chmod 600）> 配置静态 Cookie；
- 每次使用前 nav 接口校验（`code==-101` 判失效），带指纹缓存（有效 300s/无效 60s）；校验结果不确定（网络抖动）时**乐观放行**；
- 失效后自动降级游客模式，标记协助请求；每轮解析结束后触发管理员协助状态机：私聊管理员确认 → 本地 qrcode 库渲染二维码 PNG（避免泄露 token）→ 后台 2 秒轮询扫码结果 → 成功则原子安装新凭据并持久化；管理员也可主动发指令（默认 `B站更新Cookie`）触发。

**受限/试看检测**：综合 `need_vip/need_login/has_paid/PLAY_PREVIEW`、durl 累计时长 < 总时长等判断 `full / preview_only / restricted / unavailable`，结合 `is_upower_exclusive` 等标记给出"充电专属/大会员专享/付费专享/登录后可看"标签——不抛异常，返回元数据 + 可读提示。

### 3.2 抖音（douyin）

文件：`core/parser/platform/douyin.py`（业务层）+ `douyin_web.py`（传输层）+ `douyin_sign.py`（签名）

**链接形式**：`v.douyin.com` 短链、`/video|note|slides/{id}` 长链、19 位数字 ID 链接；5 组正则提取并按 `douyin:short/note/slides/video/item:` 前缀去重；短链 HEAD 跟随重定向展开（失败回退 GET）。

**主路径：Web 详情接口** `aweme/v1/web/aweme/detail/`，需要两样东西：

1. **ttwid 会话**：POST `ttwid.bytedance.com/ttwid/union/register/` 注册获取，asyncio.Lock 防并发重复注册，TTL 封顶 6 小时；401/403 或响应异常时强制刷新重试一次；
2. **a_bogus 签名**（douyin_sign.py，移植自开源项目 f2，gmssl 替换为内嵌纯 Python SM3）：
   - 参数和 body 各做"SM3(盐)+SM3(盐)"双重摘要；
   - UA 经 RC4 加密（密钥 `\x00\x01\x0e`）+ 自定义 base64 后入摘要——**UA 必须与请求实际 UA 一致**；
   - 混入随机浏览器指纹、起止时间戳、aid=6383 等，按固定表重排异或；
   - 3 组随机字节前缀 + 256 字节置换表混淆 + 自定义字母表（`Dkdpgh2ZmsQB80/...`）base64 编码输出。

**回退链**：签名接口 → iesdouyin slidesinfo 接口（图集专用，免签名）→ 分享页 HTML 提取 `window._ROUTER_DATA` → 全灭报错。

**元数据提取**：按 `aweme_id` 精确匹配目标作品（绝不拿推荐作品）；视频直链遍历 `play_addr/playAddr/download_addr/play_addr_h264/play_addr_265/bit_rate[]`，`uri` 字段拼 `/aweme/v1/play/?video_id=`；过滤畸形 play URL；支持视频/图集/**图文视频混排**（slides 内嵌视频）；下载头带 `Referer: https://www.douyin.com/`。

### 3.3 TikTok

文件：`core/parser/platform/tiktok.py`

**链接形式**：`vm/vt.tiktok.com` 短链、`/t/` 短链、`/@user/video|photo/{id}` 长链、`m.tiktok.com/v/{id}` 移动链；URL 校验防 SSRF（无用户名密码、仅 80/443 端口）。

**核心路径——不用第三方 API、不签名**：

1. **系统 curl 子进程抓页面**（刻意不用 aiohttp，因其 TLS/HTTP 指纹会触发 WAF）：`curl -L -sS --compressed`，用 `-w` 输出 `%{url_effective}` 拿最终落地 URL；最多重试 5 次，命中条件是 HTML 含 `__UNIVERSAL_DATA_FOR_REHYDRATION__` 或 `playAddr` 且不含 `Please wait...`（WAF 验证页特征）；子进程有超时强杀回收逻辑；
2. 从页面提取 `__UNIVERSAL_DATA_FOR_REHYDRATION__` 或 `SIGI_STATE`，优先取 `webapp.video-detail` 的 itemStruct，失败则全树 DFS 按 `id` 精确匹配——**URL 已给出作品 ID 时绝不回退到第一个作品**（"返回推荐作品比解析失败更危险"）；
3. oEmbed 仅作标题/作者补充和 ID 交叉验证（ID 不一致时丢弃 oEmbed 数据）。

**元数据**：视频取 `playAddr/downloadAddr/bitrateInfo[]`；图集取 `imagePostInfo`；作者拼 `昵称(@uid)`；display_url 用 uniqueId + itemId 重建规范链接。**全链路代理支持**（oEmbed/curl `-x`/aiohttp/下载透传）。

### 3.4 快手（kuaishou）

文件：`core/parser/platform/kuaishou.py`

**无签名、无需作品 ID**，纯移动端网页 HTML 解析（iPhone Safari UA）。

**链接处理**：`v.kuaishou.com` 短链手动取 302 Location（不自动跟随）；落地域名若不是 kuaishou.com（如 chenzhongtech），**改写到 `m.gifshow.com`**——因其 SSR 数据完整而 chenzhongtech 的 SSR 极其稀疏；直播落地页抛 SkipParse。

**四级提取链**：

1. `window.INIT_STATE` SSR JSON（兼容 `__APOLLO_STATE__`）：`photo.mainMvUrls` 含 mp4 为视频；`photo.type==1` 为图集，从 `ext_params.atlas`（可能双重 JSON 编码）取 cdnList/list/music，按"CDN × 图片路径"笛卡尔积拼多候选 URL；
2. 旧版正则直接搜 `"url|srcNoMark|photoUrl|videoUrl":"http....mp4"`；
3. `window.rawData` JSON；
4. 全灭报错。

**细节**：刻意保留 URL query 中的 CDN 防盗链签名参数；作者/文案不足时在整个 HTML 正则搜 `userName/caption` 兜底；时间戳可从媒体 URL 的 `/yyyy/mm/dd/` 路径或 13 位时间戳提取。无代理支持。

### 3.5 微博（weibo）

文件：`core/parser/platform/weibo.py`

**链接形式**：`weibo.com/{uid}/{bid}`、`weibo.cn/status/{id}`、`m.weibo.cn/detail/{id}`、`weibo.com/tv/show/{1034:xxx}`、`video.weibo.com/show?fid=`；SSRF 防护（拒绝凭据与非常用端口）。

**三条链路**（均需先获取访客 Cookie）：

1. 桌面 API：`GET weibo.com/ajax/statuses/show?id={bid}&isGetLongText=true`；
2. 移动页：抓 m.weibo.cn HTML 正则提取 `var $render_data = [...][0]` JSON；
3. 视频页：`POST weibo.com/tv/api/component`，body 传 `Component_Play_Playinfo: {oid}`。

**鉴权**：POST `visitor.passport.weibo.cn/visitor/genvisitor2` 拿访客 Cookie（缺 XSRF-TOKEN 则额外 GET weibo.com 补齐），请求带 `x-requested-with: XMLHttpRequest` + `x-xsrf-token` 头。

**元数据**：媒体从 `mix_media_info`（hd_url > stream_url_hd > stream_url）、`pic_infos`、`pics`（largest > original > large）、`page_info.media_info`、`video_info.video_details`（按清晰度 key 取最大）多字段汇总，最后按 URL 特征分离视频与图片；正文去 HTML 标签；**热评**走 `ajax/statuses/buildComments` 接口按点赞排序。

**风控**：ID 错配校验（数字 ID 比对 `id/idstr/mid`，否则比对 `mblogid/bid`；视频比对 `oid/fid`），返回别的作品直接拒绝；视频设 `video_force_download`（防盗链必须先下载）。

### 3.6 小红书（xiaohongshu）

文件：`core/parser/platform/xiaohongshu.py`

**链接形式**：`xhslink.com/cn` 短链（手动取 302 Location 展开）、`/explore/{id}`、`/discovery/item/{id}` 长链；移动端链接剔除 `source/xhsshare` 参数，PC 链接保留 `xsec_token`。

**抓取路径——不用 x-s/x-t 签名，不调 API**：直接 GET 笔记详情页（移动/PC UA 按链接类型选择），提取 `window.__INITIAL_STATE__`——正则失败用括号配对状态机兜底，`undefined` 替换为 `null` 再 json.loads。

**元数据**：兼容移动端 `noteData.data.noteData` 与 PC 端 `note.noteDetailMap` 两套路径；视频按编码优先级 `h264 > h265 > av1 > h266` 选流，同编码按分辨率/码率排序取最优 masterUrl；图集取 `urlDefault > url > infoList[WB_DFT]` 并过滤占位图域名；**热评不发额外请求，直接从 `__INITIAL_STATE__` 状态树挖掘**（多路径尝试 + 全树递归兜底，跳过子评论）。

**回退**：先试改写后的 `/explore/{id}`，失败回退原始 `/discovery/item` URL，全部失败才报错。

### 3.7 今日头条（toutiao）

文件：`core/parser/platform/toutiao.py`

**链接形式**：`/article|video/{id}`、`/w/{id}`（PC/移动）、`m.toutiao.com/is/` 短链（跟随重定向，最终 URL 无 ID 则从 HTML 的 canonical/og:url 提取规范链接）。

**抓取路径**：无 Cookie 无签名，Android 移动 UA 抓移动详情页，从 HTML 提取**百分号编码的内嵌状态 JSON**（`%7B...%7D` unquote 后必须含 `articleInfo` 且能 json.loads；兜底匹配 `sessionConfig` 开头的编码串）。

**视频直链**：从 `articleInfo.playAuthTokenV2` 取 base64 令牌，解码得 `GetPlayInfoToken`，调 `vod.bytedanceapi.com` 取播放信息，`PlayInfoList` 按 Bitrate 降序合并为一条媒体的多候选列表。

**特色**：文章图片会**反复刷新页面最多 5 次**（可配置），反复提取并合并图片候选 URL，以拿到更多可用 CDN 链对抗防盗链；`/w/{id}` 链接按是否存在 playAuthTokenV2 动态判定视频还是文章；ID 错配校验（`articleId/groupId/itemId` 多键比对）。无热评。

### 3.8 闲鱼（xianyu）

文件：`core/parser/platform/xianyu.py`

**链接形式**：`m.tb.cn/h.{短码}` 淘宝短链（从短页 HTML 正则提取 `window.location` / `var url = '...'` 跳转 URL）、`goofish.com/item` 商品长链；ID 从 `id/itemId/item_id` 参数或路径段提取（8-20 位纯数字）。

**阿里 MTop H5 签名**（`h5api.m.goofish.com/h5/mtop.taobao.idle.awesome.detail/1.0/`）：

1. 从 session Cookie Jar 读 `_m_h5_tk`，取下划线前缀作 token；
2. 没有 token 时先发空 sign 预热请求，让服务端下发 `_m_h5_tk`；
3. 签名：`sign = md5(f"{token}&{毫秒时间戳}&{appKey=34839810}&{data}")`；
4. 响应 `ret` 含 `FAIL_SYS_TOKEN` 时重新预热 + 重签重试一次。

**元数据**：图片三路合并（`itemDO.imageInfos`、`flowData.sections`、`shareInfoJsonString` 内嵌 JSON）；视频整树递归遍历收集键名含 `video/play/media/stream` 的 URL（一个商品最多一个视频，收集为同一媒体的多候选）；desc 拼装价格/运费/卖家城市/属性标签/商品描述；卖家昵称优先取未脱敏（不含 `***`）来源。ID 错配校验。无热评。

### 3.9 小黑盒（xiaoheihe）

文件：`core/parser/platform/xiaoheihe.py`（全插件签名最重）

**链接形式**：BBS 帖子（`/v3/bbs/app/api/web/share?link_id=`、`/bbs/link/{id}` 等）与游戏详情（`share_game_detail?appid=`、`/app/topic/game/{type}/{appid}`、`/games/detail/{appid}`）两大类。

**两套密码学组件**：

1. **hkey 签名**（`XiaoheiheSign`）：请求路径 + 时间戳（带 a-k 偏移表）+ 随机 nonce（大写 MD5），经字符表映射、三路交错、MD5、AES MixColumns 风格列混合、取模生成 hkey，连同 `_time`/`nonce` 作查询参数；
2. **数美设备指纹**（`XiaoheiheDevice`）：POST `fp-it.portal101.cn/deviceprofile/v4`，body 字段按规则用固定密钥 3DES-ECB 加密并混淆字段名（ua→bj、canvas→yk），gzip+base64 后用随机 pri_id 作 key 做 AES-CBC 加密；RSA 公钥加密 uid 得 `ep`；响应返回 `"B"+deviceId` 作为 Cookie `x_xhh_tokenid`。

**接口**：签名 GET `api.xiaoheihe.cn` + 固定参数（`os_type=web/app=heybox/version=999.0.4`）。游戏合并 `get_game_detail`（签名）与 `game_introduction`（不签名）两接口；BBS 走 `/bbs/app/link/tree`。

**风控**：返回 `lack_token` 或 `show_captcha` 时自动重新生成设备指纹与签名重试；游戏简介接口比对 steam_appid（支持前导零数字等价）；BBS 校验 link_id（纯数字时允许别名映射）。

**元数据**：游戏富文本拼装简介/类型/发布日期/开发商/评分/好评率/在线人数/价格史低/奖项；媒体来自 `screenshots[]`（movie 类型按扩展名分封面与视频）+ `about_the_game` HTML 内嵌 source/img；m3u8 链接加 `m3u8:` 前缀；BBS 帖子 `link.text` 是 JSON 数组按 html/text/img/video/gif 类型拼装。无热评。

### 3.10 Steam

文件：`core/parser/platform/steam.py`

**链接形式**：仅 `store.steampowered.com/app/{appid}`（1-12 位数字，严格校验 scheme/host/端口）。

**数据源**（配置切换）：

- 默认：官方 `store.steampowered.com/api/appdetails/`（免鉴权，强制 `l=schinese&cc=cn` 中国区中文）；响应严格校验（success=true、返回 appid 一致）；
- 备选：拼接小黑盒链接委托 `XiaoheiheParser`（API 失效时人工切换，非运行时自动回退）。

**元数据**：视频取 `movies[]` 的 `hls_h264`（加 `m3u8:` 前缀）/mp4/webm + 简介 HTML 内嵌 `<video><source>`；图片收 `header_image/capsule_image/screenshots[]/movies[].thumbnail`/简介 `<img>`；desc 拼装简介（HTML 转纯文本）/类型/发行日期/开发商/价格（含折扣）/支持语言。解析/图/视频三路独立代理开关。

### 3.11 Twitter / X

文件：`core/parser/platform/twitter.py`

**链接形式**：`twitter.com` / `x.com`（含子域、www/mobile 前缀）的 `/status/{数字ID}`。

**双路径**：

1. **主路径 FxTwitter 镜像 API**：`api.fxtwitter.com/status/{id}`，无鉴权，最多 3 次指数退避重试；4xx / 响应缺 tweet / ID 不匹配 → 直接失败不重试；网络错误 / 5xx 重试耗尽 → 回退；
2. **回退路径官方 Guest GraphQL**：硬编码公开 Web Bearer Token → POST `api.twitter.com/1.1/guest/activate.json` 拿 guest token → GET `twitter.com/i/api/graphql/.../TweetResultByRestId`（带 20 余项 features 开关）。

**元数据**：FxTwitter 路径正文按 `display_text_range` 裁剪、引用推文以"引用推文："段落合并进 desc；GraphQL 路径深度遍历找 `rest_id` 匹配节点，图片取 `media_url_https?name=orig` 原图，视频从 `video_info.variants` 筛 mp4 按码率降序选最高，长推文取 `note_tweet` 全文。视频设 `video_force_download` 并加 range 前缀。解析/图/视频三路独立代理（http/socks5）。

### 3.12 Pixiv

文件：`core/parser/platform/pixiv.py`

**链接形式**：`pixiv.net/artworks/{id}`、`/i/{id}`、`/en/artworks/{id}`（5-12 位数字，可省略 scheme）。

**API**：官方 Web Ajax 接口（非 App API，无需 OAuth）——`ajax/illust/{id}` 元信息 + `ajax/illust/{id}/pages?lang=zh` 多页列表；登录 Cookie（用户配置）+ Referer 防盗链（i.pximg.net 图片 CDN 必须带作品页 Referer）。

**元数据**：多页插画/漫画每页取 `original → regular → small` 候选回退；desc 由标签构成（英文翻译优先，`R-18` 归一为 `R18`，前 20 个拼 `#tag`），附加 `[R-18]/[R-18G]/[AI生成]` 限制标记；记录 `pixiv_illust_id/user_id/x_restrict/ai_type/sanity_level/page_count` 等专有字段。单一代理配置同时用于 API 与图片下载。

**风控**：显式识别 Cloudflare "Just a moment" 拦截页（提示 Cookie 可能失效），区分于普通错误；响应 `illustId` 一致性校验。

---

## 四、横向对比与共性设计

| 平台 | 数据源 | 鉴权/签名 | 短链 | 热评 | 风控对抗 |
|---|---|---|---|---|---|
| B 站 | 官方 API | WBI 签名 + Cookie | b23.tv 重定向 | reply/wbi/main（WBI 签名） | Cookie 失效自动降级 + 管理员扫码续期 |
| 抖音 | Web API | a_bogus（纯 Python SM3+RC4+自定义base64） | v.douyin.com HEAD→GET | 无 | ttwid 刷新重试，三级回退链 |
| TikTok | 官方页面 + oEmbed | 无 | vm/vt/t/ curl -L | 无 | 系统 curl 绕 WAF 指纹，重试 5 次 |
| 快手 | 移动网页 SSR | 无 | v.kuaishou.com 手动 302 | 无 | 域名改写 m.gifshow.com，四级提取链 |
| 微博 | ajax API + HTML | 访客 Cookie + XSRF-TOKEN | 不支持 | buildComments API | ID 错配校验 |
| 小红书 | 页面 `__INITIAL_STATE__` | 无 | xhslink 手动 302 | 页面状态树挖掘 | explore/discovery 双 URL 回退 |
| 今日头条 | 页面状态 JSON + VOD API | playAuthTokenV2 base64 令牌 | /is/ 重定向 + canonical | 无 | 多次刷新收集图片 CDN 候选 |
| 闲鱼 | MTop H5 API | `_m_h5_tk` + MD5 签名 | m.tb.cn 短页正则 | 无 | 令牌失效重签重试 |
| 小黑盒 | 签名 API | hkey + 数美 3DES/AES/RSA 设备指纹 | 不支持 | 无 | lack_token/show_captcha 自动重试 |
| Steam | 官方 store API | 无 | 无短链 | 无 | 可配置切换小黑盒数据源 |
| Twitter/X | FxTwitter → Guest GraphQL | Bearer + guest token（回退路径） | 无短链 | 无 | 指数退避 + 双路径回退 |
| Pixiv | 官方 ajax API | Cookie + Referer | 无短链 | 无 | Cloudflare 拦截页显式识别 |

**共性设计**：

1. **多候选直链**：所有解析器返回 `List[List[str]]` 结构，每个媒体配一组候选链 + 配套下载头（UA/Referer 防盗链），下载层按序尝试；
2. **ID 一致性校验**：普遍实现"接口返回了别的作品"的检测（B站/抖音/TikTok/微博/头条/闲鱼/小黑盒/Pixiv），宁失败不串数据；
3. **失败隔离**：热评等附加能力失败仅 warning，绝不拖垮主链路；单链接失败不影响同批其他链接；
4. **细粒度代理**：TikTok/Twitter/Steam/Pixiv/小黑盒支持解析/图片/视频三路独立代理开关；
5. **并发限流**：各解析器内用 `asyncio.Semaphore(Config.PARSER_MAX_CONCURRENT)` 限流（Manager 层无全局上限）；
6. **显式跳过**：直播域名统一由 `is_live_url` 识别并抛 `SkipParse` 静默跳过。
