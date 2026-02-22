"""
记忆系统测试

测试记忆模块的各项功能:
- 数据模型
- 会话管理
- 长期记忆存储
- 记忆压缩
"""

import asyncio
import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memory.models import (
    Message, Session, Memory, MemoryCategory,
    MessageRole, SessionSummary
)
from memory.session import SessionManager
from memory.store import MemoryStore
from memory.compactor import MemoryCompactor, create_memory_system


class TestModels:
    """数据模型测试"""

    def test_message_creation(self):
        """测试消息创建"""
        msg = Message(
            role=MessageRole.USER,
            content="你好"
        )
        assert msg.id is not None
        assert msg.role == "user"
        assert msg.content == "你好"
        assert msg.image_ref is None
        assert isinstance(msg.timestamp, datetime)

    def test_message_serialization(self):
        """测试消息序列化"""
        msg = Message(
            role=MessageRole.ASSISTANT,
            content="这是回复",
            image_ref="/path/to/image.jpg"
        )

        # 转换为字典
        data = msg.to_dict()
        assert data["role"] == "assistant"
        assert data["content"] == "这是回复"
        assert data["image_ref"] == "/path/to/image.jpg"

        # 从字典恢复
        restored = Message.from_dict(data)
        assert restored.id == msg.id
        assert restored.role == msg.role
        assert restored.content == msg.content

    def test_session_creation(self):
        """测试会话创建"""
        session = Session(user_id="test_user")
        assert session.id is not None
        assert session.user_id == "test_user"
        assert session.is_active is True
        assert len(session.messages) == 0

    def test_session_add_message(self):
        """测试会话添加消息"""
        session = Session(user_id="test_user")

        msg1 = session.add_message(MessageRole.USER, "问题1")
        msg2 = session.add_message(MessageRole.ASSISTANT, "回答1")

        assert len(session.messages) == 2
        assert session.messages[0].content == "问题1"
        assert session.messages[1].content == "回答1"

    def test_session_get_context(self):
        """测试获取上下文"""
        session = Session(user_id="test_user")

        # 添加多条消息
        for i in range(10):
            session.add_message(
                MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
                f"消息{i}"
            )

        # 获取最近5条
        context = session.get_context_messages(max_messages=5)
        assert len(context) == 5
        assert context[0].content == "消息5"

    def test_session_with_summary(self):
        """测试带摘要的会话上下文"""
        session = Session(user_id="test_user", summary="之前讨论了XX话题")

        session.add_message(MessageRole.USER, "继续讨论")
        session.add_message(MessageRole.ASSISTANT, "好的")

        context = session.get_context_messages()
        # 第一条应该是摘要系统消息
        assert context[0].role == MessageRole.SYSTEM
        assert "之前的对话摘要" in context[0].content

    def test_memory_creation(self):
        """测试记忆创建"""
        memory = Memory(
            user_id="test_user",
            category=MemoryCategory.PREFERENCE,
            content="用户喜欢简洁的回答",
            importance=0.8
        )

        assert memory.id is not None
        assert memory.user_id == "test_user"
        assert memory.category == "preference"
        assert memory.importance == 0.8

    def test_memory_serialization(self):
        """测试记忆序列化"""
        memory = Memory(
            user_id="test_user",
            category=MemoryCategory.FACT,
            content="用户住在北京"
        )

        data = memory.to_dict()
        restored = Memory.from_dict(data)

        assert restored.id == memory.id
        assert restored.content == memory.content


