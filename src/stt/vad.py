"""
CC_VisChat - VAD (语音活动检测) 模块

基于能量的语音活动检测器，参考 CC_VoiceIn 的 EnergyVAD 实现。

特性：
- 能量阈值检测
- 自适应噪声估计
- 静音判定 (默认 800ms)
- 挂起机制防止误断
- 线程安全设计
"""

import time
import threading
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum, auto


class VADState(Enum):
    """VAD 状态枚举"""
    IDLE = auto()           # 空闲状态
    INITIALIZING = auto()   # 初始化中 (收集噪声样本)
    LISTENING = auto()      # 监听中 (等待语音)
    SPEECH = auto()         # 检测到语音
    SILENCE = auto()        # 检测到静音 (语音结束后)
    SPEECH_END = auto()     # 语音结束 (静音超过阈值)


@dataclass
class VADConfig:
    """VAD 配置"""
    # 能量阈值 (0.0 ~ 1.0)，低于此值一定判定为静音
    energy_threshold: float = 0.01

    # 噪声倍数，能量需要高于 噪声底 × 此倍数 才判定为语音
    noise_multiplier: float = 3.0

    # 噪声估计的平滑因子 (指数移动平均的 alpha)
    noise_smooth_factor: float = 0.05

    # 语音结束后的挂起块数 (防止短暂停顿误判)
    hangover_chunks: int = 3

    # 静音判定时长 (毫秒)，超过此时长判定为语音结束
    silence_duration_ms: int = 800

    # 初始化需要的帧数 (用于估计背景噪声)
    init_frame_count: int = 10

    # 采样率 (Hz)
    sample_rate: int = 16000

    # 每块时长 (毫秒)
    chunk_duration_ms: int = 500


@dataclass
class VADResult:
    """VAD 处理结果"""
    is_speech: bool         # 是否为语音
    energy: float           # RMS 能量值
    state: VADState         # 当前状态
    noise_estimate: float   # 当前噪声估计
    speech_duration_ms: float = 0.0    # 当前语音段时长 (毫秒)
    silence_duration_ms: float = 0.0   # 当前静音时长 (毫秒)


