/**
 * CC_VisChat - WebSocket 通信模块
 * 处理与服务器的实时双向通信
 */

const WebSocketManager = {
    // WebSocket 实例
    ws: null,

    // 连接状态
    connected: false,
    authenticated: false,
    reconnecting: false,

    // 会话ID
    sessionId: null,

    // 当前用户
    username: null,

    // 重连配置
    reconnectAttempts: 0,
    maxReconnectAttempts: 5,
    reconnectDelay: 1000,

    // 事件回调
    callbacks: {
        onOpen: null,
        onClose: null,
        onError: null,
        onMessage: null,
        onTranscription: null,
        onResponse: null,
        onAudio: null,
        onStatus: null,
    },

    /**
     * 初始化 WebSocket 连接
     * @param {string} username 用户名 (用于认证)
     */
    connect(username = null) {
        if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
            console.log('WebSocket already connected or connecting');
            return;
        }

        // 保存用户名
        if (username) {
            this.username = username;
        }

        // 生成或使用现有会话ID
        if (!this.sessionId) {
            this.sessionId = this.generateSessionId();
        }

        // 构建 WebSocket URL
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        console.log('Connecting to WebSocket:', wsUrl);

        try {
            this.ws = new WebSocket(wsUrl);
            this.setupEventHandlers();
        } catch (error) {
            console.error('WebSocket connection error:', error);
            this.handleReconnect();
        }
    },

    /**
     * 设置 WebSocket 事件处理器
     */
    setupEventHandlers() {
        this.ws.onopen = (event) => {
            console.log('WebSocket connected, sending authentication...');
            this.connected = true;
            this.reconnecting = false;
            this.reconnectAttempts = 0;

            // 发送认证消息
            this.sendAuth();
        };

        this.ws.onclose = (event) => {
            console.log('WebSocket closed:', event.code, event.reason);
            this.connected = false;
            this.authenticated = false;

            if (this.callbacks.onClose) {
                this.callbacks.onClose(event);
            }

            // 如果不是主动关闭，尝试重连
            if (!event.wasClean && !this.reconnecting) {
                this.handleReconnect();
            }
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);

            if (this.callbacks.onError) {
                this.callbacks.onError(error);
            }
        };

        this.ws.onmessage = (event) => {
            this.handleMessage(event.data);
        };
    },

    /**
     * 发送认证消息
     */
    sendAuth() {
        // 获取当前用户名
        const username = this.username || (window.App && window.App.user && window.App.user.username);

        if (!username) {
            console.error('No username available for authentication');
            return;
        }

        console.log('Authenticating as:', username);

        this.ws.send(JSON.stringify({
            type: 'auth',
            username: username,
            session_id: this.sessionId,
            timestamp: Date.now()
        }));
    },

    /**
     * 处理收到的消息
     * @param {string} data 消息数据
     */
    handleMessage(data) {
        try {
            const message = JSON.parse(data);

            // 处理连接成功消息
            if (message.type === 'connected') {
                console.log('WebSocket authenticated:', message);
                this.authenticated = true;

                // 触发 onOpen 回调
                if (this.callbacks.onOpen) {
                    this.callbacks.onOpen(message);
                }
                return;
            }

            // 通用消息回调
            if (this.callbacks.onMessage) {
                this.callbacks.onMessage(message);
            }

            // 根据消息类型分发
            switch (message.type) {
                case 'transcription':
                    if (this.callbacks.onTranscription) {
                        this.callbacks.onTranscription(message.payload);
                    }
                    break;

                case 'response':
                    if (this.callbacks.onResponse) {
                        this.callbacks.onResponse(message.payload);
                    }
                    break;

                case 'audio':
                    if (this.callbacks.onAudio) {
                        this.callbacks.onAudio(message.payload);
                    }
                    break;

                case 'status':
                    if (this.callbacks.onStatus) {
                        this.callbacks.onStatus(message.payload);
                    }
                    break;

                case 'error':
                    console.error('Server error:', message.payload);
                    if (this.callbacks.onError) {
                        this.callbacks.onError(message.payload);
                    }
                    break;

                case 'pong':
                    // 心跳响应，忽略
                    break;

                default:
                    console.warn('Unknown message type:', message.type);
            }
        } catch (error) {
            console.error('Failed to parse message:', error);
        }
    },

    /**
     * 发送音频数据
     * @param {string} audioBase64 Base64 编码的音频数据
     */
    sendAudio(audioBase64) {
        this.send({
            type: 'audio',
            payload: {
                data: audioBase64,
                format: 'float32',
                sample_rate: 16000,
            },
            timestamp: Date.now(),
            session_id: this.sessionId,
        });
    },

    /**
     * 发送图片数据
     * @param {string} imageBase64 Base64 编码的图片数据
     * @param {string} source 图片来源 (camera/screen)
     */
    sendImage(imageBase64, source = 'camera') {
        this.send({
            type: 'image',
            payload: {
                data: imageBase64,
                source: source,
            },
            timestamp: Date.now(),
            session_id: this.sessionId,
        });
    },

    /**
     * 发送文本消息
     * @param {string} text 文本内容
     * @param {string} imageBase64 可选的图片数据
     */
    sendText(text, imageBase64 = null) {
        const payload = { text };
        if (imageBase64) {
            payload.image = imageBase64;
        }

        this.send({
            type: 'text',
            payload: payload,
            timestamp: Date.now(),
            session_id: this.sessionId,
        });
    },

    /**
     * 发送控制指令
     * @param {string} action 控制动作
     * @param {object} params 附加参数
     */
    sendControl(action, params = {}) {
        this.send({
            type: 'control',
            payload: {
                action: action,
                ...params,
            },
            timestamp: Date.now(),
            session_id: this.sessionId,
        });
    },

    /**
     * 发送消息
     * @param {object} message 消息对象
     */
    send(message) {
        if (!this.connected || !this.ws || !this.authenticated) {
            console.warn('WebSocket not connected or not authenticated, message not sent');
            return false;
        }

        try {
            this.ws.send(JSON.stringify(message));
            return true;
        } catch (error) {
            console.error('Failed to send message:', error);
            return false;
        }
    },

    /**
     * 处理重连逻辑
     */
    handleReconnect() {
        if (this.reconnecting) {
            return;
        }

        this.reconnecting = true;
        this.reconnectAttempts++;

        if (this.reconnectAttempts > this.maxReconnectAttempts) {
            console.error('Max reconnect attempts reached');
            this.reconnecting = false;
            return;
        }

        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
        console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

        setTimeout(() => {
            this.connect();
        }, delay);
    },

    /**
     * 关闭连接
     */
    disconnect() {
        if (this.ws) {
            this.ws.close(1000, 'Client disconnected');
            this.ws = null;
        }
        this.connected = false;
        this.reconnecting = false;
    },

    /**
     * 生成会话ID
     * @returns {string}
     */
    generateSessionId() {
        return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    },

    /**
     * 设置事件回调
     * @param {string} event 事件名称
     * @param {function} callback 回调函数
     */
    on(event, callback) {
        if (this.callbacks.hasOwnProperty(event)) {
            this.callbacks[event] = callback;
        } else {
            console.warn('Unknown event:', event);
        }
    },

    /**
     * 获取连接状态
     * @returns {string}
     */
    getStatus() {
        if (this.connected) {
            return 'connected';
        } else if (this.reconnecting) {
            return 'connecting';
        } else {
            return 'disconnected';
        }
    }
};

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WebSocketManager;
}
