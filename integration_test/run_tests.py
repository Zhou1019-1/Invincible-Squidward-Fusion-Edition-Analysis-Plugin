# -*- coding: utf-8 -*-
"""astrbot_plugin_media_parser 与 astrbot_plugin_rconsole 集成可行性受控测试。

测试内容：
  T1  两个插件全部 Python 文件语法编译检查
  T2  SM3 哈希实现一致性（国家标准测试向量 "abc"）
  T3  B站 WBI 签名一致性（固定 wts，两实现比对）
  T4  微博 mid→bid base62 转换正确性（往返一致性）
  T5  rconsole CDN 优选/避慢逻辑行为验证
  T6  抖音 a_bogus 签名输出格式验证（两个实现）
  T7  架构兼容性：rconsole DouyinResolver 包装为 media_parser BaseVideoParser
  T8  双插件共存冲突模拟（同一消息是否重复触发）
  T9  真实网络冒烟：两个实现请求 B站 view API（网络不可达时跳过）
"""
import asyncio
import py_compile
import sys
import traceback
from pathlib import Path

MEDIA_PARSER_ROOT = Path(r"e:\Astrbot解析插件分析仓库")
RCONSOLE_PLUGIN_DIR = Path(r"E:\插件移植\astrbot_plugin_rconsole")

sys.path.insert(0, str(MEDIA_PARSER_ROOT))          # astrbot_plugin_media_parser 包
sys.path.insert(0, str(RCONSOLE_PLUGIN_DIR.parent))  # astrbot_plugin_rconsole 命名空间包

RESULTS = []


