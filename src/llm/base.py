"""
视觉 LLM 抽象基类

定义所有 LLM 提供者必须实现的接口。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """LLM 配置类 - 支持运行时修改"""

    base_url: str
    model: str
    api_key: str = ""
    timeout: float = 120.0
    max_tokens: int = 4096
    temperature: float = 0.7

    # 额外配置项
    extra: Dict[str, Any] = field(default_factory=dict)

    def update(self, **kwargs) -> None:
        """动态更新配置"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                self.extra[key] = value

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "base_url": self.base_url,
            "model": self.model,
            "api_key": self.api_key,
            "timeout": self.timeout,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            **self.extra,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMConfig":
        """从字典创建配置"""
        known_fields = {"base_url", "model", "api_key", "timeout", "max_tokens", "temperature"}
        known = {k: v for k, v in data.items() if k in known_fields}
        extra = {k: v for k, v in data.items() if k not in known_fields}
        return cls(**known, extra=extra)


@dataclass
class Message:
    """消息模型"""
    role: str  # system, user, assistant
    content: str
    image_ref: Optional[str] = None  # 图片引用 (base64 或 URL)
    timestamp: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "role": self.role,
            "content": self.content,
        }


class VisionLLMProvider(ABC):
    """
    视觉 LLM 抽象基类

    所有 LLM 提供者都必须实现此接口。
    支持 OpenAI 兼容的多模态 API。
    """

    def __init__(self, config: LLMConfig):
        """
        初始化提供者

        Args:
            config: LLM 配置对象
        """
        self._config = config
        self._client = None

    @property
    def config(self) -> LLMConfig:
        """获取当前配置"""
        return self._config

    @property
    def model(self) -> str:
        """获取当前模型名"""
        return self._config.model

    @model.setter
    def model(self, value: str) -> None:
        """设置模型名"""
        self._config.model = value

    def update_config(self, **kwargs) -> None:
        """
        动态更新配置

        Args:
            **kwargs: 要更新的配置项
        """
        self._config.update(**kwargs)
        # 如果更新了 base_url 或 api_key，可能需要重新初始化客户端
        if "base_url" in kwargs or "api_key" in kwargs:
            self._reinitialize_client()

    def _reinitialize_client(self) -> None:
        """重新初始化客户端 (子类可覆盖)"""
        pass

    @abstractmethod
    async def analyze(
        self,
        image_base64: str,
        prompt: str,
        history: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> str:
        """
        分析图片并返回响应

        Args:
            image_base64: Base64 编码的图片数据
            prompt: 用户提示词
            history: 历史对话消息列表 (可选)
            **kwargs: 额外参数 (如 temperature, max_tokens 等)

        Returns:
            str: LLM 生成的响应文本

        Raises:
            ConnectionError: 连接失败
            ValueError: 参数无效
            Exception: 其他错误
        """
        pass

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        **kwargs
    ) -> str:
        """
        纯文本对话 (不含图片)

        Args:
            messages: 消息列表
            **kwargs: 额外参数

        Returns:
            str: LLM 生成的响应文本
        """
        pass

    @abstractmethod
    async def list_models(self) -> List[str]:
        """
        获取可用模型列表

        Returns:
            List[str]: 可用模型 ID 列表

        Raises:
            ConnectionError: 连接失败
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        健康检查 - 验证服务是否可用

        Returns:
            bool: 服务是否可用
        """
        pass

    async def close(self) -> None:
        """关闭客户端连接 (子类可覆盖)"""
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(base_url={self._config.base_url}, model={self._config.model})"
