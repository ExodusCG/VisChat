"""
CC_VisChat - WebSocket 消息处理器

集成 STT、TTS、Vision LLM 和 Memory 模块，
提供完整的音视频交互处理流程。
"""

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime

import numpy as np
from fastapi import WebSocket

# 内部模块
from .config import get_config

logger = logging.getLogger(__name__)


@dataclass
class UserSession:
    """用户会话上下文"""
    user_id: str
    username: str
    conn_id: str
    websocket: WebSocket
    session_id: Optional[str] = None
    current_image: Optional[str] = None  # Base64 图片
    is_recording: bool = False
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)


class MessageHandler:
    """
    WebSocket 消息处理器

    整合所有模块处理完整的交互流程:
    1. 音频输入 -> VAD -> STT -> 文本
    2. 文本 + 图片 -> Vision LLM -> 响应
    3. 响应 -> TTS -> 音频输出
    4. 会话记忆管理
    """

    def __init__(self):
        """初始化处理器"""
        self._config = get_config()

        # 模块实例 (延迟初始化)
        self._stt = None
        self._tts = None
        self._llm = None
        self._session_manager = None
        self._memory_store = None

        # 用户会话缓存
        self._user_sessions: Dict[str, UserSession] = {}

        # 用户的流式 VAD 实例
        self._user_vads: Dict[str, Any] = {}

        # 初始化状态
        self._initialized = False

    async def initialize(self) -> bool:
        """
        异步初始化所有模块

        Returns:
            是否初始化成功
        """
        if self._initialized:
            return True

        logger.info("正在初始化消息处理器...")

        try:
            # 初始化 STT
            await self._init_stt()

            # 初始化 TTS
            await self._init_tts()

            # 初始化 LLM
            await self._init_llm()

            # 初始化 Memory
            await self._init_memory()

            self._initialized = True
            logger.info("消息处理器初始化完成")
            return True

        except Exception as e:
            logger.error(f"消息处理器初始化失败: {e}")
            return False

    async def _init_stt(self):
        """初始化 STT 模块"""
        try:
            from .stt import SenseVoiceSTT, STTConfig

            stt_config = self._config.stt
            config = STTConfig(
                model_id=stt_config.get("model", "iic/SenseVoiceSmall"),
                device=stt_config.get("device", "cpu"),
                language=stt_config.get("language", "auto"),
            )

            self._stt = SenseVoiceSTT(config)
            # 预加载模型 (启动时加载，避免首次使用延迟 3-5 秒)
            logger.info("STT 模型预加载中...")
            await self._stt.load_model_async()

            logger.info("STT 模块初始化完成")

        except ImportError as e:
            logger.warning(f"STT 模块不可用: {e}")
            self._stt = None

    async def _init_tts(self):
        """初始化 TTS 模块"""
        try:
            from .tts import TTSManager

            tts_config = self._config.tts

            # 获取配置，使用默认值保证最佳兼容性
            # 参考 bailing/Talk 项目: 简洁调用效果最好
            voice = tts_config.get("voice", "zh-CN-XiaoxiaoNeural")
            speed = tts_config.get("speed", 1.0)  # 默认 1.0，不修改语速
            pitch = tts_config.get("pitch", 0)    # 默认 0，不修改音调

            # 确保 pitch 是数字而不是字符串
            if isinstance(pitch, str):
                # 移除 Hz 后缀并转换
                pitch = float(pitch.replace("Hz", "").replace("+", ""))

            self._tts = TTSManager(
                primary="edge_tts",
                fallback="gtts",
                primary_config={
                    "voice": voice,
                    "speed": float(speed),
                    "pitch": float(pitch),
                },
                fallback_config={
                    "lang": tts_config.get("fallback_lang", "zh-CN"),
                }
            )

            logger.info(f"TTS 模块初始化完成: voice={voice}, speed={speed}, pitch={pitch}")

        except ImportError as e:
            logger.warning(f"TTS 模块不可用: {e}")
            self._tts = None

    async def _init_llm(self):
        """初始化 LLM 模块"""
        try:
            from .llm import LLMManager

            self._llm = LLMManager()
            await self._llm.initialize(config_dict={"vision_llm": self._config.vision_llm})

            logger.info(f"LLM 模块初始化完成: {self._config.vision_llm.get('active_provider')}")

        except ImportError as e:
            logger.warning(f"LLM 模块不可用: {e}")
            self._llm = None

    async def _init_memory(self):
        """初始化 Memory 模块"""
        try:
            from .memory import SessionManager, MemoryStore

            self._session_manager = SessionManager()
            self._memory_store = MemoryStore()

            logger.info("Memory 模块初始化完成")

        except ImportError as e:
            logger.warning(f"Memory 模块不可用: {e}")
            self._session_manager = None
            self._memory_store = None

    def create_user_session(
        self,
        conn_id: str,
        user_id: str,
        username: str,
        websocket: WebSocket
    ) -> UserSession:
        """
        创建用户会话

        Args:
            conn_id: 连接 ID
            user_id: 用户 ID
            username: 用户名
            websocket: WebSocket 连接

        Returns:
            UserSession 对象
        """
        session = UserSession(
            user_id=user_id,
            username=username,
            conn_id=conn_id,
            websocket=websocket,
        )
        self._user_sessions[conn_id] = session

        # 为用户创建 VAD 实例
        try:
            from .stt.vad import StreamingVAD, VADConfig
            self._user_vads[conn_id] = StreamingVAD(VADConfig(
                silence_duration_ms=800,
                sample_rate=16000,
            ))
        except ImportError:
            pass

        logger.info(f"创建用户会话: {conn_id} -> {username}")
        return session

    def remove_user_session(self, conn_id: str):
        """移除用户会话"""
        self._user_sessions.pop(conn_id, None)
        self._user_vads.pop(conn_id, None)
        logger.info(f"移除用户会话: {conn_id}")

    def get_user_session(self, conn_id: str) -> Optional[UserSession]:
        """获取用户会话"""
        return self._user_sessions.get(conn_id)

    async def handle_message(
        self,
        websocket: WebSocket,
        conn_id: str,
        data: Dict[str, Any]
    ) -> None:
        """
        处理 WebSocket 消息

        Args:
            websocket: WebSocket 连接
            conn_id: 连接 ID
            data: 消息数据
        """
        msg_type = data.get("type", "")
        payload = data.get("payload", {})
        session_id = data.get("session_id")

        # 更新会话活跃时间
        user_session = self._user_sessions.get(conn_id)
        if user_session:
            user_session.last_active = time.time()
            if session_id and not user_session.session_id:
                user_session.session_id = session_id

        try:
            if msg_type == "ping":
                await self._handle_ping(websocket)

            elif msg_type == "text":
                await self._handle_text(websocket, conn_id, payload)

            elif msg_type == "audio":
                await self._handle_audio(websocket, conn_id, payload)

            elif msg_type == "image":
                await self._handle_image(websocket, conn_id, payload)

            elif msg_type == "control":
                await self._handle_control(websocket, conn_id, payload)

            elif msg_type == "switch_provider":
                await self._handle_switch_provider(websocket, conn_id, payload)

            else:
                logger.warning(f"未知消息类型 [{conn_id}]: {msg_type}")

        except Exception as e:
            logger.error(f"处理消息失败 [{conn_id}]: {e}")
            await self._send_error(websocket, str(e))

    async def handle_binary(
        self,
        websocket: WebSocket,
        conn_id: str,
        data: bytes
    ) -> None:
        """
        处理二进制消息 (原始音频数据)

        Args:
            websocket: WebSocket 连接
            conn_id: 连接 ID
            data: 二进制数据
        """
        try:
            # 将二进制数据转换为 float32 音频
            audio_array = np.frombuffer(data, dtype=np.float32)

            # 使用 VAD + STT 处理
            await self._process_audio_stream(websocket, conn_id, audio_array)

        except Exception as e:
            logger.error(f"处理二进制数据失败 [{conn_id}]: {e}")

    # ============ 消息处理方法 ============

    async def _handle_ping(self, websocket: WebSocket):
        """处理 ping 消息"""
        await websocket.send_json({
            "type": "pong",
            "timestamp": time.time()
        })

    async def _handle_text(
        self,
        websocket: WebSocket,
        conn_id: str,
        payload: Dict[str, Any]
    ):
        """
        处理文本消息 - 流式版本

        流程: 文本 + 图片 -> LLM (流式) -> 分句 TTS -> 音频
        """
        text = payload.get("text", "").strip()
        image_base64 = payload.get("image")

        if not text:
            return

        user_session = self._user_sessions.get(conn_id)
        if not user_session:
            return

        logger.info(f"收到文本消息 [{conn_id}]: {text[:50]}...")

        # 发送处理中状态
        await self._send_status(websocket, "processing", "正在处理...")

        try:
            # 使用当前图片或消息中的图片
            current_image = image_base64 or user_session.current_image

            # 获取会话上下文
            history = await self._get_conversation_history(user_session)

            # 流式调用 LLM 并分句 TTS
            full_response = await self._stream_llm_and_tts(
                websocket, conn_id, text, current_image, history
            )

            # 保存到会话记忆
            await self._save_to_memory(user_session, text, full_response, current_image)

            # 发送完成状态
            await self._send_status(websocket, "idle", "就绪")

        except Exception as e:
            logger.error(f"处理文本失败 [{conn_id}]: {e}")
            await self._send_error(websocket, f"处理失败: {e}")
            await self._send_status(websocket, "idle", "就绪")

    async def _handle_audio(
        self,
        websocket: WebSocket,
        conn_id: str,
        payload: Dict[str, Any]
    ):
        """
        处理音频消息 (Base64 编码)

        流程: 音频 -> STT -> 文本 -> LLM -> 响应 -> TTS
        """
        audio_data = payload.get("data", "")
        audio_format = payload.get("format", "float32")
        sample_rate = payload.get("sample_rate", 16000)

        if not audio_data:
            return

        try:
            # 解码 Base64 音频
            audio_bytes = base64.b64decode(audio_data)

            if audio_format == "float32":
                audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
            elif audio_format == "pcm":
                audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            else:
                logger.warning(f"不支持的音频格式: {audio_format}")
                return

            logger.info(f"收到音频 [{conn_id}]: {len(audio_array)} samples, {len(audio_array)/sample_rate:.2f}s")

            # 处理音频流
            await self._process_audio_stream(websocket, conn_id, audio_array)

        except Exception as e:
            logger.error(f"处理音频失败 [{conn_id}]: {e}")

    async def _process_audio_stream(
        self,
        websocket: WebSocket,
        conn_id: str,
        audio_array: np.ndarray
    ):
        """
        处理音频流 (直接 STT，前端已做 VAD)
        """
        # 前端已经做了 VAD，发送的是完整的语音片段，直接进行 STT 转写
        await self._transcribe_and_respond(websocket, conn_id, audio_array)

    async def _transcribe_and_respond(
        self,
        websocket: WebSocket,
        conn_id: str,
        audio_array: np.ndarray
    ):
        """
        转写音频并生成响应
        """
        if self._stt is None:
            logger.warning("STT 模块不可用")
            return

        user_session = self._user_sessions.get(conn_id)
        if not user_session:
            return

        # 发送转写中状态
        await self._send_status(websocket, "processing", "正在转写...")

        try:
            # STT 转写
            stt_result = await self._stt.transcribe(audio_array)

            if not stt_result.text:
                logger.info(f"转写结果为空 [{conn_id}]")
                # 发送空结果通知前端
                await websocket.send_json({
                    "type": "transcription",
                    "payload": {
                        "text": "",
                        "is_final": True,
                        "error": "no_speech_detected"
                    },
                    "timestamp": int(time.time() * 1000)
                })
                await self._send_status(websocket, "idle", "未检测到语音")
                return

            # 发送转写结果
            await websocket.send_json({
                "type": "transcription",
                "payload": {
                    "text": stt_result.text,
                    "language": stt_result.language,
                    "emotion": stt_result.emotion.value,
                    "is_final": True
                },
                "timestamp": int(time.time() * 1000)
            })

            logger.info(f"转写结果 [{conn_id}]: {stt_result.text}")

            # 继续处理文本
            await self._handle_text(websocket, conn_id, {
                "text": stt_result.text
            })

        except Exception as e:
            logger.error(f"转写失败 [{conn_id}]: {e}")
            await self._send_error(websocket, f"转写失败: {e}")
            await self._send_status(websocket, "idle", "就绪")

    async def _handle_image(
        self,
        websocket: WebSocket,
        conn_id: str,
        payload: Dict[str, Any]
    ):
        """
        处理图片消息

        保存当前图片供后续问答使用
        """
        image_data = payload.get("data", "")
        source = payload.get("source", "camera")

        if not image_data:
            return

        user_session = self._user_sessions.get(conn_id)
        if not user_session:
            return

        # 保存当前图片
        user_session.current_image = image_data

        logger.info(f"收到图片 [{conn_id}], 来源: {source}, 大小: {len(image_data)} bytes")

        await websocket.send_json({
            "type": "status",
            "payload": {
                "state": "image_received",
                "message": f"图片已接收 ({source})"
            },
            "timestamp": int(time.time() * 1000)
        })

    async def _handle_control(
        self,
        websocket: WebSocket,
        conn_id: str,
        payload: Dict[str, Any]
    ):
        """处理控制指令"""
        action = payload.get("action", "")

        user_session = self._user_sessions.get(conn_id)
        if not user_session:
            return

        logger.info(f"控制指令 [{conn_id}]: {action}")

        if action == "start_recording":
            user_session.is_recording = True
            # 重置 VAD
            vad = self._user_vads.get(conn_id)
            if vad:
                vad.reset()
            await self._send_status(websocket, "listening", "开始录音")

        elif action == "stop_recording":
            user_session.is_recording = False
            await self._send_status(websocket, "idle", "停止录音")

        elif action == "clear_image":
            user_session.current_image = None
            await self._send_status(websocket, "idle", "图片已清除")

        elif action == "new_session":
            # 创建新会话
            if self._session_manager:
                session = await self._session_manager.create_session(user_session.user_id)
                user_session.session_id = session.id
            await self._send_status(websocket, "idle", "新会话已创建")

        elif action == "set_config":
            # 设置配置 (提供者、模型等)
            # payload 格式: {action: "set_config", provider: "...", model: "..."}
            provider = payload.get("provider")
            model = payload.get("model")

            if provider and self._llm:
                try:
                    # 切换提供者
                    await self._llm.switch_provider(provider)
                    logger.info(f"切换 LLM 提供者: {provider}")

                    # 如果指定了模型，更新配置
                    if model and self._llm._provider:
                        self._llm._provider._config.model = model

                    await websocket.send_json({
                        "type": "status",
                        "payload": {
                            "state": "provider_switched",
                            "provider": provider,
                            "model": model or "",
                            "message": f"已切换到 {provider}"
                        },
                        "timestamp": int(time.time() * 1000)
                    })
                except Exception as e:
                    logger.error(f"切换提供者失败: {e}")
                    await self._send_error(websocket, f"切换提供者失败: {e}")
            else:
                await websocket.send_json({
                    "type": "status",
                    "payload": {"state": "ok", "action": action},
                    "timestamp": int(time.time() * 1000)
                })

        else:
            await websocket.send_json({
                "type": "status",
                "payload": {"state": "ok", "action": action},
                "timestamp": int(time.time() * 1000)
            })

    async def _handle_switch_provider(
        self,
        websocket: WebSocket,
        conn_id: str,
        payload: Dict[str, Any]
    ):
        """切换 LLM 提供者"""
        provider = payload.get("provider", "")

        if not provider:
            return

        logger.info(f"切换 LLM 提供者 [{conn_id}]: {provider}")

        if self._llm:
            try:
                await self._llm.switch_provider(provider)
                await websocket.send_json({
                    "type": "status",
                    "payload": {
                        "state": "provider_switched",
                        "provider": provider,
                        "message": f"已切换到 {provider}"
                    },
                    "timestamp": int(time.time() * 1000)
                })
            except Exception as e:
                await self._send_error(websocket, f"切换提供者失败: {e}")
        else:
            await self._send_error(websocket, "LLM 模块不可用")

    # ============ 辅助方法 ============

    # 系统提示词 - 优化语音对话体验
    SYSTEM_PROMPT = """你是一个智能语音助手，正在通过语音与用户对话。请遵循以下规则：

1. 回复要简洁，控制在50字以内，适合语音朗读
2. 使用口语化表达，避免书面语和复杂句式
3. 如果问题复杂，先给出简短回答，然后询问是否需要详细解释
4. 不要使用列表、编号、代码块等不适合语音的格式
5. 语气要友好自然，像朋友聊天一样
6. 禁止使用任何表情符号（emoji）、特殊符号或颜文字"""

    # 句子结束标点符号 (用于分句 TTS)
    SENTENCE_ENDINGS = {'。', '！', '？', '；', '.', '!', '?', ';', '\n'}

    async def _stream_llm_and_tts(
        self,
        websocket: WebSocket,
        conn_id: str,
        text: str,
        image_base64: Optional[str],
        history: Optional[List[Dict]] = None
    ) -> str:
        """
        流式调用 LLM 并分句进行 TTS

        实现低延迟响应:
        1. LLM 流式输出 token
        2. 检测到完整句子时立即进行 TTS
        3. 边生成边播放，大幅降低首次响应时间

        Returns:
            完整的响应文本
        """
        if self._llm is None:
            error_msg = f"LLM 模块不可用。您说: {text}"
            await websocket.send_json({
                "type": "response",
                "payload": {"text": error_msg, "is_final": True},
                "timestamp": int(time.time() * 1000)
            })
            return error_msg

        # 构建消息
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        if history:
            messages.extend(history)

        full_response = ""
        current_sentence = ""
        sentence_count = 0

        try:
            # 获取流式生成器
            if image_base64:
                # 检查是否支持流式视觉分析
                if hasattr(self._llm, 'analyze_stream'):
                    stream = self._llm.analyze_stream(
                        image_base64=image_base64,
                        prompt=text,
                        history=messages
                    )
                else:
                    # 回退到非流式
                    response = await self._llm.analyze(
                        image_base64=image_base64,
                        prompt=text,
                        history=messages
                    )
                    await self._send_response_and_tts(websocket, response)
                    return response
            else:
                messages.append({"role": "user", "content": text})
                if hasattr(self._llm, 'chat_stream'):
                    stream = self._llm.chat_stream(messages)
                else:
                    # 回退到非流式
                    response = await self._llm.chat(messages)
                    await self._send_response_and_tts(websocket, response)
                    return response

            # TTS 任务队列 - 保证顺序
            tts_tasks = []

            # 流式处理
            async for chunk in stream:
                full_response += chunk
                current_sentence += chunk

                # 发送流式文本更新
                await websocket.send_json({
                    "type": "response",
                    "payload": {
                        "text": chunk,
                        "is_streaming": True,
                        "is_final": False
                    },
                    "timestamp": int(time.time() * 1000)
                })

                # 检测句子结束，进行 TTS
                if any(end in chunk for end in self.SENTENCE_ENDINGS):
                    # 清理句子
                    sentence_to_speak = current_sentence.strip()
                    if sentence_to_speak and len(sentence_to_speak) > 1:
                        sentence_count += 1
                        logger.debug(f"句子 #{sentence_count}: {sentence_to_speak[:30]}...")

                        # 创建 TTS 任务但不等待，保存到队列
                        task = asyncio.create_task(
                            self._synthesize_audio(sentence_to_speak)
                        )
                        tts_tasks.append((sentence_count, task))

                    current_sentence = ""

            # 处理最后一个未完成的句子
            if current_sentence.strip():
                sentence_count += 1
                task = asyncio.create_task(
                    self._synthesize_audio(current_sentence.strip())
                )
                tts_tasks.append((sentence_count, task))

            # 按顺序等待并发送 TTS 音频
            for idx, task in tts_tasks:
                try:
                    audio_data = await task
                    if audio_data:
                        await self._send_audio(websocket, audio_data)
                        logger.debug(f"发送句子 #{idx} 的音频")
                except Exception as e:
                    logger.error(f"TTS 任务 #{idx} 失败: {e}")

            # 发送流式结束标记
            await websocket.send_json({
                "type": "response",
                "payload": {
                    "text": "",
                    "is_streaming": False,
                    "is_final": True,
                    "full_text": full_response
                },
                "timestamp": int(time.time() * 1000)
            })

            return full_response

        except Exception as e:
            logger.error(f"流式 LLM 调用失败: {e}")
            error_msg = f"抱歉，处理请求时出错: {e}"
            await websocket.send_json({
                "type": "response",
                "payload": {"text": error_msg, "is_final": True},
                "timestamp": int(time.time() * 1000)
            })
            return error_msg

    async def _send_response_and_tts(
        self,
        websocket: WebSocket,
        response: str
    ):
        """非流式情况下发送响应和 TTS"""
        await websocket.send_json({
            "type": "response",
            "payload": {"text": response, "is_streaming": False, "is_final": True},
            "timestamp": int(time.time() * 1000)
        })
        await self._synthesize_and_send(websocket, response)

    async def _call_llm(
        self,
        text: str,
        image_base64: Optional[str],
        history: Optional[List[Dict]] = None
    ) -> str:
        """
        调用 LLM 生成响应
        """
        if self._llm is None:
            return f"LLM 模块不可用。您说: {text}"

        try:
            # 构建带系统提示词的消息
            messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]

            if history:
                messages.extend(history)

            if image_base64:
                # 视觉分析
                response = await self._llm.analyze(
                    image_base64=image_base64,
                    prompt=text,
                    history=messages
                )
            else:
                # 纯文本对话
                messages.append({"role": "user", "content": text})
                response = await self._llm.chat(messages)

            return response

        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return f"抱歉，处理请求时出错: {e}"

    async def _synthesize_audio(self, text: str) -> Optional[bytes]:
        """
        仅合成音频，不发送（用于流式处理保证顺序）
        """
        if self._tts is None or not text:
            return None

        try:
            return await self._tts.synthesize(text)
        except Exception as e:
            logger.error(f"TTS 合成失败: {e}")
            return None

    async def _send_audio(self, websocket: WebSocket, audio_data: bytes):
        """
        发送音频数据到客户端
        """
        if not audio_data:
            return

        await websocket.send_json({
            "type": "audio",
            "payload": {
                "data": base64.b64encode(audio_data).decode('utf-8'),
                "format": "mp3"
            },
            "timestamp": int(time.time() * 1000)
        })

    async def _synthesize_and_send(
        self,
        websocket: WebSocket,
        text: str
    ):
        """
        TTS 合成并发送音频
        """
        if self._tts is None:
            logger.warning("TTS 模块不可用，跳过语音合成")
            return

        if not text:
            return

        try:
            await self._send_status(websocket, "speaking", "正在合成语音...")

            # 合成音频
            audio_data = await self._tts.synthesize(text)

            # 发送音频
            await websocket.send_json({
                "type": "audio",
                "payload": {
                    "data": base64.b64encode(audio_data).decode('utf-8'),
                    "format": "mp3"
                },
                "timestamp": int(time.time() * 1000)
            })

        except Exception as e:
            logger.error(f"TTS 合成失败: {e}")

    async def _get_conversation_history(
        self,
        user_session: UserSession
    ) -> List[Dict]:
        """
        获取对话历史
        """
        if self._session_manager is None:
            return []

        try:
            # 获取或创建会话
            if not user_session.session_id:
                session = await self._session_manager.create_session(user_session.user_id)
                user_session.session_id = session.id

            # 获取上下文消息
            messages = await self._session_manager.get_context(
                user_session.user_id,
                user_session.session_id,
                max_messages=10
            )

            # 转换为 LLM 格式
            return [msg.to_llm_format() for msg in messages]

        except Exception as e:
            logger.error(f"获取对话历史失败: {e}")
            return []

    async def _save_to_memory(
        self,
        user_session: UserSession,
        user_text: str,
        assistant_response: str,
        image_ref: Optional[str] = None
    ):
        """
        保存对话到记忆
        """
        if self._session_manager is None:
            return

        try:
            # 确保有会话 ID
            if not user_session.session_id:
                session = await self._session_manager.create_session(user_session.user_id)
                user_session.session_id = session.id

            from .memory import MessageRole

            # 保存用户消息
            await self._session_manager.add_message(
                user_session.user_id,
                user_session.session_id,
                MessageRole.USER,
                user_text,
                image_ref="image" if image_ref else None
            )

            # 保存助手响应
            await self._session_manager.add_message(
                user_session.user_id,
                user_session.session_id,
                MessageRole.ASSISTANT,
                assistant_response
            )

        except Exception as e:
            logger.error(f"保存记忆失败: {e}")

    async def _send_status(
        self,
        websocket: WebSocket,
        state: str,
        message: str
    ):
        """发送状态更新"""
        await websocket.send_json({
            "type": "status",
            "payload": {
                "state": state,
                "message": message
            },
            "timestamp": int(time.time() * 1000)
        })

    async def _send_error(
        self,
        websocket: WebSocket,
        message: str,
        code: str = "ERR_001"
    ):
        """发送错误消息"""
        await websocket.send_json({
            "type": "error",
            "payload": {
                "code": code,
                "message": message
            },
            "timestamp": int(time.time() * 1000)
        })

    async def close(self):
        """关闭处理器，释放资源"""
        logger.info("关闭消息处理器...")

        # 关闭 STT
        if self._stt:
            self._stt.close()

        # 关闭 TTS
        if self._tts:
            await self._tts.close()

        # 关闭 LLM
        if self._llm:
            await self._llm.close()

        # 清理会话
        self._user_sessions.clear()
        self._user_vads.clear()

        self._initialized = False
        logger.info("消息处理器已关闭")


# 全局单例
_handler_instance: Optional[MessageHandler] = None


def get_handler() -> MessageHandler:
    """获取全局消息处理器实例"""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = MessageHandler()
    return _handler_instance
