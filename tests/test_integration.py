"""
CC_VisChat - 集成测试

测试各模块的集成和协作
"""

import pytest
import asyncio
import json
import base64
import numpy as np
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

# 确保可以导入项目模块
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSTTModule:
    """STT 模块测试"""

    def test_import_stt(self):
        """测试 STT 模块导入"""
        from src.stt import SenseVoiceSTT, STTConfig, VAD, VADConfig
        assert SenseVoiceSTT is not None
        assert STTConfig is not None
        assert VAD is not None
        assert VADConfig is not None

    def test_stt_config_defaults(self):
        """测试 STT 配置默认值"""
        from src.stt import STTConfig
        config = STTConfig()
        assert config.model_id == "iic/SenseVoiceSmall"
        assert config.device == "cpu"
        assert config.language == "auto"
        assert config.sample_rate == 16000

    def test_vad_config_defaults(self):
        """测试 VAD 配置默认值"""
        from src.stt import VADConfig
        config = VADConfig()
        assert config.silence_duration_ms == 800
        assert config.sample_rate == 16000

    def test_vad_process(self):
        """测试 VAD 处理"""
        from src.stt import VAD, VADConfig

        vad = VAD(VADConfig(init_frame_count=3))

        # 生成静音音频
        silence = np.random.randn(8000).astype(np.float32) * 0.001

        # 初始化阶段
        for _ in range(3):
            result = vad.process(silence)
            # 初始化阶段返回 False

        # 应该已初始化
        assert vad.is_initialized

        # 测试语音检测
        speech = np.sin(np.linspace(0, 100, 8000)).astype(np.float32) * 0.5
        is_speech = vad.process(speech)
        assert is_speech is True


class TestTTSModule:
    """TTS 模块测试"""

    def test_import_tts(self):
        """测试 TTS 模块导入"""
        from src.tts import TTSFactory, TTSManager, EdgeTTS, GTTSBackend
        assert TTSFactory is not None
        assert TTSManager is not None
        assert EdgeTTS is not None
        assert GTTSBackend is not None

    def test_tts_factory_backends(self):
        """测试 TTS 工厂可用后端"""
        from src.tts import TTSFactory
        backends = TTSFactory.get_available_backends()
        assert "edge_tts" in backends
        assert "gtts" in backends

    def test_edge_tts_init(self):
        """测试 EdgeTTS 初始化"""
        from src.tts import EdgeTTS
        tts = EdgeTTS(voice="zh-CN-XiaoxiaoNeural")
        assert tts.config.voice == "zh-CN-XiaoxiaoNeural"

    def test_gtts_init(self):
        """测试 GTTS 初始化"""
        from src.tts import GTTSBackend
        tts = GTTSBackend(lang="zh-CN")
        assert tts.config.voice == "zh-CN"

    @pytest.mark.asyncio
    async def test_tts_manager_init(self):
        """测试 TTS 管理器初始化"""
        from src.tts import TTSManager
        manager = TTSManager(
            primary="edge_tts",
            fallback="gtts"
        )
        assert manager._primary_name == "edge_tts"
        assert manager._fallback_name == "gtts"


class TestLLMModule:
    """LLM 模块测试"""

    def test_import_llm(self):
        """测试 LLM 模块导入"""
        from src.llm import LLMFactory, LLMManager, LMStudioProvider, LocalProxyProvider
        assert LLMFactory is not None
        assert LLMManager is not None
        assert LMStudioProvider is not None
        assert LocalProxyProvider is not None

    def test_llm_factory_providers(self):
        """测试 LLM 工厂可用提供者"""
        from src.llm import LLMFactory
        providers = LLMFactory.list_providers()
        assert "lmstudio" in providers
        assert "local_proxy" in providers

    def test_llm_factory_create(self):
        """测试 LLM 工厂创建"""
        from src.llm import LLMFactory

        provider = LLMFactory.create("lmstudio", {
            "base_url": "http://test:1234/v1",
            "model": "test-model"
        })
        assert provider is not None
        assert provider.config.base_url == "http://test:1234/v1"

    def test_llm_config_from_dict(self):
        """测试 LLM 配置从字典创建"""
        from src.llm import LLMConfig

        config = LLMConfig.from_dict({
            "base_url": "http://test:1234",
            "model": "test-model"
        })
        assert config.base_url == "http://test:1234"
        assert config.model == "test-model"
        assert config.temperature == 0.7  # 默认值


