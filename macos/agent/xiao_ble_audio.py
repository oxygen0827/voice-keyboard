"""BLE audio source for Seeed XIAO nRF52840 Sense boards.

The PsyGuard firmware streams 8 kHz, 16-bit mono PCM over Nordic UART
Service. Voice Keyboard's Speech Interpretation Providers expect 16 kHz
PCM, so this adapter upsamples before handing chunks to the existing
Capture Path.
"""

from __future__ import annotations

import asyncio
import importlib.util
import math
import struct
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

NUS_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_RX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_TX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

SOURCE_SAMPLE_RATE = 8000
TARGET_SAMPLE_RATE = 16000
TARGET_STT_RMS = 900.0
MAX_STT_GAIN = 10.0
TRIM_FRAME_MS = 20
TRIM_THRESHOLD = 260
TRIM_PADDING_MS = 120

_XIAO_BLE_ALIASES = {
    "xiao_ble",
    "xiaoble",
    "xiao",
    "ble_xiao",
    "psyguard",
    "psyguard_ble",
}

_DEFAULT_NAME_KEYWORDS = ("psyguard", "xiao", "sense", "arduino")


@dataclass(frozen=True)
class AudioQuality:
    duration_sec: float
    rms: float
    max_amplitude: int
    silent_percent: float
    clipped_percent: float


def is_xiao_ble_device_hint(hint: object) -> bool:
    if not isinstance(hint, str):
        return False
    normalized = hint.strip().lower().replace("-", "_")
    if normalized in _XIAO_BLE_ALIASES:
        return True
    return normalized.startswith("xiao_ble:") or normalized.startswith("ble_xiao:")


def xiao_ble_target_from_hint(hint: object) -> str | None:
    if not isinstance(hint, str) or ":" not in hint:
        return None
    prefix, _, target = hint.partition(":")
    if is_xiao_ble_device_hint(prefix):
        return target.strip() or None
    return None


def upsample_pcm_8k_to_16k(pcm: bytes) -> bytes:
    """Duplicate int16 samples to convert 8 kHz PCM to 16 kHz PCM."""
    even_len = len(pcm) - (len(pcm) % 2)
    if even_len <= 0:
        return b""
    out = bytearray(even_len * 2)
    write_at = 0
    for read_at in range(0, even_len, 2):
        sample = pcm[read_at:read_at + 2]
        out[write_at:write_at + 2] = sample
        out[write_at + 2:write_at + 4] = sample
        write_at += 4
    return bytes(out)


def analyze_pcm_16k(pcm: bytes) -> AudioQuality:
    even_len = len(pcm) - (len(pcm) % 2)
    if even_len <= 0:
        return AudioQuality(0.0, 0.0, 0, 100.0, 0.0)
    samples = struct.unpack(f"<{even_len // 2}h", pcm[:even_len])
    count = len(samples)
    rms = math.sqrt(sum(s * s for s in samples) / count)
    max_amplitude = max(abs(s) for s in samples)
    silent_percent = sum(1 for s in samples if abs(s) < 200) / count * 100
    clipped_percent = sum(1 for s in samples if abs(s) > 30000) / count * 100
    return AudioQuality(
        duration_sec=even_len / TARGET_SAMPLE_RATE / 2,
        rms=rms,
        max_amplitude=max_amplitude,
        silent_percent=silent_percent,
        clipped_percent=clipped_percent,
    )


