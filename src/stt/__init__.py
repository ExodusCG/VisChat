"""
CC_VisChat - STT (语音转文字) 模块

使用 SenseVoiceSmall 模型进行语音识别，支持：
- 50+ 语言自动识别
- 情感识别
- 声学事件检测
- CPU / GPU 运行

模块组成：
- sensevoice.py: SenseVoiceSmall STT 后端
- vad.py: 语音活动检测 (VAD)
"""

from .sensevoice import SenseVoiceSTT, STTConfig, STTResult, StreamingSTT
from .vad import VAD, VADConfig, VADState, StreamingVAD

__all__ = [
    "SenseVoiceSTT",
    "STTConfig",
    "STTResult",
    "StreamingSTT",
    "VAD",
    "VADConfig",
    "VADState",
    "StreamingVAD",
]
