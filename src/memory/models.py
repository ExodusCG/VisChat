"""
记忆系统数据模型

定义了会话、消息和记忆的数据结构
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
import uuid


def generate_id() -> str:
    """生成唯一标识符"""
    return str(uuid.uuid4())


class MessageRole(str, Enum):
    """消息角色枚举"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MemoryCategory(str, Enum):
    """记忆分类枚举"""
    PREFERENCE = "preference"  # 用户偏好
    SUMMARY = "summary"        # 对话摘要
    FACT = "fact"              # 重要事实


class Message(BaseModel):
    """
    消息模型

    表示对话中的单条消息，包含用户输入或助手响应
    """
    id: str = Field(default_factory=generate_id, description="消息唯一标识")
    role: MessageRole = Field(..., description="消息角色: user/assistant/system")
    content: str = Field(..., description="消息内容")
    image_ref: Optional[str] = Field(default=None, description="关联图片引用路径")
    timestamp: datetime = Field(default_factory=datetime.now, description="消息时间戳")

    class Config:
        use_enum_values = True

    def to_llm_format(self) -> dict:
        """转换为 LLM API 格式"""
        message = {
            "role": self.role,
            "content": self.content
        }
        return message

    def to_dict(self) -> dict:
        """转换为字典格式 (用于 JSON 序列化)"""
        return {
            "id": self.id,
            "role": self.role if isinstance(self.role, str) else self.role.value,
            "content": self.content,
            "image_ref": self.image_ref,
            "timestamp": self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """从字典创建消息"""
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


class Session(BaseModel):
    """
    会话模型

    表示一次完整的对话会话，包含多条消息
    短期记忆的核心容器
    """
    id: str = Field(default_factory=generate_id, description="会话唯一标识")
    user_id: str = Field(..., description="所属用户 ID")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="最后更新时间")
    messages: List[Message] = Field(default_factory=list, description="消息列表")
    summary: Optional[str] = Field(default=None, description="会话摘要 (压缩后)")
    is_active: bool = Field(default=True, description="会话是否活跃")

    def add_message(self, role: MessageRole, content: str, image_ref: Optional[str] = None) -> Message:
        """
        添加消息到会话

        Args:
            role: 消息角色
            content: 消息内容
            image_ref: 可选的图片引用

        Returns:
            新创建的消息对象
        """
        message = Message(
            role=role,
            content=content,
            image_ref=image_ref
        )
        self.messages.append(message)
        self.updated_at = datetime.now()
        return message

    def get_context_messages(self, max_messages: int = 20) -> List[Message]:
        """
        获取上下文消息 (用于发送给 LLM)

        Args:
            max_messages: 最大消息数量

        Returns:
            消息列表
        """
        # 如果有摘要，将其作为系统消息添加到上下文开头
        context = []
        if self.summary:
            context.append(Message(
                role=MessageRole.SYSTEM,
                content=f"之前的对话摘要: {self.summary}"
            ))

        # 添加最近的消息
        recent_messages = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        context.extend(recent_messages)

        return context

    def get_message_count(self) -> int:
        """获取消息数量"""
        return len(self.messages)

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": [msg.to_dict() for msg in self.messages],
            "summary": self.summary,
            "is_active": self.is_active
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """从字典创建会话"""
        messages_data = data.pop("messages", [])

        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        session = cls(**data)
        session.messages = [Message.from_dict(m) for m in messages_data]
        return session


class Memory(BaseModel):
    """
    长期记忆模型

    存储跨会话的重要信息，如用户偏好、对话摘要、重要事实等
    """
    id: str = Field(default_factory=generate_id, description="记忆唯一标识")
    user_id: str = Field(..., description="所属用户 ID")
    category: MemoryCategory = Field(..., description="记忆分类: preference/summary/fact")
    content: str = Field(..., description="记忆内容")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="重要性评分 0-1")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    last_accessed: datetime = Field(default_factory=datetime.now, description="最后访问时间")
    metadata: Optional[dict] = Field(default=None, description="附加元数据")

    class Config:
        use_enum_values = True

    def touch(self) -> None:
        """更新最后访问时间"""
        self.last_accessed = datetime.now()

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "category": self.category if isinstance(self.category, str) else self.category.value,
            "content": self.content,
            "importance": self.importance,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Memory":
        """从字典创建记忆"""
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("last_accessed"), str):
            data["last_accessed"] = datetime.fromisoformat(data["last_accessed"])
        return cls(**data)

    @classmethod
    def from_db_row(cls, row: tuple) -> "Memory":
        """从数据库行创建记忆"""
        return cls(
            id=row[0],
            user_id=row[1],
            category=row[2],
            content=row[3],
            importance=row[4],
            created_at=datetime.fromisoformat(row[5]) if isinstance(row[5], str) else row[5],
            last_accessed=datetime.fromisoformat(row[6]) if isinstance(row[6], str) else row[6],
            metadata=None  # 数据库中暂不存储 metadata
        )


class SessionSummary(BaseModel):
    """
    会话摘要模型 (用于数据库存储)
    """
    id: str = Field(..., description="会话 ID")
    user_id: str = Field(..., description="用户 ID")
    created_at: datetime = Field(..., description="创建时间")
    message_count: int = Field(default=0, description="消息数量")
    summary: Optional[str] = Field(default=None, description="会话摘要")

    @classmethod
    def from_db_row(cls, row: tuple) -> "SessionSummary":
        """从数据库行创建"""
        return cls(
            id=row[0],
            user_id=row[1],
            created_at=datetime.fromisoformat(row[2]) if isinstance(row[2], str) else row[2],
            message_count=row[3],
            summary=row[4]
        )