def trim_pcm_16k_silence(
    pcm: bytes,
    *,
    threshold: int = TRIM_THRESHOLD,
    frame_ms: int = TRIM_FRAME_MS,
    padding_ms: int = TRIM_PADDING_MS,
    min_duration_sec: float = 0.3,
) -> tuple[bytes, float, float]:
    """Trim obvious leading/trailing silence while preserving speech edges."""
    even_len = len(pcm) - (len(pcm) % 2)
    if even_len <= 0:
        return pcm, 0.0, 0.0

    sample_count = even_len // 2
    min_samples = int(TARGET_SAMPLE_RATE * min_duration_sec)
    if sample_count <= min_samples:
        return pcm, 0.0, 0.0

    samples = struct.unpack(f"<{sample_count}h", pcm[:even_len])
    frame_samples = max(1, int(TARGET_SAMPLE_RATE * frame_ms / 1000))

    start_frame = None
    end_frame = None
    for start in range(0, sample_count, frame_samples):
        frame = samples[start:start + frame_samples]
        if not frame:
            continue
        frame_rms = math.sqrt(sum(s * s for s in frame) / len(frame))
        if frame_rms >= threshold:
            start_frame = start
            break

    if start_frame is None:
        return pcm, 0.0, 0.0

    for start in range(sample_count - frame_samples, -frame_samples, -frame_samples):
        start = max(0, start)
        frame = samples[start:start + frame_samples]
        if not frame:
            continue
        frame_rms = math.sqrt(sum(s * s for s in frame) / len(frame))
        if frame_rms >= threshold:
            end_frame = min(sample_count, start + frame_samples)
            break

    if end_frame is None or end_frame <= start_frame:
        return pcm, 0.0, 0.0

    padding_samples = int(TARGET_SAMPLE_RATE * padding_ms / 1000)
    trim_start = max(0, start_frame - padding_samples)
    trim_end = min(sample_count, end_frame + padding_samples)

    if trim_end - trim_start < min_samples:
        return pcm, 0.0, 0.0

    leading_sec = trim_start / TARGET_SAMPLE_RATE
    trailing_sec = (sample_count - trim_end) / TARGET_SAMPLE_RATE
    if leading_sec < 0.05 and trailing_sec < 0.05:
        return pcm, 0.0, 0.0

    trimmed = pcm[trim_start * 2:trim_end * 2] + pcm[even_len:]
    return trimmed, leading_sec, trailing_sec


def normalize_pcm_16k_for_stt(
    pcm: bytes,
    *,
    target_rms: float = TARGET_STT_RMS,
    max_gain: float = MAX_STT_GAIN,
) -> tuple[bytes, float, AudioQuality]:
    """Apply conservative automatic gain for quiet XIAO BLE recordings."""
    before = analyze_pcm_16k(pcm)
    even_len = len(pcm) - (len(pcm) % 2)
    if even_len <= 0 or before.rms <= 0:
        return pcm, 1.0, before

    gain = min(max_gain, max(1.0, target_rms / before.rms))
    if gain <= 1.01:
        return pcm, 1.0, before

    samples = struct.unpack(f"<{even_len // 2}h", pcm[:even_len])
    boosted = bytearray(even_len)
    for i, sample in enumerate(samples):
        value = int(sample * gain)
        if value > 32767:
            value = 32767
        elif value < -32768:
            value = -32768
        struct.pack_into("<h", boosted, i * 2, value)
    boosted.extend(pcm[even_len:])
    return bytes(boosted), gain, analyze_pcm_16k(bytes(boosted))


