"""
会话管理器

负责管理用户会话的生命周期:
- 创建/获取/关闭会话
- 短期记忆管理 (内存中的消息)
- 会话持久化 (JSON 文件)
"""

import json
import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import logging

from .models import Session, Message, MessageRole

logger = logging.getLogger(__name__)


class SessionManager:
    """
    会话管理器

    管理用户的对话会话，提供短期记忆功能
    每个用户的会话存储在独立目录中
    """

    def __init__(self, data_dir: str = "data/users"):
        """
        初始化会话管理器

        Args:
            data_dir: 用户数据根目录
        """
        self.data_dir = Path(data_dir)
        # 内存中的活跃会话缓存: {user_id: {session_id: Session}}
        self._active_sessions: Dict[str, Dict[str, Session]] = {}
        # 锁，用于并发控制
        self._locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, user_id: str) -> asyncio.Lock:
        """获取用户的锁"""
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    def _get_user_sessions_dir(self, user_id: str) -> Path:
        """获取用户会话目录"""
        sessions_dir = self.data_dir / user_id / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        return sessions_dir

    def _get_session_file(self, user_id: str, session_id: str) -> Path:
        """获取会话文件路径"""
        return self._get_user_sessions_dir(user_id) / f"{session_id}.json"

    async def create_session(self, user_id: str) -> Session:
        """
        创建新会话

        Args:
            user_id: 用户 ID

        Returns:
            新创建的会话对象
        """
        async with self._get_lock(user_id):
            session = Session(user_id=user_id)

            # 添加到活跃会话缓存
            if user_id not in self._active_sessions:
                self._active_sessions[user_id] = {}
            self._active_sessions[user_id][session.id] = session

            # 持久化保存
            await self._save_session(session)

            logger.info(f"Created new session {session.id} for user {user_id}")
            return session

    async def get_session(self, user_id: str, session_id: str) -> Optional[Session]:
        """
        获取会话

        优先从内存缓存获取，如果不存在则从文件加载

        Args:
            user_id: 用户 ID
            session_id: 会话 ID

        Returns:
            会话对象，如果不存在返回 None
        """
        # 先检查内存缓存
        if user_id in self._active_sessions:
            if session_id in self._active_sessions[user_id]:
                return self._active_sessions[user_id][session_id]

        # 从文件加载
        session_file = self._get_session_file(user_id, session_id)
        if session_file.exists():
            try:
                async with self._get_lock(user_id):
                    with open(session_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    session = Session.from_dict(data)

                    # 添加到缓存
                    if user_id not in self._active_sessions:
                        self._active_sessions[user_id] = {}
                    self._active_sessions[user_id][session_id] = session

                    return session
            except Exception as e:
                logger.error(f"Failed to load session {session_id}: {e}")
                return None

        return None

    async def get_or_create_session(self, user_id: str, session_id: Optional[str] = None) -> Session:
        """
        获取或创建会话

        如果指定了 session_id 且存在，返回该会话
        否则创建新会话

        Args:
            user_id: 用户 ID
            session_id: 可选的会话 ID

        Returns:
            会话对象
        """
        if session_id:
            session = await self.get_session(user_id, session_id)
            if session and session.is_active:
                return session

        return await self.create_session(user_id)

    async def get_active_session(self, user_id: str) -> Optional[Session]:
        """
        获取用户的活跃会话

        返回最近创建的活跃会话

        Args:
            user_id: 用户 ID

        Returns:
            活跃会话，如果没有返回 None
        """
        if user_id in self._active_sessions:
            active = [s for s in self._active_sessions[user_id].values() if s.is_active]
            if active:
                # 返回最近更新的会话
                return max(active, key=lambda s: s.updated_at)
        return None

    async def add_message(
        self,
        user_id: str,
        session_id: str,
        role: MessageRole,
        content: str,
        image_ref: Optional[str] = None
    ) -> Optional[Message]:
        """
        向会话添加消息

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            role: 消息角色
            content: 消息内容
            image_ref: 可选的图片引用

        Returns:
            新添加的消息，如果会话不存在返回 None
        """
        session = await self.get_session(user_id, session_id)
        if not session:
            logger.warning(f"Session {session_id} not found for user {user_id}")
            return None

        async with self._get_lock(user_id):
            message = session.add_message(role, content, image_ref)
            await self._save_session(session)

            logger.debug(f"Added message to session {session_id}: {role}")
            return message

    async def get_context(
        self,
        user_id: str,
        session_id: str,
        max_messages: int = 20
    ) -> List[Message]:
        """
        获取会话上下文 (用于发送给 LLM)

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            max_messages: 最大消息数量

        Returns:
            上下文消息列表
        """
        session = await self.get_session(user_id, session_id)
        if not session:
            return []

        return session.get_context_messages(max_messages)

    async def close_session(self, user_id: str, session_id: str) -> bool:
        """
        关闭会话

        Args:
            user_id: 用户 ID
            session_id: 会话 ID

        Returns:
            是否成功关闭
        """
        session = await self.get_session(user_id, session_id)
        if not session:
            return False

        async with self._get_lock(user_id):
            session.is_active = False
            session.updated_at = datetime.now()
            await self._save_session(session)

            logger.info(f"Closed session {session_id} for user {user_id}")
            return True

    async def update_session_summary(
        self,
        user_id: str,
        session_id: str,
        summary: str,
        keep_recent: int = 5
    ) -> bool:
        """
        更新会话摘要并裁剪消息

        用于记忆压缩后更新会话状态

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            summary: 会话摘要
            keep_recent: 保留最近的消息数量

        Returns:
            是否成功更新
        """
        session = await self.get_session(user_id, session_id)
        if not session:
            return False

        async with self._get_lock(user_id):
            session.summary = summary
            # 保留最近的消息
            if len(session.messages) > keep_recent:
                session.messages = session.messages[-keep_recent:]
            session.updated_at = datetime.now()
            await self._save_session(session)

            logger.info(f"Updated summary for session {session_id}")
            return True

    async def list_sessions(self, user_id: str, include_inactive: bool = False) -> List[Session]:
        """
        列出用户的所有会话

        Args:
            user_id: 用户 ID
            include_inactive: 是否包含非活跃会话

        Returns:
            会话列表
        """
        sessions = []
        sessions_dir = self._get_user_sessions_dir(user_id)

        for session_file in sessions_dir.glob("*.json"):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                session = Session.from_dict(data)

                if include_inactive or session.is_active:
                    sessions.append(session)
            except Exception as e:
                logger.error(f"Failed to load session from {session_file}: {e}")

        # 按更新时间排序
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    async def delete_session(self, user_id: str, session_id: str) -> bool:
        """
        删除会话

        Args:
            user_id: 用户 ID
            session_id: 会话 ID

        Returns:
            是否成功删除
        """
        async with self._get_lock(user_id):
            # 从缓存中移除
            if user_id in self._active_sessions:
                self._active_sessions[user_id].pop(session_id, None)

            # 删除文件
            session_file = self._get_session_file(user_id, session_id)
            if session_file.exists():
                try:
                    os.remove(session_file)
                    logger.info(f"Deleted session {session_id} for user {user_id}")
                    return True
                except Exception as e:
                    logger.error(f"Failed to delete session file {session_file}: {e}")
                    return False

            return False

    async def clear_user_sessions(self, user_id: str) -> int:
        """
        清除用户的所有会话

        Args:
            user_id: 用户 ID

        Returns:
            删除的会话数量
        """
        async with self._get_lock(user_id):
            # 清除缓存
            if user_id in self._active_sessions:
                del self._active_sessions[user_id]

            # 删除所有会话文件
            sessions_dir = self._get_user_sessions_dir(user_id)
            count = 0
            for session_file in sessions_dir.glob("*.json"):
                try:
                    os.remove(session_file)
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to delete session file {session_file}: {e}")

            logger.info(f"Cleared {count} sessions for user {user_id}")
            return count

    async def _save_session(self, session: Session) -> None:
        """
        保存会话到文件

        Args:
            session: 会话对象
        """
        session_file = self._get_session_file(session.user_id, session.id)
        try:
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save session {session.id}: {e}")
            raise

    def get_stats(self, user_id: str) -> dict:
        """
        获取用户会话统计信息

        Args:
            user_id: 用户 ID

        Returns:
            统计信息字典
        """
        cached_count = len(self._active_sessions.get(user_id, {}))
        sessions_dir = self._get_user_sessions_dir(user_id)
        total_count = len(list(sessions_dir.glob("*.json")))

        return {
            "cached_sessions": cached_count,
            "total_sessions": total_count,
            "sessions_dir": str(sessions_dir)
        }
