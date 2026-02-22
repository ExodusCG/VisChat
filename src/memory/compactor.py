"""
记忆压缩器

当会话消息过多时，使用 LLM 生成摘要并存入长期记忆
压缩策略:
1. 检测消息数量是否超过阈值
2. 使用 LLM 生成对话摘要
3. 提取重要信息存入长期记忆
4. 保留最近的消息 + 摘要
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Protocol
import logging

from .models import Session, Message, Memory, MemoryCategory, MessageRole
from .session import SessionManager
from .store import MemoryStore

logger = logging.getLogger(__name__)


# 默认配置
DEFAULT_MAX_CONTEXT_MESSAGES = 20    # 最大上下文消息数
DEFAULT_COMPACT_THRESHOLD = 15       # 触发压缩的阈值
DEFAULT_KEEP_RECENT_COUNT = 5        # 压缩后保留的最近消息数


class LLMProvider(Protocol):
    """LLM 提供者协议"""

    async def generate(self, messages: List[dict], system_prompt: Optional[str] = None) -> str:
        """生成响应"""
        ...


class MemoryCompactor:
    """
    记忆压缩器

    负责会话的压缩和长期记忆的提取
    """

    # 摘要生成提示词
    SUMMARY_PROMPT = """请根据以下对话内容生成一个简洁的摘要，包含以下要点：
1. 对话的主要话题
2. 用户的关键问题或需求
3. 助手提供的主要信息或解决方案
4. 任何重要的决定或结论

请用简洁的中文回复，控制在200字以内。

对话内容：
{conversation}
"""

    # 信息提取提示词
    EXTRACTION_PROMPT = """请从以下对话中提取重要信息，分为以下几类：

1. 用户偏好 (preference): 用户表达的喜好、习惯、偏好设置等
2. 重要事实 (fact): 用户提到的重要事实信息，如姓名、地点、时间等

请以JSON格式返回，例如：
{{
    "preferences": ["偏好1", "偏好2"],
    "facts": ["事实1", "事实2"]
}}

如果没有发现相关信息，对应列表为空。

