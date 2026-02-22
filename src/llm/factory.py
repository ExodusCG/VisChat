"""
LLM 工厂模块

提供统一的 LLM 提供者创建和管理接口。
支持从配置文件加载和运行时切换。
"""

import logging
from typing import Dict, Any, Optional, Type, List
from pathlib import Path
import yaml

from .base import VisionLLMProvider, LLMConfig
from .lmstudio import LMStudioProvider
from .local_proxy import LocalProxyProvider

logger = logging.getLogger(__name__)


# 提供者注册表
PROVIDER_REGISTRY: Dict[str, Type[VisionLLMProvider]] = {
    "lmstudio": LMStudioProvider,
    "local_proxy": LocalProxyProvider,
}


class LLMFactory:
    """
    LLM 工厂类

    统一管理 LLM 提供者的创建和配置。
    支持:
        - 从代码创建提供者
        - 从配置文件加载
        - 运行时切换提供者
        - 注册自定义提供者

    Example:
        ```python
        # 方式1: 直接创建
        provider = LLMFactory.create("lmstudio", {
            "base_url": "http://192.168.0.189:11234/v1",
            "model": "qwen3-vl-30b-a3b-instruct-mlx"
        })

        # 方式2: 从配置文件加载
        provider = LLMFactory.from_config("config/config.yaml")

        # 方式3: 使用默认配置
        provider = LLMFactory.create_default()
        ```
    """

    # 默认配置
    DEFAULT_PROVIDER = "lmstudio"
    DEFAULT_CONFIGS = {
        "lmstudio": {
            "base_url": "http://192.168.0.189:11234/v1",
            "model": "qwen3-vl-30b-a3b-instruct-mlx",
            "api_key": "lm-studio",
        },
        "local_proxy": {
            "base_url": "http://localhost:4141",
            "model": "claude-sonnet-4.6",
            "api_key": "",
        },
    }

    @classmethod
    def create(
        cls,
        provider: str,
        config: Optional[Dict[str, Any]] = None
    ) -> VisionLLMProvider:
        """
        创建 LLM 提供者实例

        Args:
            provider: 提供者类型 ("lmstudio" 或 "local_proxy")
            config: 配置字典

        Returns:
            VisionLLMProvider: LLM 提供者实例

        Raises:
            ValueError: 未知的提供者类型
        """
        if provider not in PROVIDER_REGISTRY:
            available = list(PROVIDER_REGISTRY.keys())
            raise ValueError(
                f"未知的 LLM 提供者: {provider}. 可用: {available}"
            )

        # 合并默认配置
        final_config = cls.DEFAULT_CONFIGS.get(provider, {}).copy()
        if config:
            final_config.update(config)

        # 创建配置对象
        llm_config = LLMConfig.from_dict(final_config)

        # 创建提供者实例
        provider_class = PROVIDER_REGISTRY[provider]
        instance = provider_class(config=llm_config)

        logger.info(f"Created LLM provider: {provider} -> {llm_config.base_url}")
        return instance

    @classmethod
    def create_default(cls) -> VisionLLMProvider:
        """
        使用默认配置创建 LMStudio 提供者

        Returns:
            VisionLLMProvider: 默认 LLM 提供者 (LMStudio)
        """
        return cls.create(cls.DEFAULT_PROVIDER)

    @classmethod
    def from_config(
        cls,
        config_path: str,
        provider_override: Optional[str] = None
    ) -> VisionLLMProvider:
        """
        从配置文件加载 LLM 提供者

        Args:
            config_path: 配置文件路径
            provider_override: 覆盖配置文件中的 active_provider

        Returns:
            VisionLLMProvider: LLM 提供者实例

        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置格式错误
        """
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(config_file, "r", encoding="utf-8") as f:
            full_config = yaml.safe_load(f)

        # 获取 vision_llm 配置段
        llm_config = full_config.get("vision_llm", {})

        # 确定使用哪个提供者
        provider = provider_override or llm_config.get("active_provider", cls.DEFAULT_PROVIDER)

        # 获取该提供者的配置
        provider_config = llm_config.get(provider, {})

        return cls.create(provider, provider_config)

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> VisionLLMProvider:
        """
        从配置字典创建 LLM 提供者

        配置格式:
        ```python
        {
            "active_provider": "lmstudio",
            "lmstudio": {
                "base_url": "http://...",
                "model": "...",
                "api_key": "..."
            },
            "local_proxy": {
                ...
            }
        }
        ```

        Args:
            config: 配置字典

        Returns:
            VisionLLMProvider: LLM 提供者实例
        """
        provider = config.get("active_provider", cls.DEFAULT_PROVIDER)
        provider_config = config.get(provider, {})
        return cls.create(provider, provider_config)

    @classmethod
    def register_provider(
        cls,
        name: str,
        provider_class: Type[VisionLLMProvider]
    ) -> None:
        """
        注册自定义 LLM 提供者

        Args:
            name: 提供者名称
            provider_class: 提供者类 (必须继承 VisionLLMProvider)
        """
        if not issubclass(provider_class, VisionLLMProvider):
            raise TypeError(
                f"{provider_class.__name__} 必须继承 VisionLLMProvider"
            )

        PROVIDER_REGISTRY[name] = provider_class
        logger.info(f"Registered LLM provider: {name}")

    @classmethod
    def list_providers(cls) -> list:
        """
        列出所有可用的提供者类型

        Returns:
            list: 提供者名称列表
        """
        return list(PROVIDER_REGISTRY.keys())


