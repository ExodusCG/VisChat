/**
 * CC_VisChat - 媒体模块
 * 处理摄像头、麦克风和屏幕截图
 */

const MediaManager = {
    // 媒体流
    videoStream: null,
    audioStream: null,
    screenStream: null,

    // DOM 元素
    videoElement: null,

    // 音频处理
    audioContext: null,
    audioAnalyser: null,
    audioProcessor: null,
    audioSource: null,

    // 录音状态
    isRecording: false,
    audioChunks: [],

    // VAD 配置
    vadConfig: {
        threshold: 0.02,         // 音量阈值
        silenceDuration: 800,    // 静音判定时间(ms)
        hangoverFrames: 3,       // 挂起帧数
    },

    // VAD 状态
    vadState: {
        isSpeaking: false,
        silenceStart: null,
        hangoverCount: 0,
    },

    // 回调
    callbacks: {
        onVolumeChange: null,
        onSpeechStart: null,
        onSpeechEnd: null,
        onAudioData: null,
    },

    /**
     * 初始化媒体管理器
     * @param {HTMLVideoElement} videoElement 视频预览元素
     */
    init(videoElement) {
        this.videoElement = videoElement;
    },

    /**
     * 获取可用的摄像头列表
     * @returns {Promise<Array<{deviceId: string, label: string}>>}
     */
    async getCameras() {
        try {
            // 先请求权限
            await navigator.mediaDevices.getUserMedia({ video: true });

            const devices = await navigator.mediaDevices.enumerateDevices();
            return devices
                .filter(device => device.kind === 'videoinput')
                .map(device => ({
                    deviceId: device.deviceId,
                    label: device.label || `摄像头 ${device.deviceId.substr(0, 8)}`,
                }));
        } catch (error) {
            console.error('Failed to get cameras:', error);
            return [];
        }
    },

    /**
     * 获取可用的麦克风列表
     * @returns {Promise<Array<{deviceId: string, label: string}>>}
     */
    async getMicrophones() {
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            return devices
                .filter(device => device.kind === 'audioinput')
                .map(device => ({
                    deviceId: device.deviceId,
                    label: device.label || `麦克风 ${device.deviceId.substr(0, 8)}`,
                }));
        } catch (error) {
            console.error('Failed to get microphones:', error);
            return [];
        }
    },

    /**
     * 启动摄像头
     * @param {string} deviceId 设备ID (可选)
     * @returns {Promise<boolean>}
     */
    async startCamera(deviceId = null) {
        try {
            // 停止现有流
            this.stopCamera();

            const constraints = {
                video: deviceId ? { deviceId: { exact: deviceId } } : {
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                    facingMode: 'user',
                },
            };

            this.videoStream = await navigator.mediaDevices.getUserMedia(constraints);

            if (this.videoElement) {
                this.videoElement.srcObject = this.videoStream;
            }

            return true;
        } catch (error) {
            console.error('Failed to start camera:', error);
            return false;
        }
    },

    /**
     * 停止摄像头
     */
    stopCamera() {
        if (this.videoStream) {
            this.videoStream.getTracks().forEach(track => track.stop());
            this.videoStream = null;
        }

        if (this.videoElement) {
            this.videoElement.srcObject = null;
        }
    },

    // 图片压缩配置
    imageConfig: {
        maxWidth: 1280,      // 最大宽度
        maxHeight: 1280,     // 最大高度
        quality: 0.7,        // JPEG 质量 (0-1)
        mobileQuality: 0.6,  // 移动端质量 (更激进压缩)
    },

    /**
     * 检测是否为移动端
     */
    isMobile() {
        return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    },

    /**
     * 压缩图片
     * @param {HTMLCanvasElement|HTMLVideoElement|HTMLImageElement} source 图片源
     * @param {number} srcWidth 原始宽度
     * @param {number} srcHeight 原始高度
     * @returns {string} Base64 编码的压缩图片
     */
    compressImage(source, srcWidth, srcHeight) {
        const config = this.imageConfig;
        const quality = this.isMobile() ? config.mobileQuality : config.quality;

        // 计算缩放比例
        let width = srcWidth;
        let height = srcHeight;

        if (width > config.maxWidth || height > config.maxHeight) {
            const ratio = Math.min(config.maxWidth / width, config.maxHeight / height);
            width = Math.round(width * ratio);
            height = Math.round(height * ratio);
        }

        // 创建压缩后的 canvas
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;

        const ctx = canvas.getContext('2d');
        ctx.drawImage(source, 0, 0, width, height);

        // 返回压缩后的 base64
        return canvas.toDataURL('image/jpeg', quality).split(',')[1];
    },

    /**
     * 从摄像头截图
     * @returns {string|null} Base64 编码的图片数据
     */
    captureFrame() {
        if (!this.videoStream || !this.videoElement) {
            console.warn('Camera not started');
            return null;
        }

        try {
            const srcWidth = this.videoElement.videoWidth;
            const srcHeight = this.videoElement.videoHeight;

            // 使用压缩函数
            return this.compressImage(this.videoElement, srcWidth, srcHeight);
        } catch (error) {
            console.error('Failed to capture frame:', error);
            return null;
        }
    },

    /**
     * 屏幕截图
     * @returns {Promise<string|null>} Base64 编码的图片数据
     */
    async captureScreen() {
        try {
            // 请求屏幕共享
            this.screenStream = await navigator.mediaDevices.getDisplayMedia({
                video: {
                    cursor: 'always',
                },
            });

            // 创建视频元素来捕获帧
            const video = document.createElement('video');
            video.srcObject = this.screenStream;
            video.muted = true;

            return new Promise((resolve, reject) => {
                video.onloadedmetadata = () => {
                    video.play();

                    // 等待一帧后截图
                    setTimeout(() => {
                        try {
                            const srcWidth = video.videoWidth;
                            const srcHeight = video.videoHeight;

                            // 停止屏幕共享
                            this.screenStream.getTracks().forEach(track => track.stop());
                            this.screenStream = null;

                            // 使用压缩函数返回 base64 图片
                            resolve(this.compressImage(video, srcWidth, srcHeight));
                        } catch (error) {
                            reject(error);
                        }
                    }, 100);
                };

                video.onerror = reject;
            });
        } catch (error) {
            console.error('Failed to capture screen:', error);
            if (this.screenStream) {
                this.screenStream.getTracks().forEach(track => track.stop());
                this.screenStream = null;
            }
            return null;
        }
    },

    /**
     * 启动麦克风录音
     * @returns {Promise<boolean>}
     */
    async startRecording() {
        if (this.isRecording) {
            return true;
        }

        try {
            // 获取音频流
            this.audioStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    sampleRate: 16000,
                },
            });

            // 创建音频上下文
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000,
            });

            // 创建音频源
            this.audioSource = this.audioContext.createMediaStreamSource(this.audioStream);

            // 创建分析器 (用于音量检测)
            this.audioAnalyser = this.audioContext.createAnalyser();
            this.audioAnalyser.fftSize = 256;
            this.audioSource.connect(this.audioAnalyser);

            // 创建处理器 (用于获取音频数据)
            // 使用 ScriptProcessorNode (已废弃但兼容性好)
            const bufferSize = 4096; // 约 256ms @ 16kHz
            this.audioProcessor = this.audioContext.createScriptProcessor(bufferSize, 1, 1);

            this.audioProcessor.onaudioprocess = (event) => {
                if (!this.isRecording) return;

                const inputData = event.inputBuffer.getChannelData(0);
                this.processAudioData(inputData);
            };

            this.audioSource.connect(this.audioProcessor);
            this.audioProcessor.connect(this.audioContext.destination);

            this.isRecording = true;
            this.audioChunks = [];
            this.resetVadState();

            // 启动音量监测
            this.startVolumeMonitor();

            return true;
        } catch (error) {
            console.error('Failed to start recording:', error);
            return false;
        }
    },

    /**
     * 停止录音
     * @param {boolean} sendRemaining 是否发送已录制的内容 (默认 true)
     */
    stopRecording(sendRemaining = true) {
        // 如果有已录制的音频且需要发送
        if (sendRemaining && this.audioChunks.length > 0 && this.callbacks.onAudioData) {
            const combinedAudio = this.combineAudioChunks();
            // 只发送有效长度的音频 (至少 0.3 秒 @ 16kHz = 4800 samples)
            if (combinedAudio.length > 4800) {
                const base64Audio = this.audioToBase64(combinedAudio);
                this.callbacks.onAudioData(base64Audio);
                if (window.debugLog) debugLog('[Media] Sent remaining audio on stop, samples: ' + combinedAudio.length);
            }
        }

        this.isRecording = false;

        if (this.audioProcessor) {
            this.audioProcessor.disconnect();
            this.audioProcessor = null;
        }

        if (this.audioAnalyser) {
            this.audioAnalyser.disconnect();
            this.audioAnalyser = null;
        }

        if (this.audioSource) {
            this.audioSource.disconnect();
            this.audioSource = null;
        }

        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        if (this.audioStream) {
            this.audioStream.getTracks().forEach(track => track.stop());
            this.audioStream = null;
        }

        this.stopVolumeMonitor();
        this.audioChunks = [];  // 清空音频块
    },

    /**
     * 处理音频数据
     * @param {Float32Array} audioData 音频数据
     */
    processAudioData(audioData) {
        // 计算音量 (RMS)
        let sum = 0;
        for (let i = 0; i < audioData.length; i++) {
            sum += audioData[i] * audioData[i];
        }
        const rms = Math.sqrt(sum / audioData.length);

        // VAD 检测
        const isSpeech = rms > this.vadConfig.threshold;

        if (isSpeech) {
            // 检测到语音
            this.vadState.silenceStart = null;
            this.vadState.hangoverCount = this.vadConfig.hangoverFrames;

            if (!this.vadState.isSpeaking) {
                this.vadState.isSpeaking = true;
                if (this.callbacks.onSpeechStart) {
                    this.callbacks.onSpeechStart();
                }
            }

            // 收集音频数据
            this.audioChunks.push(new Float32Array(audioData));
        } else {
            // 静音
            if (this.vadState.isSpeaking) {
                if (this.vadState.hangoverCount > 0) {
                    // 挂起期间继续收集
                    this.vadState.hangoverCount--;
                    this.audioChunks.push(new Float32Array(audioData));
                } else if (!this.vadState.silenceStart) {
                    this.vadState.silenceStart = Date.now();
                    this.audioChunks.push(new Float32Array(audioData));
                } else if (Date.now() - this.vadState.silenceStart >= this.vadConfig.silenceDuration) {
                    // 静音超过阈值，语音结束
                    this.vadState.isSpeaking = false;

                    // 发送收集的音频数据
                    if (this.audioChunks.length > 0 && this.callbacks.onAudioData) {
                        const combinedAudio = this.combineAudioChunks();
                        const base64Audio = this.audioToBase64(combinedAudio);
                        this.callbacks.onAudioData(base64Audio);
                    }

                    // 重置状态以便继续检测下一段语音
                    this.audioChunks = [];
                    this.vadState.silenceStart = null;
                    this.vadState.hangoverCount = 0;

                    if (this.callbacks.onSpeechEnd) {
                        this.callbacks.onSpeechEnd();
                    }
                } else {
                    // 继续等待
                    this.audioChunks.push(new Float32Array(audioData));
                }
            }
        }
    },

    /**
     * 合并音频块
     * @returns {Float32Array}
     */
    combineAudioChunks() {
        const totalLength = this.audioChunks.reduce((sum, chunk) => sum + chunk.length, 0);
        const combined = new Float32Array(totalLength);

        let offset = 0;
        for (const chunk of this.audioChunks) {
            combined.set(chunk, offset);
            offset += chunk.length;
        }

        return combined;
    },

    /**
     * 将音频数据转换为 Base64
     * @param {Float32Array} audioData 音频数据
     * @returns {string}
     */
    audioToBase64(audioData) {
        // 将 Float32Array 转换为 ArrayBuffer
        const buffer = audioData.buffer;
        const bytes = new Uint8Array(buffer);

        // 转换为 Base64
        let binary = '';
        for (let i = 0; i < bytes.length; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    },

    /**
     * 重置 VAD 状态
     */
    resetVadState() {
        this.vadState = {
            isSpeaking: false,
            silenceStart: null,
            hangoverCount: 0,
        };
        this.audioChunks = [];
    },

    /**
     * 启动音量监测
     */
    startVolumeMonitor() {
        if (!this.audioAnalyser) return;

        const dataArray = new Uint8Array(this.audioAnalyser.frequencyBinCount);

        const monitor = () => {
            if (!this.isRecording || !this.audioAnalyser) return;

            this.audioAnalyser.getByteFrequencyData(dataArray);

            // 计算平均音量
            let sum = 0;
            for (let i = 0; i < dataArray.length; i++) {
                sum += dataArray[i];
            }
            const average = sum / dataArray.length;
            const volume = average / 255; // 归一化到 0-1

            if (this.callbacks.onVolumeChange) {
                this.callbacks.onVolumeChange(volume);
            }

            requestAnimationFrame(monitor);
        };

        monitor();
    },

    /**
     * 停止音量监测
     */
    stopVolumeMonitor() {
        // 监测会随着 isRecording = false 自动停止
    },

    /**
     * 设置回调
     * @param {string} event 事件名称
     * @param {function} callback 回调函数
     */
    on(event, callback) {
        if (this.callbacks.hasOwnProperty(event)) {
            this.callbacks[event] = callback;
        }
    },

    /**
     * 检查是否有摄像头
     * @returns {boolean}
     */
    hasCamera() {
        return this.videoStream !== null;
    },

    /**
     * 检查是否正在录音
     * @returns {boolean}
     */
    isRecordingNow() {
        return this.isRecording;
    },

    /**
     * 播放 TTS 音频
     * @param {string} audioBase64 Base64 编码的音频数据
     * @param {HTMLAudioElement} audioElement 音频元素
     */
    playAudio(audioBase64, audioElement) {
        try {
            // 假设是 MP3 格式
            const audioSrc = `data:audio/mp3;base64,${audioBase64}`;
            audioElement.src = audioSrc;
            audioElement.play().catch(error => {
                console.error('Failed to play audio:', error);
            });
        } catch (error) {
            console.error('Failed to play audio:', error);
        }
    }
};

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MediaManager;
}