class TestSessionManager:
    """会话管理器测试"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp = tempfile.mkdtemp()
        yield temp
        shutil.rmtree(temp)

    @pytest.mark.asyncio
    async def test_create_session(self, temp_dir):
        """测试创建会话"""
        manager = SessionManager(data_dir=temp_dir)

        session = await manager.create_session("user1")
        assert session is not None
        assert session.user_id == "user1"

        # 验证文件已创建
        session_file = Path(temp_dir) / "user1" / "sessions" / f"{session.id}.json"
        assert session_file.exists()

    @pytest.mark.asyncio
    async def test_get_session(self, temp_dir):
        """测试获取会话"""
        manager = SessionManager(data_dir=temp_dir)

        # 创建会话
        session1 = await manager.create_session("user1")

        # 获取会话
        session2 = await manager.get_session("user1", session1.id)
        assert session2 is not None
        assert session2.id == session1.id

    @pytest.mark.asyncio
    async def test_add_message_to_session(self, temp_dir):
        """测试向会话添加消息"""
        manager = SessionManager(data_dir=temp_dir)

        session = await manager.create_session("user1")

        await manager.add_message(
            "user1", session.id,
            MessageRole.USER, "你好"
        )
        await manager.add_message(
            "user1", session.id,
            MessageRole.ASSISTANT, "你好！有什么可以帮你的？"
        )

        # 重新获取会话验证
        updated = await manager.get_session("user1", session.id)
        assert len(updated.messages) == 2

    @pytest.mark.asyncio
    async def test_list_sessions(self, temp_dir):
        """测试列出会话"""
        manager = SessionManager(data_dir=temp_dir)

        # 创建多个会话
        await manager.create_session("user1")
        await manager.create_session("user1")
        await manager.create_session("user1")

        sessions = await manager.list_sessions("user1")
        assert len(sessions) == 3

    @pytest.mark.asyncio
    async def test_close_session(self, temp_dir):
        """测试关闭会话"""
        manager = SessionManager(data_dir=temp_dir)

        session = await manager.create_session("user1")
        assert session.is_active is True

        await manager.close_session("user1", session.id)

        closed = await manager.get_session("user1", session.id)
        assert closed.is_active is False


class TestMemoryStore:
    """记忆存储测试"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp = tempfile.mkdtemp()
        yield temp
        shutil.rmtree(temp)

    @pytest.mark.asyncio
    async def test_save_and_get_memory(self, temp_dir):
        """测试保存和获取记忆"""
        store = MemoryStore(data_dir=temp_dir)

        memory = Memory(
            user_id="user1",
            category=MemoryCategory.PREFERENCE,
            content="喜欢详细的解释"
        )

        await store.save_memory(memory)

        retrieved = await store.get_memory("user1", memory.id)
        assert retrieved is not None
        assert retrieved.content == memory.content

        await store.close()

    @pytest.mark.asyncio
    async def test_get_memories_by_category(self, temp_dir):
        """测试按类别获取记忆"""
        store = MemoryStore(data_dir=temp_dir)

        # 添加不同类别的记忆
        await store.save_memory(Memory(
            user_id="user1",
            category=MemoryCategory.PREFERENCE,
            content="偏好1"
        ))
        await store.save_memory(Memory(
            user_id="user1",
            category=MemoryCategory.FACT,
            content="事实1"
        ))
        await store.save_memory(Memory(
            user_id="user1",
            category=MemoryCategory.PREFERENCE,
            content="偏好2"
        ))

        prefs = await store.get_memories_by_category("user1", MemoryCategory.PREFERENCE)
        assert len(prefs) == 2

        facts = await store.get_memories_by_category("user1", MemoryCategory.FACT)
        assert len(facts) == 1

        await store.close()

    @pytest.mark.asyncio
    async def test_search_memories(self, temp_dir):
        """测试搜索记忆"""
        store = MemoryStore(data_dir=temp_dir)

        await store.save_memory(Memory(
            user_id="user1",
            category=MemoryCategory.FACT,
            content="用户住在北京"
        ))
        await store.save_memory(Memory(
            user_id="user1",
            category=MemoryCategory.FACT,
            content="用户喜欢编程"
        ))

        results = await store.search_memories("user1", "北京")
        assert len(results) == 1
        assert "北京" in results[0].content

        await store.close()

    @pytest.mark.asyncio
    async def test_delete_memory(self, temp_dir):
        """测试删除记忆"""
        store = MemoryStore(data_dir=temp_dir)

        memory = Memory(
            user_id="user1",
            category=MemoryCategory.FACT,
            content="测试内容"
        )
        await store.save_memory(memory)

        await store.delete_memory("user1", memory.id)

        deleted = await store.get_memory("user1", memory.id)
        assert deleted is None

        await store.close()

    @pytest.mark.asyncio
    async def test_memory_stats(self, temp_dir):
        """测试记忆统计"""
        store = MemoryStore(data_dir=temp_dir)

        for i in range(5):
            await store.save_memory(Memory(
                user_id="user1",
                category=MemoryCategory.PREFERENCE,
                content=f"偏好{i}",
                importance=0.5 + i * 0.1
            ))

        stats = await store.get_memory_stats("user1")
        assert stats["total_memories"] == 5
        assert stats["by_category"]["preference"] == 5
        assert stats["avg_importance"] > 0

        await store.close()


class TestMemoryCompactor:
    """记忆压缩器测试"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp = tempfile.mkdtemp()
        yield temp
        shutil.rmtree(temp)

    @pytest.mark.asyncio
    async def test_should_compact(self, temp_dir):
        """测试是否需要压缩判断"""
        manager, store, compactor = await create_memory_system(
            data_dir=temp_dir,
            compact_threshold=5
        )

        session = Session(user_id="user1")

        # 少于阈值不需要压缩
        for i in range(3):
            session.add_message(MessageRole.USER, f"消息{i}")
        assert not await compactor.should_compact(session)

        # 达到阈值需要压缩
        for i in range(3, 6):
            session.add_message(MessageRole.USER, f"消息{i}")
        assert await compactor.should_compact(session)

        await store.close()

    @pytest.mark.asyncio
    async def test_create_memory_system(self, temp_dir):
        """测试创建完整记忆系统"""
        manager, store, compactor = await create_memory_system(
            data_dir=temp_dir
        )

        assert manager is not None
        assert store is not None
        assert compactor is not None

        await store.close()


class TestIntegration:
    """集成测试"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp = tempfile.mkdtemp()
        yield temp
        shutil.rmtree(temp)

    @pytest.mark.asyncio
    async def test_full_workflow(self, temp_dir):
        """测试完整工作流程"""
        # 创建记忆系统
        manager, store, compactor = await create_memory_system(
            data_dir=temp_dir
        )

        user_id = "test_user"

        # 1. 创建会话
        session = await manager.create_session(user_id)
        assert session is not None

        # 2. 添加消息
        await manager.add_message(
            user_id, session.id,
            MessageRole.USER, "我叫张三，住在北京"
        )
        await manager.add_message(
            user_id, session.id,
            MessageRole.ASSISTANT, "你好张三！北京是个好地方。"
        )

        # 3. 手动保存记忆
        memory = await compactor.manual_save_memory(
            user_id,
            "用户名叫张三，住在北京",
            MemoryCategory.FACT,
            0.8
        )

        # 4. 验证记忆已保存
        memories = await store.get_relevant_memories(user_id)
        assert len(memories) == 1
        assert "张三" in memories[0].content

        # 5. 获取包含记忆的上下文
        context = await compactor.get_context_with_memories(
            user_id, session.id
        )
        # 应该包含系统消息（记忆）和对话消息
        assert len(context) >= 2

        await store.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