对话内容：
{conversation}
"""

    def __init__(
        self,
        session_manager: SessionManager,
        memory_store: MemoryStore,
        max_context_messages: int = DEFAULT_MAX_CONTEXT_MESSAGES,
        compact_threshold: int = DEFAULT_COMPACT_THRESHOLD,
        keep_recent_count: int = DEFAULT_KEEP_RECENT_COUNT
    ):
        """
        初始化记忆压缩器

        Args:
            session_manager: 会话管理器
            memory_store: 记忆存储
            max_context_messages: 最大上下文消息数
            compact_threshold: 触发压缩的阈值
            keep_recent_count: 压缩后保留的最近消息数
        """
        self.session_manager = session_manager
        self.memory_store = memory_store
        self.max_context_messages = max_context_messages
        self.compact_threshold = compact_threshold
        self.keep_recent_count = keep_recent_count

    async def should_compact(self, session: Session) -> bool:
        """
        检查是否需要压缩会话

        Args:
            session: 会话对象

        Returns:
            是否需要压缩
        """
        return len(session.messages) >= self.compact_threshold

    async def compact_session(
        self,
        session: Session,
        llm_provider: LLMProvider
    ) -> Optional[str]:
        """
        压缩会话

        当消息数超过阈值时，生成摘要并存入长期记忆

        Args:
            session: 会话对象
            llm_provider: LLM 提供者

        Returns:
            生成的摘要，如果不需要压缩返回 None
        """
        if not await self.should_compact(session):
            logger.debug(f"Session {session.id} does not need compaction")
            return None

        logger.info(f"Starting compaction for session {session.id} with {len(session.messages)} messages")

        try:
            # 1. 获取需要压缩的消息 (保留最近的消息)
            messages_to_compact = session.messages[:-self.keep_recent_count]

            # 2. 格式化对话内容
            conversation = self._format_conversation(messages_to_compact)

            # 3. 生成摘要
            summary = await self._generate_summary(conversation, llm_provider)

            # 4. 提取重要信息并存入长期记忆
            await self._extract_and_save_memories(
                session.user_id,
                conversation,
                llm_provider
            )

            # 5. 更新会话
            await self.session_manager.update_session_summary(
                session.user_id,
                session.id,
                summary,
                self.keep_recent_count
            )

            # 6. 保存会话摘要到数据库
            await self.memory_store.save_session_summary(
                session.user_id,
                session.id,
                len(session.messages),
                summary
            )

            # 7. 将摘要作为记忆保存
            summary_memory = Memory(
                user_id=session.user_id,
                category=MemoryCategory.SUMMARY,
                content=f"会话 {session.id[:8]} 摘要: {summary}",
                importance=0.6
            )
            await self.memory_store.save_memory(summary_memory)

            logger.info(f"Compaction completed for session {session.id}")
            return summary

        except Exception as e:
            logger.error(f"Failed to compact session {session.id}: {e}")
            return None

    def _format_conversation(self, messages: List[Message]) -> str:
        """
        格式化对话内容为文本

        Args:
            messages: 消息列表

        Returns:
            格式化的对话文本
        """
        lines = []
        for msg in messages:
            role_name = "用户" if msg.role == MessageRole.USER else "助手"
            lines.append(f"{role_name}: {msg.content}")
        return "\n".join(lines)

    async def _generate_summary(
        self,
        conversation: str,
        llm_provider: LLMProvider
    ) -> str:
        """
        使用 LLM 生成对话摘要

        Args:
            conversation: 对话内容
            llm_provider: LLM 提供者

        Returns:
            生成的摘要
        """
        prompt = self.SUMMARY_PROMPT.format(conversation=conversation)

        messages = [{"role": "user", "content": prompt}]

        try:
            summary = await llm_provider.generate(
                messages,
                system_prompt="你是一个专业的对话摘要助手，擅长提取对话的关键信息。"
            )
            return summary.strip()
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            # 如果 LLM 调用失败，返回简单摘要
            return f"对话包含 {len(conversation.split(chr(10)))} 条消息"

    async def _extract_and_save_memories(
        self,
        user_id: str,
        conversation: str,
        llm_provider: LLMProvider
    ) -> None:
        """
        从对话中提取信息并保存为长期记忆

        Args:
            user_id: 用户 ID
            conversation: 对话内容
            llm_provider: LLM 提供者
        """
        prompt = self.EXTRACTION_PROMPT.format(conversation=conversation)

        messages = [{"role": "user", "content": prompt}]

        try:
            response = await llm_provider.generate(
                messages,
                system_prompt="你是一个信息提取助手，擅长从对话中识别用户偏好和重要事实。请只返回JSON格式的结果。"
            )

            # 解析 JSON 响应
            import json

            # 尝试从响应中提取 JSON
            response = response.strip()
            if response.startswith("```"):
                # 移除 markdown 代码块
                lines = response.split("\n")
                response = "\n".join(lines[1:-1])

            data = json.loads(response)

            # 保存偏好
            for pref in data.get("preferences", []):
                if pref and pref.strip():
                    memory = Memory(
                        user_id=user_id,
                        category=MemoryCategory.PREFERENCE,
                        content=pref.strip(),
                        importance=0.7
                    )
                    await self.memory_store.save_memory(memory)
                    logger.debug(f"Saved preference: {pref[:50]}")

            # 保存事实
            for fact in data.get("facts", []):
                if fact and fact.strip():
                    memory = Memory(
                        user_id=user_id,
                        category=MemoryCategory.FACT,
                        content=fact.strip(),
                        importance=0.5
                    )
                    await self.memory_store.save_memory(memory)
                    logger.debug(f"Saved fact: {fact[:50]}")

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse extraction response as JSON: {e}")
        except Exception as e:
            logger.error(f"Failed to extract memories: {e}")

    async def get_context_with_memories(
        self,
        user_id: str,
        session_id: str,
        max_messages: int = None
    ) -> List[Message]:
        """
        获取包含长期记忆的完整上下文

        组合短期记忆 (会话消息) 和长期记忆 (重要信息)

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            max_messages: 最大消息数，默认使用配置值

        Returns:
            上下文消息列表
        """
        if max_messages is None:
            max_messages = self.max_context_messages

        context = []

        # 1. 获取长期记忆
        memories = await self.memory_store.get_relevant_memories(user_id, limit=10)

        if memories:
            memory_content = self._format_memories_for_context(memories)
            context.append(Message(
                role=MessageRole.SYSTEM,
                content=f"关于用户的已知信息:\n{memory_content}"
            ))

        # 2. 获取会话上下文
        session_messages = await self.session_manager.get_context(
            user_id, session_id, max_messages
        )
        context.extend(session_messages)

        # 更新记忆的访问时间
        for memory in memories:
            await self.memory_store.update_memory_access(user_id, memory.id)

        return context

    def _format_memories_for_context(self, memories: List[Memory]) -> str:
        """
        格式化记忆为上下文文本

        Args:
            memories: 记忆列表

        Returns:
            格式化的文本
        """
        lines = []

        # 按类别分组
        by_category = {}
        for mem in memories:
            cat = mem.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(mem.content)

        # 格式化输出
        category_names = {
            MemoryCategory.PREFERENCE: "用户偏好",
            MemoryCategory.FACT: "已知事实",
            MemoryCategory.SUMMARY: "历史摘要",
            "preference": "用户偏好",
            "fact": "已知事实",
            "summary": "历史摘要"
        }

        for cat, contents in by_category.items():
            cat_name = category_names.get(cat, str(cat))
            lines.append(f"【{cat_name}】")
            for content in contents[:5]:  # 每类最多5条
                lines.append(f"- {content}")

        return "\n".join(lines)

    async def manual_save_memory(
        self,
        user_id: str,
        content: str,
        category: MemoryCategory = MemoryCategory.FACT,
        importance: float = 0.5
    ) -> Memory:
        """
        手动保存记忆

        允许用户或系统直接添加重要信息到长期记忆

        Args:
            user_id: 用户 ID
            content: 记忆内容
            category: 记忆类别
            importance: 重要性评分

        Returns:
            创建的记忆对象
        """
        memory = Memory(
            user_id=user_id,
            category=category,
            content=content,
            importance=importance
        )
        await self.memory_store.save_memory(memory)
        logger.info(f"Manually saved memory for user {user_id}: {content[:50]}")
        return memory


class SimpleLLMProvider:
    """
    简单的 LLM 提供者实现 (用于测试)

    实际使用时应替换为真正的 LLM 提供者
    """

    async def generate(
        self,
        messages: List[dict],
        system_prompt: Optional[str] = None
    ) -> str:
        """简单的生成方法，返回固定响应"""
        # 这是一个占位实现，实际应该调用真正的 LLM
        return "这是一个测试摘要。"


async def create_memory_system(
    data_dir: str = "data/users",
    max_context_messages: int = DEFAULT_MAX_CONTEXT_MESSAGES,
    compact_threshold: int = DEFAULT_COMPACT_THRESHOLD,
    keep_recent_count: int = DEFAULT_KEEP_RECENT_COUNT
) -> tuple:
    """
    创建完整的记忆系统

    便捷函数，一次性创建所有组件

    Args:
        data_dir: 用户数据目录
        max_context_messages: 最大上下文消息数
        compact_threshold: 触发压缩的阈值
        keep_recent_count: 压缩后保留的最近消息数

    Returns:
        (SessionManager, MemoryStore, MemoryCompactor) 元组
    """
    session_manager = SessionManager(data_dir)
    memory_store = MemoryStore(data_dir)
    compactor = MemoryCompactor(
        session_manager,
        memory_store,
        max_context_messages,
        compact_threshold,
        keep_recent_count
    )

    return session_manager, memory_store, compactor
