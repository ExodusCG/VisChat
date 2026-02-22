"""
TTS (Text-to-Speech) 抽象基类

定义所有 TTS 后端必须实现的接口
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TTSConfig:
    """TTS 配置数据类"""
    voice: str = "zh-CN-XiaoxiaoNeural"  # 默认语音
    speed: float = 1.0  # 语速 (0.5 - 2.0)
    pitch: float = 0.0  # 音调调整 (-50 to +50 Hz)
    volume: float = 1.0  # 音量 (0.0 - 1.0)
    output_format: str = "mp3"  # 输出格式: mp3, wav, pcm
    sample_rate: int = 24000  # 采样率

    def validate(self) -> None:
        """验证配置参数"""
        if not 0.5 <= self.speed <= 2.0:
            raise ValueError(f"speed must be between 0.5 and 2.0, got {self.speed}")
        if not -50 <= self.pitch <= 50:
            raise ValueError(f"pitch must be between -50 and 50, got {self.pitch}")
        if not 0.0 <= self.volume <= 1.0:
            raise ValueError(f"volume must be between 0.0 and 1.0, got {self.volume}")
        if self.output_format not in ("mp3", "wav", "pcm"):
            raise ValueError(f"output_format must be mp3, wav, or pcm, got {self.output_format}")


@dataclass
class TTSResult:
    """TTS 合成结果"""
    audio_data: bytes  # 音频数据
    format: str  # 音频格式
    duration_ms: Optional[int] = None  # 音频时长 (毫秒)
    sample_rate: int = 24000  # 采样率
    text: str = ""  # 原始文本
    voice: str = ""  # 使用的语音

    @property
    def is_valid(self) -> bool:
        """检查结果是否有效"""
        return bool(self.audio_data) and len(self.audio_data) > 0


class BaseTTS(ABC):
    """
    TTS 抽象基类

    所有 TTS 后端必须继承此类并实现所有抽象方法
    """

    def __init__(self, config: Optional[TTSConfig] = None):
        """
        初始化 TTS 后端

        Args:
            config: TTS 配置，如果为 None 则使用默认配置
        """
        self.config = config or TTSConfig()
        self._initialized = False
        self._available_voices: List[str] = []

    @property
    def name(self) -> str:
        """返回 TTS 后端名称"""
        return self.__class__.__name__

    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized

    async def initialize(self) -> bool:
        """
        初始化 TTS 后端

        子类可以重写此方法进行必要的初始化工作

        Returns:
            初始化是否成功
        """
        self._initialized = True
        logger.info(f"{self.name} 初始化成功")
        return True

    async def close(self) -> None:
        """
        关闭 TTS 后端，释放资源

        子类可以重写此方法进行清理工作
        """
        self._initialized = False
        logger.info(f"{self.name} 已关闭")

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """
        将文本转换为音频

        Args:
            text: 要转换的文本

        Returns:
            音频数据 (bytes)

        Raises:
            TTSError: 合成失败时抛出
        """
        pass

    async def synthesize_to_result(self, text: str) -> TTSResult:
        """
        将文本转换为音频，返回详细结果

        Args:
            text: 要转换的文本

        Returns:
            TTSResult 对象，包含音频数据和元信息
        """
        audio_data = await self.synthesize(text)
        return TTSResult(
            audio_data=audio_data,
            format=self.config.output_format,
            sample_rate=self.config.sample_rate,
            text=text,
            voice=self.config.voice
        )

    async def synthesize_stream(self, text: str):
        """
        流式合成音频

        Args:
            text: 要转换的文本

        Yields:
            音频数据块 (bytes)

        Note:
            默认实现直接返回完整音频，子类可以重写以支持真正的流式输出
        """
        audio_data = await self.synthesize(text)
        yield audio_data

    @abstractmethod
    async def get_available_voices(self) -> List[str]:
        """
        获取可用的语音列表

        Returns:
            语音名称列表
        """
        pass

    def set_voice(self, voice: str) -> None:
        """
        设置语音

        Args:
            voice: 语音名称
        """
        self.config.voice = voice
        logger.debug(f"{self.name} 语音设置为: {voice}")

    def set_speed(self, speed: float) -> None:
        """
        设置语速

        Args:
            speed: 语速 (0.5 - 2.0)
        """
        if not 0.5 <= speed <= 2.0:
            raise ValueError(f"speed must be between 0.5 and 2.0, got {speed}")
        self.config.speed = speed
        logger.debug(f"{self.name} 语速设置为: {speed}")

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            TTS 服务是否可用
        """
        try:
            # 尝试合成一个简单的测试文本
            test_text = "测试"
            audio = await self.synthesize(test_text)
            return len(audio) > 0
        except Exception as e:
            logger.warning(f"{self.name} 健康检查失败: {e}")
            return False

    def __repr__(self) -> str:
        return f"<{self.name}(voice={self.config.voice}, speed={self.config.speed})>"


class TTSError(Exception):
    """TTS 相关错误的基类"""

    def __init__(self, message: str, backend: str = "", original_error: Optional[Exception] = None):
        super().__init__(message)
        self.backend = backend
        self.original_error = original_error

    def __str__(self) -> str:
        if self.backend:
            return f"[{self.backend}] {super().__str__()}"
        return super().__str__()


class TTSSynthesisError(TTSError):
    """TTS 合成错误"""
    pass


class TTSConnectionError(TTSError):
    """TTS 连接错误"""
    pass


class TTSConfigError(TTSError):
    """TTS 配置错误"""
    pass