class XiaoBleAudioSource:
    """Persistent BLE connection used by hotkey-driven Capture Paths."""

    def __init__(
        self,
        *,
        device_hint: str = "xiao_ble",
        scan_timeout: float = 8.0,
        retry_delay: float = 2.0,
        log: Callable[[str], None] = print,
    ):
        self._target = xiao_ble_target_from_hint(device_hint)
        self._scan_timeout = scan_timeout
        self._retry_delay = retry_delay
        self._log = log
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: Any = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._recording = False
        self._audio_callback: Callable[[bytes], None] | None = None

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        if importlib.util.find_spec("bleak") is None:
            self._log("[xiao] 缺少 BLE 依赖 bleak，请运行: .venv/bin/pip install bleak")
            return False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._thread_main,
            name="XiaoBleAudioSource",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self.stop_recording()
        self._stop.set()
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(lambda: None)
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    def wait_until_ready(self, timeout: float | None = None) -> bool:
        return self._connected.wait(timeout)

    def start_recording(self, callback: Callable[[bytes], None]) -> None:
        with self._lock:
            self._audio_callback = callback
            self._recording = True
        self._send_control(0x01)

    def stop_recording(self) -> None:
        with self._lock:
            was_recording = self._recording
            self._recording = False
            self._audio_callback = None
        if was_recording:
            self._send_control(0x00)

    def _thread_main(self) -> None:
        asyncio.run(self._run_forever())

    async def _run_forever(self) -> None:
        from bleak import BleakClient, BleakScanner

        self._loop = asyncio.get_running_loop()
        while not self._stop.is_set():
            device = await self._find_device(BleakScanner)
            if device is None:
                await self._sleep(self._retry_delay)
                continue

            name = getattr(device, "name", None) or "(unnamed)"
            address = getattr(device, "address", "")
            try:
                self._log(f"[xiao] 连接 BLE 设备: {name} {address}")
                async with BleakClient(address, timeout=15.0) as client:
                    with self._lock:
                        self._client = client
                    self._connected.set()
                    self._log("[xiao] BLE 已连接，等待热键开始录音")
                    await client.start_notify(NUS_TX_UUID, self._handle_notify)
                    if self._recording:
                        await self._write_control_value(client, 0x01)
                    while not self._stop.is_set() and client.is_connected:
                        await asyncio.sleep(0.1)
                    try:
                        await self._write_control_value(client, 0x00)
                    except Exception:
                        pass
                    try:
                        await client.stop_notify(NUS_TX_UUID)
                    except Exception:
                        pass
            except Exception as e:
                if not self._stop.is_set():
                    self._log(f"[xiao] BLE 连接异常: {e}")
            finally:
                self._connected.clear()
                with self._lock:
                    self._client = None
                if not self._stop.is_set():
                    self._log("[xiao] BLE 已断开，准备重连")
                    await self._sleep(self._retry_delay)

    async def _find_device(self, scanner_cls):
        target = self._target.lower() if self._target else None
        self._log("[xiao] 扫描 XIAO Sense BLE 音频设备...")
        try:
            devices = await scanner_cls.discover(timeout=self._scan_timeout)
        except Exception as e:
            self._log(f"[xiao] BLE 扫描失败: {e}")
            return None
        for device in devices:
            name = (getattr(device, "name", None) or "").lower()
            address = (getattr(device, "address", None) or "").lower()
            if target:
                if target in name or target in address:
                    return device
                continue
            if any(keyword in name for keyword in _DEFAULT_NAME_KEYWORDS):
                return device
        self._log("[xiao] 未找到 XIAO/PsyGuard BLE 设备，请确认固件在广播")
        return None

    async def _sleep(self, seconds: float) -> None:
        end = asyncio.get_running_loop().time() + seconds
        while not self._stop.is_set() and asyncio.get_running_loop().time() < end:
            await asyncio.sleep(0.1)

    def _handle_notify(self, sender, data: bytearray) -> None:
        with self._lock:
            if not self._recording or self._audio_callback is None:
                return
            callback = self._audio_callback
        pcm = upsample_pcm_8k_to_16k(bytes(data))
        if not pcm:
            return
        try:
            callback(pcm)
        except Exception as e:
            self._log(f"[xiao] 音频回调异常: {e}")

    def _send_control(self, value: int) -> None:
        loop = self._loop
        with self._lock:
            client = self._client
        if loop is None or client is None or not getattr(client, "is_connected", False):
            return
        asyncio.run_coroutine_threadsafe(
            self._write_control_value(client, value),
            loop,
        )

    async def _write_control_value(self, client, value: int) -> None:
        try:
            await client.write_gatt_char(NUS_RX_UUID, bytes([value]), response=False)
        except Exception:
            await client.write_gatt_char(NUS_RX_UUID, bytes([value]), response=True)


def record_xiao_ble_for_seconds(
    seconds: float,
    *,
    device_hint: str = "xiao_ble",
    ready_timeout: float = 12.0,
    log: Callable[[str], None] = print,
) -> bytes:
    source = XiaoBleAudioSource(device_hint=device_hint, log=log)
    chunks: list[bytes] = []
    lock = threading.Lock()

    def on_audio(pcm: bytes) -> None:
        with lock:
            chunks.append(pcm)

    if not source.start():
        return b""
    try:
        if not source.wait_until_ready(ready_timeout):
            log("[xiao] 连接超时，未录到音频")
            return b""
        source.start_recording(on_audio)
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            time.sleep(0.05)
        source.stop_recording()
    finally:
        source.stop()
    with lock:
        return b"".join(chunks)


def record_xiao_ble_until_enter(
    *,
    device_hint: str = "xiao_ble",
    ready_timeout: float = 12.0,
    log: Callable[[str], None] = print,
) -> bytes:
    source = XiaoBleAudioSource(device_hint=device_hint, log=log)
    chunks: list[bytes] = []
    lock = threading.Lock()

    def on_audio(pcm: bytes) -> None:
        with lock:
            chunks.append(pcm)

    print("按 Enter 开始录音，再按 Enter 停止。", flush=True)
    input()
    if not source.start():
        return b""
    try:
        if not source.wait_until_ready(ready_timeout):
            log("[xiao] 连接超时，未录到音频")
            return b""
        print("[rec] XIAO BLE 录音中...", flush=True)
        source.start_recording(on_audio)
        input()
        source.stop_recording()
    finally:
        source.stop()
    with lock:
        return b"".join(chunks)
