"""
GTTS (Google Text-to-Speech) 后端实现

作为 EdgeTTS 的备用方案
"""

import io
import logging
import asyncio
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

try:
    from gtts import gTTS
    from gtts.lang import tts_langs
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    gTTS = None
    tts_langs = None

from .base import (
    BaseTTS,
    TTSConfig,
    TTSResult,
    TTSError,
    TTSSynthesisError,
    TTSConnectionError
)

logger = logging.getLogger(__name__)


# GTTS 支持的语言代码映射
LANGUAGE_CODES = {
    "zh-CN": "zh-CN",  # 简体中文
    "zh-TW": "zh-TW",  # 繁体中文
    "en": "en",        # 英语
    "en-US": "en",     # 美式英语
    "en-GB": "en",     # 英式英语
    "ja": "ja",        # 日语
    "ko": "ko",        # 韩语
    "fr": "fr",        # 法语
    "de": "de",        # 德语
    "es": "es",        # 西班牙语
}


class GTTSBackend(BaseTTS):
    """
    Google Text-to-Speech 后端

    特点:
    - 免费使用
    - 支持多种语言
    - 依赖 Google 服务，可能需要代理
    - 输出质量一般，作为备用方案

    使用示例:
        ```python
        tts = GTTSBackend(lang="zh-CN")
        audio_data = await tts.synthesize("你好，世界！")
        ```

    Note:
        GTTS 不支持调整语速、音调等参数，这些设置将被忽略
    """

    def __init__(
        self,
        lang: str = "zh-CN",
        slow: bool = False,
        config: Optional[TTSConfig] = None
    ):
        """
        初始化 GTTS 后端

        Args:
            lang: 语言代码，默认 "zh-CN"
            slow: 是否使用慢速，默认 False
            config: TTSConfig 配置对象
        """
        if not GTTS_AVAILABLE:
            raise ImportError(
                "gtts 库未安装，请运行: pip install gtts"
            )

        if config:
            super().__init__(config)
            self.lang = self._normalize_lang(config.voice)
        else:
            super().__init__(TTSConfig(
                voice=lang,
                output_format="mp3"
            ))
            self.lang = self._normalize_lang(lang)

        self.slow = slow
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._available_langs: Optional[List[str]] = None

        logger.info(f"GTTS 初始化: lang={self.lang}, slow={self.slow}")

    def _normalize_lang(self, lang: str) -> str:
        """
        标准化语言代码

        Args:
            lang: 输入的语言代码

        Returns:
            标准化后的语言代码
        """
        # 如果是 EdgeTTS 格式的语音名称，提取语言代码
        if "Neural" in lang:
            # 例如 "zh-CN-XiaoxiaoNeural" -> "zh-CN"
            parts = lang.split("-")
            if len(parts) >= 2:
                lang = f"{parts[0]}-{parts[1]}"

        # 查找映射
        return LANGUAGE_CODES.get(lang, lang)

    def _synthesize_sync(self, text: str) -> bytes:
        """
        同步合成方法 (在线程池中运行)

        Args:
            text: 要转换的文本

        Returns:
            MP3 格式的音频数据
        """
        tts = gTTS(text=text, lang=self.lang, slow=self.slow)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp.read()

    async def synthesize(self, text: str) -> bytes:
        """
        将文本转换为音频

        Args:
            text: 要转换的文本

        Returns:
            MP3 格式的音频数据

        Raises:
            TTSSynthesisError: 合成失败时抛出
        """
        if not text or not text.strip():
            logger.warning("GTTS: 空文本，返回空音频")
            return b""

        try:
            # 在线程池中运行同步方法，避免阻塞事件循环
            loop = asyncio.get_event_loop()
            audio_data = await loop.run_in_executor(
                self._executor,
                self._synthesize_sync,
                text
            )

            if not audio_data:
                raise TTSSynthesisError(
                    "GTTS 返回空音频数据",
                    backend="GTTS"
                )

            logger.debug(f"GTTS 合成成功: {len(text)} 字符 -> {len(audio_data)} 字节")
            return audio_data

        except Exception as e:
            error_str = str(e).lower()

            # 检查网络相关错误
            if any(keyword in error_str for keyword in ["connection", "timeout", "network", "failed to connect"]):
                raise TTSConnectionError(
                    f"GTTS 网络错误: {e}",
                    backend="GTTS",
                    original_error=e
                )

            # 检查 Google 服务错误
            if "429" in error_str or "too many requests" in error_str:
                raise TTSConnectionError(
                    f"GTTS 请求过于频繁: {e}",
                    backend="GTTS",
                    original_error=e
                )

            raise TTSSynthesisError(
                f"GTTS 合成失败: {e}",
                backend="GTTS",
                original_error=e
            )

    async def get_available_voices(self) -> List[str]:
        """
        获取可用的语言列表

        GTTS 不支持不同的语音，只支持不同的语言

        Returns:
            语言代码列表
        """
        if self._available_langs is not None:
            return self._available_langs

        try:
            # 获取 GTTS 支持的所有语言
            langs = tts_langs()
            self._available_langs = list(langs.keys())
            logger.debug(f"GTTS 支持 {len(self._available_langs)} 种语言")
            return self._available_langs
        except Exception as e:
            logger.error(f"获取 GTTS 语言列表失败: {e}")
            # 返回常用语言作为备选
            return list(LANGUAGE_CODES.values())

    def set_voice(self, voice: str) -> None:
        """
        设置语言

        Args:
            voice: 语言代码
        """
        self.lang = self._normalize_lang(voice)
        self.config.voice = voice
        logger.debug(f"GTTS 语言设置为: {self.lang}")

    def set_slow(self, slow: bool) -> None:
        """
        设置是否使用慢速

        Args:
            slow: 是否慢速
        """
        self.slow = slow
        logger.debug(f"GTTS 慢速模式: {slow}")

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            GTTS 服务是否可用
        """
        try:
            audio = await self.synthesize("测试")
            return len(audio) > 100
        except Exception as e:
            logger.warning(f"GTTS 健康检查失败: {e}")
            return False

    async def close(self) -> None:
        """关闭线程池"""
        self._executor.shutdown(wait=False)
        await super().close()
