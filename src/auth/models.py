"""
用户模型定义

包含用户、角色、会话等数据模型。
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class UserRole(str, Enum):
    """用户角色枚举"""
    ADMIN = "admin"
    USER = "user"


class User(BaseModel):
    """用户模型"""
    id: str = Field(..., description="用户唯一标识")
    username: str = Field(..., description="用户名")
    password_hash: str = Field(..., description="密码哈希 (bcrypt)")
    role: UserRole = Field(default=UserRole.USER, description="用户角色")
    display_name: str = Field(..., description="显示名称")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    last_login: Optional[datetime] = Field(default=None, description="最后登录时间")
    is_active: bool = Field(default=True, description="是否激活")

    class Config:
        use_enum_values = True


class UserSession(BaseModel):
    """用户会话模型"""
    token: str = Field(..., description="JWT Token")
    user_id: str = Field(..., description="用户ID")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    expires_at: datetime = Field(..., description="过期时间")
    ip_address: Optional[str] = Field(default=None, description="客户端IP地址")
    user_agent: Optional[str] = Field(default=None, description="客户端User-Agent")


class TokenData(BaseModel):
    """JWT Token 载荷数据"""
    sub: str = Field(..., description="主题 (用户ID)")
    username: str = Field(..., description="用户名")
    role: UserRole = Field(..., description="用户角色")
    exp: datetime = Field(..., description="过期时间")
    iat: datetime = Field(default_factory=datetime.utcnow, description="签发时间")


# ============ API 请求/响应模型 ============

class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=1, max_length=50, description="用户名")
    password: str = Field(..., min_length=1, max_length=128, description="密码")


class LoginResponse(BaseModel):
    """登录响应"""
    success: bool = Field(..., description="是否成功")
    token: Optional[str] = Field(default=None, description="JWT Token")
    user: Optional["UserPublic"] = Field(default=None, description="用户信息")
    error: Optional[str] = Field(default=None, description="错误信息")


class UserPublic(BaseModel):
    """用户公开信息 (不包含敏感数据)"""
    id: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    role: UserRole = Field(..., description="用户角色")
    display_name: str = Field(..., description="显示名称")
    created_at: datetime = Field(..., description="创建时间")
    last_login: Optional[datetime] = Field(default=None, description="最后登录时间")

    class Config:
        use_enum_values = True

    @classmethod
    def from_user(cls, user: User) -> "UserPublic":
        """从 User 模型创建公开信息"""
        return cls(
            id=user.id,
            username=user.username,
            role=user.role,
            display_name=user.display_name,
            created_at=user.created_at,
            last_login=user.last_login,
        )


class LogoutResponse(BaseModel):
    """登出响应"""
    success: bool = Field(..., description="是否成功")


class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = Field(default=False, description="是否成功")
    error: str = Field(..., description="错误信息")
    code: Optional[str] = Field(default=None, description="错误代码")


# 更新 LoginResponse 的前向引用
LoginResponse.model_rebuild()
