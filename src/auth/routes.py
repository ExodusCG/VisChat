"""
认证 API 路由

提供登录、登出、获取当前用户信息等 API 端点。
"""

from typing import Optional

from fastapi import APIRouter, Request, Response, HTTPException, status, Depends

from .models import (
    User,
    UserPublic,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    ErrorResponse,
)
from .service import get_auth_service, AuthService
from .middleware import (
    get_current_active_user,
    set_auth_cookie,
    clear_auth_cookie,
    ACCESS_TOKEN_COOKIE,
)


# 创建路由器
router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        200: {"description": "登录成功"},
        401: {"description": "认证失败", "model": ErrorResponse},
    },
    summary="用户登录",
    description="验证用户凭据并返回 JWT Token。Token 会同时通过响应体和 HttpOnly Cookie 返回。",
)
async def login(
    request: Request,
    response: Response,
    login_data: LoginRequest,
) -> LoginResponse:
    """
    用户登录接口

    - **username**: 用户名
    - **password**: 密码

    成功后返回 JWT Token 和用户信息。
    Token 同时设置在 HttpOnly Cookie 中。
    """
    auth_service = get_auth_service()

    # 获取客户端信息
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    # 执行登录
    token, user_public, error = auth_service.login(
        username=login_data.username,
        password=login_data.password,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if error:
        # 登录失败
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"success": False, "error": error},
        )

    # 设置 HttpOnly Cookie
    set_auth_cookie(response, token, max_age=86400)  # 24 小时

    return LoginResponse(
        success=True,
        token=token,
        user=user_public,
    )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="用户登出",
    description="使当前会话失效并清除认证 Cookie。",
)
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_active_user),
) -> LogoutResponse:
    """
    用户登出接口

    清除服务端会话和客户端 Cookie。
    """
    auth_service = get_auth_service()

    # 获取当前 Token
    token = getattr(request.state, "token", None)

    if token:
        # 使会话失效
        auth_service.logout(token)

    # 清除 Cookie
    clear_auth_cookie(response)

    return LogoutResponse(success=True)


@router.get(
    "/me",
    response_model=UserPublic,
    responses={
        200: {"description": "获取成功"},
        401: {"description": "未认证", "model": ErrorResponse},
    },
    summary="获取当前用户信息",
    description="返回当前已登录用户的基本信息。",
)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
) -> UserPublic:
    """
    获取当前用户信息接口

    返回当前登录用户的公开信息（不包含密码等敏感数据）。
    """
    return UserPublic.from_user(current_user)


@router.get(
    "/verify",
    response_model=dict,
    summary="验证 Token",
    description="验证当前 Token 是否有效。",
)
async def verify_token(
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    验证 Token 接口

    如果请求能到达这里，说明 Token 有效。
    """
    return {
        "valid": True,
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role.value if hasattr(current_user.role, 'value') else current_user.role,
    }


@router.post(
    "/refresh",
    response_model=LoginResponse,
    summary="刷新 Token",
    description="使用当前有效的 Token 获取新的 Token。",
)
async def refresh_token(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_active_user),
) -> LoginResponse:
    """
    刷新 Token 接口

    使用当前有效 Token 获取新 Token，延长会话时间。
    """
    auth_service = get_auth_service()

    # 获取客户端信息
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    # 创建新会话
    session = auth_service.create_session(
        user=current_user,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # 使旧 Token 失效
    old_token = getattr(request.state, "token", None)
    if old_token:
        auth_service.logout(old_token)

    # 设置新 Cookie
    set_auth_cookie(response, session.token, max_age=86400)

    return LoginResponse(
        success=True,
        token=session.token,
        user=UserPublic.from_user(current_user),
    )
