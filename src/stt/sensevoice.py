"""
CC_VisChat - SenseVoiceSmall STT 后端

使用 ModelScope 的 SenseVoiceSmall 模型进行语音识别。

模型特性：
- 模型大小: 220MB
- 运行环境: CPU 即可运行 (支持 GPU 加速)
- 推理速度: 10s 音频仅需 70ms，比 Whisper-Large 快 15 倍
- 语言支持: 50+ 语言，支持中文、粤语、英语、日语、韩语等
- 自动语种识别: 支持 language="auto"
- 额外能力: 情感识别、声学事件检测 (掌声、笑声等)

依赖安装：
    pip install -U funasr modelscope

参考文档：
    https://www.modelscope.cn/models/iic/SenseVoiceSmall
"""

import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Union
from enum import Enum

import numpy as np

# 设置日志
logger = logging.getLogger(__name__)


class Emotion(str, Enum):
    """情感类型枚举"""
    NEUTRAL = "neutral"     # 中性
    HAPPY = "happy"         # 高兴
    SAD = "sad"             # 悲伤
    ANGRY = "angry"         # 愤怒
    FEARFUL = "fearful"     # 恐惧
    DISGUSTED = "disgusted" # 厌恶
    SURPRISED = "surprised" # 惊讶
    UNKNOWN = "unknown"     # 未知


class AcousticEvent(str, Enum):
    """声学事件类型枚举"""
    SPEECH = "Speech"           # 语音
    APPLAUSE = "Applause"       # 掌声
    LAUGHTER = "Laughter"       # 笑声
    CRYING = "Crying"           # 哭声
    COUGHING = "Coughing"       # 咳嗽
    SNEEZING = "Sneezing"       # 喷嚏
    MUSIC = "Music"             # 音乐
    NOISE = "BGM"               # 背景噪音
    UNKNOWN = "unknown"


@dataclass
class STTResult:
    """STT 识别结果"""
    text: str                               # 转写文本
    language: str                           # 检测到的语言代码
    emotion: Emotion = Emotion.NEUTRAL      # 情感 (如果启用)
    events: List[AcousticEvent] = None      # 声学事件列表
    confidence: float = 0.0                 # 置信度 (如果可用)
    raw_result: Dict[str, Any] = None       # 原始结果 (用于调试)

    def __post_init__(self):
        if self.events is None:
            self.events = []


@dataclass
class STTConfig:
    """STT 配置"""
    # 模型配置
    model_id: str = "iic/SenseVoiceSmall"   # ModelScope 模型 ID
    device: str = "cpu"                      # 运行设备: "cpu" 或 "cuda:0"

    # 识别配置
    language: str = "auto"                   # 语言: "auto" / "zh" / "en" / "ja" / "ko" / "yue"
    use_itn: bool = True                     # 是否使用逆文本正则化 (数字转换等)

    # 音频配置
    sample_rate: int = 16000                 # 采样率 (Hz)

    # 线程池配置 (用于异步调用)
    max_workers: int = 2                     # 最大工作线程数


