/**
 * CC_VisChat - UI 控制模块
 * 处理界面交互和状态管理
 */

const UI = {
    // DOM 元素缓存
    elements: {},

    // 设置状态
    settings: {
        darkTheme: false,
        provider: 'lmstudio',
        model: '',
        autoTTS: true,
        autoCapture: true,
    },

    /**
     * 初始化 UI
     */
    init() {
        this.cacheElements();
        this.loadSettings();
        this.setupEventListeners();
        this.applyTheme();
    },

    /**
     * 缓存 DOM 元素
     */
    cacheElements() {
        this.elements = {
            // 用户菜单
            displayName: document.getElementById('display-name'),
            userMenuTrigger: document.getElementById('user-menu-trigger'),
            userMenuDropdown: document.getElementById('user-menu-dropdown'),
            btnSettings: document.getElementById('btn-settings'),
            btnAdmin: document.getElementById('btn-admin'),
            btnClearMemory: document.getElementById('btn-clear-memory'),
            btnLogout: document.getElementById('btn-logout'),

            // 视频区域
            videoPreview: document.getElementById('video-preview'),
            videoPlaceholder: document.getElementById('video-placeholder'),
            videoRecordingOverlay: document.getElementById('video-recording-overlay'),
            cameraSelect: document.getElementById('camera-select'),
            btnStartCamera: document.getElementById('btn-start-camera'),
            btnCapture: document.getElementById('btn-capture'),

            // 对话区域
            chatMessages: document.getElementById('chat-messages'),
            chatEmpty: document.getElementById('chat-empty'),
            btnClearChat: document.getElementById('btn-clear-chat'),
            textInput: document.getElementById('text-input'),
            btnSendText: document.getElementById('btn-send-text'),

            // 录音区域
            recordingIndicator: document.getElementById('recording-indicator'),
            recordingText: document.getElementById('recording-text'),
            volumeMeterFill: document.getElementById('volume-meter-fill'),
            btnRecord: document.getElementById('btn-record'),

            // 状态栏
            connectionStatusDot: document.getElementById('connection-status-dot'),
            connectionStatusText: document.getElementById('connection-status-text'),
            providerMode: document.getElementById('provider-mode'),
            currentModel: document.getElementById('current-model'),

            // 设置模态框
            settingsModal: document.getElementById('settings-modal'),
            settingsClose: document.getElementById('settings-close'),
            settingsCancel: document.getElementById('settings-cancel'),
            settingsSave: document.getElementById('settings-save'),
            settingDarkTheme: document.getElementById('setting-dark-theme'),
            settingProvider: document.getElementById('setting-provider'),
            settingModel: document.getElementById('setting-model'),
            settingAutoTTS: document.getElementById('setting-auto-tts'),
            settingAutoCapture: document.getElementById('setting-auto-capture'),

            // 图片预览
            imagePreviewModal: document.getElementById('image-preview-modal'),
            imagePreviewImg: document.getElementById('image-preview-img'),

            // 图片上传
            btnUploadImage: document.getElementById('btn-upload-image'),
            imageUpload: document.getElementById('image-upload'),
            pendingImagePreview: document.getElementById('pending-image-preview'),
            pendingImageImg: document.getElementById('pending-image-img'),
            pendingImageRemove: document.getElementById('pending-image-remove'),

            // 修改密码
            btnChangePassword: document.getElementById('btn-change-password'),
            passwordModal: document.getElementById('password-modal'),
            passwordClose: document.getElementById('password-close'),
            passwordCancel: document.getElementById('password-cancel'),
            passwordSave: document.getElementById('password-save'),
            oldPassword: document.getElementById('old-password'),
            newPassword: document.getElementById('new-password'),
            confirmPassword: document.getElementById('confirm-password'),
            passwordError: document.getElementById('password-error'),

            // Toast 容器
            toastContainer: document.getElementById('toast-container'),

            // 音频播放器
            ttsAudio: document.getElementById('tts-audio'),
        };
    },

    /**
     * 加载设置
     */
    loadSettings() {
        const savedSettings = localStorage.getItem('cc_vischat_settings');
        if (savedSettings) {
            try {
                Object.assign(this.settings, JSON.parse(savedSettings));
            } catch (e) {
                console.error('Failed to load settings:', e);
            }
        }

        // 应用到 UI
        this.elements.settingDarkTheme.checked = this.settings.darkTheme;
        this.elements.settingProvider.value = this.settings.provider;
        this.elements.settingAutoTTS.checked = this.settings.autoTTS;
        this.elements.settingAutoCapture.checked = this.settings.autoCapture;
    },

    /**
     * 保存设置
     */
    saveSettings() {
        localStorage.setItem('cc_vischat_settings', JSON.stringify(this.settings));
    },

    /**
     * 应用主题
     */
    applyTheme() {
        document.documentElement.setAttribute('data-theme', this.settings.darkTheme ? 'dark' : 'light');
    },

    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        // 用户菜单
        this.elements.userMenuTrigger.addEventListener('click', () => {
            this.elements.userMenuDropdown.classList.toggle('show');
        });

        // 点击其他地方关闭菜单
        document.addEventListener('click', (e) => {
            if (!this.elements.userMenuTrigger.contains(e.target)) {
                this.elements.userMenuDropdown.classList.remove('show');
            }
        });

        // 设置按钮
        this.elements.btnSettings.addEventListener('click', () => {
            this.openSettingsModal();
        });

        // 设置模态框
        this.elements.settingsClose.addEventListener('click', () => {
            this.closeSettingsModal();
        });

        this.elements.settingsCancel.addEventListener('click', () => {
            this.closeSettingsModal();
        });

        this.elements.settingsSave.addEventListener('click', () => {
            this.saveSettingsFromModal();
        });

        // 点击模态框背景关闭
        this.elements.settingsModal.addEventListener('click', (e) => {
            if (e.target === this.elements.settingsModal) {
                this.closeSettingsModal();
            }
        });

        // 图片预览模态框
        this.elements.imagePreviewModal.addEventListener('click', () => {
            this.elements.imagePreviewModal.classList.remove('show');
        });

        // 文本输入回车发送
        this.elements.textInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.elements.btnSendText.click();
            }
        });

        // 提供者切换时更新模型列表
        this.elements.settingProvider.addEventListener('change', () => {
            this.updateModelList();
        });

        // 图片上传按钮
        if (this.elements.btnUploadImage && this.elements.imageUpload) {
            this.elements.btnUploadImage.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                console.log('[UI] Upload button clicked');
                this.elements.imageUpload.click();
            });

            // 图片文件选择
            this.elements.imageUpload.addEventListener('change', (e) => {
                console.log('[UI] File selected');
                const file = e.target.files[0];
                if (file) {
                    this.handleImageFile(file);
                }
                // 清空 input 以便重复选择同一文件
                e.target.value = '';
            });
        } else {
            console.warn('[UI] Upload elements not found:', {
                btnUploadImage: this.elements.btnUploadImage,
                imageUpload: this.elements.imageUpload
            });
        }

        // 移除待发送图片
        if (this.elements.pendingImageRemove) {
            this.elements.pendingImageRemove.addEventListener('click', () => {
                this.clearPendingImage();
            });
        }

        // 粘贴图片支持
        document.addEventListener('paste', (e) => {
            const items = e.clipboardData?.items;
            if (!items) return;

            for (const item of items) {
                if (item.type.startsWith('image/')) {
                    e.preventDefault();
                    const file = item.getAsFile();
                    if (file) {
                        this.handleImageFile(file);
                    }
                    break;
                }
            }
        });

        // 修改密码按钮
        if (this.elements.btnChangePassword) {
            this.elements.btnChangePassword.addEventListener('click', () => {
                this.openPasswordModal();
            });
        }

        // 修改密码模态框
        if (this.elements.passwordClose) {
            this.elements.passwordClose.addEventListener('click', () => {
                this.closePasswordModal();
            });
        }

        if (this.elements.passwordCancel) {
            this.elements.passwordCancel.addEventListener('click', () => {
                this.closePasswordModal();
            });
        }

        if (this.elements.passwordSave) {
            this.elements.passwordSave.addEventListener('click', () => {
                this.submitPasswordChange();
            });
        }

        if (this.elements.passwordModal) {
            this.elements.passwordModal.addEventListener('click', (e) => {
                if (e.target === this.elements.passwordModal) {
                    this.closePasswordModal();
                }
            });
        }
    },

    /**
     * 处理图片文件
     * @param {File} file 图片文件
     */
    handleImageFile(file) {
        // 检查文件类型
        if (!file.type.startsWith('image/')) {
            this.showToast('请选择图片文件', 'warning');
            return;
        }

        // 检查文件大小 (最大 10MB)
        const maxSize = 10 * 1024 * 1024;
        if (file.size > maxSize) {
            this.showToast('图片大小不能超过 10MB', 'warning');
            return;
        }

        // 使用 Image 对象加载图片进行压缩
        const reader = new FileReader();
        reader.onload = (e) => {
            const img = new Image();
            img.onload = () => {
                // 使用 MediaManager 的压缩函数
                if (window.MediaManager && window.MediaManager.compressImage) {
                    const compressedBase64 = MediaManager.compressImage(img, img.width, img.height);
                    const dataUrl = 'data:image/jpeg;base64,' + compressedBase64;
                    this.setPendingImage(compressedBase64, dataUrl);
                } else {
                    // 回退: 直接使用原图
                    const base64 = e.target.result.split(',')[1];
                    this.setPendingImage(base64, e.target.result);
                }
            };
            img.onerror = () => {
                this.showToast('图片加载失败', 'error');
            };
            img.src = e.target.result;
        };
        reader.onerror = () => {
            this.showToast('读取图片失败', 'error');
        };
        reader.readAsDataURL(file);
    },

    /**
     * 设置待发送图片
     * @param {string} base64 Base64 编码的图片数据
     * @param {string} dataUrl 完整的 Data URL (用于预览)
     */
    setPendingImage(base64, dataUrl) {
        // 通知 App 设置图片
        if (window.App) {
            window.App.currentImage = base64;
        }

        // 显示预览
        this.elements.pendingImageImg.src = dataUrl;
        this.elements.pendingImagePreview.style.display = 'flex';

        this.showToast('图片已添加，将随消息发送', 'success');
    },

    /**
     * 清除待发送图片
     */
    clearPendingImage() {
        if (window.App) {
            window.App.currentImage = null;
        }

        this.elements.pendingImageImg.src = '';
        this.elements.pendingImagePreview.style.display = 'none';
    },

    /**
     * 打开修改密码模态框
     */
    openPasswordModal() {
        // 清空输入
        this.elements.oldPassword.value = '';
        this.elements.newPassword.value = '';
        this.elements.confirmPassword.value = '';
        this.elements.passwordError.textContent = '';
        this.elements.passwordError.classList.remove('show');

        this.elements.passwordModal.classList.add('show');
    },

    /**
     * 关闭修改密码模态框
     */
    closePasswordModal() {
        this.elements.passwordModal.classList.remove('show');
    },

    /**
     * 提交密码修改
     */
    async submitPasswordChange() {
        const oldPassword = this.elements.oldPassword.value;
        const newPassword = this.elements.newPassword.value;
        const confirmPassword = this.elements.confirmPassword.value;

        // 验证
        if (!oldPassword) {
            this.showPasswordError('请输入当前密码');
            return;
        }

        if (!newPassword) {
            this.showPasswordError('请输入新密码');
            return;
        }

        if (newPassword.length < 6) {
            this.showPasswordError('新密码长度至少6位');
            return;
        }

        if (newPassword !== confirmPassword) {
            this.showPasswordError('两次输入的新密码不一致');
            return;
        }

        // 提交
        try {
            const response = await fetch('/api/auth/change-password', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({
                    old_password: oldPassword,
                    new_password: newPassword,
                }),
            });

            const data = await response.json();

            if (response.ok) {
                this.closePasswordModal();
                this.showToast('密码修改成功，请重新登录', 'success');
                // 调用登出接口清除 session，然后跳转到登录页
                setTimeout(async () => {
                    await fetch('/api/auth/logout', {
                        method: 'POST',
                        credentials: 'include',
                    });
                    window.location.href = '/static/login.html';
                }, 1500);
            } else {
                this.showPasswordError(data.detail || '密码修改失败');
            }
        } catch (error) {
            console.error('Change password error:', error);
            this.showPasswordError('网络错误，请重试');
        }
    },

    /**
     * 显示密码错误信息
     */
    showPasswordError(message) {
        this.elements.passwordError.textContent = message;
        this.elements.passwordError.classList.add('show');
    },

    /**
     * 设置用户信息
     * @param {object} user 用户对象
     */
    setUser(user) {
        this.elements.displayName.textContent = user.display_name || user.username;

        // 显示/隐藏管理按钮
        if (user.role === 'admin') {
            this.elements.btnAdmin.style.display = 'block';
        } else {
            this.elements.btnAdmin.style.display = 'none';
        }
    },

    /**
     * 更新连接状态
     * @param {string} status 状态 (connected/disconnected/connecting)
     */
    setConnectionStatus(status) {
        const dot = this.elements.connectionStatusDot;
        const text = this.elements.connectionStatusText;

        dot.className = 'status-dot';

        switch (status) {
            case 'connected':
                dot.classList.add('connected');
                text.textContent = '已连接';
                break;
            case 'connecting':
                dot.classList.add('connecting');
                text.textContent = '连接中...';
                break;
            default:
                dot.classList.add('disconnected');
                text.textContent = '未连接';
        }
    },

    /**
     * 更新提供者和模型显示
     * @param {string} provider 提供者
     * @param {string} model 模型
     */
    setProviderInfo(provider, model) {
        this.elements.providerMode.textContent = provider === 'lmstudio' ? 'LMStudio' : '本地反代';
        this.elements.currentModel.textContent = model || '-';
        this.settings.provider = provider;
        this.settings.model = model;
    },

    /**
     * 更新模型列表
     */
    async updateModelList() {
        const provider = this.elements.settingProvider.value;
        const select = this.elements.settingModel;

        select.innerHTML = '<option value="">加载中...</option>';

        try {
            const response = await fetch(`/api/models?provider=${provider}`, {
                credentials: 'include'
            });
            if (response.ok) {
                const data = await response.json();
                const models = data.models || [];
                select.innerHTML = '';

                if (models.length === 0) {
                    select.innerHTML = '<option value="">无可用模型</option>';
                } else {
                    models.forEach(model => {
                        const option = document.createElement('option');
                        option.value = model.id || model;
                        option.textContent = model.name || model.id || model;
                        select.appendChild(option);
                    });

                    // 选中当前模型或默认模型
                    if (this.settings.model) {
                        select.value = this.settings.model;
                    } else if (data.default_model) {
                        select.value = data.default_model;
                    }
                }
            } else {
                select.innerHTML = '<option value="">加载失败</option>';
            }
        } catch (error) {
            console.error('Failed to fetch models:', error);
            select.innerHTML = '<option value="">加载失败</option>';
        }
    },

    /**
     * 打开设置模态框
     */
    openSettingsModal() {
        // 同步当前设置到 UI
        this.elements.settingDarkTheme.checked = this.settings.darkTheme;
        this.elements.settingProvider.value = this.settings.provider;
        this.elements.settingAutoTTS.checked = this.settings.autoTTS;
        this.elements.settingAutoCapture.checked = this.settings.autoCapture;

        // 更新模型列表
        this.updateModelList();

        this.elements.settingsModal.classList.add('show');
    },

    /**
     * 关闭设置模态框
     */
    closeSettingsModal() {
        this.elements.settingsModal.classList.remove('show');
    },

    /**
     * 从模态框保存设置
     */
    saveSettingsFromModal() {
        const newSettings = {
            darkTheme: this.elements.settingDarkTheme.checked,
            provider: this.elements.settingProvider.value,
            model: this.elements.settingModel.value,
            autoTTS: this.elements.settingAutoTTS.checked,
            autoCapture: this.elements.settingAutoCapture.checked,
        };

        // 检查是否有变化需要通知服务器
        const providerChanged = newSettings.provider !== this.settings.provider;
        const modelChanged = newSettings.model !== this.settings.model;

        Object.assign(this.settings, newSettings);
        this.saveSettings();
        this.applyTheme();

        // 更新状态栏
        this.setProviderInfo(this.settings.provider, this.settings.model);

        // 如果提供者或模型变化，通知应用
        if ((providerChanged || modelChanged) && window.App) {
            window.App.onSettingsChanged(this.settings);
        }

        this.closeSettingsModal();
        this.showToast('设置已保存', 'success');
    },

    /**
     * 更新摄像头列表
     * @param {Array} cameras 摄像头列表
     */
    updateCameraList(cameras) {
        const select = this.elements.cameraSelect;
        select.innerHTML = '<option value="">选择摄像头...</option>';

        cameras.forEach(camera => {
            const option = document.createElement('option');
            option.value = camera.deviceId;
            option.textContent = camera.label;
            select.appendChild(option);
        });
    },

    /**
     * 设置摄像头状态
     * @param {boolean} active 是否激活
     */
    setCameraActive(active) {
        if (active) {
            this.elements.videoPlaceholder.classList.add('hidden');
            this.elements.btnStartCamera.innerHTML = '<span>&#128247;</span> 关闭摄像头';
        } else {
            this.elements.videoPlaceholder.classList.remove('hidden');
            this.elements.btnStartCamera.innerHTML = '<span>&#128247;</span> 启动摄像头';
        }
    },

    /**
     * 设置录音状态
     * @param {boolean} active 是否激活
     * @param {string} text 状态文字
     */
    setRecordingState(active, text = '') {
        const indicator = this.elements.recordingIndicator;
        const statusText = this.elements.recordingText;
        const btn = this.elements.btnRecord;

        if (active) {
            indicator.classList.add('listening');
            statusText.textContent = text || '正在聆听...';
            btn.classList.add('active');
            btn.innerHTML = '<span>&#128264;</span> 停止录音';
        } else {
            indicator.classList.remove('listening', 'active');
            statusText.textContent = text || '点击开始录音';
            btn.classList.remove('active');
            btn.innerHTML = '<span>&#127908;</span> 开始录音';
        }
    },

    /**
     * 设置语音检测状态
     * @param {boolean} speaking 是否正在说话
     */
    setSpeakingState(speaking) {
        const indicator = this.elements.recordingIndicator;
        const statusText = this.elements.recordingText;

        if (speaking) {
            indicator.classList.remove('listening');
            indicator.classList.add('active');
            statusText.textContent = '正在录音...';
        } else {
            indicator.classList.remove('active');
            indicator.classList.add('listening');
            statusText.textContent = '正在聆听...';
        }
    },

    /**
     * 更新音量指示器
     * @param {number} volume 音量 (0-1)
     */
    setVolume(volume) {
        const percentage = Math.min(100, Math.max(0, volume * 100));
        this.elements.volumeMeterFill.style.width = percentage + '%';
    },

    /**
     * 添加聊天消息
     * @param {string} role 角色 (user/assistant)
     * @param {string} content 内容
     * @param {string} imageBase64 可选图片
     */
    addChatMessage(role, content, imageBase64 = null) {
        // 隐藏空状态
        this.elements.chatEmpty.classList.add('hidden');

        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${role}`;

        const time = new Date().toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
        });

        let imageHtml = '';
        if (imageBase64) {
            imageHtml = `<img class="chat-message-image" src="data:image/jpeg;base64,${imageBase64}" alt="图片" onclick="UI.showImagePreview(this.src)">`;
        }

        messageDiv.innerHTML = `
            <div class="chat-message-header">
                <span class="chat-message-role ${role}">${role === 'user' ? '用户' : 'AI'}</span>
                <span class="chat-message-time">${time}</span>
            </div>
            <div class="chat-message-content">
                ${this.escapeHtml(content)}
                ${imageHtml}
            </div>
        `;

        this.elements.chatMessages.appendChild(messageDiv);

        // 滚动到底部
        this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
    },

    // 当前流式消息元素
    _streamingMessage: null,
    _streamingContent: '',

    /**
     * 追加流式消息内容
     * @param {string} role 角色
     * @param {string} chunk 文本片段
     */
    appendStreamingMessage(role, chunk) {
        // 如果没有当前流式消息，创建一个新的
        if (!this._streamingMessage) {
            this.elements.chatEmpty.classList.add('hidden');

            const messageDiv = document.createElement('div');
            messageDiv.className = `chat-message ${role} streaming`;

            const time = new Date().toLocaleTimeString('zh-CN', {
                hour: '2-digit',
                minute: '2-digit',
            });

            messageDiv.innerHTML = `
                <div class="chat-message-header">
                    <span class="chat-message-role ${role}">${role === 'user' ? '用户' : 'AI'}</span>
                    <span class="chat-message-time">${time}</span>
                    <span class="streaming-indicator">●</span>
                </div>
                <div class="chat-message-content"></div>
            `;

            this.elements.chatMessages.appendChild(messageDiv);
            this._streamingMessage = messageDiv;
            this._streamingContent = '';
        }

        // 追加内容
        this._streamingContent += chunk;
        const contentDiv = this._streamingMessage.querySelector('.chat-message-content');
        contentDiv.textContent = this._streamingContent;

        // 滚动到底部
        this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
    },

    /**
     * 完成流式消息
     * @param {string} role 角色
     */
    finalizeStreamingMessage(role) {
        if (this._streamingMessage) {
            // 移除流式指示器
            this._streamingMessage.classList.remove('streaming');
            const indicator = this._streamingMessage.querySelector('.streaming-indicator');
            if (indicator) {
                indicator.remove();
            }

            // 重置状态
            this._streamingMessage = null;
            this._streamingContent = '';
        }
    },

    /**
     * 清空聊天记录
     */
    clearChat() {
        this.elements.chatMessages.innerHTML = '';
        this.elements.chatEmpty.classList.remove('hidden');
        this.elements.chatMessages.appendChild(this.elements.chatEmpty);
    },

    /**
     * 显示图片预览
     * @param {string} src 图片源
     */
    showImagePreview(src) {
        this.elements.imagePreviewImg.src = src;
        this.elements.imagePreviewModal.classList.add('show');
    },

    /**
     * 显示 Toast 通知
     * @param {string} message 消息
     * @param {string} type 类型 (success/error/warning)
     * @param {number} duration 持续时间(ms)
     */
    showToast(message, type = 'success', duration = 3000) {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        let icon = '&#9989;'; // success
        if (type === 'error') icon = '&#10060;';
        if (type === 'warning') icon = '&#9888;';

        toast.innerHTML = `
            <span class="toast-icon">${icon}</span>
            <span class="toast-message">${this.escapeHtml(message)}</span>
        `;

        this.elements.toastContainer.appendChild(toast);

        // 自动移除
        setTimeout(() => {
            toast.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, duration);
    },

    /**
     * HTML 转义
     * @param {string} text 文本
     * @returns {string}
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    // 音频解锁状态
    audioUnlocked: false,

    /**
     * 解锁音频播放（移动端需要用户交互后才能播放）
     */
    async unlockAudio() {
        if (this.audioUnlocked) return true;

        try {
            // 使用 AudioContext 来解锁音频（更可靠的方式）
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) {
                const ctx = new AudioContext();

                // 如果是暂停状态，恢复它
                if (ctx.state === 'suspended') {
                    await ctx.resume();
                }

                // 创建一个短暂的静音音频并播放
                const buffer = ctx.createBuffer(1, 1, 22050);
                const source = ctx.createBufferSource();
                source.buffer = buffer;
                source.connect(ctx.destination);
                source.start(0);

                // 关闭临时 context
                setTimeout(() => ctx.close(), 100);

                this.audioUnlocked = true;
                console.log('[TTS] Audio unlocked via AudioContext');
                return true;
            }

            // 备用方案：直接标记为已解锁，让实际播放时再处理
            this.audioUnlocked = true;
            console.log('[TTS] Audio marked as unlocked (fallback)');
            return true;
        } catch (error) {
            console.warn('[TTS] Failed to unlock audio:', error.message);
            // 即使失败也标记为已尝试，避免重复尝试
            this.audioUnlocked = true;
            return false;
        }
    },

    // 音频播放队列
    _audioQueue: [],
    _isPlayingAudio: false,

    /**
     * 播放 TTS 音频 (支持队列)
     * @param {string} audioBase64 Base64 音频数据
     */
    async playTTSAudio(audioBase64) {
        if (window.debugLog) debugLog('[TTS] playTTSAudio called, data length: ' + (audioBase64 ? audioBase64.length : 0));

        if (!this.settings.autoTTS) {
            if (window.debugLog) debugLog('[TTS] autoTTS disabled');
            return;
        }

        if (!audioBase64) {
            if (window.debugLog) debugLog('[TTS] No audio data');
            return;
        }

        // 添加到队列
        this._audioQueue.push(audioBase64);

        // 如果没有在播放，开始播放
        if (!this._isPlayingAudio) {
            this._playNextAudio();
        }
    },

    /**
     * 播放队列中的下一个音频
     */
    async _playNextAudio() {
        if (this._audioQueue.length === 0) {
            this._isPlayingAudio = false;
            return;
        }

        this._isPlayingAudio = true;
        const audioBase64 = this._audioQueue.shift();

        try {
            // 清理之前的 Blob URL (如果有)
            if (this._lastBlobUrl) {
                URL.revokeObjectURL(this._lastBlobUrl);
                this._lastBlobUrl = null;
            }

            // 将 Base64 转换为 Blob (比 Data URL 更高效)
            const binaryString = atob(audioBase64);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            const blob = new Blob([bytes], { type: 'audio/mpeg' });
            const blobUrl = URL.createObjectURL(blob);
            this._lastBlobUrl = blobUrl;

            // 设置音频源
            this.elements.ttsAudio.src = blobUrl;

            if (window.debugLog) debugLog('[TTS] Playing audio from queue...');

            // 监听播放结束，继续播放下一个
            const onEnded = () => {
                this.elements.ttsAudio.removeEventListener('ended', onEnded);
                this._playNextAudio();
            };
            this.elements.ttsAudio.addEventListener('ended', onEnded);

            try {
                await this.elements.ttsAudio.play();
                if (window.debugLog) debugLog('[TTS] Play SUCCESS!');
            } catch (playError) {
                if (window.debugLog) debugLog('[TTS] Play ERROR: ' + playError.name + ' - ' + playError.message);
                this.elements.ttsAudio.removeEventListener('ended', onEnded);

                if (playError.name === 'NotAllowedError') {
                    this.showToast('请点击页面启用语音', 'warning');

                    const retryPlay = async () => {
                        document.removeEventListener('click', retryPlay);
                        document.removeEventListener('touchstart', retryPlay);
                        await this.unlockAudio();
                        try {
                            this.elements.ttsAudio.addEventListener('ended', onEnded);
                            await this.elements.ttsAudio.play();
                            if (window.debugLog) debugLog('[TTS] Retry SUCCESS!');
                        } catch (e) {
                            if (window.debugLog) debugLog('[TTS] Retry FAILED: ' + e.message);
                            this._playNextAudio();  // 继续播放下一个
                        }
                    };
                    document.addEventListener('click', retryPlay, { once: true });
                    document.addEventListener('touchstart', retryPlay, { once: true });
                } else {
                    // 其他错误，继续播放下一个
                    this._playNextAudio();
                }
            }
        } catch (error) {
            if (window.debugLog) debugLog('[TTS] Exception: ' + error.message);
            this._playNextAudio();  // 发生异常也继续播放下一个
        }
    },

    /**
     * 获取文本输入内容并清空
     * @returns {string}
     */
    getAndClearTextInput() {
        const text = this.elements.textInput.value.trim();
        this.elements.textInput.value = '';
        return text;
    }
};

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = UI;
}
