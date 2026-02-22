"""
记忆持久化存储

使用 SQLite 实现长期记忆的持久化存储
每个用户的数据存储在独立的数据库文件中
"""

import aiosqlite
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
import logging

from .models import Memory, MemoryCategory, SessionSummary

logger = logging.getLogger(__name__)


# SQL 语句定义
SQL_CREATE_MEMORIES_TABLE = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    importance REAL DEFAULT 0.5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

SQL_CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    message_count INTEGER DEFAULT 0,
    summary TEXT
);
"""

SQL_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
"""


class MemoryStore:
    """
    记忆存储管理器

    管理用户的长期记忆，使用 SQLite 进行持久化
    每个用户拥有独立的数据库文件
    """

    def __init__(self, data_dir: str = "data/users"):
        """
        初始化记忆存储

        Args:
            data_dir: 用户数据根目录
        """
        self.data_dir = Path(data_dir)
        # 数据库连接池: {user_id: connection}
        self._connections: dict = {}
        # 锁，用于并发控制
        self._locks: dict = {}

    def _get_lock(self, user_id: str) -> asyncio.Lock:
        """获取用户的锁"""
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    def _get_db_path(self, user_id: str) -> Path:
        """获取用户数据库路径"""
        user_dir = self.data_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir / "memory.db"

    async def _get_connection(self, user_id: str) -> aiosqlite.Connection:
        """
        获取数据库连接

        如果连接不存在，则创建新连接并初始化数据库
        """
        if user_id not in self._connections:
            db_path = self._get_db_path(user_id)
            conn = await aiosqlite.connect(str(db_path))
            # 启用外键约束
            await conn.execute("PRAGMA foreign_keys = ON")
            # 初始化表结构
            await self._init_database(conn)
            self._connections[user_id] = conn
            logger.info(f"Created database connection for user {user_id}")

        return self._connections[user_id]

    async def _init_database(self, conn: aiosqlite.Connection) -> None:
        """初始化数据库表结构"""
        await conn.execute(SQL_CREATE_MEMORIES_TABLE)
        await conn.execute(SQL_CREATE_SESSIONS_TABLE)
        await conn.executescript(SQL_CREATE_INDEXES)
        await conn.commit()

    async def close(self, user_id: Optional[str] = None) -> None:
        """
        关闭数据库连接

        Args:
            user_id: 指定用户 ID，如果为 None 则关闭所有连接
        """
        if user_id:
            if user_id in self._connections:
                await self._connections[user_id].close()
                del self._connections[user_id]
                logger.info(f"Closed database connection for user {user_id}")
        else:
            for uid, conn in self._connections.items():
                await conn.close()
                logger.info(f"Closed database connection for user {uid}")
            self._connections.clear()

    # ==================== 记忆操作 ====================

    async def save_memory(self, memory: Memory) -> bool:
        """
        保存记忆

        Args:
            memory: 记忆对象

        Returns:
            是否保存成功
        """
        async with self._get_lock(memory.user_id):
            try:
                conn = await self._get_connection(memory.user_id)
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO memories
                    (id, user_id, category, content, importance, created_at, last_accessed)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        memory.id,
                        memory.user_id,
                        memory.category if isinstance(memory.category, str) else memory.category.value,
                        memory.content,
                        memory.importance,
                        memory.created_at.isoformat(),
                        memory.last_accessed.isoformat()
                    )
                )
                await conn.commit()
                logger.debug(f"Saved memory {memory.id} for user {memory.user_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to save memory: {e}")
                return False

    async def get_memory(self, user_id: str, memory_id: str) -> Optional[Memory]:
        """
        获取单条记忆

        Args:
            user_id: 用户 ID
            memory_id: 记忆 ID

        Returns:
            记忆对象，如果不存在返回 None
        """
        try:
            conn = await self._get_connection(user_id)
            async with conn.execute(
                "SELECT id, user_id, category, content, importance, created_at, last_accessed FROM memories WHERE id = ?",
                (memory_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return Memory.from_db_row(row)
        except Exception as e:
            logger.error(f"Failed to get memory {memory_id}: {e}")
        return None

    async def get_memories_by_category(
        self,
        user_id: str,
        category: MemoryCategory,
        limit: int = 50
    ) -> List[Memory]:
        """
        按类别获取记忆

        Args:
            user_id: 用户 ID
            category: 记忆类别
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        memories = []
        try:
            conn = await self._get_connection(user_id)
            cat_value = category if isinstance(category, str) else category.value
            async with conn.execute(
                """
                SELECT id, user_id, category, content, importance, created_at, last_accessed
                FROM memories
                WHERE user_id = ? AND category = ?
                ORDER BY importance DESC, last_accessed DESC
                LIMIT ?
                """,
                (user_id, cat_value, limit)
            ) as cursor:
                async for row in cursor:
                    memories.append(Memory.from_db_row(row))
        except Exception as e:
            logger.error(f"Failed to get memories by category: {e}")
        return memories

    async def get_relevant_memories(
        self,
        user_id: str,
        limit: int = 20,
        min_importance: float = 0.3
    ) -> List[Memory]:
        """
        获取相关记忆 (用于构建上下文)

        按重要性和最近访问时间排序

        Args:
            user_id: 用户 ID
            limit: 返回数量限制
            min_importance: 最低重要性阈值

        Returns:
            记忆列表
        """
        memories = []
        try:
            conn = await self._get_connection(user_id)
            async with conn.execute(
                """
                SELECT id, user_id, category, content, importance, created_at, last_accessed
                FROM memories
                WHERE user_id = ? AND importance >= ?
                ORDER BY importance DESC, last_accessed DESC
                LIMIT ?
                """,
                (user_id, min_importance, limit)
            ) as cursor:
                async for row in cursor:
                    memory = Memory.from_db_row(row)
                    memories.append(memory)
        except Exception as e:
            logger.error(f"Failed to get relevant memories: {e}")
        return memories

    async def search_memories(
        self,
        user_id: str,
        keyword: str,
        limit: int = 20
    ) -> List[Memory]:
        """
        搜索记忆内容

        Args:
            user_id: 用户 ID
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            匹配的记忆列表
        """
        memories = []
        try:
            conn = await self._get_connection(user_id)
            async with conn.execute(
                """
                SELECT id, user_id, category, content, importance, created_at, last_accessed
                FROM memories
                WHERE user_id = ? AND content LIKE ?
                ORDER BY importance DESC
                LIMIT ?
                """,
                (user_id, f"%{keyword}%", limit)
            ) as cursor:
                async for row in cursor:
                    memories.append(Memory.from_db_row(row))
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
        return memories

    async def update_memory_access(self, user_id: str, memory_id: str) -> bool:
        """
        更新记忆的最后访问时间

        Args:
            user_id: 用户 ID
            memory_id: 记忆 ID

        Returns:
            是否更新成功
        """
        try:
            conn = await self._get_connection(user_id)
            await conn.execute(
                "UPDATE memories SET last_accessed = ? WHERE id = ?",
                (datetime.now().isoformat(), memory_id)
            )
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update memory access: {e}")
            return False

    async def delete_memory(self, user_id: str, memory_id: str) -> bool:
        """
        删除记忆

        Args:
            user_id: 用户 ID
            memory_id: 记忆 ID

        Returns:
            是否删除成功
        """
        async with self._get_lock(user_id):
            try:
                conn = await self._get_connection(user_id)
                await conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                await conn.commit()
                logger.info(f"Deleted memory {memory_id} for user {user_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to delete memory: {e}")
                return False

    async def clear_memories(
        self,
        user_id: str,
        category: Optional[MemoryCategory] = None
    ) -> int:
        """
        清除记忆

        Args:
            user_id: 用户 ID
            category: 可选的类别过滤，如果为 None 则清除所有

        Returns:
            删除的记忆数量
        """
        async with self._get_lock(user_id):
            try:
                conn = await self._get_connection(user_id)

                if category:
                    cat_value = category if isinstance(category, str) else category.value
                    cursor = await conn.execute(
                        "DELETE FROM memories WHERE user_id = ? AND category = ?",
                        (user_id, cat_value)
                    )
                else:
                    cursor = await conn.execute(
                        "DELETE FROM memories WHERE user_id = ?",
                        (user_id,)
                    )

                await conn.commit()
                count = cursor.rowcount
                logger.info(f"Cleared {count} memories for user {user_id}")
                return count
            except Exception as e:
                logger.error(f"Failed to clear memories: {e}")
                return 0

    # ==================== 会话摘要操作 ====================

    async def save_session_summary(
        self,
        user_id: str,
        session_id: str,
        message_count: int,
        summary: Optional[str] = None
    ) -> bool:
        """
        保存会话摘要

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            message_count: 消息数量
            summary: 会话摘要

        Returns:
            是否保存成功
        """
        async with self._get_lock(user_id):
            try:
                conn = await self._get_connection(user_id)
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO sessions
                    (id, user_id, created_at, message_count, summary)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (session_id, user_id, datetime.now().isoformat(), message_count, summary)
                )
                await conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to save session summary: {e}")
                return False

    async def get_session_summaries(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[SessionSummary]:
        """
        获取用户的会话摘要列表

        Args:
            user_id: 用户 ID
            limit: 返回数量限制

        Returns:
            会话摘要列表
        """
        summaries = []
        try:
            conn = await self._get_connection(user_id)
            async with conn.execute(
                """
                SELECT id, user_id, created_at, message_count, summary
                FROM sessions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit)
            ) as cursor:
                async for row in cursor:
                    summaries.append(SessionSummary.from_db_row(row))
        except Exception as e:
            logger.error(f"Failed to get session summaries: {e}")
        return summaries

    # ==================== 统计和工具 ====================

    async def get_memory_stats(self, user_id: str) -> dict:
        """
        获取用户记忆统计信息

        Args:
            user_id: 用户 ID

        Returns:
            统计信息字典
        """
        stats = {
            "total_memories": 0,
            "by_category": {},
            "avg_importance": 0.0
        }

        try:
            conn = await self._get_connection(user_id)

            # 总数
            async with conn.execute(
                "SELECT COUNT(*) FROM memories WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                stats["total_memories"] = row[0] if row else 0

            # 按类别统计
            async with conn.execute(
                """
                SELECT category, COUNT(*)
                FROM memories
                WHERE user_id = ?
                GROUP BY category
                """,
                (user_id,)
            ) as cursor:
                async for row in cursor:
                    stats["by_category"][row[0]] = row[1]

            # 平均重要性
            async with conn.execute(
                "SELECT AVG(importance) FROM memories WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                stats["avg_importance"] = round(row[0], 3) if row and row[0] else 0.0

        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")

        return stats

    async def cleanup_old_memories(
        self,
        user_id: str,
        days_threshold: int = 90,
        importance_threshold: float = 0.3
    ) -> int:
        """
        清理旧的低重要性记忆

        Args:
            user_id: 用户 ID
            days_threshold: 天数阈值
            importance_threshold: 重要性阈值

        Returns:
            删除的记忆数量
        """
        async with self._get_lock(user_id):
            try:
                conn = await self._get_connection(user_id)
                cursor = await conn.execute(
                    """
                    DELETE FROM memories
                    WHERE user_id = ?
                    AND importance < ?
                    AND julianday('now') - julianday(last_accessed) > ?
                    """,
                    (user_id, importance_threshold, days_threshold)
                )
                await conn.commit()
                count = cursor.rowcount
                if count > 0:
                    logger.info(f"Cleaned up {count} old memories for user {user_id}")
                return count
            except Exception as e:
                logger.error(f"Failed to cleanup old memories: {e}")
                return 0
