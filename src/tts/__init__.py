"""
TTS (Text-to-Speech) 模块

提供文本转语音功能，支持多种后端：
- EdgeTTS (默认): 微软 Edge TTS 服务，免费高质量
- GTTS (备用): Google Text-to-Speech，作为容错备选

使用示例:
    ```python
    from src.tts import TTSFactory, EdgeTTS, GTTSBackend

    # 方式 1: 使用工厂创建 (推荐)
    tts = TTSFactory.create("edge_tts", {"voice": "zh-CN-XiaoxiaoNeural"})
    audio = await tts.synthesize("你好，世界！")

    # 方式 2: 直接实例化
    tts = EdgeTTS(voice="zh-CN-XiaoxiaoNeural", speed=1.0)
    audio = await tts.synthesize("你好，世界！")

    # 方式 3: 使用带容错的 TTS 管理器
    manager = TTSManager(primary="edge_tts", fallback="gtts")
    audio = await manager.synthesize("你好，世界！")
    ```
"""

import logging
from typing import Dict, Any, Optional, Type, List

from .base import (
    BaseTTS,
    TTSConfig,
    TTSResult,
    TTSError,
    TTSSynthesisError,
    TTSConnectionError,
    TTSConfigError
)
from .edge_tts import EdgeTTS, CHINESE_VOICES, ENGLISH_VOICES
from .gtts_backend import GTTSBackend

logger = logging.getLogger(__name__)

__all__ = [
    # 基类和配置
    "BaseTTS",
    "TTSConfig",
    "TTSResult",

    # 错误类
    "TTSError",
    "TTSSynthesisError",
    "TTSConnectionError",
    "TTSConfigError",

    # 后端实现
    "EdgeTTS",
    "GTTSBackend",

    # 工厂和管理器
    "TTSFactory",
    "TTSManager",

    # 常量
    "CHINESE_VOICES",
    "ENGLISH_VOICES",
]


# 注册可用的 TTS 后端
_TTS_BACKENDS: Dict[str, Type[BaseTTS]] = {
    "edge_tts": EdgeTTS,
    "edgetts": EdgeTTS,
    "edge": EdgeTTS,
    "gtts": GTTSBackend,
    "google": GTTSBackend,
}


class TTSFactory:
    """
    TTS 工厂类

    用于根据配置创建合适的 TTS 后端实例

    使用示例:
        ```python
        # 创建 EdgeTTS
        tts = TTSFactory.create("edge_tts", {
            "voice": "zh-CN-XiaoxiaoNeural",
            "speed": 1.2
        })

        # 创建 GTTS
        tts = TTSFactory.create("gtts", {
            "lang": "zh-CN"
        })
        ```
    """

    @staticmethod
    def create(backend: str, config: Optional[Dict[str, Any]] = None) -> BaseTTS:
        """
        创建 TTS 后端实例

        Args:
            backend: 后端名称 ("edge_tts", "gtts" 等)
            config: 配置字典

        Returns:
            TTS 后端实例

        Raises:
            TTSConfigError: 未知的后端名称
        """
        backend_lower = backend.lower().replace("-", "_")

        if backend_lower not in _TTS_BACKENDS:
            available = ", ".join(_TTS_BACKENDS.keys())
            raise TTSConfigError(
                f"未知的 TTS 后端: {backend}。可用后端: {available}"
            )

        backend_class = _TTS_BACKENDS[backend_lower]
        config = config or {}

        try:
            if backend_class == EdgeTTS:
                return EdgeTTS(
                    voice=config.get("voice", "zh-CN-XiaoxiaoNeural"),
                    speed=config.get("speed", 1.0),
                    pitch=config.get("pitch", 0.0),
                    volume=config.get("volume", 1.0)
                )
            elif backend_class == GTTSBackend:
                return GTTSBackend(
                    lang=config.get("lang", config.get("voice", "zh-CN")),
                    slow=config.get("slow", False)
                )
            else:
                # 通用实例化
                return backend_class(**config)

        except Exception as e:
            raise TTSConfigError(
                f"创建 TTS 后端失败: {e}",
                backend=backend,
                original_error=e
            )

    @staticmethod
    def get_available_backends() -> List[str]:
        """
        获取所有可用的后端名称

        Returns:
            后端名称列表
        """
        # 返回去重后的主要名称
        return ["edge_tts", "gtts"]

    @staticmethod
    def register_backend(name: str, backend_class: Type[BaseTTS]) -> None:
        """
        注册新的 TTS 后端

        Args:
            name: 后端名称
            backend_class: 后端类
        """
        _TTS_BACKENDS[name.lower()] = backend_class
        logger.info(f"注册 TTS 后端: {name}")


