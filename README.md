# VisChat

[English](#english) | [中文](#中文)

---

## English

A web-based intelligent visual conversation application with real-time speech recognition, vision understanding, and speech synthesis.

### Features

- 🎤 **Voice Conversation** - Real-time STT (SenseVoice) + TTS (EdgeTTS)
- 📷 **Vision Understanding** - Camera/Screenshot/Upload + Vision LLM analysis
- 💬 **Streaming Response** - LLM streaming output + sentence-based TTS for low latency
- 🔐 **User Authentication** - Multi-user support with encrypted password storage
- 📱 **Mobile Friendly** - Responsive design, mobile browser compatible

### Quick Start

#### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 2. Configuration

```bash
# Copy user config template
cp config/users.yaml.example config/users.yaml

# Edit config/config.yaml to configure LLM service address
```

#### 3. Generate SSL Certificate

```bash
python generate_cert.py
```

#### 4. Start Server

```bash
# HTTPS mode (local development)
python -m src.main

# HTTP mode (with reverse proxy)
python -m src.main --no-ssl

# Debug mode
python -m src.main --debug
```

#### 5. Access

Open browser and visit `https://localhost:5180`

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Browser)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────────┐│
│  │ Camera   │ │ Audio    │ │ WebSocket│ │ UI (Chat, Settings)  ││
│  │ Capture  │ │ Recorder │ │ Manager  │ │                      ││
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │ WSS
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI + WebSocket)                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐      │
│  │   STT    │   │   TTS    │   │   LLM    │   │  Memory  │      │
│  │SenseVoice│   │ EdgeTTS  │   │ LMStudio │   │ Session  │      │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

### Configuration

#### LLM Providers

- **LMStudio** (default): Runs in LAN, privacy-first
- **LocalProxy**: Access cloud models via local proxy, performance-first

#### Config Files

- `config/config.yaml` - Main config (server, LLM, TTS, etc.)
- `config/users.yaml` - User credentials (do not commit to version control)

### Development

```bash
# Run tests
pytest tests/

# STT module test
python -m src.stt.sensevoice
```

### Tech Stack

- **Backend**: FastAPI, Uvicorn, WebSocket
- **Frontend**: Vanilla JavaScript, CSS3
- **STT**: SenseVoiceSmall (FunASR)
- **TTS**: EdgeTTS
- **LLM**: OpenAI-compatible API (LMStudio, Local Proxy)

---

## 中文

基于 Web 的智能视觉对话应用，支持实时语音识别、视觉理解和语音合成。

### 功能特性

- 🎤 **语音对话** - 实时语音识别 (SenseVoice) + 语音合成 (EdgeTTS)
- 📷 **视觉理解** - 摄像头/截图/上传图片 + Vision LLM 分析
- 💬 **流式响应** - LLM 流式输出 + 分句 TTS 低延迟
- 🔐 **用户认证** - 多用户支持，密码加密存储
- 📱 **移动端适配** - 响应式设计，支持移动端浏览器

### 快速开始

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

#### 2. 配置

```bash
# 复制用户配置模板
cp config/users.yaml.example config/users.yaml

# 编辑 config/config.yaml 配置 LLM 服务地址
```

#### 3. 生成 SSL 证书

```bash
python generate_cert.py
```

#### 4. 启动服务

```bash
# HTTPS 模式 (本地开发)
python -m src.main

# HTTP 模式 (配合反向代理)
python -m src.main --no-ssl

# 调试模式
python -m src.main --debug
```

#### 5. 访问

打开浏览器访问 `https://localhost:5180`

### 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端 (浏览器)                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────────┐│
│  │ 摄像头   │ │ 录音器   │ │ WebSocket│ │ UI (对话、设置)      ││
│  │ 捕获     │ │          │ │ 管理器   │ │                      ││
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │ WSS
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    后端 (FastAPI + WebSocket)                    │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐      │
│  │   STT    │   │   TTS    │   │   LLM    │   │  记忆    │      │
│  │SenseVoice│   │ EdgeTTS  │   │ LMStudio │   │ 会话管理 │      │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

### 配置说明

#### LLM 提供者

- **LMStudio** (默认): 局域网内运行，隐私优先
- **LocalProxy**: 通过本地代理访问云端模型，性能优先

#### 配置文件

- `config/config.yaml` - 主配置 (服务器、LLM、TTS 等)
- `config/users.yaml` - 用户凭据 (不要提交到版本控制)

### 开发

```bash
# 运行测试
pytest tests/

# STT 模块测试
python -m src.stt.sensevoice
```

### 技术栈

- **后端**: FastAPI, Uvicorn, WebSocket
- **前端**: 原生 JavaScript, CSS3
- **STT**: SenseVoiceSmall (FunASR)
- **TTS**: EdgeTTS
- **LLM**: OpenAI 兼容 API (LMStudio, 本地代理)

---

## License

MIT
