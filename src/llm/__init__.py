"""
CC_VisChat 视觉 LLM 模块

支持双模式:
- LMStudio (默认 - 隐私优先): 局域网内运行，数据不出网
- 本地反代 (可选 - 性能优先): 通过本地代理访问云端模型
"""

from .base import VisionLLMProvider, LLMConfig
from .lmstudio import LMStudioProvider
from .local_proxy import LocalProxyProvider
from .factory import LLMFactory, LLMManager

__all__ = [
    "VisionLLMProvider",
    "LLMConfig",
    "LMStudioProvider",
    "LocalProxyProvider",
    "LLMFactory",
    "LLMManager",
]
