"""
EdgeTTS 后端实现

使用微软 Edge 浏览器的 TTS 服务，免费且质量较高
"""

import logging
import asyncio
from typing import List, Optional

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    edge_tts = None

from .base import (
    BaseTTS,
    TTSConfig,
    TTSResult,
    TTSError,
    TTSSynthesisError,
    TTSConnectionError
)

logger = logging.getLogger(__name__)


# EdgeTTS 常用中文语音
CHINESE_VOICES = {
    # 女声
    "zh-CN-XiaoxiaoNeural": "晓晓 (女, 温和活泼)",
    "zh-CN-XiaoyiNeural": "晓伊 (女, 温暖亲切)",
    "zh-CN-XiaochenNeural": "晓辰 (女, 沉稳知性)",
    "zh-CN-XiaohanNeural": "晓涵 (女, 明亮自然)",
    "zh-CN-XiaomengNeural": "晓梦 (女, 甜美可爱)",
    "zh-CN-XiaomoNeural": "晓墨 (女, 温柔感性)",
    "zh-CN-XiaoqiuNeural": "晓秋 (女, 成熟稳重)",
    "zh-CN-XiaoruiNeural": "晓睿 (女, 活力青春)",
    "zh-CN-XiaoshuangNeural": "晓双 (女, 儿童声音)",
    "zh-CN-XiaoxuanNeural": "晓萱 (女, 甜美知性)",
    "zh-CN-XiaoyanNeural": "晓颜 (女, 温柔舒缓)",
    "zh-CN-XiaoyouNeural": "晓悠 (女, 儿童声音)",
    "zh-CN-XiaozhenNeural": "晓甄 (女, 新闻播音)",

    # 男声
    "zh-CN-YunxiNeural": "云希 (男, 阳光少年)",
    "zh-CN-YunjianNeural": "云健 (男, 运动解说)",
    "zh-CN-YunxiaNeural": "云夏 (男, 儿童声音)",
    "zh-CN-YunyangNeural": "云扬 (男, 新闻播音)",
    "zh-CN-YunyeNeural": "云野 (男, 故事旁白)",
    "zh-CN-YunzeNeural": "云泽 (男, 沉稳知性)",
    "zh-CN-YunfengNeural": "云枫 (男, 广告配音)",
    "zh-CN-YunhaoNeural": "云皓 (男, 广告配音)",
}

# 英文语音
ENGLISH_VOICES = {
    "en-US-JennyNeural": "Jenny (女, 美式英语)",
    "en-US-GuyNeural": "Guy (男, 美式英语)",
    "en-US-AriaNeural": "Aria (女, 美式英语)",
    "en-US-DavisNeural": "Davis (男, 美式英语)",
    "en-GB-SoniaNeural": "Sonia (女, 英式英语)",
    "en-GB-RyanNeural": "Ryan (男, 英式英语)",
}