class TestMemoryModule:
    """记忆模块测试"""

    def test_import_memory(self):
        """测试记忆模块导入"""
        from src.memory import SessionManager, MemoryStore, Message, Session
        assert SessionManager is not None
        assert MemoryStore is not None
        assert Message is not None
        assert Session is not None

    def test_message_creation(self):
        """测试消息创建"""
        from src.memory.models import Message, MessageRole

        msg = Message(role=MessageRole.USER, content="Hello")
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"
        assert msg.id is not None

    def test_session_creation(self):
        """测试会话创建"""
        from src.memory import Session

        session = Session(user_id="test_user")
        assert session.user_id == "test_user"
        assert session.is_active is True
        assert len(session.messages) == 0

    def test_session_add_message(self):
        """测试会话添加消息"""
        from src.memory import Session
        from src.memory.models import MessageRole

        session = Session(user_id="test_user")
        msg = session.add_message(MessageRole.USER, "Test message")

        assert len(session.messages) == 1
        assert session.messages[0].content == "Test message"

    @pytest.mark.asyncio
    async def test_session_manager_create(self):
        """测试会话管理器创建会话"""
        from src.memory import SessionManager
        import tempfile
        import shutil

        # 使用临时目录
        temp_dir = tempfile.mkdtemp()
        try:
            manager = SessionManager(data_dir=temp_dir)
            session = await manager.create_session("test_user")

            assert session is not None
            assert session.user_id == "test_user"
        finally:
            shutil.rmtree(temp_dir)


class TestHandlerModule:
    """消息处理器模块测试"""

    def test_import_handler(self):
        """测试处理器模块导入"""
        from src.handler import MessageHandler, get_handler, UserSession
        assert MessageHandler is not None
        assert get_handler is not None
        assert UserSession is not None

    def test_user_session_creation(self):
        """测试用户会话创建"""
        from src.handler import UserSession
        from unittest.mock import Mock

        session = UserSession(
            user_id="user1",
            username="testuser",
            conn_id="conn_123",
            websocket=Mock()
        )

        assert session.user_id == "user1"
        assert session.username == "testuser"
        assert session.conn_id == "conn_123"

    def test_handler_singleton(self):
        """测试处理器单例"""
        from src.handler import get_handler

        handler1 = get_handler()
        handler2 = get_handler()
        assert handler1 is handler2


class TestConfigModule:
    """配置模块测试"""

    def test_import_config(self):
        """测试配置模块导入"""
        from src.config import get_config
        assert get_config is not None

    def test_config_loading(self):
        """测试配置加载"""
        from src.config import get_config

        config = get_config()
        assert config is not None
        assert hasattr(config, 'server')
        assert hasattr(config, 'ssl')
        assert hasattr(config, 'vision_llm')

    def test_config_vision_llm(self):
        """测试 Vision LLM 配置"""
        from src.config import get_config

        config = get_config()
        assert 'active_provider' in config.vision_llm
        assert config.vision_llm['active_provider'] in ['lmstudio', 'local_proxy']


class TestServerModule:
    """服务器模块测试"""

    def test_import_server(self):
        """测试服务器模块导入"""
        from src.server import create_app
        assert create_app is not None

    def test_create_app(self):
        """测试创建应用"""
        from src.server import create_app

        app = create_app()
        assert app is not None
        assert app.title == "CC_VisChat"


class TestAuthModule:
    """认证模块测试"""

    def test_import_auth(self):
        """测试认证模块导入"""
        from src.auth import AuthService
        assert AuthService is not None


# ============ 集成测试 ============

class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_text_flow(self):
        """测试完整文本处理流程 (模拟)"""
        from src.handler import MessageHandler
        from unittest.mock import AsyncMock, Mock

        handler = MessageHandler()

        # 创建模拟 WebSocket
        mock_ws = AsyncMock()
        mock_ws.send_json = AsyncMock()

        # 创建用户会话
        session = handler.create_user_session(
            conn_id="test_conn",
            user_id="test_user",
            username="tester",
            websocket=mock_ws
        )

        assert session is not None
        assert handler.get_user_session("test_conn") is session

        # 清理
        handler.remove_user_session("test_conn")
        assert handler.get_user_session("test_conn") is None

    @pytest.mark.asyncio
    async def test_memory_integration(self):
        """测试记忆系统集成"""
        from src.memory import SessionManager
        from src.memory.models import MessageRole
        import tempfile
        import shutil

        temp_dir = tempfile.mkdtemp()
        try:
            manager = SessionManager(data_dir=temp_dir)

            # 创建会话
            session = await manager.create_session("user1")

            # 添加消息
            await manager.add_message(
                "user1", session.id, MessageRole.USER, "Hello"
            )
            await manager.add_message(
                "user1", session.id, MessageRole.ASSISTANT, "Hi there!"
            )

            # 获取上下文
            context = await manager.get_context("user1", session.id)
            assert len(context) == 2

            # 关闭会话
            success = await manager.close_session("user1", session.id)
            assert success is True

        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