class VAD:
    """
    基于能量的语音活动检测器 (Energy-based Voice Activity Detector)

    工作原理：
    1. 计算每个音频块的 RMS (均方根) 能量
    2. 维护一个自适应的背景噪声估计 (使用指数移动平均)
    3. 当能量超过 "噪声底 × 倍数 + 固定阈值" 时判定为语音
    4. 使用 hangover 机制避免语音中短暂停顿导致的误判
    5. 静音超过阈值 (默认 800ms) 后判定为语音结束

    使用示例::

        vad = VAD()

        # 处理音频块
        for audio_chunk in audio_stream:
            is_speech = vad.process(audio_chunk)

            if vad.is_speech_end():
                # 语音结束，可以进行 STT
                break
    """

    def __init__(self, config: Optional[VADConfig] = None):
        """
        初始化 VAD

        Args:
            config: VAD 配置，为 None 时使用默认配置
        """
        self._config = config or VADConfig()

        # 内部状态
        self._noise_estimate: float = 0.0           # 背景噪声能量估计
        self._is_initialized: bool = False          # 是否已完成初始化校准
        self._init_frames: List[float] = []         # 初始化阶段收集的能量值
        self._hangover_counter: int = 0             # 挂起计数器
        self._is_speech: bool = False               # 当前是否处于语音状态
        self._state: VADState = VADState.IDLE       # 当前状态

        # 时间追踪
        self._speech_start_time: Optional[float] = None   # 语音开始时间
        self._silence_start_time: Optional[float] = None  # 静音开始时间
        self._speech_duration_ms: float = 0.0             # 当前语音段时长
        self._silence_duration_ms: float = 0.0            # 当前静音时长

        # 语音结束标志
        self._speech_end_detected: bool = False

        # 线程锁 (保护内部状态的线程安全)
        self._lock = threading.Lock()

    def reset(self) -> None:
        """重置 VAD 状态，用于新一轮检测开始时"""
        with self._lock:
            self._noise_estimate = 0.0
            self._is_initialized = False
            self._init_frames.clear()
            self._hangover_counter = 0
            self._is_speech = False
            self._state = VADState.IDLE
            self._speech_start_time = None
            self._silence_start_time = None
            self._speech_duration_ms = 0.0
            self._silence_duration_ms = 0.0
            self._speech_end_detected = False

    @staticmethod
    def compute_rms_energy(audio_data: np.ndarray) -> float:
        """
        计算音频数据的 RMS (均方根) 能量

        Args:
            audio_data: float32 音频数组，值域 [-1.0, 1.0]

        Returns:
            RMS 能量值
        """
        if audio_data.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(audio_data.astype(np.float64) ** 2)))

    def process(self, audio_chunk: np.ndarray) -> bool:
        """
        处理一块音频数据，返回是否检测到语音

        Args:
            audio_chunk: float32 音频数组，值域 [-1.0, 1.0]

        Returns:
            是否检测到语音
        """
        energy = self.compute_rms_energy(audio_chunk)
        current_time = time.monotonic()

        with self._lock:
            # ---- 初始化阶段：收集前几帧用于估计背景噪声 ----
            if not self._is_initialized:
                self._state = VADState.INITIALIZING
                self._init_frames.append(energy)

                if len(self._init_frames) >= self._config.init_frame_count:
                    # 取中位数作为初始噪声估计 (比均值更鲁棒)
                    self._noise_estimate = float(np.median(self._init_frames))
                    self._is_initialized = True
                    self._state = VADState.LISTENING

                # 初始化阶段保守地判定为无语音
                return False

            # ---- 正常检测阶段 ----
            # 动态阈值 = max(固定阈值, 噪声底 × 倍数)
            dynamic_threshold = max(
                self._config.energy_threshold,
                self._noise_estimate * self._config.noise_multiplier,
            )

            prev_is_speech = self._is_speech

            if energy > dynamic_threshold:
                # 能量超过阈值 → 判定为语音
                self._is_speech = True
                self._hangover_counter = self._config.hangover_chunks
                self._state = VADState.SPEECH

                # 记录语音开始时间
                if self._speech_start_time is None:
                    self._speech_start_time = current_time

                # 重置静音计时
                self._silence_start_time = None
                self._silence_duration_ms = 0.0

                # 更新语音时长
                self._speech_duration_ms = (current_time - self._speech_start_time) * 1000

            else:
                # 能量低于阈值
                if self._hangover_counter > 0:
                    # 挂起期间仍判定为语音 (防止短暂停顿误判)
                    self._hangover_counter -= 1
                    # 保持语音状态
                else:
                    self._is_speech = False

                # 仅在非语音状态下更新噪声估计 (避免语音污染噪声底)
                if not self._is_speech:
                    self._noise_estimate = (
                        (1 - self._config.noise_smooth_factor) * self._noise_estimate
                        + self._config.noise_smooth_factor * energy
                    )

                    # 检测静音
                    if prev_is_speech and not self._is_speech:
                        # 刚刚从语音转为静音，开始计时
                        self._silence_start_time = current_time
                        self._state = VADState.SILENCE

                    if self._silence_start_time is not None:
                        # 更新静音时长
                        self._silence_duration_ms = (current_time - self._silence_start_time) * 1000

                        # 检查是否语音结束
                        if self._silence_duration_ms >= self._config.silence_duration_ms:
                            self._speech_end_detected = True
                            self._state = VADState.SPEECH_END
                    else:
                        self._state = VADState.LISTENING

            return self._is_speech

    def is_speech_end(self) -> bool:
        """
        返回是否语音结束 (静音 > silence_duration_ms)

        Returns:
            是否语音结束
        """
        with self._lock:
            return self._speech_end_detected

    def get_result(self) -> VADResult:
        """
        获取详细的 VAD 结果

        Returns:
            VADResult 对象，包含所有状态信息
        """
        with self._lock:
            return VADResult(
                is_speech=self._is_speech,
                energy=self._noise_estimate * self._config.noise_multiplier,  # 当前阈值
                state=self._state,
                noise_estimate=self._noise_estimate,
                speech_duration_ms=self._speech_duration_ms,
                silence_duration_ms=self._silence_duration_ms,
            )

    @property
    def state(self) -> VADState:
        """返回当前 VAD 状态"""
        with self._lock:
            return self._state

    @property
    def noise_estimate(self) -> float:
        """返回当前噪声估计值"""
        with self._lock:
            return self._noise_estimate

    @property
    def is_initialized(self) -> bool:
        """是否已完成初始化校准"""
        with self._lock:
            return self._is_initialized

    @property
    def speech_duration_ms(self) -> float:
        """当前语音段时长 (毫秒)"""
        with self._lock:
            return self._speech_duration_ms

    @property
    def silence_duration_ms(self) -> float:
        """当前静音时长 (毫秒)"""
        with self._lock:
            return self._silence_duration_ms

    @property
    def config(self) -> VADConfig:
        """返回 VAD 配置"""
        return self._config


