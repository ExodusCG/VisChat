"""
FastAPI 服务器模块
支持 HTTPS、WebSocket、静态文件服务
集成 STT、TTS、Vision LLM 和 Memory 模块
"""

import os
import sys
import json
import time
import asyncio
import logging
import socket
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

import uvicorn

try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False

from .config import get_config, PROJECT_ROOT
from .handler import get_handler, MessageHandler

# 配置日志
logger = logging.getLogger(__name__)

# 活跃的 WebSocket 连接
active_connections: Dict[str, Dict[str, Any]] = {}

# 连接超时时间（秒）
CONNECTION_TIMEOUT = 600

# 全局消息处理器
message_handler: Optional[MessageHandler] = None


async def cleanup_inactive_connections():
    """清理不活跃的连接"""
    while True:
        now = time.time()
        for conn_id, conn_data in list(active_connections.items()):
            if now - conn_data.get("last_active", 0) > CONNECTION_TIMEOUT:
                logger.info(f"清理超时连接: {conn_id}")
                try:
                    ws = conn_data.get("websocket")
                    if ws:
                        await ws.close()
                except Exception as e:
                    logger.error(f"关闭 WebSocket 失败: {e}")
                active_connections.pop(conn_id, None)
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global message_handler

    # 启动时
    logger.info("CC_VisChat 服务启动中...")

    # 初始化消息处理器
    message_handler = get_handler()
    await message_handler.initialize()

    cleanup_task = asyncio.create_task(cleanup_inactive_connections())

    yield

    # 关闭时
    logger.info("CC_VisChat 服务关闭中...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    # 关闭消息处理器
    if message_handler:
        await message_handler.close()

    # 关闭所有 WebSocket 连接
    for conn_id, conn_data in active_connections.items():
        try:
            ws = conn_data.get("websocket")
            if ws:
                await ws.close()
        except Exception:
            pass
    active_connections.clear()


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    config = get_config()

    app = FastAPI(
        title="CC_VisChat",
        description="Web-based Audio-Visual Interactive Application",
        version="0.1.0",
        lifespan=lifespan
    )

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Session 中间件
    secret_key = config.security.get("secret_key", "cc_vischat_secret_key")
    app.add_middleware(SessionMiddleware, secret_key=secret_key)

    # 注册路由
    register_routes(app)

    # 静态文件服务
    static_dir = PROJECT_ROOT / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        logger.info(f"静态文件目录: {static_dir}")

    return app


def register_routes(app: FastAPI):
    """注册路由"""
    config = get_config()

    # ============ 认证相关路由 ============

    @app.get("/")
    async def root():
        """根路由 - 重定向到登录页或主页"""
        return RedirectResponse(url="/static/login.html")

    @app.get("/login")
    async def login_page():
        """登录页面"""
        login_file = PROJECT_ROOT / "static" / "login.html"
        if login_file.exists():
            return FileResponse(str(login_file))
        return JSONResponse({"error": "Login page not found"}, status_code=404)

    @app.post("/api/auth/login")
    async def login(request: Request):
        """用户登录"""
        try:
            body = await request.json()
            username = body.get("username", "")
            password = body.get("password", "")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid request body")

        # 验证用户
        user = config.get_user(username)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        # 验证密码
        password_valid = False

        # 优先检查 password_hash (bcrypt)
        if user.get("password_hash") and BCRYPT_AVAILABLE:
            try:
                password_valid = bcrypt.checkpw(
                    password.encode('utf-8'),
                    user["password_hash"].encode('utf-8')
                )
            except Exception as e:
                logger.error(f"bcrypt 验证失败: {e}")

        # 如果没有 hash 或 bcrypt 不可用，回退到明文比较
        if not password_valid and user.get("password"):
            password_valid = (user.get("password") == password)

        if not password_valid:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        # 设置 session
        user_data = {
            "username": username,
            "role": user.get("role", "user"),
            "display_name": user.get("display_name", username),
            "login_time": datetime.now().isoformat()
        }
        request.session["user"] = user_data

        logger.info(f"用户登录成功: {username}")

        return JSONResponse({
            "status": "ok",
            "user": {
                "username": username,
                "role": user_data["role"],
                "display_name": user_data["display_name"]
            }
        })

    @app.post("/api/auth/logout")
    async def logout(request: Request):
        """用户登出"""
        user = request.session.get("user")
        if user:
            logger.info(f"用户登出: {user.get('username')}")
        request.session.clear()
        return JSONResponse({"status": "ok"})

    @app.get("/api/auth/me")
    async def get_current_user(request: Request):
        """获取当前用户信息"""
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return JSONResponse(user)

    @app.post("/api/auth/change-password")
    async def change_password(request: Request):
        """修改密码"""
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        try:
            body = await request.json()
            old_password = body.get("old_password", "")
            new_password = body.get("new_password", "")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid request body")

        if not old_password or not new_password:
            raise HTTPException(status_code=400, detail="请提供旧密码和新密码")

        if len(new_password) < 6:
            raise HTTPException(status_code=400, detail="新密码长度至少6位")

        # 获取用户信息验证旧密码
        username = user.get("username")
        user_data = config.get_user(username)
        if not user_data:
            raise HTTPException(status_code=404, detail="用户不存在")

        # 验证旧密码
        password_valid = False
        if user_data.get("password_hash") and BCRYPT_AVAILABLE:
            try:
                password_valid = bcrypt.checkpw(
                    old_password.encode('utf-8'),
                    user_data["password_hash"].encode('utf-8')
                )
            except Exception as e:
                logger.error(f"bcrypt 验证失败: {e}")

        if not password_valid and user_data.get("password"):
            password_valid = (user_data.get("password") == old_password)

        if not password_valid:
            raise HTTPException(status_code=401, detail="旧密码错误")

        # 生成新密码哈希
        if BCRYPT_AVAILABLE:
            new_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        else:
            raise HTTPException(status_code=500, detail="服务器不支持密码加密")

        # 更新密码
        if config.update_user_password(username, new_hash):
            logger.info(f"用户 {username} 修改密码成功")
            return JSONResponse({"status": "ok", "message": "密码修改成功"})
        else:
            raise HTTPException(status_code=500, detail="密码修改失败")

    # ============ 配置相关路由 ============

    @app.get("/api/config")
    async def get_frontend_config(request: Request):
        """获取前端配置"""
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        # 获取当前提供者的默认模型
        active_provider = config.vision_llm.get("active_provider", "lmstudio")
        provider_config = config.vision_llm.get(active_provider, {})
        default_model = provider_config.get("default_model", "")

        # 返回前端需要的配置（不包含敏感信息）
        return JSONResponse({
            "language": config.language,
            "vision_llm": {
                "active_provider": active_provider,
                "default_model": default_model,
                "providers": ["lmstudio", "local_proxy"]
            },
            "audio": config.audio
        })

    @app.get("/api/models")
    async def get_models(request: Request, provider: Optional[str] = None):
        """获取可用模型列表

        Args:
            provider: 可选，指定要查询的提供者 (lmstudio 或 local_proxy)
                      如果不指定，使用当前活跃的提供者
        """
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        vision_llm = config.vision_llm

        # 确定要查询的提供者
        target_provider = provider or vision_llm.get("active_provider", "lmstudio")
        provider_config = vision_llm.get(target_provider, {})

        # 从 LLM 管理器获取模型列表
        models = []
        try:
            if message_handler and message_handler._llm:
                # 如果请求的是不同的提供者，需要临时切换
                current_provider = vision_llm.get("active_provider", "lmstudio")
                if target_provider != current_provider:
                    # 临时创建目标提供者来获取模型列表
                    from src.llm.factory import LLMFactory
                    temp_provider = LLMFactory.create(target_provider, provider_config)
                    try:
                        models = await temp_provider.list_models()
                    finally:
                        await temp_provider.close()
                else:
                    models = await message_handler._llm.list_models()
        except Exception as e:
            logger.warning(f"获取模型列表失败 ({target_provider}): {e}")
            # 回退到配置中的默认模型
            default_model = provider_config.get("default_model", "")
            if default_model:
                models = [default_model]

        return JSONResponse({
            "active_provider": target_provider,
            "default_model": provider_config.get("default_model", ""),
            "models": models
        })

    @app.get("/api/status")
    async def get_status(request: Request):
        """系统状态"""
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        return JSONResponse({
            "status": "running",
            "version": "0.1.0",
            "active_connections": len(active_connections),
            "timestamp": datetime.now().isoformat()
        })

    # ============ WebSocket 路由 ============

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket 端点 - 集成 STT/TTS/LLM/Memory"""
        global message_handler

        await websocket.accept()

        # 生成连接 ID
        conn_id = f"conn_{int(time.time() * 1000)}"
        user_info = None

        try:
            # 等待认证消息
            auth_msg = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
            auth_data = json.loads(auth_msg)

            if auth_data.get("type") != "auth":
                await websocket.send_json({"type": "error", "message": "Authentication required"})
                await websocket.close(code=1008)
                return

            # 验证用户
            username = auth_data.get("username", "")
            user = config.get_user(username)
            if not user:
                await websocket.send_json({"type": "error", "message": "Invalid user"})
                await websocket.close(code=1008)
                return

            user_info = {
                "username": username,
                "role": user.get("role", "user"),
                "user_id": user.get("id", username)
            }

            # 记录连接
            active_connections[conn_id] = {
                "websocket": websocket,
                "user": user_info,
                "connected_at": time.time(),
                "last_active": time.time()
            }

            # 在消息处理器中创建用户会话
            if message_handler:
                message_handler.create_user_session(
                    conn_id=conn_id,
                    user_id=user_info["user_id"],
                    username=username,
                    websocket=websocket
                )

            logger.info(f"WebSocket 连接建立: {conn_id}, 用户: {username}")

            # 发送连接成功消息
            await websocket.send_json({
                "type": "connected",
                "connection_id": conn_id,
                "user": user_info
            })

            # 消息循环
            while True:
                msg = await websocket.receive()

                if msg["type"] == "websocket.disconnect":
                    break

                # 更新活跃时间
                if conn_id in active_connections:
                    active_connections[conn_id]["last_active"] = time.time()

                if "text" in msg:
                    try:
                        data = json.loads(msg["text"])
                        # 使用消息处理器处理
                        if message_handler:
                            await message_handler.handle_message(websocket, conn_id, data)
                        else:
                            await handle_text_message(websocket, conn_id, data)
                    except json.JSONDecodeError:
                        logger.warning(f"无效的 JSON 消息: {msg['text'][:100]}")

                elif "bytes" in msg:
                    # 使用消息处理器处理二进制数据
                    if message_handler:
                        await message_handler.handle_binary(websocket, conn_id, msg["bytes"])
                    else:
                        await handle_binary_message(websocket, conn_id, msg["bytes"])

        except asyncio.TimeoutError:
            logger.warning(f"WebSocket 认证超时: {conn_id}")
            await websocket.close(code=1008)
        except WebSocketDisconnect:
            logger.info(f"WebSocket 断开连接: {conn_id}")
        except Exception as e:
            logger.error(f"WebSocket 错误: {e}")
        finally:
            # 清理连接
            active_connections.pop(conn_id, None)
            # 从消息处理器移除会话
            if message_handler:
                message_handler.remove_user_session(conn_id)
            if user_info:
                logger.info(f"WebSocket 连接关闭: {conn_id}, 用户: {user_info.get('username')}")


async def handle_text_message(websocket: WebSocket, conn_id: str, data: Dict[str, Any]):
    """处理文本消息"""
    msg_type = data.get("type", "")

    if msg_type == "ping":
        await websocket.send_json({"type": "pong", "timestamp": time.time()})

    elif msg_type == "text":
        # 处理文本输入
        text = data.get("text", "")
        logger.info(f"收到文本消息 [{conn_id}]: {text[:50]}...")

        # TODO: 发送到 LLM 处理
        await websocket.send_json({
            "type": "response",
            "payload": {"text": f"收到消息: {text}"}
        })

    elif msg_type == "control":
        # 处理控制指令
        action = data.get("action", "")
        logger.info(f"收到控制指令 [{conn_id}]: {action}")

        await websocket.send_json({
            "type": "status",
            "payload": {"state": "ok", "action": action}
        })

    elif msg_type == "switch_provider":
        # 切换 LLM 提供者
        provider = data.get("provider", "")
        logger.info(f"切换 LLM 提供者 [{conn_id}]: {provider}")

        await websocket.send_json({
            "type": "status",
            "payload": {"state": "provider_switched", "provider": provider}
        })

    else:
        logger.warning(f"未知消息类型 [{conn_id}]: {msg_type}")


async def handle_binary_message(websocket: WebSocket, conn_id: str, data: bytes):
    """处理二进制消息（音频/图片数据）"""
    # 根据数据头判断类型
    # TODO: 实现音频和图片处理
    logger.debug(f"收到二进制数据 [{conn_id}]: {len(data)} bytes")

    # 占位响应
    await websocket.send_json({
        "type": "status",
        "payload": {"state": "received", "size": len(data)}
    })


def get_lan_ip() -> str:
    """获取局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        return f"无法获取IP: {e}"


def run_server(host: Optional[str] = None, port: Optional[int] = None, debug: bool = False, no_ssl: bool = False):
    """运行服务器

    Args:
        host: 监听地址
        port: 监听端口
        debug: 调试模式
        no_ssl: 禁用 SSL (用于反向代理场景)
    """
    config = get_config()

    # 使用参数或配置
    host = host or config.server.get("host", "0.0.0.0")
    port = port or config.server.get("port", 5180)
    debug = debug or config.server.get("debug", False)

    # SSL 证书检测
    ssl_keyfile = None
    ssl_certfile = None
    protocol = "http"

    if no_ssl:
        # 明确禁用 SSL (用于反向代理)
        print("\n" + "=" * 60)
        print("  SSL 已禁用 (HTTP 模式)")
        print("  适用于 Caddy/Nginx 等反向代理场景")
        print("  确保反向代理已配置 HTTPS")
        print("=" * 60 + "\n")
    else:
        # 尝试加载 SSL 证书
        ssl_config = config.ssl
        ssl_keyfile = str(PROJECT_ROOT / ssl_config.get("key_file", "ssl/key.pem"))
        ssl_certfile = str(PROJECT_ROOT / ssl_config.get("cert_file", "ssl/cert.pem"))

        if not os.path.exists(ssl_keyfile) or not os.path.exists(ssl_certfile):
            ssl_keyfile = None
            ssl_certfile = None
            print("\n" + "=" * 60)
            print("  WARNING: SSL 证书未找到，将以 HTTP 模式启动")
            print("  注意: HTTP 模式下浏览器将禁用摄像头和麦克风访问")
            print("  请运行 python generate_cert.py 生成自签名证书")
            print("  或使用 --no-ssl 配合反向代理")
            print("=" * 60 + "\n")
        else:
            protocol = "https"

    # 打印访问地址
    lan_ip = get_lan_ip()
    print("\n" + "=" * 60)
    print("  CC_VisChat 服务启动")
    print("=" * 60)
    print(f"  本地访问: {protocol}://localhost:{port}")
    print(f"  局域网访问: {protocol}://{lan_ip}:{port}")
    print("=" * 60 + "\n")

    # 配置日志
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
        ]
    )

    # 创建应用
    app = create_app()

    # 运行服务
    uvicorn.run(
        app if not debug else "src.server:create_app",
        host=host,
        port=port,
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
        ws_ping_interval=20,
        ws_ping_timeout=30,
        reload=debug,
        factory=debug,
    )


# 导出应用实例（用于 uvicorn 直接启动）
app = create_app()