class TTSManager:
    """
    TTS 管理器

    提供带容错机制的 TTS 服务，当主后端失败时自动切换到备用后端

    使用示例:
        ```python
        manager = TTSManager(
            primary="edge_tts",
            fallback="gtts",
            primary_config={"voice": "zh-CN-XiaoxiaoNeural"},
            fallback_config={"lang": "zh-CN"}
        )

        # 自动容错
        audio = await manager.synthesize("你好，世界！")
        ```
    """

    def __init__(
        self,
        primary: str = "edge_tts",
        fallback: str = "gtts",
        primary_config: Optional[Dict[str, Any]] = None,
        fallback_config: Optional[Dict[str, Any]] = None,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        retry_primary_interval: int = 5  # 每隔多少次请求重试主后端
    ):
        """
        初始化 TTS 管理器

        Args:
            primary: 主后端名称
            fallback: 备用后端名称
            primary_config: 主后端配置
            fallback_config: 备用后端配置
            max_retries: 主后端最大重试次数
            retry_delay: 重试延迟 (秒)
            retry_primary_interval: 回退模式下，每隔多少次请求重试主后端
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.retry_primary_interval = retry_primary_interval

        # 创建后端实例
        self._primary = TTSFactory.create(primary, primary_config)
        self._fallback = TTSFactory.create(fallback, fallback_config)

        self._primary_name = primary
        self._fallback_name = fallback
        self._use_fallback = False
        self._fallback_count = 0  # 回退后的请求计数

        logger.info(
            f"TTSManager 初始化: primary={primary}, fallback={fallback}"
        )

    @property
    def current_backend(self) -> BaseTTS:
        """获取当前使用的后端"""
        return self._fallback if self._use_fallback else self._primary

    @property
    def current_backend_name(self) -> str:
        """获取当前使用的后端名称"""
        return self._fallback_name if self._use_fallback else self._primary_name

    async def synthesize(self, text: str) -> bytes:
        """
        合成语音，带容错机制

        Args:
            text: 要转换的文本

        Returns:
            音频数据

        Raises:
            TTSError: 所有后端都失败时抛出
        """
        import asyncio

        last_error = None

        # 周期性重试主后端（即使在回退模式下）
        if self._use_fallback:
            self._fallback_count += 1
            if self._fallback_count >= self.retry_primary_interval:
                logger.info(f"尝试恢复主后端 {self._primary_name}...")
                self._use_fallback = False
                self._fallback_count = 0

        # 尝试主后端
        if not self._use_fallback:
            for attempt in range(self.max_retries):
                try:
                    audio = await self._primary.synthesize(text)
                    if audio:
                        # 主后端成功，确保重置回退状态
                        if self._fallback_count > 0:
                            logger.info(f"{self._primary_name} 恢复正常")
                            self._fallback_count = 0
                        return audio
                except TTSConnectionError as e:
                    logger.warning(
                        f"{self._primary_name} 第 {attempt + 1} 次尝试失败: {e}"
                    )
                    last_error = e
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay)
                except TTSError as e:
                    logger.error(f"{self._primary_name} 合成错误: {e}")
                    last_error = e
                    break

        # 主后端失败，尝试备用后端
        logger.info(f"{self._primary_name} 失败，尝试 {self._fallback_name}...")
        self._use_fallback = True

        try:
            audio = await self._fallback.synthesize(text)
            if audio:
                logger.info(f"使用 {self._fallback_name} 合成成功")
                return audio
        except TTSError as e:
            logger.error(f"{self._fallback_name} 也失败: {e}")
            last_error = e

        # 所有后端都失败
        raise TTSSynthesisError(
            f"所有 TTS 后端都失败: {last_error}",
            backend="TTSManager",
            original_error=last_error
        )

    async def synthesize_to_result(self, text: str) -> TTSResult:
        """
        合成语音并返回详细结果

        Args:
            text: 要转换的文本

        Returns:
            TTSResult 对象
        """
        audio_data = await self.synthesize(text)
        return TTSResult(
            audio_data=audio_data,
            format="mp3",
            text=text,
            voice=self.current_backend.config.voice
        )

    async def health_check(self) -> Dict[str, bool]:
        """
        检查所有后端的健康状态

        Returns:
            {后端名称: 是否健康}
        """
        results = {}

        try:
            results[self._primary_name] = await self._primary.health_check()
        except Exception:
            results[self._primary_name] = False

        try:
            results[self._fallback_name] = await self._fallback.health_check()
        except Exception:
            results[self._fallback_name] = False

        return results

    def reset_fallback(self) -> None:
        """重置为使用主后端"""
        self._use_fallback = False
        self._fallback_count = 0
        logger.info("TTSManager 重置为主后端")

    async def close(self) -> None:
        """关闭所有后端"""
        await self._primary.close()
        await self._fallback.close()


# 便捷函数
async def synthesize(
    text: str,
    backend: str = "edge_tts",
    **kwargs
) -> bytes:
    """
    便捷的合成函数

    Args:
        text: 要转换的文本
        backend: 后端名称
        **kwargs: 传递给后端的配置

    Returns:
        音频数据

    使用示例:
        ```python
        from src.tts import synthesize
        audio = await synthesize("你好", voice="zh-CN-XiaoxiaoNeural")
        ```
    """
    tts = TTSFactory.create(backend, kwargs)
    return await tts.synthesize(text)
