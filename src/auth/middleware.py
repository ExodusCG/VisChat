"""
FastAPI 认证中间件

提供 JWT 验证、权限检查等中间件功能。
"""

from typing import Optional, Callable
from functools import wraps

from fastapi import Request, Response, HTTPException, status, Depends, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware

from .models import User, UserRole, UserPublic
from .service import get_auth_service, AuthService


# HTTP Bearer 认证方案
bearer_scheme = HTTPBearer(auto_error=False)

# Cookie 名称
ACCESS_TOKEN_COOKIE = "access_token"


# ============ 依赖注入函数 ============

async def get_token_from_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[str]:
    """
    从请求中提取 Token

    优先级:
    1. Authorization Header (Bearer Token)
    2. HttpOnly Cookie

    Args:
        request: FastAPI 请求对象
        credentials: Bearer 认证凭据

    Returns:
        JWT Token 字符串，如果未找到返回 None
    """
    # 1. 尝试从 Authorization Header 获取
    if credentials:
        return credentials.credentials

    # 2. 尝试从 Cookie 获取
    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if token:
        return token

    return None


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(get_token_from_request),
) -> User:
    """
    获取当前已认证用户

    Args:
        request: FastAPI 请求对象
        token: JWT Token

    Returns:
        当前用户对象

    Raises:
        HTTPException: 未认证或 Token 无效
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_service = get_auth_service()
    user = auth_service.verify_token(token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 将用户信息存储到请求状态中，供后续使用
    request.state.user = user
    request.state.token = token

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    获取当前激活的用户

    Args:
        current_user: 当前用户

    Returns:
        当前用户对象

    Raises:
        HTTPException: 用户未激活
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    return current_user


async def get_optional_user(
    request: Request,
    token: Optional[str] = Depends(get_token_from_request),
) -> Optional[User]:
    """
    获取当前用户 (可选，不强制认证)

    Args:
        request: FastAPI 请求对象
        token: JWT Token

    Returns:
        当前用户对象，如果未认证返回 None
    """
    if not token:
        return None

    auth_service = get_auth_service()
    user = auth_service.verify_token(token)

    if user:
        request.state.user = user
        request.state.token = token

    return user


# ============ 权限检查依赖 ============

def require_role(required_role: UserRole):
    """
    创建角色检查依赖

    Args:
        required_role: 要求的角色

    Returns:
        依赖函数
    """
    async def role_checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        user_role = current_user.role
        if isinstance(user_role, str):
            user_role = UserRole(user_role)

        # Admin 拥有所有权限
        if user_role == UserRole.ADMIN:
            return current_user

        # 检查角色是否匹配
        if user_role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied",
            )

        return current_user

    return role_checker


async def require_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    要求管理员权限

    Args:
        current_user: 当前用户

    Returns:
        当前用户对象

    Raises:
        HTTPException: 无管理员权限
    """
    user_role = current_user.role
    if isinstance(user_role, str):
        user_role = UserRole(user_role)

    if user_role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required",
        )

    return current_user


# ============ 中间件类 ============

class JWTAuthMiddleware(BaseHTTPMiddleware):
    """
    JWT 认证中间件

    自动验证请求中的 Token，并将用户信息注入到请求状态中。
    不会阻止未认证的请求，只是尝试提取用户信息。
    """

    # 不需要认证的路径
    PUBLIC_PATHS = {
        "/",
        "/api/auth/login",
        "/api/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    }

    # 静态资源路径前缀
    STATIC_PREFIXES = {
        "/static/",
        "/favicon.ico",
    }

    def __init__(self, app, auth_service: Optional[AuthService] = None):
        super().__init__(app)
        self._auth_service = auth_service

    @property
    def auth_service(self) -> AuthService:
        """获取认证服务"""
        if self._auth_service is None:
            return get_auth_service()
        return self._auth_service

    async def dispatch(self, request: Request, call_next) -> Response:
        """处理请求"""
        # 检查是否是公开路径
        path = request.url.path

        if self._is_public_path(path):
            return await call_next(request)

        # 尝试提取 Token
        token = await self._extract_token(request)

        if token:
            # 验证 Token
            user = self.auth_service.verify_token(token)
            if user:
                # 将用户信息注入到请求状态
                request.state.user = user
                request.state.token = token

        # 继续处理请求
        response = await call_next(request)
        return response

    def _is_public_path(self, path: str) -> bool:
        """检查是否是公开路径"""
        # 精确匹配
        if path in self.PUBLIC_PATHS:
            return True

        # 前缀匹配
        for prefix in self.STATIC_PREFIXES:
            if path.startswith(prefix):
                return True

        return False

    async def _extract_token(self, request: Request) -> Optional[str]:
        """从请求中提取 Token"""
        # 1. 从 Authorization Header 获取
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]

        # 2. 从 Cookie 获取
        token = request.cookies.get(ACCESS_TOKEN_COOKIE)
        if token:
            return token

        # 3. 从查询参数获取 (用于 WebSocket)
        token = request.query_params.get("token")
        if token:
            return token

        return None


# ============ Cookie 辅助函数 ============

def set_auth_cookie(response: Response, token: str, max_age: int = 86400) -> None:
    """
    设置认证 Cookie

    Args:
        response: FastAPI 响应对象
        token: JWT Token
        max_age: Cookie 有效期 (秒)，默认 24 小时
    """
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        max_age=max_age,
        httponly=True,  # 防止 XSS
        samesite="lax",  # 防止 CSRF
        secure=False,  # 开发环境设为 False，生产环境应设为 True
    )


def clear_auth_cookie(response: Response) -> None:
    """
    清除认证 Cookie

    Args:
        response: FastAPI 响应对象
    """
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE,
        httponly=True,
        samesite="lax",
    )


# ============ WebSocket 认证 ============

async def authenticate_websocket(
    token: Optional[str] = None,
    auth_service: Optional[AuthService] = None,
) -> Optional[User]:
    """
    验证 WebSocket 连接的 Token

    Args:
        token: JWT Token (通常从查询参数获取)
        auth_service: 认证服务实例

    Returns:
        用户对象，如果无效返回 None
    """
    if not token:
        return None

    if auth_service is None:
        auth_service = get_auth_service()

    return auth_service.verify_token(token)