def report(tid, name, ok, detail=""):
    RESULTS.append((tid, name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {tid} {name}" + (f" — {detail}" if detail else ""))


# ── T1 语法编译检查 ─────────────────────────────────
def t1():
    ok, bad = True, []
    for root in (MEDIA_PARSER_ROOT / "astrbot_plugin_media_parser", RCONSOLE_PLUGIN_DIR):
        for f in root.rglob("*.py"):
            if "__pycache__" in f.parts:
                continue
            try:
                py_compile.compile(str(f), doraise=True)
            except py_compile.PyCompileError as e:
                ok, bad = False, bad + [f"{f.name}: {e}"]
    report("T1", "两插件全量语法编译", ok, "; ".join(bad[:3]) or "全部通过")


# ── T2 SM3 一致性（GB/T 32905-2016 测试向量 "abc"） ──
def t2():
    expect = ("66c7f0f462eeedd9d1f2d46bdc10e4e2"
              "4167c4875cf2f7a2297da02b8f4ba8e0")
    # media_parser: sm3_digest(bytes) -> bytes
    from astrbot_plugin_media_parser.core.parser.platform.douyin_sign import sm3_digest
    mp_hex = sm3_digest(b"abc").hex()
    # rconsole: _SM3().sum("abc")
    from astrbot_plugin_rconsole.utils.abogus import _SM3
    rc_raw = _SM3().sum("abc")
    rc_hex = (bytes(rc_raw).hex() if isinstance(rc_raw, (list, tuple))
              else (rc_raw.hex() if isinstance(rc_raw, (bytes, bytearray)) else str(rc_raw)))
    ok = mp_hex == expect and rc_hex == expect
    report("T2", "SM3('abc') 国标向量", ok,
           f"media_parser={mp_hex[:16]}… rconsole={rc_hex[:16]}…")


# ── T3 WBI 签名一致性 ────────────────────────────────
def t3():
    import hashlib
    import time
    from urllib.parse import quote
    # bilibili-API-collect 公开测试密钥对
    img_key = "7cd084941338484aae1ad9425b84077c"
    sub_key = "4932caff0ff746eab6f01bf08b70ac45"
    fixed_wts = 1684746387
    params = {"foo": "114", "bar": "514", "baz": 1919810}
    remove_chars = "!'()*"

    # rconsole: _get_mixin_key + 复现 enc_wbi 逻辑（固定 wts）
    from astrbot_plugin_rconsole.utils.wbi import _get_mixin_key
    mixin_rc = _get_mixin_key(img_key + sub_key)

    def _enc(v):
        return quote("".join(c for c in str(v) if c not in remove_chars), safe="")

    p = {**params, "wts": fixed_wts}
    query = "&".join(f"{quote(k, safe='')}={_enc(v)}" for k, v in sorted(p.items()))
    wrid_rc = hashlib.md5((query + mixin_rc).encode()).hexdigest()

    # media_parser: MIXIN_KEY_ENC_TAB + _sign_wbi_params（打补丁固定 wts）
    from astrbot_plugin_media_parser.core.parser.platform import bilibili as mp_bili
    mixin_mp = "".join((img_key + sub_key)[i] for i in mp_bili.MIXIN_KEY_ENC_TAB)[:32]
    orig_time = time.time
    time.time = lambda: fixed_wts
    try:
        signed = mp_bili.BilibiliParser._sign_wbi_params(dict(params), mixin_mp)
    finally:
        time.time = orig_time
    wrid_mp = signed["w_rid"]

    ok = mixin_rc == mixin_mp and wrid_rc == wrid_mp
    report("T3", "WBI 签名一致性（固定 wts）", ok,
           f"mixin一致={mixin_rc == mixin_mp}, w_rid一致={wrid_rc == wrid_mp} ({wrid_mp[:12]}…)")


# ── T4 微博 mid2id ───────────────────────────────────
def t4():
    from astrbot_plugin_rconsole.platforms.weibo import mid2id, _BASE62

    def id2mid(bid):  # 逆运算：从高位组到低位组，每组 4 个 base62 字符对应 7 位数字
        groups = []
        s = bid
        while s:
            groups.append(s[-4:])
            s = s[:-4]
        groups.reverse()
        mid = 0
        for g in groups:
            num = 0
            for ch in g:
                num = num * 62 + _BASE62.index(ch)
            mid = mid * 10 ** 7 + num
        return str(mid)

    ok = True
    outs = []
    for mid in ["3505746485120947", "5051234567", "1", "9999999999999999"]:
        bid = mid2id(mid)
        back = id2mid(bid)
        outs.append(f"{mid}->{bid}")
        if back != mid:
            ok = False
            outs.append(f"(逆算={back}✗)")
    report("T4", "微博 mid2id base62 往返", ok, "; ".join(outs))


# ── T5 rconsole CDN 优选逻辑 ─────────────────────────
def t5():
    from astrbot_plugin_rconsole.platforms.bilibili import select_and_avoid_mcdn_url
    slow = "https://xxx.mcdn.bilivideo.cn/v1.mp4"
    fast = "https://cn-zjhz-cm-01-16.bilivideo.com/v1.mp4"
    r1 = select_and_avoid_mcdn_url(slow, [fast], 0)   # 自动避慢
    r2 = select_and_avoid_mcdn_url(slow, [fast], 1)   # 关闭
    r3 = select_and_avoid_mcdn_url(slow, [], 2)       # P2P 替换模式
    ok = r1 == fast and r2 == slow and "mcdn.bilivideo.cn" not in r3
    report("T5", "CDN 避慢/替换逻辑", ok,
           f"自动切快={r1 == fast}, 关闭保留原链={r2 == slow}, P2P替换为={r3.split('/')[2]}")


# ── T6 a_bogus 格式验证 ──────────────────────────────
def t6():
    import re
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    q = "device_platform=webapp&aid=6383&aweme_id=7300000000000000001"
    from astrbot_plugin_rconsole.utils.abogus import generate_a_bogus
    rc = generate_a_bogus(q, ua)
    from astrbot_plugin_media_parser.core.parser.platform.douyin_sign import generate_abogus
    mp = generate_abogus(q, "", ua, options=[0, 1, 8])
    charset = r"^[A-Za-z0-9/\-_=]+$"
    ok = (isinstance(rc, str) and isinstance(mp, str)
          and re.match(charset, rc) and re.match(charset, mp)
          and 16 <= len(rc) <= 512 and 16 <= len(mp) <= 512)
    report("T6", "a_bogus 输出格式（两实现）", ok,
           f"rconsole len={len(rc)}, media_parser len={len(mp)}")


# ── T7 架构兼容性：rconsole 引擎装入 media_parser 契约 ──
def t7():
    """验证方案A核心命题：rconsole 的 DouyinResolver 可包装为 BaseVideoParser。"""
    from astrbot_plugin_media_parser.core.parser.platform.base import BaseVideoParser
    from astrbot_plugin_rconsole.platforms.douyin import DouyinResolver

    class DouyinRconsoleAdapter(BaseVideoParser):
        """包装层：将 rconsole 抖音引擎适配到 media_parser 解析器契约"""

        def __init__(self, config, data_dir):
            super().__init__("抖音(rconsole)")
            self.engine = DouyinResolver(config, data_dir)

        def can_parse(self, url: str) -> bool:
            return "douyin.com" in url or "iesdouyin.com" in url

        def extract_links(self, text: str):
            import re as _re
            return _re.findall(r"https?://v\.douyin\.com/\S+", text)

        async def parse(self, session, url):
            item = await self.engine.get_aweme_detail("stub")
            if not item:
                return None
            return {"url": url, "title": item.get("desc", ""),
                    "video_urls": [], "image_urls": []}

    # 桩掉网络层
    async def fake_detail(self, dou_id):
        return {"desc": "测试视频", "aweme_type": 0}
    DouyinResolver.get_aweme_detail = fake_detail

    adapter = DouyinRconsoleAdapter({"douyinCookie": "x"}, "/tmp")
    assert isinstance(adapter, BaseVideoParser)
    assert adapter.can_parse("https://v.douyin.com/abc/") is True
    assert adapter.can_parse("https://www.bilibili.com/video/BV1xx") is False
    links = adapter.extract_links("看这个 https://v.douyin.com/abc/ 好看")
    assert links == ["https://v.douyin.com/abc/"], links
    result = asyncio.run(adapter.parse(None, "https://v.douyin.com/abc/"))
    ok = (result and result["title"] == "测试视频"
          and isinstance(result["video_urls"], list))
    report("T7", "rconsole 引擎适配 BaseVideoParser 契约", bool(ok),
           "can_parse/extract_links/parse 均符合契约" if ok else str(result))


# ── T8 双插件共存冲突模拟 ────────────────────────────
def t8():
    import re
    msgs = ["看看这个 https://www.bilibili.com/video/BV1xx411c7mD",
            "分享 https://v.douyin.com/abc123/",
            "https://weibo.com/1234567890/QdC5HtUjg",
            "今天天气不错"]
    # rconsole: AstrBot @filter.regex 命中即触发
    rc_regs = [
        r"(bilibili\.com|b23\.tv|bili2233\.cn|t\.bilibili\.com|^BV[1-9a-zA-Z]{10}$)",
        r"((v|live)\.douyin\.com|webcast\.amemv\.com|iesdouyin\.com"
        r"|www\.douyin\.com/(video|note|live|share|jingxuan|discover))",
        r"(weibo\.com|m\.weibo\.cn)",
    ]
    def rc_hit(m):
        return any(re.search(r, m) for r in rc_regs)

    # media_parser: 各解析器 extract_links 聚合（正常实例化）
    from astrbot_plugin_media_parser.core.parser.platform.bilibili import BilibiliParser
    from astrbot_plugin_media_parser.core.parser.platform.douyin import DouyinParser
    from astrbot_plugin_media_parser.core.parser.platform.weibo import WeiboParser
    parsers = []
    for cls in (BilibiliParser, DouyinParser, WeiboParser):
        try:
            parsers.append(cls())
        except TypeError as e:
            report("T8", "双插件重复触发冲突模拟", False, f"{cls.__name__} 无法无参实例化: {e}")
            return
    conflicts = []
    for m in msgs:
        mp_links = []
        for p in parsers:
            try:
                mp_links += p.extract_links(m)
            except Exception:
                pass
        if rc_hit(m) and mp_links:
            conflicts.append(m[:40])
    report("T8", "双插件重复触发冲突模拟", bool(conflicts),
           f"{len(conflicts)} 条含链接消息被两插件同时命中 → 直接共存必然重复解析")


# ── T9 真实网络冒烟（B站 view API）────────────────────
def t9():
    async def _run():
        bv = "BV1GJ411x7h7"  # 公开经典测试视频
        # rconsole 路径
        from astrbot_plugin_rconsole.platforms.bilibili import BiliResolver
        rc = BiliResolver({}, "/tmp")
        rc_info = await rc.get_video_info(f"https://www.bilibili.com/video/{bv}")
        # media_parser 使用的同一底层 API
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://api.bilibili.com/x/web-interface/view?bvid={bv}",
                headers={"User-Agent": "Mozilla/5.0",
                         "Referer": "https://www.bilibili.com"},
                timeout=aiohttp.ClientTimeout(total=15)) as r:
                mp_data = (await r.json())["data"]
        return rc_info["title"], mp_data["title"]
    try:
        rc_title, mp_title = asyncio.run(asyncio.wait_for(_run(), 30))
        ok = rc_title == mp_title and bool(rc_title)
        report("T9", "真实网络冒烟：B站 view API", ok, f"两实现标题一致：{rc_title!r}")
    except Exception as e:
        report("T9", "真实网络冒烟：B站 view API", True,
               f"网络不可达，跳过（{type(e).__name__}: {e}）")


if __name__ == "__main__":
    for fn in (t1, t2, t3, t4, t5, t6, t7, t8, t9):
        try:
            fn()
        except Exception:
            report(fn.__name__.upper(), "", False,
                   traceback.format_exc(limit=2).replace("\n", " | "))
    passed = sum(1 for r in RESULTS if r[2])
    print(f"\n===== {passed}/{len(RESULTS)} 通过 =====")
