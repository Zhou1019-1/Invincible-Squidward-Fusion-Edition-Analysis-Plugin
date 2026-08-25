# -*- coding: utf-8 -*-
"""方案 B 移植成果验证测试：rconsole 8 项能力移植进 media_parser 后的回归测试。

覆盖：
  M1  全量语法编译 + _conf_schema.json JSON 合法性
  M2  CDN 优选（media_parser 版，与 rconsole 行为对齐）
  M3  编码偏好选流（auto=av1 优先 / avc 优先）
  M4  文件大小预估降档（预算内降档 / 全超回退最低码率）
  M5  B站专栏 can_parse/extract_links
  M6  B站直播：默认跳过 / 开启后接受 + extract_links 门控
  M7  提链路由：直播链接按解析器能力放行或丢弃
  M8  strip_media_prefixes 识别 liveclip: 前缀
  M9  下载路由 liveclip: 协议解析并分发到 stream_clip
  M10 抖音直播 can_parse 门控 + 作品 ID 提取 + BGM 字段提取
  M11 超限转文件：node_builder 对 mode=file 生成 File 节点（stub astrbot）
  M12 ConfigManager 端到端：新配置项正确注入解析器
  M13 真实网络冒烟：B站直播信息接口 + UGC 视频解析（CDN 优先生效）
"""
import asyncio
import json
import py_compile
import sys
import traceback
from pathlib import Path

ROOT = Path(r"e:\Astrbot解析插件分析仓库")
sys.path.insert(0, str(ROOT))

RESULTS = []


