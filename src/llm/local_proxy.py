"""
本地反代 视觉 LLM 提供者

可选模式 - 性能优先
- 通过本地代理服务访问云端模型
- 使用 OpenAI 兼容 API
- 默认连接: http://localhost:4141
- 默认模型: claude-sonnet-4.6
"""

import logging
from typing import List, Optional, Dict, Any

from openai import AsyncOpenAI, APIError, APIConnectionError

from .base import VisionLLMProvider, LLMConfig

logger = logging.getLogger(__name__)


# 默认配置
DEFAULT_BASE_URL = "http://localhost:4141"
DEFAULT_MODEL = "claude-sonnet-4.6"
DEFAULT_API_KEY = ""  # 本地反代通常不需要 key


class LocalProxyProvider(VisionLLMProvider):
    """
    本地反代 视觉 LLM 提供者

    通过本地代理服务 (如 one-api, new-api 等) 访问各类云端模型。
    适用于追求性能和模型能力的场景。

    Features:
        - 多模态图片分析
        - 对话历史支持
        - 动态模型列表获取
        - 配置热更新
        - 支持多种后端模型 (Claude, GPT-4V 等)

    Example:
        ```python
        config = LLMConfig(
            base_url="http://localhost:4141",
            model="claude-sonnet-4.6",
            api_key=""
        )
        provider = LocalProxyProvider(config)

        # 分析图片
        response = await provider.analyze(
            image_base64="...",
            prompt="描述这张图片"
        )
        ```
    """

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        初始化本地反代提供者

        Args:
            config: LLM 配置对象 (优先使用)
            base_url: API 基础 URL (当 config 为 None 时使用)
            model: 模型名称 (当 config 为 None 时使用)
            api_key: API 密钥 (当 config 为 None 时使用)
        """
        if config is None:
            config = LLMConfig(
                base_url=base_url or DEFAULT_BASE_URL,
                model=model or DEFAULT_MODEL,
                api_key=api_key if api_key is not None else DEFAULT_API_KEY,
            )

        super().__init__(config)
        self._init_client()

    def _init_client(self) -> None:
        """初始化 OpenAI 客户端"""
        # 本地反代可能不需要 /v1 后缀，根据具体实现调整
        base_url = self._config.base_url
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=self._config.api_key or "not-needed",  # 某些代理需要非空 key
            timeout=self._config.timeout,
        )
        logger.info(f"LocalProxy client initialized: {base_url}")

    def _reinitialize_client(self) -> None:
        """重新初始化客户端"""
        self._init_client()

    async def analyze(
        self,
        image_base64: str,
        prompt: str,
        history: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> str:
        """
        分析图片并返回响应

        支持 Claude 和其他视觉模型的图片分析。

        Args:
            image_base64: Base64 编码的图片数据 (不含 data:image 前缀)
            prompt: 用户提示词
            history: 历史对话消息列表
            **kwargs: 额外参数
                - temperature: 采样温度
                - max_tokens: 最大生成长度
                - model: 覆盖默认模型
                - image_media_type: 图片 MIME 类型 (默认 image/jpeg)

        Returns:
            str: LLM 生成的响应文本
        """
        # 构建消息列表
        messages = list(history) if history else []

        # 获取图片类型
        image_media_type = kwargs.pop("image_media_type", "image/jpeg")

        # 添加当前用户消息 (图片 + 文本)
        # OpenAI 兼容格式
        user_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image_media_type};base64,{image_base64}"
                    }
                }
            ]
        }
        messages.append(user_message)

        # 准备请求参数
        model = kwargs.pop("model", self._config.model)
        temperature = kwargs.pop("temperature", self._config.temperature)
        max_tokens = kwargs.pop("max_tokens", self._config.max_tokens)

        try:
            logger.debug(f"Sending vision request to LocalProxy, model={model}")

            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            result = response.choices[0].message.content
            logger.debug(f"LocalProxy response received, length={len(result)}")

            return result

        except APIConnectionError as e:
            logger.error(f"LocalProxy connection failed: {e}")
            raise ConnectionError(f"无法连接到本地代理服务: {self._config.base_url}") from e
        except APIError as e:
            logger.error(f"LocalProxy API error: {e}")
            raise
        except Exception as e:
            logger.error(f"LocalProxy unexpected error: {e}")
            raise

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
        model = kwargs.pop("model", self._config.model)
        temperature = kwargs.pop("temperature", self._config.temperature)
        max_tokens = kwargs.pop("max_tokens", self._config.max_tokens)

        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            return response.choices[0].message.content

        except APIConnectionError as e:
            logger.error(f"LocalProxy connection failed: {e}")
            raise ConnectionError(f"无法连接到本地代理服务: {self._config.base_url}") from e
        except APIError as e:
            logger.error(f"LocalProxy API error: {e}")
            raise

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        **kwargs
    ):
        """
        流式文本对话 - 逐 token 返回

        Args:
            messages: 消息列表
            **kwargs: 额外参数

        Yields:
            str: 每次生成的文本片段
        """
        model = kwargs.pop("model", self._config.model)
        temperature = kwargs.pop("temperature", self._config.temperature)
        max_tokens = kwargs.pop("max_tokens", self._config.max_tokens)

        try:
            stream = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except APIConnectionError as e:
            logger.error(f"LocalProxy connection failed: {e}")
            raise ConnectionError(f"无法连接到本地代理服务: {self._config.base_url}") from e
        except APIError as e:
            logger.error(f"LocalProxy API error: {e}")
            raise

    async def analyze_stream(
        self,
        image_base64: str,
        prompt: str,
        history: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ):
        """
        流式图片分析 - 逐 token 返回

        Args:
            image_base64: Base64 编码的图片数据
            prompt: 用户提示词
            history: 历史对话消息列表
            **kwargs: 额外参数

        Yields:
            str: 每次生成的文本片段
        """
        # 构建消息列表
        messages = list(history) if history else []

        # 获取图片类型
        image_media_type = kwargs.pop("image_media_type", "image/jpeg")

        # 添加当前用户消息 (图片 + 文本)
        user_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image_media_type};base64,{image_base64}"
                    }
                }
            ]
        }
        messages.append(user_message)

        model = kwargs.pop("model", self._config.model)
        temperature = kwargs.pop("temperature", self._config.temperature)
        max_tokens = kwargs.pop("max_tokens", self._config.max_tokens)

        try:
            stream = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except APIConnectionError as e:
            logger.error(f"LocalProxy connection failed: {e}")
            raise ConnectionError(f"无法连接到本地代理服务: {self._config.base_url}") from e
        except APIError as e:
            logger.error(f"LocalProxy API error: {e}")
            raise

    async def list_models(self) -> List[str]:
        """
        获取本地代理可用模型列表

        注意: 并非所有代理服务都支持 /models 端点

        Returns:
            List[str]: 模型 ID 列表
        """
        try:
            response = await self._client.models.list()
            models = [m.id for m in response.data]
            logger.info(f"LocalProxy available models: {models}")
            return models

        except APIConnectionError as e:
            logger.error(f"Failed to list LocalProxy models: {e}")
            raise ConnectionError(f"无法获取模型列表: {self._config.base_url}") from e
        except APIError as e:
            # 某些代理可能不支持 list models
            logger.warning(f"LocalProxy may not support listing models: {e}")
            # 返回默认模型
            return [self._config.model]
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            raise

    async def health_check(self) -> bool:
        """
        健康检查 - 验证本地代理服务是否可用

        Returns:
            bool: 服务是否可用
        """
        try:
            # 尝试列出模型来验证连接
            await self._client.models.list()
            return True
        except Exception as e:
            logger.warning(f"LocalProxy health check failed: {e}")
            return False

    async def close(self) -> None:
        """关闭客户端连接"""
        if self._client:
            await self._client.close()
            logger.info("LocalProxy client closed")