class EdgeTTS(BaseTTS):
    """
    EdgeTTS 后端

    使用微软 Edge TTS 服务进行文本转语音

    特点:
    - 免费使用
    - 高质量语音
    - 支持多种语言和语音
    - 支持 SSML 标记
    - 支持语速、音调调整

    使用示例:
        ```python
        tts = EdgeTTS(voice="zh-CN-XiaoxiaoNeural", speed=1.0)
        audio_data = await tts.synthesize("你好，世界！")
        ```
    """

    def __init__(
        self,
        voice: str = "zh-CN-XiaoxiaoNeural",
        speed: float = 1.0,
        pitch: float = 0.0,
        volume: float = 1.0,
        config: Optional[TTSConfig] = None
    ):
        """
        初始化 EdgeTTS

        Args:
            voice: 语音名称，默认 "zh-CN-XiaoxiaoNeural"
            speed: 语速 (0.5 - 2.0)，默认 1.0
            pitch: 音调调整 (-50 到 +50 Hz)，默认 0.0
            volume: 音量 (0.0 - 1.0)，默认 1.0
            config: TTSConfig 配置对象，如果提供则忽略其他参数
        """
        if not EDGE_TTS_AVAILABLE:
            raise ImportError(
                "edge-tts 库未安装，请运行: pip install edge-tts"
            )

        if config:
            super().__init__(config)
        else:
            super().__init__(TTSConfig(
                voice=voice,
                speed=speed,
                pitch=pitch,
                volume=volume,
                output_format="mp3"
            ))

        self._voices_cache: Optional[List[str]] = None
        logger.info(f"EdgeTTS 初始化: voice={self.config.voice}, speed={self.config.speed}")

    def _build_rate_string(self) -> str:
        """
        构建语速参数字符串

        Returns:
            语速参数字符串，如 "+20%" 或 "-10%"
        """
        # 将 0.5-2.0 的速度值转换为百分比
        rate_percent = int((self.config.speed - 1.0) * 100)
        if rate_percent >= 0:
            return f"+{rate_percent}%"
        else:
            return f"{rate_percent}%"

    def _build_pitch_string(self) -> str:
        """
        构建音调参数字符串

        Returns:
            音调参数字符串，如 "+10Hz" 或 "-5Hz"
        """
        pitch_hz = int(self.config.pitch)
        if pitch_hz >= 0:
            return f"+{pitch_hz}Hz"
        else:
            return f"{pitch_hz}Hz"

    def _build_volume_string(self) -> str:
        """
        构建音量参数字符串

        Returns:
            音量参数字符串，如 "+50%" 或 "-20%"
        """
        # 将 0.0-1.0 的音量转换为 -100% 到 0% 的范围
        volume_percent = int((self.config.volume - 1.0) * 100)
        if volume_percent >= 0:
            return f"+{volume_percent}%"
        else:
            return f"{volume_percent}%"

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
            logger.warning("EdgeTTS: 空文本，返回空音频")
            return b""

        try:
            # 构建参数 - 只有非默认值时才传递，避免不必要的参数导致 403 错误
            kwargs = {
                "text": text,
                "voice": self.config.voice,
            }

            # 只在非默认值时添加参数 (参考 bailing/Talk 项目的简洁实现)
            if self.config.speed != 1.0:
                kwargs["rate"] = self._build_rate_string()
            if self.config.pitch != 0.0:
                kwargs["pitch"] = self._build_pitch_string()
            if self.config.volume != 1.0:
                kwargs["volume"] = self._build_volume_string()

            # 创建 Communicate 对象
            communicate = edge_tts.Communicate(**kwargs)

            # 收集音频数据
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]

            if not audio_data:
                raise TTSSynthesisError(
                    "EdgeTTS 返回空音频数据",
                    backend="EdgeTTS"
                )

            logger.debug(f"EdgeTTS 合成成功: {len(text)} 字符 -> {len(audio_data)} 字节")
            return audio_data

        except edge_tts.exceptions.NoAudioReceived as e:
            raise TTSSynthesisError(
                f"EdgeTTS 未收到音频数据: {e}",
                backend="EdgeTTS",
                original_error=e
            )
        except Exception as e:
            # 检查是否是网络相关错误
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ["connection", "timeout", "network", "403", "429"]):
                raise TTSConnectionError(
                    f"EdgeTTS 网络错误: {e}",
                    backend="EdgeTTS",
                    original_error=e
                )
            raise TTSSynthesisError(
                f"EdgeTTS 合成失败: {e}",
                backend="EdgeTTS",
                original_error=e
            )

    async def synthesize_stream(self, text: str):
        """
        流式合成音频

        Args:
            text: 要转换的文本

        Yields:
            音频数据块 (bytes)
        """
        if not text or not text.strip():
            return

        try:
            # 构建参数 - 只有非默认值时才传递
            kwargs = {
                "text": text,
                "voice": self.config.voice,
            }

            if self.config.speed != 1.0:
                kwargs["rate"] = self._build_rate_string()
            if self.config.pitch != 0.0:
                kwargs["pitch"] = self._build_pitch_string()
            if self.config.volume != 1.0:
                kwargs["volume"] = self._build_volume_string()

            communicate = edge_tts.Communicate(**kwargs)

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]

        except Exception as e:
            logger.error(f"EdgeTTS 流式合成错误: {e}")
            raise TTSSynthesisError(
                f"EdgeTTS 流式合成失败: {e}",
                backend="EdgeTTS",
                original_error=e
            )

    async def get_available_voices(self) -> List[str]:
        """
        获取所有可用的语音列表

        Returns:
            语音名称列表
        """
        if self._voices_cache is not None:
            return self._voices_cache

        try:
            voices = await edge_tts.list_voices()
            self._voices_cache = [v["ShortName"] for v in voices]
            logger.debug(f"EdgeTTS 获取到 {len(self._voices_cache)} 个语音")
            return self._voices_cache
        except Exception as e:
            logger.error(f"获取 EdgeTTS 语音列表失败: {e}")
            # 返回预定义的语音列表作为备选
            return list(CHINESE_VOICES.keys()) + list(ENGLISH_VOICES.keys())

    async def get_chinese_voices(self) -> List[str]:
        """
        获取中文语音列表

        Returns:
            中文语音名称列表
        """
        all_voices = await self.get_available_voices()
        return [v for v in all_voices if v.startswith("zh-")]

    async def get_english_voices(self) -> List[str]:
        """
        获取英文语音列表

        Returns:
            英文语音名称列表
        """
        all_voices = await self.get_available_voices()
        return [v for v in all_voices if v.startswith("en-")]

    @staticmethod
    def get_voice_description(voice: str) -> str:
        """
        获取语音的描述信息

        Args:
            voice: 语音名称

        Returns:
            语音描述，如果未找到则返回语音名称
        """
        if voice in CHINESE_VOICES:
            return CHINESE_VOICES[voice]
        if voice in ENGLISH_VOICES:
            return ENGLISH_VOICES[voice]
        return voice

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            EdgeTTS 服务是否可用
        """
        try:
            # 使用一个简短的测试文本
            audio = await self.synthesize("测试")
            return len(audio) > 100  # 确保返回了有效的音频
        except Exception as e:
            logger.warning(f"EdgeTTS 健康检查失败: {e}")
            return False
