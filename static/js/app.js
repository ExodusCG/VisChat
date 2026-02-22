/**
 * CC_VisChat - 主应用模块
 * 协调各模块工作，处理业务逻辑
 */

const App = {
    // 应用状态
    initialized: false,
    user: null,
    cameraActive: false,
    recordingActive: false,

    // 当前捕获的图片 (用于语音发送时携带)
    currentImage: null,

    /**
     * 初始化应用
     */
    async init() {
        console.log('CC_VisChat initializing...');
        const startTime = performance.now();

        // 检查登录状态 (必须先完成)
        this.user = await Auth.requireAuth();
        if (!this.user) {
            return; // 未登录，会被重定向到登录页
        }

        // 初始化 UI (必须先完成，后续模块依赖 UI.elements)
        UI.init();
        UI.setUser(this.user);

        // 初始化媒体管理器
        MediaManager.init(UI.elements.videoPreview);

        // 设置回调和事件处理 (同步，快速)
        this.setupMediaCallbacks();
        this.setupWebSocketCallbacks();
        this.setupUIHandlers();
        this.setupAudioUnlock();

        // 并行执行以下操作 (无依赖关系)
        const parallelTasks = [
            // 连接 WebSocket
            new Promise(resolve => {
                WebSocketManager.connect(this.user.username);
                resolve();
            }),
            // 获取摄像头列表
            this.loadCameras(),
            // 加载配置
            this.loadConfig(),
        ];

        await Promise.all(parallelTasks);

        this.initialized = true;
        const elapsed = (performance.now() - startTime).toFixed(0);
        console.log(`CC_VisChat initialized in ${elapsed}ms`);
    },

    /**
     * 设置首次用户交互时解锁音频
     * 移动端浏览器需要用户交互后才能播放音频
     */
    setupAudioUnlock() {
        const unlockAudio = async () => {
            document.removeEventListener('click', unlockAudio);
            document.removeEventListener('touchstart', unlockAudio);
            await UI.unlockAudio();
        };

        // 监听首次用户交互
        document.addEventListener('click', unlockAudio, { once: true });
        document.addEventListener('touchstart', unlockAudio, { once: true });
    },

    /**
     * 设置媒体回调
     */
    setupMediaCallbacks() {
        // 音量变化
        MediaManager.on('onVolumeChange', (volume) => {
            UI.setVolume(volume);
        });

        // 开始说话
        MediaManager.on('onSpeechStart', () => {
            if (window.debugLog) debugLog('[STT] Speech started');
            UI.setSpeakingState(true);

            // 自动截图
            if (UI.settings.autoCapture && this.cameraActive) {
                this.currentImage = MediaManager.captureFrame();
                if (window.debugLog) debugLog('[STT] Auto captured image');
            }
        });

        // 结束说话
        MediaManager.on('onSpeechEnd', () => {
            if (window.debugLog) debugLog('[STT] Speech ended');
            UI.setSpeakingState(false);
        });

        // 音频数据就绪
        MediaManager.on('onAudioData', (audioBase64) => {
            if (window.debugLog) debugLog('[STT] Audio data ready, length: ' + (audioBase64 ? audioBase64.length : 0));

            // 如果有图片，一起发送
            if (this.currentImage) {
                WebSocketManager.sendImage(this.currentImage, 'camera');
                if (window.debugLog) debugLog('[STT] Sent image');
            }

            // 发送音频
            WebSocketManager.sendAudio(audioBase64);
            if (window.debugLog) debugLog('[STT] Sent audio to server');

            // 清除当前图片和预览
            this.currentImage = null;
            UI.clearPendingImage();
        });
    },

    /**
     * 设置 WebSocket 回调
     */
    setupWebSocketCallbacks() {
        // 连接打开
        WebSocketManager.on('onOpen', () => {
            UI.setConnectionStatus('connected');
            UI.showToast('已连接到服务器', 'success');

            // 发送配置
            WebSocketManager.sendControl('set_config', {
                provider: UI.settings.provider,
                model: UI.settings.model,
            });
        });

        // 连接关闭
        WebSocketManager.on('onClose', () => {
            UI.setConnectionStatus('disconnected');
        });

        // 连接错误
        WebSocketManager.on('onError', (error) => {
            console.error('WebSocket error:', error);
            UI.showToast('连接错误', 'error');
        });

        // 收到转写结果
        WebSocketManager.on('onTranscription', (payload) => {
            console.log('Transcription:', payload);

            if (payload.is_final) {
                if (payload.text) {
                    // 显示用户消息
                    UI.addChatMessage('user', payload.text, this.currentImage);
                } else if (payload.error === "no_speech_detected") {
                    // 未检测到语音
                    UI.showToast('未检测到语音，请重新说话', 'warning');
                } else {
                    // 其他情况（识别结果为空但无错误码）
                    UI.showToast('未能识别语音，请重试', 'warning');
                }
            }
        });

        // 收到 AI 响应 (支持流式)
        WebSocketManager.on('onResponse', (payload) => {
            console.log('Response:', payload);

            if (payload.is_streaming) {
                // 流式响应: 追加文本到当前消息
                if (payload.text) {
                    UI.appendStreamingMessage('assistant', payload.text);
                }
            } else if (payload.is_final) {
                // 流式响应结束: 完成当前消息
                UI.finalizeStreamingMessage('assistant');
            } else if (payload.text) {
                // 非流式响应: 直接添加完整消息
                UI.addChatMessage('assistant', payload.text);
            }
        });

        // 收到 TTS 音频
        WebSocketManager.on('onAudio', (payload) => {
            if (window.debugLog) debugLog('Audio received, len: ' + (payload.data ? payload.data.length : 0));

            if (payload.data) {
                UI.playTTSAudio(payload.data);
            }
        });

        // 收到状态更新
        WebSocketManager.on('onStatus', (payload) => {
            console.log('Status:', payload);

            if (payload.provider && payload.model) {
                UI.setProviderInfo(payload.provider, payload.model);
            }
        });
    },

    /**
     * 设置 UI 事件处理
     */
    setupUIHandlers() {
        // 登出
        UI.elements.btnLogout.addEventListener('click', async () => {
            await Auth.logout();
            window.location.href = '/static/login.html';
        });

        // 清除记忆
        UI.elements.btnClearMemory.addEventListener('click', async () => {
            if (confirm('确定要清除所有对话记忆吗？此操作不可恢复。')) {
                try {
                    const response = await fetch('/api/memory/clear', {
                        method: 'DELETE',
                        credentials: 'include',
                    });

                    if (response.ok) {
                        UI.showToast('记忆已清除', 'success');
                        UI.clearChat();
                    } else {
                        UI.showToast('清除失败', 'error');
                    }
                } catch (error) {
                    UI.showToast('操作失败', 'error');
                }
            }
        });

        // 管理页面
        UI.elements.btnAdmin.addEventListener('click', () => {
            window.location.href = '/static/admin.html';
        });

        // 启动/关闭摄像头
        UI.elements.btnStartCamera.addEventListener('click', async () => {
            if (this.cameraActive) {
                MediaManager.stopCamera();
                this.cameraActive = false;
                UI.setCameraActive(false);
            } else {
                const deviceId = UI.elements.cameraSelect.value || null;
                const success = await MediaManager.startCamera(deviceId);

                if (success) {
                    this.cameraActive = true;
                    UI.setCameraActive(true);
                } else {
                    UI.showToast('无法启动摄像头', 'error');
                }
            }
        });

        // 摄像头选择变化
        UI.elements.cameraSelect.addEventListener('change', async () => {
            if (this.cameraActive) {
                const deviceId = UI.elements.cameraSelect.value;
                await MediaManager.startCamera(deviceId);
            }
        });

        // 拍照
        UI.elements.btnCapture.addEventListener('click', () => {
            if (!this.cameraActive) {
                UI.showToast('请先启动摄像头', 'warning');
                return;
            }

            const image = MediaManager.captureFrame();
            if (image) {
                this.currentImage = image;
                UI.showToast('已拍照，发送消息时将附带此图片', 'success');
            } else {
                UI.showToast('拍照失败', 'error');
            }
        });

        // 开始/停止录音
        UI.elements.btnRecord.addEventListener('click', async () => {
            if (this.recordingActive) {
                // 手动停止时，如果有摄像头开启，自动截图
                if (UI.settings.autoCapture && this.cameraActive) {
                    this.currentImage = MediaManager.captureFrame();
                    if (window.debugLog) debugLog('[Record] Auto captured image on manual stop');
                }
                // 停止录音并发送已录制的内容
                MediaManager.stopRecording(true);
                this.recordingActive = false;
                UI.setRecordingState(false);
            } else {
                const success = await MediaManager.startRecording();

                if (success) {
                    this.recordingActive = true;
                    UI.setRecordingState(true);
                } else {
                    UI.showToast('无法启动麦克风', 'error');
                }
            }
        });

        // 发送文本
        UI.elements.btnSendText.addEventListener('click', () => {
            const text = UI.getAndClearTextInput();
            if (!text) return;

            // 发送文本和可选图片
            WebSocketManager.sendText(text, this.currentImage);

            // 显示用户消息
            UI.addChatMessage('user', text, this.currentImage);

            // 清除当前图片和预览
            this.currentImage = null;
            UI.clearPendingImage();
        });

        // 清空对话
        UI.elements.btnClearChat.addEventListener('click', () => {
            if (confirm('确定要清空当前对话吗？')) {
                UI.clearChat();
                WebSocketManager.sendControl('clear_session');
            }
        });
    },

    /**
     * 加载摄像头列表
     */
    async loadCameras() {
        const cameras = await MediaManager.getCameras();
        UI.updateCameraList(cameras);
    },

    /**
     * 加载配置
     */
    async loadConfig() {
        try {
            const response = await fetch('/api/config', {
                credentials: 'include',
            });

            if (response.ok) {
                const config = await response.json();

                if (config.vision_llm) {
                    const provider = config.vision_llm.active_provider || 'lmstudio';
                    const model = config.vision_llm.default_model || '';

                    UI.setProviderInfo(provider, model);

                    // 更新设置
                    UI.settings.provider = provider;
                    UI.settings.model = model;
                }
            }
        } catch (error) {
            console.error('Failed to load config:', error);
        }
    },

    /**
     * 设置变更回调
     * @param {object} settings 新设置
     */
    onSettingsChanged(settings) {
        // 通知服务器
        if (WebSocketManager.connected) {
            WebSocketManager.sendControl('set_config', {
                provider: settings.provider,
                model: settings.model,
            });
        }
    },

    /**
     * 清理资源
     */
    cleanup() {
        MediaManager.stopCamera();
        MediaManager.stopRecording();
        WebSocketManager.disconnect();
    }
};

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});

// 页面关闭前清理
window.addEventListener('beforeunload', () => {
    App.cleanup();
});

// 导出到全局
window.App = App;
