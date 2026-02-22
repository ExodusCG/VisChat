"""
CC_VisChat 认证授权模块

提供用户认证、JWT Token 管理、权限控制等功能。
"""

from .models import User, UserRole, UserSession, TokenData
from .service import AuthService
from .middleware import (
    get_current_user,
    get_current_active_user,
    require_admin,
    JWTAuthMiddleware,
)
from .routes import router as auth_router

__all__ = [
    # Models
    "User",
    "UserRole",
    "UserSession",
    "TokenData",
    # Service
    "AuthService",
    # Middleware
    "get_current_user",
    "get_current_active_user",
    "require_admin",
    "JWTAuthMiddleware",
    # Routes
    "auth_router",
]
