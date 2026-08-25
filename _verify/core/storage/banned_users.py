"""管理员指令永久屏蔽用户的持久化名单。"""
import json
import os
import threading
from typing import Any, List

from ..logger import logger


class BannedUserManager:
    """按 `平台:用户ID` 记录被管理员永久屏蔽的用户。"""

    def __init__(self, record_file: str):
        self._record_file = record_file
        self._lock = threading.Lock()
        self._banned: set[str] = set()
        self._load()

    @staticmethod
    def build_user_key(platform_name: Any, sender_id: Any) -> str:
        platform = str(platform_name or "unknown").strip() or "unknown"
        sender = str(sender_id or "").strip()
        return f"{platform}:{sender}"

    def _load(self) -> None:
        if not self._record_file or not os.path.exists(self._record_file):
            return
        try:
            with open(self._record_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._banned = {str(item) for item in data if str(item).strip()}
        except (OSError, ValueError) as exc:
            logger.warning(f"读取屏蔽名单失败，按空名单处理: {exc}")

    def _save_locked(self) -> None:
        if not self._record_file:
            return
        try:
            os.makedirs(os.path.dirname(self._record_file), exist_ok=True)
            tmp_file = self._record_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(sorted(self._banned), f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self._record_file)
        except OSError as exc:
            logger.warning(f"保存屏蔽名单失败: {exc}")

    def is_banned(self, user_key: str) -> bool:
        with self._lock:
            return user_key in self._banned

    def ban(self, user_key: str) -> bool:
        """加入屏蔽名单，返回是否为新增。"""
        with self._lock:
            if user_key in self._banned:
                return False
            self._banned.add(user_key)
            self._save_locked()
            return True

    def unban(self, user_key: str) -> bool:
        """移出屏蔽名单，返回是否确有移除。"""
        with self._lock:
            if user_key not in self._banned:
                return False
            self._banned.discard(user_key)
            self._save_locked()
            return True

    def list_banned(self) -> List[str]:
        with self._lock:
            return sorted(self._banned)