class SenseVoiceSTT:
    """
    SenseVoiceSmall STT 后端

    使用 FunASR 框架加载 SenseVoiceSmall 模型进行语音识别。
    支持同步和异步两种调用方式。

    使用示例::

        # 初始化
        stt = SenseVoiceSTT()

        # 同步调用
        result = stt.transcribe_sync(audio_array)
        print(result.text)

        # 异步调用
        result = await stt.transcribe(audio_array)
        print(result.text)
    """

    def __init__(self, config: Optional[STTConfig] = None):
        """
        初始化 SenseVoiceSmall STT

        Args:
            config: STT 配置，为 None 时使用默认配置
        """
        self._config = config or STTConfig()
        self._model = None
        self._executor = ThreadPoolExecutor(max_workers=self._config.max_workers)
        self._is_loaded = False

        # 语言代码映射
        self._language_map = {
            "zh": "zh",
            "en": "en",
            "ja": "ja",
            "ko": "ko",
            "yue": "yue",  # 粤语
            "auto": "auto",
        }

        # 情感标签映射 (SenseVoice 输出格式)
        self._emotion_map = {
            "NEUTRAL": Emotion.NEUTRAL,
            "HAPPY": Emotion.HAPPY,
            "SAD": Emotion.SAD,
            "ANGRY": Emotion.ANGRY,
            "FEARFUL": Emotion.FEARFUL,
            "DISGUSTED": Emotion.DISGUSTED,
            "SURPRISED": Emotion.SURPRISED,
        }

        # 声学事件映射
        self._event_map = {
            "Speech": AcousticEvent.SPEECH,
            "Applause": AcousticEvent.APPLAUSE,
            "Laughter": AcousticEvent.LAUGHTER,
            "Crying": AcousticEvent.CRYING,
            "Coughing": AcousticEvent.COUGHING,
            "Sneezing": AcousticEvent.SNEEZING,
            "Music": AcousticEvent.MUSIC,
            "BGM": AcousticEvent.NOISE,
        }

        logger.info(
            f"SenseVoiceSTT 初始化: model={self._config.model_id}, "
            f"device={self._config.device}, language={self._config.language}"
        )

    def load_model(self) -> bool:
        """
        加载模型 (同步)

        首次调用 transcribe 时会自动加载，也可手动提前加载。

        Returns:
            是否加载成功
        """
        if self._is_loaded:
            return True

        try:
            logger.info(f"正在加载 SenseVoiceSmall 模型 ({self._config.model_id})...")

            from funasr import AutoModel

            self._model = AutoModel(
                model=self._config.model_id,
                trust_remote_code=True,
                device=self._config.device,
            )

            self._is_loaded = True
            logger.info("SenseVoiceSmall 模型加载完成")
            return True

        except ImportError as e:
            logger.error(f"缺少依赖包，请安装: pip install -U funasr modelscope")
            logger.error(f"错误详情: {e}")
            return False

        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            return False

    async def load_model_async(self) -> bool:
        """
        异步加载模型

        Returns:
            是否加载成功
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self.load_model)

    def _preprocess_audio(self, audio: Union[np.ndarray, bytes]) -> np.ndarray:
        """
        预处理音频数据

        Args:
            audio: 音频数据，支持 numpy 数组或 bytes

        Returns:
            处理后的 float32 numpy 数组
        """
        if isinstance(audio, bytes):
            # 假设是 16-bit PCM
            audio = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0

        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # 确保是 1D 数组
        if audio.ndim > 1:
            audio = audio.flatten()

        # 归一化到 [-1.0, 1.0]
        max_val = np.abs(audio).max()
        if max_val > 1.0:
            audio = audio / max_val

        return audio

    def _parse_result(self, result: Any) -> STTResult:
        """
        解析 FunASR 返回的结果

        SenseVoice 的输出格式示例:
        [{'key': 'rand_id', 'text': '<|zh|><|NEUTRAL|><|Speech|>识别的文本'}]

        Args:
            result: FunASR 返回的原始结果

        Returns:
            STTResult 对象
        """
        try:
            # 提取文本
            if isinstance(result, list) and len(result) > 0:
                raw_text = result[0].get("text", "")
            else:
                raw_text = str(result)

            # 解析特殊标签
            # 格式: <|语言|><|情感|><|事件|>文本
            language = "zh"
            emotion = Emotion.NEUTRAL
            events = []
            text = raw_text

            # 使用正则提取标签
            # 匹配模式: <|TAG|>
            tag_pattern = r"<\|([^|]+)\|>"
            tags = re.findall(tag_pattern, raw_text)

            # 移除所有标签，获取纯文本
            text = re.sub(tag_pattern, "", raw_text).strip()

            # 解析标签
            for tag in tags:
                tag_upper = tag.upper()

                # 检查是否是语言标签
                if tag.lower() in self._language_map:
                    language = tag.lower()
                    continue

                # 检查是否是情感标签
                if tag_upper in self._emotion_map:
                    emotion = self._emotion_map[tag_upper]
                    continue

                # 检查是否是声学事件
                if tag in self._event_map:
                    events.append(self._event_map[tag])
                    continue

            return STTResult(
                text=text,
                language=language,
                emotion=emotion,
                events=events,
                raw_result={"original": raw_text, "tags": tags},
            )

        except Exception as e:
            logger.warning(f"解析结果时出错: {e}, 原始结果: {result}")
            return STTResult(
                text=str(result),
                language="unknown",
                emotion=Emotion.UNKNOWN,
                raw_result={"error": str(e), "original": result},
            )

    def transcribe_sync(self, audio: Union[np.ndarray, bytes]) -> STTResult:
        """
        同步转写音频 (阻塞调用)

        Args:
            audio: 音频数据
                - numpy.ndarray: float32，值域 [-1.0, 1.0]，采样率 16kHz
                - bytes: 16-bit PCM

        Returns:
            STTResult 对象
        """
        # 确保模型已加载
        if not self._is_loaded:
            if not self.load_model():
                return STTResult(
                    text="",
                    language="unknown",
                    emotion=Emotion.UNKNOWN,
                    raw_result={"error": "Model not loaded"},
                )

        try:
            # 预处理音频
            audio = self._preprocess_audio(audio)

            # 检查音频长度
            duration_sec = len(audio) / self._config.sample_rate
            if duration_sec < 0.1:
                logger.warning(f"音频过短 ({duration_sec:.2f}s)，可能无法识别")

            # 调用模型
            result = self._model.generate(
                input=audio,
                language=self._config.language,
                use_itn=self._config.use_itn,
            )

            # 解析结果
            return self._parse_result(result)

        except Exception as e:
            logger.error(f"转写失败: {e}")
            return STTResult(
                text="",
                language="unknown",
                emotion=Emotion.UNKNOWN,
                raw_result={"error": str(e)},
            )

    async def transcribe(self, audio: Union[np.ndarray, bytes]) -> STTResult:
        """
        异步转写音频 (非阻塞)

        在后台线程池中执行模型推理，不阻塞事件循环。

        Args:
            audio: 音频数据
                - numpy.ndarray: float32，值域 [-1.0, 1.0]，采样率 16kHz
                - bytes: 16-bit PCM

        Returns:
            STTResult 对象，包含:
                - text: 转写文本
                - language: 检测到的语言
                - emotion: 情感 (neutral/happy/sad/angry 等)
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.transcribe_sync,
            audio
        )

    def set_language(self, language: str) -> None:
        """
        设置识别语言

        Args:
            language: 语言代码 ("auto" / "zh" / "en" / "ja" / "ko" / "yue")
        """
        if language in self._language_map:
            self._config.language = language
            logger.info(f"STT 语言设置为: {language}")
        else:
            logger.warning(f"不支持的语言: {language}，保持原设置: {self._config.language}")

    def set_device(self, device: str) -> None:
        """
        设置运行设备 (需要重新加载模型)

        Args:
            device: 设备标识 ("cpu" / "cuda:0")
        """
        if device != self._config.device:
            self._config.device = device
            self._is_loaded = False
            self._model = None
            logger.info(f"STT 设备设置为: {device}，模型将在下次使用时重新加载")

    @property
    def is_loaded(self) -> bool:
        """模型是否已加载"""
        return self._is_loaded

    @property
    def config(self) -> STTConfig:
        """返回当前配置"""
        return self._config

    def close(self) -> None:
        """
        释放资源
        """
        logger.info("释放 SenseVoiceSTT 资源...")

        self._executor.shutdown(wait=False)

        if self._model is not None:
            self._model = None

        self._is_loaded = False
        logger.info("SenseVoiceSTT 资源已释放")

    def __enter__(self):
        """支持 with 语句"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """with 语句退出时自动释放资源"""
        self.close()
        return False

    def __del__(self):
        """析构时确保资源释放"""
        try:
            self.close()
        except Exception:
            pass


class StreamingSTT:
    """
    流式 STT - 结合 VAD 的完整流式语音识别

    将 VAD 和 STT 组合，提供完整的流式语音识别功能：
    1. 接收音频流
    2. VAD 检测语音活动
    3. 语音结束时自动调用 STT

    使用示例::

        streaming = StreamingSTT()

        async def handle_audio(audio_chunk: np.ndarray):
            result = await streaming.feed(audio_chunk)

            if result is not None:
                print(f"识别结果: {result.text}")
    """

    def __init__(
        self,
        stt_config: Optional[STTConfig] = None,
        vad_config: Optional["VADConfig"] = None,
    ):
        """
        初始化流式 STT

        Args:
            stt_config: STT 配置
            vad_config: VAD 配置
        """
        from .vad import VADConfig, StreamingVAD

        self._stt = SenseVoiceSTT(stt_config)
        self._vad = StreamingVAD(vad_config)
        self._is_processing = False

    def reset(self) -> None:
        """重置状态"""
        self._vad.reset()
        self._is_processing = False

    async def feed(self, audio_chunk: np.ndarray) -> Optional[STTResult]:
        """
        喂入音频块

        Args:
            audio_chunk: float32 音频数组

        Returns:
            如果语音结束，返回 STTResult；否则返回 None
        """
        if self._is_processing:
            return None

        result = self._vad.feed(audio_chunk)

        if result.is_complete and result.audio is not None:
            self._is_processing = True
            try:
                stt_result = await self._stt.transcribe(result.audio)
                return stt_result
            finally:
                self._is_processing = False
                self.reset()

        return None

    def feed_sync(self, audio_chunk: np.ndarray) -> Optional[STTResult]:
        """
        同步喂入音频块

        Args:
            audio_chunk: float32 音频数组

        Returns:
            如果语音结束，返回 STTResult；否则返回 None
        """
        if self._is_processing:
            return None

        result = self._vad.feed(audio_chunk)

        if result.is_complete and result.audio is not None:
            self._is_processing = True
            try:
                stt_result = self._stt.transcribe_sync(result.audio)
                return stt_result
            finally:
                self._is_processing = False
                self.reset()

        return None

    @property
    def stt(self) -> SenseVoiceSTT:
        """返回 STT 实例"""
        return self._stt

    @property
    def vad(self):
        """返回 VAD 实例"""
        return self._vad

    @property
    def is_speech(self) -> bool:
        """是否检测到语音"""
        return self._vad.has_speech

    def close(self) -> None:
        """释放资源"""
        self._stt.close()


# ============================================================
#  模块自测
# ============================================================

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("  CC_VisChat SenseVoiceSTT 模块 - 自测")
    print("=" * 60)

    # 检查依赖
    print("\n【检查依赖】")
    try:
        import funasr
        print(f"  ✅ funasr 已安装: {funasr.__version__}")
    except ImportError:
        print("  ❌ funasr 未安装")
        print("  请运行: pip install -U funasr modelscope")
        sys.exit(1)

    try:
        import modelscope
        print(f"  ✅ modelscope 已安装")
    except ImportError:
        print("  ❌ modelscope 未安装")
        print("  请运行: pip install -U modelscope")
        sys.exit(1)

    # 测试模型加载
    print("\n【测试模型加载】")
    stt = SenseVoiceSTT(STTConfig(device="cpu"))

    print("  正在加载模型 (首次加载需要下载，约 220MB)...")
    if stt.load_model():
        print("  ✅ 模型加载成功")
    else:
        print("  ❌ 模型加载失败")
        sys.exit(1)

    # 测试转写
    print("\n【测试转写】")

    # 生成测试音频 (440Hz 正弦波，模拟语音)
    sample_rate = 16000
    duration = 2.0
    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    test_audio = np.sin(2 * np.pi * 440 * t) * 0.3

    print(f"  测试音频: {len(test_audio)} 样本, {duration}s")
    print("  注意: 测试音频是正弦波，不是真实语音，识别结果可能为空或无意义")

    result = stt.transcribe_sync(test_audio)
    print(f"\n  识别结果:")
    print(f"    文本: '{result.text}'")
    print(f"    语言: {result.language}")
    print(f"    情感: {result.emotion.value}")
    print(f"    事件: {[e.value for e in result.events]}")

    # 清理
    stt.close()

    print("\n✅ 自测完成！")
    print("\n提示: 要测试真实语音识别，请使用实际的语音音频文件。")