class LLMManager:
    """
    LLM 管理器 - 单例模式

    管理应用中的 LLM 提供者实例，支持运行时切换。

    Example:
        ```python
        manager = LLMManager()

        # 初始化
        await manager.initialize("config/config.yaml")

        # 使用
        response = await manager.analyze(image_base64, prompt)

        # 切换提供者
        await manager.switch_provider("local_proxy")
        ```
    """

    _instance: Optional["LLMManager"] = None

    def __new__(cls) -> "LLMManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._provider = None
            cls._instance._config = {}
        return cls._instance

    @property
    def provider(self) -> Optional[VisionLLMProvider]:
        """当前 LLM 提供者"""
        return self._provider

    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._provider is not None

    async def initialize(
        self,
        config_path: Optional[str] = None,
        config_dict: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        初始化 LLM 管理器

        Args:
            config_path: 配置文件路径
            config_dict: 配置字典 (优先于 config_path)
        """
        if config_dict:
            self._config = config_dict.get("vision_llm", config_dict)
            self._provider = LLMFactory.from_dict(self._config)
        elif config_path:
            self._provider = LLMFactory.from_config(config_path)
        else:
            self._provider = LLMFactory.create_default()

        logger.info(f"LLMManager initialized with: {self._provider}")

    async def switch_provider(
        self,
        provider: str,
        config: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        切换 LLM 提供者

        Args:
            provider: 提供者类型
            config: 可选的配置覆盖
        """
        # 关闭旧提供者
        if self._provider:
            await self._provider.close()

        # 创建新提供者
        if config:
            self._provider = LLMFactory.create(provider, config)
        else:
            # 使用存储的配置
            stored_config = self._config.get(provider, {})
            self._provider = LLMFactory.create(provider, stored_config)

        logger.info(f"Switched LLM provider to: {provider}")

    async def analyze(
        self,
        image_base64: str,
        prompt: str,
        history: Optional[list] = None,
        **kwargs
    ) -> str:
        """
        分析图片

        Args:
            image_base64: Base64 图片数据
            prompt: 提示词
            history: 对话历史
            **kwargs: 额外参数

        Returns:
            str: LLM 响应
        """
        if not self._provider:
            raise RuntimeError("LLMManager 未初始化")

        return await self._provider.analyze(image_base64, prompt, history, **kwargs)

    async def chat(self, messages: list, **kwargs) -> str:
        """
        纯文本对话
        """
        if not self._provider:
            raise RuntimeError("LLMManager 未初始化")

        return await self._provider.chat(messages, **kwargs)

    async def chat_stream(self, messages: list, **kwargs):
        """
        流式文本对话

        Yields:
            str: 每次生成的文本片段
        """
        if not self._provider:
            raise RuntimeError("LLMManager 未初始化")

        if hasattr(self._provider, 'chat_stream'):
            async for chunk in self._provider.chat_stream(messages, **kwargs):
                yield chunk
        else:
            # 回退到非流式
            result = await self._provider.chat(messages, **kwargs)
            yield result

    async def analyze_stream(
        self,
        image_base64: str,
        prompt: str,
        history: Optional[list] = None,
        **kwargs
    ):
        """
        流式图片分析

        Yields:
            str: 每次生成的文本片段
        """
        if not self._provider:
            raise RuntimeError("LLMManager 未初始化")

        if hasattr(self._provider, 'analyze_stream'):
            async for chunk in self._provider.analyze_stream(image_base64, prompt, history, **kwargs):
                yield chunk
        else:
            # 回退到非流式
            result = await self._provider.analyze(image_base64, prompt, history, **kwargs)
            yield result

    async def list_models(self) -> list:
        """获取可用模型列表"""
        if not self._provider:
            raise RuntimeError("LLMManager 未初始化")

        return await self._provider.list_models()

    async def health_check(self) -> bool:
        """健康检查"""
        if not self._provider:
            return False

        return await self._provider.health_check()

    async def close(self) -> None:
        """关闭管理器"""
        if self._provider:
            await self._provider.close()
            self._provider = None
