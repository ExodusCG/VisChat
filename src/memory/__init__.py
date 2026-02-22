"""
CC_VisChat 记忆系统模块

混合记忆架构:
- 短期记忆: 当前会话的对话历史 (内存)
- 长期记忆: 跨会话的摘要和偏好 (SQLite)

用户数据隔离:
每个用户的数据存储在独立目录:
    data/users/{username}/
    ├── memory.db     # 用户记忆数据库
    ├── sessions/     # 会话历史 JSON 文件
    └── temp/         # 临时文件
"""

from .models import Message, Session, Memory, MemoryCategory
from .session import SessionManager
from .store import MemoryStore
from .compactor import MemoryCompactor

__all__ = [
    "Message",
    "Session",
    "Memory",
    "MemoryCategory",
    "SessionManager",
    "MemoryStore",
    "MemoryCompactor",
]