class StreamingVAD:
    """
    流式 VAD - 用于 WebSocket 音频流处理

    对 VAD 的封装，提供更便捷的流式处理接口。
    支持累积音频缓冲，在语音结束时返回完整音频段。

    使用示例::

        streaming_vad = StreamingVAD()

        async def handle_audio_chunk(audio_data: np.ndarray):
            result = streaming_vad.feed(audio_data)

            if result.is_complete:
                # 语音段完成，获取完整音频
                complete_audio = result.audio
                # 进行 STT 处理...
    """

    @dataclass
    class StreamResult:
        """流式处理结果"""
        is_speech: bool             # 当前块是否为语音
        is_complete: bool           # 语音段是否完成
        audio: Optional[np.ndarray] # 完成时返回完整音频，否则为 None
        duration_ms: float          # 当前语音段时长
        state: VADState             # VAD 状态

    def __init__(self, config: Optional[VADConfig] = None):
        """
        初始化流式 VAD

        Args:
            config: VAD 配置
        """
        self._vad = VAD(config)
        self._config = config or VADConfig()
        self._audio_buffer: List[np.ndarray] = []
        self._has_speech: bool = False
        self._lock = threading.Lock()

    def reset(self) -> None:
        """重置状态"""
        with self._lock:
            self._vad.reset()
            self._audio_buffer.clear()
            self._has_speech = False

    def feed(self, audio_chunk: np.ndarray) -> "StreamingVAD.StreamResult":
        """
        喂入音频块，返回处理结果

        Args:
            audio_chunk: float32 音频数组

        Returns:
            StreamResult 对象
        """
        with self._lock:
            is_speech = self._vad.process(audio_chunk)
            state = self._vad.state

            # 累积音频 (仅在检测到语音后开始)
            if is_speech or self._has_speech:
                self._audio_buffer.append(audio_chunk.copy())
                self._has_speech = True

            # 检查是否语音结束
            is_complete = self._vad.is_speech_end()
            complete_audio = None

            if is_complete and self._audio_buffer:
                # 合并所有音频块
                complete_audio = np.concatenate(self._audio_buffer)
                # 不自动清空缓冲区，由调用方决定是否重置

            return StreamingVAD.StreamResult(
                is_speech=is_speech,
                is_complete=is_complete,
                audio=complete_audio,
                duration_ms=self._vad.speech_duration_ms,
                state=state,
            )

    def get_buffered_audio(self) -> Optional[np.ndarray]:
        """
        获取当前缓冲的音频数据

        Returns:
            合并后的音频数组，如果无数据则返回 None
        """
        with self._lock:
            if not self._audio_buffer:
                return None
            return np.concatenate(self._audio_buffer)

    @property
    def vad(self) -> VAD:
        """返回内部 VAD 实例"""
        return self._vad

    @property
    def has_speech(self) -> bool:
        """是否已检测到语音"""
        with self._lock:
            return self._has_speech

    @property
    def buffer_duration_ms(self) -> float:
        """当前缓冲区时长 (毫秒)"""
        with self._lock:
            if not self._audio_buffer:
                return 0.0
            total_samples = sum(chunk.size for chunk in self._audio_buffer)
            return total_samples / self._config.sample_rate * 1000


