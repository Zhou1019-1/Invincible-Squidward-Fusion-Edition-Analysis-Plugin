"""直播流片段录制处理器，按秒数截取 FLV 流并用 ffmpeg 转封装为 MP4。

移植自 rconsole-plugin 的直播片段录制功能。
"""

import asyncio
import os
from typing import Dict, Any, Optional

import aiohttp

from ...logger import logger
from ...constants import Config
from ...storage import cleanup_file, stamp_subdir
from ..budget import resolve_max_bytes

_RECORD_READ_CHUNK = 64 * 1024
# 录制允许在目标秒数基础上多等一段缓冲时间，避免慢速流提前超时
_RECORD_TIMEOUT_GRACE_SECONDS = 10


async def _record_flv_segment(
    session: aiohttp.ClientSession,
    stream_url: str,
    output_path: str,
    seconds: int,
    headers: dict = None,
    proxy: str = None,
    max_bytes: Optional[int] = None,
) -> Optional[str]:
    """从直播 FLV 流持续读取指定秒数并写入本地文件。

    Args:
        session: aiohttp会话
        stream_url: FLV 直播流地址
        output_path: 输出文件路径
        seconds: 录制秒数
        headers: 请求头
        proxy: 代理地址
        max_bytes: 下载硬限制字节数

    Returns:
        录制成功的文件路径，失败时为None
    """
    byte_limit = resolve_max_bytes(max_bytes, is_video=True)
    timeout = aiohttp.ClientTimeout(
        total=seconds + _RECORD_TIMEOUT_GRACE_SECONDS, sock_read=30
    )
    written = 0
    try:
        async with session.get(
            stream_url, headers=headers, proxy=proxy, timeout=timeout
        ) as resp:
            if resp.status != 200:
                logger.warning(f"直播流请求失败，状态码: {resp.status}")
                return None
            loop = asyncio.get_running_loop()
            deadline = loop.time() + seconds
            with open(output_path, "wb") as fp:
                async for chunk in resp.content.iter_chunked(_RECORD_READ_CHUNK):
                    fp.write(chunk)
                    written += len(chunk)
                    if written > byte_limit:
                        logger.warning("直播片段录制超过下载硬限制，提前结束")
                        break
                    if loop.time() >= deadline:
                        break
    except asyncio.TimeoutError:
        # 总时长超时视为正常结束（已录满目标秒数或流本身缓慢）
        if written <= 0:
            logger.warning("直播片段录制超时且未写入任何数据")
            cleanup_file(output_path)
            return None
    except (aiohttp.ClientError, OSError) as e:
        logger.warning(f"直播片段录制失败: {e}")
        cleanup_file(output_path)
        return None

    if written <= 0:
        cleanup_file(output_path)
        return None
    return output_path


async def _remux_flv_to_mp4(flv_path: str, output_path: str) -> bool:
    """使用 ffmpeg 将 FLV 无损转封装为 MP4。"""
    process = None
    try:
        temp_output = f"{output_path}.part.mp4"
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            flv_path,
            "-c",
            "copy",
            temp_output,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(
            process.communicate(), timeout=Config.VIDEO_DOWNLOAD_TIMEOUT
        )
        if process.returncode == 0 and os.path.exists(temp_output):
            os.replace(temp_output, output_path)
            return True
        error_output = stderr.decode("utf-8", errors="ignore").strip() if stderr else ""
        logger.warning(
            f"直播片段 ffmpeg 转封装失败(退出码 {process.returncode}): "
            f"{error_output[:200]}"
        )
        return False
    except asyncio.TimeoutError:
        await _terminate_ffmpeg_process(process)
        logger.warning("直播片段 ffmpeg 转封装超时")
        return False
    except asyncio.CancelledError:
        await _terminate_ffmpeg_process(process)
        raise
    except FileNotFoundError:
        logger.warning("ffmpeg 未找到，无法转封装直播片段")
        return False
    except Exception as e:
        logger.warning(f"直播片段 ffmpeg 转封装异常: {e}")
        return False
    finally:
        cleanup_file(f"{output_path}.part.mp4")


async def _terminate_ffmpeg_process(process) -> None:
    """取消或超时时终止并回收 ffmpeg 子进程。"""
    if process is None:
        return
    try:
        if process.returncode is None:
            process.kill()
    except ProcessLookupError:
        pass
    except Exception as e:
        logger.warning(f"直播片段转封装进程终止失败: {e}")
    try:
        await process.communicate()
    except Exception as e:
        logger.warning(f"直播片段转封装进程回收失败: {e}")


async def download_stream_clip_to_cache(
    session: aiohttp.ClientSession,
    stream_url: str,
    seconds: int,
    cache_dir: str,
    media_id: str,
    index: int = 0,
    headers: dict = None,
    proxy: str = None,
    max_bytes: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """录制直播流片段到缓存目录，优先输出 MP4，ffmpeg 不可用时保留 FLV。

    Args:
        session: aiohttp会话
        stream_url: FLV 直播流地址
        seconds: 录制秒数
        cache_dir: 缓存目录
        media_id: 媒体ID
        index: 媒体索引
        headers: 请求头
        proxy: 代理地址
        max_bytes: 下载硬限制字节数

    Returns:
        下载结果字典，包含file_path和size_mb字段，失败时为None
    """
    if not cache_dir or not stream_url or seconds <= 0:
        return None

    logger.debug(f"开始直播片段录制: url={stream_url[:60]}..., seconds={seconds}")

    cache_subdir = os.path.normpath(os.path.join(cache_dir, media_id))
    os.makedirs(cache_subdir, exist_ok=True)
    stamp_subdir(cache_subdir)
    flv_path = os.path.normpath(os.path.join(cache_subdir, f"video_{index}.flv"))
    output_path = os.path.normpath(os.path.join(cache_subdir, f"video_{index}.mp4"))

    recorded = await _record_flv_segment(
        session=session,
        stream_url=stream_url,
        output_path=flv_path,
        seconds=seconds,
        headers=headers,
        proxy=proxy,
        max_bytes=max_bytes,
    )
    if not recorded:
        return {
            "file_path": None,
            "size_mb": None,
            "status_code": None,
            "error": "直播片段录制失败",
        }

    final_path = flv_path
    if await _remux_flv_to_mp4(flv_path, output_path):
        cleanup_file(flv_path)
        final_path = output_path
    else:
        logger.warning("直播片段转封装失败，按 FLV 原样发送")

    try:
        size_mb = os.path.getsize(final_path) / (1024 * 1024)
    except OSError:
        size_mb = None
    return {
        "file_path": os.path.normpath(final_path),
        "size_mb": size_mb,
        "status_code": None,
    }
