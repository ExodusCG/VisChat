"""
认证服务

提供用户验证、Token 生成、密码哈希等核心认证功能。
"""

import os
import uuid
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List

import bcrypt
import yaml
from jose import jwt, JWTError

from .models import User, UserRole, UserSession, TokenData, UserPublic


class AuthService:
    """认证服务类"""

    # JWT 配置
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_HOURS = 24  # Token 有效期 24 小时

    def __init__(
        self,
        secret_key: Optional[str] = None,
        users_config_path: str = "config/users.yaml",
    ):
        """
        初始化认证服务

        Args:
            secret_key: JWT 签名密钥，如果不提供则从环境变量获取或自动生成
            users_config_path: 用户配置文件路径
        """
        # JWT 密钥
        self._secret_key = secret_key or os.getenv("JWT_SECRET_KEY") or self._generate_secret_key()

        # 用户存储 (从 YAML 加载)
        self._users: Dict[str, User] = {}
        self._users_config_path = users_config_path

        # 活跃会话存储 (内存中)
        self._active_sessions: Dict[str, UserSession] = {}

        # 加载用户配置
        self._load_users()

    def _generate_secret_key(self) -> str:
        """生成随机密钥"""
        return secrets.token_urlsafe(32)

    @property
    def secret_key(self) -> str:
        """获取 JWT 密钥"""
        return self._secret_key

    # ============ 密码处理 ============

    def hash_password(self, password: str) -> str:
        """
        对密码进行哈希处理

        Args:
            password: 明文密码

        Returns:
            bcrypt 哈希后的密码
        """
        return bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        验证密码

        Args:
            plain_password: 明文密码
            hashed_password: 哈希后的密码

        Returns:
            密码是否匹配
        """
        try:
            return bcrypt.checkpw(
                plain_password.encode('utf-8'),
                hashed_password.encode('utf-8')
            )
        except Exception:
            return False

    # ============ 用户管理 ============

    def _load_users(self) -> None:
        """从 YAML 配置文件加载用户"""
        config_path = Path(self._users_config_path)

        if not config_path.exists():
            # 如果配置文件不存在，创建默认管理员
            self._create_default_users()
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if not config or "users" not in config:
                self._create_default_users()
                return

            for user_data in config.get("users", []):
                # 支持两种密码格式:
                # 1. password_hash: 已哈希的密码 (生产环境)
                # 2. password: 明文密码 (开发环境，会自动哈希)
                if "password_hash" in user_data:
                    password_hash = user_data["password_hash"]
                elif "password" in user_data:
                    # 开发模式: 将明文密码哈希
                    password_hash = self.hash_password(user_data["password"])
                else:
                    print(f"[AuthService] 用户 {user_data.get('username')} 缺少密码配置，跳过")
                    continue

                user = User(
                    id=user_data.get("id", str(uuid.uuid4())),
                    username=user_data["username"],
                    password_hash=password_hash,
                    role=UserRole(user_data.get("role", "user")),
                    display_name=user_data.get("display_name", user_data["username"]),
                    created_at=datetime.fromisoformat(user_data["created_at"])
                        if "created_at" in user_data else datetime.utcnow(),
                    last_login=datetime.fromisoformat(user_data["last_login"])
                        if user_data.get("last_login") else None,
                    is_active=user_data.get("is_active", True),
                )
                self._users[user.username] = user

            print(f"[AuthService] 已加载 {len(self._users)} 个用户")

        except Exception as e:
            print(f"[AuthService] 加载用户配置失败: {e}")
            self._create_default_users()

    def _create_default_users(self) -> None:
        """创建默认用户"""
        # 创建默认管理员
        admin = User(
            id=str(uuid.uuid4()),
            username="admin",
            password_hash=self.hash_password("admin123"),  # 默认密码，应该修改
            role=UserRole.ADMIN,
            display_name="管理员",
            created_at=datetime.utcnow(),
            is_active=True,
        )
        self._users["admin"] = admin

        # 保存到配置文件
        self._save_users()
        print("[AuthService] 已创建默认管理员账户 (用户名: admin, 密码: admin123)")

    def _save_users(self) -> None:
        """保存用户配置到 YAML 文件"""
        config_path = Path(self._users_config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        users_data = []
        for user in self._users.values():
            users_data.append({
                "id": user.id,
                "username": user.username,
                "password_hash": user.password_hash,
                "role": user.role.value if isinstance(user.role, UserRole) else user.role,
                "display_name": user.display_name,
                "created_at": user.created_at.isoformat(),
                "last_login": user.last_login.isoformat() if user.last_login else None,
                "is_active": user.is_active,
            })

        config = {"users": users_data}

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    def get_user_by_username(self, username: str) -> Optional[User]:
        """
        通过用户名获取用户

        Args:
            username: 用户名

        Returns:
            用户对象，如果不存在返回 None
        """
        return self._users.get(username)

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """
        通过用户ID获取用户

        Args:
            user_id: 用户ID

        Returns:
            用户对象，如果不存在返回 None
        """
        for user in self._users.values():
            if user.id == user_id:
                return user
        return None

    def get_all_users(self) -> List[User]:
        """获取所有用户列表"""
        return list(self._users.values())

    def create_user(
        self,
        username: str,
        password: str,
        role: UserRole = UserRole.USER,
        display_name: Optional[str] = None,
    ) -> User:
        """
        创建新用户

        Args:
            username: 用户名
            password: 明文密码
            role: 用户角色
            display_name: 显示名称

        Returns:
            创建的用户对象

        Raises:
            ValueError: 用户名已存在
        """
        if username in self._users:
            raise ValueError(f"用户名 '{username}' 已存在")

        user = User(
            id=str(uuid.uuid4()),
            username=username,
            password_hash=self.hash_password(password),
            role=role,
            display_name=display_name or username,
            created_at=datetime.utcnow(),
            is_active=True,
        )

        self._users[username] = user
        self._save_users()

        return user

    def update_user(self, user_id: str, **kwargs) -> Optional[User]:
        """
        更新用户信息

        Args:
            user_id: 用户ID
            **kwargs: 要更新的字段

        Returns:
            更新后的用户对象
        """
        user = self.get_user_by_id(user_id)
        if not user:
            return None

        # 如果更新密码，需要重新哈希
        if "password" in kwargs:
            kwargs["password_hash"] = self.hash_password(kwargs.pop("password"))

        # 更新字段
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)

        self._save_users()
        return user

    def delete_user(self, user_id: str) -> bool:
        """
        删除用户

        Args:
            user_id: 用户ID

        Returns:
            是否删除成功
        """
        user = self.get_user_by_id(user_id)
        if not user:
            return False

        del self._users[user.username]
        self._save_users()
        return True

    # ============ 认证验证 ============

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        验证用户凭据

        Args:
            username: 用户名
            password: 明文密码

        Returns:
            验证通过返回用户对象，否则返回 None
        """
        user = self.get_user_by_username(username)

        if not user:
            return None

        if not user.is_active:
            return None

        if not self.verify_password(password, user.password_hash):
            return None

        return user

    # ============ Token 管理 ============

    def create_access_token(
        self,
        user: User,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """
        创建 JWT Access Token

        Args:
            user: 用户对象
            expires_delta: 过期时间增量，默认 24 小时

        Returns:
            JWT Token 字符串
        """
        if expires_delta is None:
            expires_delta = timedelta(hours=self.ACCESS_TOKEN_EXPIRE_HOURS)

        now = datetime.utcnow()
        expire = now + expires_delta

        payload = {
            "sub": user.id,
            "username": user.username,
            "role": user.role.value if isinstance(user.role, UserRole) else user.role,
            "exp": expire,
            "iat": now,
        }

        token = jwt.encode(payload, self._secret_key, algorithm=self.ALGORITHM)
        return token

    def decode_token(self, token: str) -> Optional[TokenData]:
        """
        解码并验证 JWT Token

        Args:
            token: JWT Token 字符串

        Returns:
            Token 数据对象，如果无效返回 None
        """
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[self.ALGORITHM])

            token_data = TokenData(
                sub=payload["sub"],
                username=payload["username"],
                role=UserRole(payload["role"]),
                exp=datetime.fromtimestamp(payload["exp"]),
                iat=datetime.fromtimestamp(payload["iat"]),
            )

            # 检查是否过期
            if token_data.exp < datetime.utcnow():
                return None

            return token_data

        except JWTError:
            return None
        except Exception:
            return None

    def verify_token(self, token: str) -> Optional[User]:
        """
        验证 Token 并返回对应用户

        Args:
            token: JWT Token 字符串

        Returns:
            对应的用户对象，如果无效返回 None
        """
        token_data = self.decode_token(token)
        if not token_data:
            return None

        user = self.get_user_by_id(token_data.sub)
        if not user or not user.is_active:
            return None

        return user

    # ============ 会话管理 ============

    def create_session(
        self,
        user: User,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserSession:
        """
        创建用户会话

        Args:
            user: 用户对象
            ip_address: 客户端IP
            user_agent: 客户端UA

        Returns:
            会话对象
        """
        token = self.create_access_token(user)
        expires_at = datetime.utcnow() + timedelta(hours=self.ACCESS_TOKEN_EXPIRE_HOURS)

        session = UserSession(
            token=token,
            user_id=user.id,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # 存储活跃会话
        self._active_sessions[token] = session

        # 更新用户最后登录时间
        user.last_login = datetime.utcnow()
        self._save_users()

        return session

    def invalidate_session(self, token: str) -> bool:
        """
        使会话失效 (登出)

        Args:
            token: JWT Token

        Returns:
            是否成功
        """
        if token in self._active_sessions:
            del self._active_sessions[token]
            return True
        return True  # 即使不在活跃会话中也返回成功

    def is_session_valid(self, token: str) -> bool:
        """
        检查会话是否有效

        Args:
            token: JWT Token

        Returns:
            会话是否有效
        """
        # 首先验证 Token 本身
        if not self.verify_token(token):
            return False

        # 检查是否在活跃会话中 (可选，用于支持主动登出)
        # 如果不在活跃会话中，但 Token 有效，仍然允许访问
        # 这样可以支持无状态验证
        return True

    def get_active_sessions_count(self) -> int:
        """获取活跃会话数量"""
        # 清理过期会话
        now = datetime.utcnow()
        expired = [
            token for token, session in self._active_sessions.items()
            if session.expires_at < now
        ]
        for token in expired:
            del self._active_sessions[token]

        return len(self._active_sessions)

    # ============ 登录/登出 ============

    def login(
        self,
        username: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[UserPublic], Optional[str]]:
        """
        用户登录

        Args:
            username: 用户名
            password: 密码
            ip_address: 客户端IP
            user_agent: 客户端UA

        Returns:
            (token, user_public, error) 元组
        """
        user = self.authenticate_user(username, password)

        if not user:
            return None, None, "Invalid credentials"

        session = self.create_session(user, ip_address, user_agent)
        user_public = UserPublic.from_user(user)

        return session.token, user_public, None

    def logout(self, token: str) -> bool:
        """
        用户登出

        Args:
            token: JWT Token

        Returns:
            是否成功
        """
        return self.invalidate_session(token)


# 全局认证服务实例
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """获取全局认证服务实例"""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


def init_auth_service(
    secret_key: Optional[str] = None,
    users_config_path: str = "config/users.yaml",
) -> AuthService:
    """
    初始化全局认证服务

    Args:
        secret_key: JWT 密钥
        users_config_path: 用户配置文件路径

    Returns:
        认证服务实例
    """
    global _auth_service
    _auth_service = AuthService(
        secret_key=secret_key,
        users_config_path=users_config_path,
    )
    return _auth_service