# ============================================================
#  模块自测
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  CC_VisChat VAD 模块 - 自测")
    print("=" * 60)

    # 创建测试数据
    sample_rate = 16000
    chunk_duration_ms = 500
    chunk_samples = int(sample_rate * chunk_duration_ms / 1000)

    # 生成测试音频：静音 -> 语音 -> 静音
    print("\n【生成测试音频】")

    # 静音段 (噪声)
    silence1 = np.random.randn(chunk_samples * 5).astype(np.float32) * 0.001

    # 语音段 (模拟)
    t = np.linspace(0, 2, sample_rate * 2, dtype=np.float32)
    speech = np.sin(2 * np.pi * 440 * t) * 0.3  # 440Hz 正弦波
    speech += np.random.randn(len(speech)).astype(np.float32) * 0.01

    # 静音段 (噪声)
    silence2 = np.random.randn(chunk_samples * 5).astype(np.float32) * 0.001

    # 合并
    test_audio = np.concatenate([silence1, speech, silence2])

    print(f"  总时长: {len(test_audio) / sample_rate:.2f}s")
    print(f"  静音1: {len(silence1) / sample_rate:.2f}s")
    print(f"  语音: {len(speech) / sample_rate:.2f}s")
    print(f"  静音2: {len(silence2) / sample_rate:.2f}s")

    # 测试 VAD
    print("\n【VAD 测试】")
    vad = VAD(VADConfig(
        silence_duration_ms=800,
        sample_rate=sample_rate,
        chunk_duration_ms=chunk_duration_ms,
    ))

    # 分块处理
    num_chunks = len(test_audio) // chunk_samples
    speech_chunks = 0
    silence_chunks = 0

    for i in range(num_chunks):
        start = i * chunk_samples
        end = start + chunk_samples
        chunk = test_audio[start:end]

        is_speech = vad.process(chunk)
        state = vad.state

        if is_speech:
            speech_chunks += 1
        else:
            silence_chunks += 1

        # 显示状态变化
        time_pos = i * chunk_duration_ms / 1000
        energy = vad.compute_rms_energy(chunk)
        print(f"  {time_pos:5.1f}s | 能量={energy:.6f} | 语音={'是' if is_speech else '否'} | 状态={state.name}")

        if vad.is_speech_end():
            print(f"\n  ✅ 语音结束检测！")
            print(f"     语音时长: {vad.speech_duration_ms:.0f}ms")
            print(f"     静音时长: {vad.silence_duration_ms:.0f}ms")
            break

    print(f"\n【统计】")
    print(f"  语音块: {speech_chunks}")
    print(f"  静音块: {silence_chunks}")
    print(f"  噪声估计: {vad.noise_estimate:.6f}")

    # 测试流式 VAD
    print("\n【流式 VAD 测试】")
    streaming_vad = StreamingVAD(VADConfig(
        silence_duration_ms=800,
        sample_rate=sample_rate,
        chunk_duration_ms=chunk_duration_ms,
    ))

    for i in range(num_chunks):
        start = i * chunk_samples
        end = start + chunk_samples
        chunk = test_audio[start:end]

        result = streaming_vad.feed(chunk)

        if result.is_complete:
            print(f"\n  ✅ 流式 VAD 检测到语音结束！")
            print(f"     音频长度: {len(result.audio) if result.audio is not None else 0} 样本")
            print(f"     语音时长: {result.duration_ms:.0f}ms")
            break

    print("\n✅ 自测完成！")
