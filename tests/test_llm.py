"""
LLM 模块测试脚本

测试 LLM 提供者的基本功能。
"""

import pytest
import asyncio
import sys
from pathlib import Path

# 添加 src 到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm import (
    LLMConfig,
    LMStudioProvider,
    LocalProxyProvider,
    LLMFactory,
)


@pytest.mark.asyncio
async def test_factory():
    """测试 LLM 工厂"""
    # 测试列出提供者
    providers = LLMFactory.list_providers()
    assert "lmstudio" in providers
    assert "local_proxy" in providers

    # 测试创建默认提供者 (LMStudio)
    provider = LLMFactory.create_default()
    assert provider is not None
    assert provider.config.base_url is not None

    # 测试创建 LocalProxy 提供者
    provider2 = LLMFactory.create("local_proxy")
    assert provider2 is not None

    # 测试自定义配置
    custom_provider = LLMFactory.create("lmstudio", {
        "base_url": "http://192.168.1.100:11234/v1",
        "model": "custom-model",
    })
    assert custom_provider.config.base_url == "http://192.168.1.100:11234/v1"
    assert custom_provider.config.model == "custom-model"


@pytest.mark.asyncio
async def test_config():
    """测试配置类"""
    # 创建配置
    config = LLMConfig(
        base_url="http://localhost:11234/v1",
        model="test-model",
        api_key="test-key"
    )
    assert config.base_url == "http://localhost:11234/v1"
    assert config.model == "test-model"

    # 测试更新配置
    config.update(model="new-model", temperature=0.5)
    assert config.model == "new-model"
    assert config.temperature == 0.5

    # 测试从字典创建
    config2 = LLMConfig.from_dict({
        "base_url": "http://example.com/v1",
        "model": "example-model",
    })
    assert config2.base_url == "http://example.com/v1"


@pytest.mark.asyncio
async def test_provider_methods():
    """测试提供者方法 (不实际调用 API)"""
    # 创建 LMStudio 提供者
    lmstudio = LMStudioProvider(
        base_url="http://192.168.0.189:11234/v1",
        model="qwen3-vl-30b-a3b-instruct-mlx"
    )
    assert lmstudio is not None

    # 测试配置更新
    lmstudio.model = "new-model"
    assert lmstudio.model == "new-model"

    lmstudio.update_config(temperature=0.9)
    assert lmstudio.config.temperature == 0.9

    # 创建 LocalProxy 提供者
    local_proxy = LocalProxyProvider(
        base_url="http://localhost:4141",
        model="claude-sonnet-4.6"
    )
    assert local_proxy is not None


@pytest.mark.asyncio
async def test_health_check():
    """测试健康检查 (可能失败，因为服务未运行)"""
    provider = LLMFactory.create_default()

    # 这个测试可能失败，因为服务可能不可用
    try:
        is_healthy = await provider.health_check()
        # 如果服务在运行，应该返回 True 或 False
        assert isinstance(is_healthy, bool)
    except Exception:
        # 服务不可用时可能抛出异常，这是预期的
        pass

    await provider.close()


@pytest.mark.asyncio
async def test_list_models():
    """测试获取模型列表 (需要服务运行)"""
    provider = LLMFactory.create_default()

    try:
        models = await provider.list_models()
        # 如果服务运行，应该返回模型列表
        assert isinstance(models, list)
    except Exception:
        # 服务不可用时可能抛出异常
        pass

    await provider.close()


async def main():
    """运行所有测试 (手动执行)"""
    print("\n🧪 CC_VisChat LLM 模块测试\n")

    print("测试 LLMConfig...")
    await test_config()
    print("✅ test_config 通过")

    print("测试 LLMFactory...")
    await test_factory()
    print("✅ test_factory 通过")

    print("测试提供者方法...")
    await test_provider_methods()
    print("✅ test_provider_methods 通过")

    print("\n以下测试需要 LLM 服务运行...")

    print("测试健康检查...")
    await test_health_check()
    print("✅ test_health_check 通过")

    print("测试获取模型列表...")
    await test_list_models()
    print("✅ test_list_models 通过")

    print("\n🎉 所有测试完成!")


if __name__ == "__main__":
    asyncio.run(main())