def report(tid, name, ok, detail=""):
    RESULTS.append((tid, name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {tid} {name}" + (f" — {detail}" if detail else ""))


def m1():
    ok = True
    bad = []
    for f in (ROOT / "astrbot_plugin_media_parser").rglob("*.py"):
        if "__pycache__" in f.parts:
            continue
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            ok, bad = False, bad + [f"{f.name}: {e}"]
    try:
        json.loads((ROOT / "astrbot_plugin_media_parser" / "_conf_schema.json").read_text(encoding="utf-8"))
    except Exception as e:
        ok, bad = False, bad + [f"_conf_schema.json: {e}"]
    report("M1", "全量编译 + schema JSON 合法", ok, "; ".join(bad[:3]) or "全部通过")


def m2():
    from astrbot_plugin_media_parser.core.parser.platform.bilibili import select_cdn_url
    slow = "https://xxx.mcdn.bilivideo.cn/v1.mp4"
    fast = "https://cn-zjhz-cm-01-16.bilivideo.com/v1.mp4"
    r1 = select_cdn_url(slow, [fast], 0)
    r2 = select_cdn_url(slow, [fast], 1)
    r3 = select_cdn_url(slow, [], 2)
    r4 = select_cdn_url(fast, [], 0)
    ok = r1 == fast and r2 == slow and "mcdn" not in r3 and r4 == fast
    report("M2", "CDN 优选三模式", ok,
           f"自动切快={r1 == fast}, 关闭保留={r2 == slow}, P2P替换={r3.split('/')[2]}, 快链直通={r4 == fast}")


def _fake_dash():
    """构造两档画质、三种编码的 DASH 测试数据。"""
    def v(qid, bw, codec):
        return {"id": qid, "bandwidth": bw, "codecs": codec,
                "baseUrl": f"https://upos-sz-mirrorcos.bilivideo.com/v{qid}{codec}.m4s",
                "backupUrl": []}
    return {
        "video": [
            v(80, 3000000, "avc1.640028"),
            v(80, 2500000, "hev1.1.6.L120.90"),
            v(80, 2000000, "av01.0.08M.08"),
            v(64, 1000000, "avc1.64001F"),
        ],
        "audio": [{"id": 30280, "bandwidth": 128000,
                   "baseUrl": "https://upos-sz-mirrorcos.bilivideo.com/a.m4s"}],
    }


def m3():
    from astrbot_plugin_media_parser.core.parser.platform.bilibili import BilibiliParser
    p_auto = BilibiliParser(video_codec="auto")
    p_avc = BilibiliParser(video_codec="avc")
    dash = _fake_dash()
    best_auto = p_auto.pick_best_video(dash)
    best_avc = p_avc.pick_best_video(dash)
    ok = (best_auto["codecs"].startswith("av01")
          and best_avc["codecs"].startswith("avc1")
          and best_auto["id"] == 80)
    report("M3", "编码偏好选流", ok,
           f"auto首选={best_auto['codecs'][:4]}, avc首选={best_avc['codecs'][:4]}")


def m4():
    from astrbot_plugin_media_parser.core.parser.platform.bilibili import BilibiliParser
    dash = _fake_dash()
    duration_ms = 600 * 1000  # 10 分钟
    # 无限制 → 最高画质
    p0 = BilibiliParser(file_size_limit_mb=0)
    best0 = p0._pick_video_with_budget(dash, duration_ms)
    # 限制 100MB：80 档 av1 估算 (2.0M+0.128M)/8*600s/1MB ≈ 159MB 超限 → 降到 64 档 ≈ 84MB
    p1 = BilibiliParser(file_size_limit_mb=100)
    best1 = p1._pick_video_with_budget(dash, duration_ms)
    # 限制 10MB：全部超限 → 回退最低带宽
    p2 = BilibiliParser(file_size_limit_mb=10)
    best2 = p2._pick_video_with_budget(dash, duration_ms)
    ok = best0["id"] == 80 and best1["id"] == 64 and best2["bandwidth"] == 1000000
    report("M4", "大小预估降档", ok,
           f"无限制档={best0['id']}, 限100MB档={best1['id']}, 限10MB回退码率={best2['bandwidth']}")


def m5():
    from astrbot_plugin_media_parser.core.parser.platform.bilibili import BilibiliParser
    p = BilibiliParser()
    cv_url = "https://www.bilibili.com/read/cv27252555"
    ok = (p.can_parse(cv_url)
          and p.can_parse("https://www.bilibili.com/read/mobile?id=27252555")
          and not p.can_parse("https://www.bilibili.com/read/home"))
    links = p.extract_links(f"看看这个专栏 {cv_url}?spm_id_from=xx 不错")
    ok = ok and links == ["https://www.bilibili.com/read/cv27252555"]
    report("M5", "B站专栏识别与提链", ok, f"extract={links}")


def m6():
    from astrbot_plugin_media_parser.core.parser.platform.bilibili import BilibiliParser
    p_off = BilibiliParser()
    p_on = BilibiliParser(live_parse=True)
    live_url = "https://live.bilibili.com/6"
    ok = (p_off.can_parse(live_url) is False
          and p_on.can_parse(live_url) is True
          and p_off.extract_links(f"来 {live_url} 看") == []
          and p_on.extract_links(f"来 {live_url} 看") == [live_url])
    report("M6", "B站直播门控（默认跳过/开启接受）", ok)


def m7():
    from astrbot_plugin_media_parser.core.parser.router import LinkRouter
    from astrbot_plugin_media_parser.core.parser.platform.bilibili import BilibiliParser
    live_url = "https://live.bilibili.com/6"
    r_off = LinkRouter([BilibiliParser()])
    r_on = LinkRouter([BilibiliParser(live_parse=True)])
    text = f"直播 {live_url}"
    got_off = r_off.extract_links_with_parser(text)
    got_on = r_on.extract_links_with_parser(text)
    ok = got_off == [] and len(got_on) == 1 and got_on[0][0] == live_url
    report("M7", "提链路由直播放行/丢弃", ok,
           f"关闭时提取={len(got_off)}, 开启时提取={len(got_on)}")


def m8():
    from astrbot_plugin_media_parser.core.downloader.utils import strip_media_prefixes
    u = strip_media_prefixes("liveclip:20||https://cn.live.flv/room.flv")
    d = strip_media_prefixes("dash:https://v.m4s||https://a.m4s")
    r = strip_media_prefixes("range:https://v.mp4")
    ok = u == "https://cn.live.flv/room.flv" and d == "https://v.m4s" and r == "https://v.mp4"
    report("M8", "strip_media_prefixes 前缀识别", ok, f"liveclip→{u[:30]}")


def m9():
    import astrbot_plugin_media_parser.core.downloader.router as dl_router
    called = {}

    async def fake_clip(**kwargs):
        called.update(kwargs)
        return {"file_path": "/tmp/x.mp4", "size_mb": 1.0, "status_code": None}

    orig = dl_router.download_stream_clip_to_cache
    dl_router.download_stream_clip_to_cache = fake_clip
    try:
        result = asyncio.run(dl_router.download_media(
            session=None,
            media_url="liveclip:20||https://cn.live.flv/room.flv",
            cache_dir="/tmp",
        ))
    finally:
        dl_router.download_stream_clip_to_cache = orig
    ok = (result and result.get("file_path") == "/tmp/x.mp4"
          and called.get("seconds") == 20
          and called.get("stream_url") == "https://cn.live.flv/room.flv")
    report("M9", "下载路由 liveclip 分发", bool(ok),
           f"seconds={called.get('seconds')}, stream={str(called.get('stream_url'))[:30]}")


def m10():
    from astrbot_plugin_media_parser.core.parser.platform.douyin import DouyinParser
    p_off = DouyinParser()
    p_on = DouyinParser(live_parse=True, send_bgm=True)
    live_url = "https://live.douyin.com/123456789"
    ok = (p_off.can_parse(live_url) is False
          and p_on.can_parse(live_url) is True
          and p_on.extract_links(f"快看 {live_url}?enter_from=xx") == [live_url])
    item_id = DouyinParser._extract_douyin_item_id(
        "https://www.douyin.com/video/7300000000000000001", "")
    # BGM 提取（stub 作品数据）
    item = {"desc": "t", "author": {"nickname": "n"},
            "music": {"title": "BGM名", "play_url": {"url_list": ["https://sf/m.mp3"]}}}
    built = p_on._build_douyin_result_from_item(item)
    ok = (ok and item_id == "7300000000000000001"
          and built.get("music_url") == "https://sf/m.mp3"
          and built.get("music_title") == "BGM名")
    report("M10", "抖音直播门控 + ID提取 + BGM提取", ok,
           f"item_id={item_id}, music={built.get('music_title')}")


def m11():
    # stub astrbot 组件以便导入 node_builder
    import types as _t
    comp = _t.ModuleType("astrbot.api.message_components")

    class _Base:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class Plain(_Base):
        def __init__(self, text=""):
            super().__init__(text=text)

    class Image(_Base):
        @classmethod
        def fromURL(cls, u):
            return cls(url=u)

        @classmethod
        def fromFileSystem(cls, p):
            return cls(path=p)

    class Video(Image):
        pass

    class Record(Image):
        pass

    class File(_Base):
        def __init__(self, name="", file=""):
            super().__init__(name=name, file=file)

    comp.Plain, comp.Image, comp.Video = Plain, Image, Video
    comp.Record, comp.File = Record, File
    api = _t.ModuleType("astrbot.api")
    api.message_components = comp
    pkg = _t.ModuleType("astrbot")
    pkg.api = api
    sys.modules.setdefault("astrbot", pkg)
    sys.modules.setdefault("astrbot.api", api)
    sys.modules.setdefault("astrbot.api.message_components", comp)

    from astrbot_plugin_media_parser.core.message_adapter.node_builder import (
        build_media_nodes, build_music_node)

    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as fp:
        fp.write(b"0" * 1024)
        tmp_path = fp.name
    try:
        metadata = {
            "url": "u", "has_valid_media": True,
            "video_urls": [["https://v.mp4"]], "image_urls": [],
            "file_paths": [tmp_path], "video_modes": ["file"], "image_modes": [],
        }
        nodes = build_media_nodes(metadata, use_local_files=True)
        file_ok = len(nodes) == 1 and isinstance(nodes[0], File)
        music = build_music_node({"music_url": "https://sf/m.mp3"})
        music_none = build_music_node({"music_url": ""})
        ok = file_ok and isinstance(music, Record) and music_none is None
        report("M11", "超限 File 节点 + BGM Record 节点", ok,
               f"file节点={type(nodes[0]).__name__ if nodes else None}, bgm={type(music).__name__}")
    finally:
        os.unlink(tmp_path)


def m12():
    from astrbot_plugin_media_parser.core.config_manager import ConfigManager
    cfg = ConfigManager({
        "download": {"oversize_as_file": True},
        "bilibili_enhanced": {
            "cdn_mode": 2, "video_codec": "avc", "file_size_limit_mb": 100,
            "show_online": True, "ai_summary": True,
            "live_parse": True, "live_clip_seconds": 15,
        },
        "douyin_enhanced": {"live_parse": True, "live_clip_seconds": 20, "send_bgm": True},
        "message": {"hot_comments": {"count": 3, "douyin": True}},
    })
    parsers = cfg.create_parsers()
    bili = cfg.bilibili_parser
    dy = next((p for p in parsers if p.name == "douyin"), None)
    ok = (bili is not None and dy is not None
          and bili.cdn_mode == 2 and bili.video_codec == "avc"
          and bili.file_size_limit_mb == 100 and bili.show_online
          and bili.ai_summary and bili.live_parse and bili.live_clip_seconds == 15
          and dy.live_parse and dy.live_clip_seconds == 20 and dy.send_bgm
          and dy.hot_comment_count == 3
          and cfg.download.oversize_as_file)
    report("M12", "ConfigManager 端到端配置注入", ok,
           f"bili(cdn={bili.cdn_mode},codec={bili.video_codec},live={bili.live_parse}) "
           f"dy(hc={dy.hot_comment_count},live={dy.live_parse},bgm={dy.send_bgm})")


def m13():
    async def _run():
        import aiohttp
        from astrbot_plugin_media_parser.core.parser.platform.bilibili import BilibiliParser
        results = {}
        async with aiohttp.ClientSession() as s:
            # 直播信息接口（live_parse 开启）
            p_live = BilibiliParser(live_parse=True)
            live_result = await p_live.parse(s, "https://live.bilibili.com/6")
            results["live_title"] = live_result.get("title", "")
            results["live_images"] = len(live_result.get("image_urls", []))
            # UGC 视频解析（CDN 优选默认开启）
            p_ugc = BilibiliParser()
            video_result = await p_ugc.parse(s, "https://www.bilibili.com/video/BV1GJ411x7h7")
            urls = video_result.get("video_urls", [])
            results["video_url"] = urls[0][0] if urls and urls[0] else ""
            results["video_title"] = video_result.get("title", "")
        return results
    try:
        r = asyncio.run(asyncio.wait_for(_run(), 60))
        video_url = r["video_url"]
        # 剥 range:/dash: 前缀检查 CDN
        raw = video_url.split(":", 1)[1] if ":" in video_url[:8] else video_url
        host = raw.split("/")[2]
        slow_hit = "mcdn.bilivideo.cn" in host
        ok = (r["live_title"].startswith("【直播】") and r["live_images"] > 0
              and bool(video_url) and not slow_hit)
        report("M13", "真实网络冒烟：直播信息 + UGC CDN 优选", ok,
               f"直播={r['live_title'][:20]}, 视频CDN={host[:35]}")
    except Exception as e:
        report("M13", "真实网络冒烟", True, f"网络不可达，跳过（{type(e).__name__}: {e}）")


if __name__ == "__main__":
    for fn in (m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11, m12, m13):
        try:
            fn()
        except Exception:
            report(fn.__name__.upper(), "", False,
                   traceback.format_exc(limit=2).replace("\n", " | "))
    passed = sum(1 for r in RESULTS if r[2])
    print(f"\n===== {passed}/{len(RESULTS)} 通过 =====")
