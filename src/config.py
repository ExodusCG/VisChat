"""
配置加载模块
支持 YAML 配置文件和环境变量覆盖
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 默认配置路径
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
DEFAULT_USERS_PATH = PROJECT_ROOT / "config" / "users.yaml"


class Config:
    """配置管理类"""

    _instance: Optional["Config"] = None
    _config: Dict[str, Any] = {}
    _users: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._config:
            self.reload()

    def reload(self, config_path: Optional[str] = None, users_path: Optional[str] = None):
        """重新加载配置"""
        config_file = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        users_file = Path(users_path) if users_path else DEFAULT_USERS_PATH

        # 加载主配置
        self._config = self._load_yaml(config_file)
        logger.info(f"已加载配置文件: {config_file}")

        # 加载用户配置
        self._users = self._load_yaml(users_file)
        logger.info(f"已加载用户配置: {users_file}")

        # 应用环境变量覆盖
        self._apply_env_overrides()

    def _load_yaml(self, file_path: Path) -> Dict[str, Any]:
        """加载 YAML 文件"""
        try:
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            else:
                logger.warning(f"配置文件不存在: {file_path}")
                return {}
        except Exception as e:
            logger.error(f"加载配置文件失败 {file_path}: {e}")
            return {}

    def _apply_env_overrides(self):
        """应用环境变量覆盖"""
        # LMStudio API Key
        if os.environ.get("LMSTUDIO_API_KEY"):
            self._config.setdefault("vision_llm", {}).setdefault("lmstudio", {})
            self._config["vision_llm"]["lmstudio"]["api_key"] = os.environ["LMSTUDIO_API_KEY"]

        # Local Proxy API Key
        if os.environ.get("LOCAL_PROXY_API_KEY"):
            self._config.setdefault("vision_llm", {}).setdefault("local_proxy", {})
            self._config["vision_llm"]["local_proxy"]["api_key"] = os.environ["LOCAL_PROXY_API_KEY"]

        # JWT Secret Key
        if os.environ.get("JWT_SECRET_KEY"):
            self._config.setdefault("security", {})
            self._config["security"]["secret_key"] = os.environ["JWT_SECRET_KEY"]

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项，支持点号分隔的嵌套访问"""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def set(self, key: str, value: Any):
        """设置配置项"""
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            config = config.setdefault(k, {})
        config[keys[-1]] = value

    @property
    def server(self) -> Dict[str, Any]:
        """服务器配置"""
        return self._config.get("server", {
            "host": "0.0.0.0",
            "port": 5180,
            "debug": False
        })

    @property
    def ssl(self) -> Dict[str, Any]:
        """SSL 配置"""
        return self._config.get("ssl", {
            "enabled": True,
            "cert_file": "ssl/cert.pem",
            "key_file": "ssl/key.pem"
        })

    @property
    def language(self) -> Dict[str, Any]:
        """语言配置"""
        return self._config.get("language", {
            "primary": "zh",
            "stt_language": "zh",
            "tts_voice": "zh-CN-XiaoxiaoNeural"
        })

    @property
    def stt(self) -> Dict[str, Any]:
        """STT 配置"""
        return self._config.get("stt", {
            "model": "iic/SenseVoiceSmall",
            "device": "cpu",
            "language": "auto",
            "vad_threshold": 0.5,
            "silence_duration_ms": 800
        })

    @property
    def tts(self) -> Dict[str, Any]:
        """TTS 配置"""
        return self._config.get("tts", {
            "backend": "edge_tts",
            "fallback": "gtts",
            "speed": 1.0
        })

    @property
    def vision_llm(self) -> Dict[str, Any]:
        """视觉 LLM 配置"""
        return self._config.get("vision_llm", {
            "active_provider": "lmstudio",
            "lmstudio": {
                "base_url": "http://192.168.0.189:11234/v1",
                "default_model": "qwen3-vl-30b-a3b-instruct-mlx",
                "api_key": "lm-studio"
            },
            "local_proxy": {
                "base_url": "http://localhost:4141",
                "default_model": "claude-sonnet-4.6",
                "api_key": ""
            }
        })

    @property
    def memory(self) -> Dict[str, Any]:
        """记忆配置"""
        return self._config.get("memory", {
            "max_context_messages": 20,
            "compact_threshold": 15,
            "enable_long_term": True
        })

    @property
    def audio(self) -> Dict[str, Any]:
        """音频配置"""
        return self._config.get("audio", {
            "sample_rate": 16000,
            "chunk_duration_ms": 500,
            "output_format": "pcm"
        })

    @property
    def users(self) -> Dict[str, Any]:
        """用户配置"""
        return self._users

    @property
    def security(self) -> Dict[str, Any]:
        """安全配置"""
        return self._config.get("security", {
            "enabled": True,
            "secret_key": "cc_vischat_secret_key_change_me_in_production",
            "token_expire_hours": 24
        })

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        users_list = self._users.get("users", [])
        for user in users_list:
            if user.get("username") == username:
                return user
        return None

    def get_all_users(self) -> list:
        """获取所有用户"""
        return self._users.get("users", [])

    def update_user_password(self, username: str, new_password_hash: str) -> bool:
        """更新用户密码"""
        users_list = self._users.get("users", [])
        for user in users_list:
            if user.get("username") == username:
                user["password_hash"] = new_password_hash
                # 保存到文件
                self._save_users()
                return True
        return False

    def _save_users(self):
        """保存用户配置到文件"""
        try:
            with open(DEFAULT_USERS_PATH, "w", encoding="utf-8") as f:
                yaml.dump(self._users, f, allow_unicode=True, default_flow_style=False)
            logger.info("用户配置已保存")
        except Exception as e:
            logger.error(f"保存用户配置失败: {e}")


# 全局配置实例
config = Config()


def get_config() -> Config:
    """获取配置实例"""
    return config


def reload_config(config_path: Optional[str] = None, users_path: Optional[str] = None):
    """重新加载配置"""
    config.reload(config_path, users_path)
