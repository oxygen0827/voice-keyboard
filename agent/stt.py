"""
STT（语音转文字）客户端，支持多家云服务。

支持的 provider：
  openai      — OpenAI Whisper API（多语言通用）
  aliyun      — 阿里云智能语音 NLS（中文最优，支持方言）
  volcengine  — 火山引擎 ASR（字节跳动，中文优化）
  zhipuai     — 智谱 AI GLM-4-Voice（参考 transmission_assistant 项目的集成方式）

调用方只需：
    client = STTClient(cfg["stt"])
    text   = client.transcribe(pcm_bytes)   # pcm: 16kHz 16bit mono

扩展新 provider：
    1. 实现一个类，提供 transcribe(pcm: bytes) -> str 方法
    2. 在文件末尾的 _PROVIDERS 字典中注册
    3. 在 config.yaml / .env 中指定 provider 名称即可
"""

import base64
import io
import time
import uuid
import wave

import requests

SAMPLE_RATE = 16000


def _pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


# ── OpenAI Whisper ────────────────────────────────────────────────

class _OpenAISTT:
    def __init__(self, cfg: dict):
        from openai import OpenAI
        self._client   = OpenAI(api_key=cfg["api_key"])
        self._model    = cfg.get("model", "whisper-1")
        self._language = cfg.get("language", "zh")

    def transcribe(self, pcm: bytes) -> str:
        wav  = _pcm_to_wav(pcm)
        resp = self._client.audio.transcriptions.create(
            model=self._model,
            file=("audio.wav", wav, "audio/wav"),
            language=self._language,
        )
        return resp.text.strip()


# ── 阿里云 NLS ────────────────────────────────────────────────────

class _AliyunSTT:
    """
    阿里云智能语音·一句话识别（REST）。

    所需配置：
      access_key_id      阿里云 AccessKey ID
      access_key_secret  阿里云 AccessKey Secret
      app_key            NLS 应用的 Appkey（控制台创建项目后可见）
      region             地域，默认 cn-shanghai（也支持 cn-beijing）
      language           zh（中文，默认）/ en（英文）
    """

    _TOKEN_URL = "https://nls-gateway.{region}.aliyuncs.com/token"
    _ASR_URL   = "https://nls-gateway.{region}.aliyuncs.com/stream/v1/asr"

    def __init__(self, cfg: dict):
        self._access_key_id     = cfg["access_key_id"]
        self._access_key_secret = cfg["access_key_secret"]
        self._app_key           = cfg["app_key"]
        self._region            = cfg.get("region", "cn-shanghai")
        self._language          = cfg.get("language", "zh")
        self._token             = None
        self._token_expiry      = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        url  = self._TOKEN_URL.format(region=self._region)
        resp = requests.post(url, json={
            "AccessKeyId":     self._access_key_id,
            "AccessKeySecret": self._access_key_secret,
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self._token        = data["Token"]["Id"]
        self._token_expiry = float(data["Token"]["ExpireTime"])
        return self._token

    def transcribe(self, pcm: bytes) -> str:
        token = self._get_token()
        wav   = _pcm_to_wav(pcm)
        url   = self._ASR_URL.format(region=self._region)
        resp  = requests.post(
            url,
            params={
                "appkey":                          self._app_key,
                "format":                          "wav",
                "sample_rate":                     SAMPLE_RATE,
                "enable_punctuation_prediction":   "true",
                "enable_inverse_text_normalization":"true",
            },
            headers={
                "X-NLS-Token":  token,
                "Content-Type": "application/octet-stream",
            },
            data=wav,
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("status") == 20000000:
            return result.get("result", "").strip()
        raise RuntimeError(f"阿里云 NLS 错误: {result.get('message', result)}")


# ── 火山引擎 ASR（字节跳动）─────────────────────────────────────────

class _VolcengineSTT:
    """
    火山引擎语音识别·录音文件识别（HTTP）。

    所需配置：
      app_id   火山引擎应用 ID（控制台 → 语音技术 → 应用管理）
      token    访问令牌（控制台生成的长期 Token）
      cluster  集群，默认 volcengine_streaming_common
      language 语言，默认 zh-CN
    """

    _ASR_URL = "https://openspeech.bytedance.com/api/v1/asr"

    def __init__(self, cfg: dict):
        self._app_id   = cfg["app_id"]
        self._token    = cfg["token"]
        self._cluster  = cfg.get("cluster", "volcengine_streaming_common")
        self._language = cfg.get("language", "zh-CN")

    def transcribe(self, pcm: bytes) -> str:
        wav      = _pcm_to_wav(pcm)
        audio_b64 = base64.b64encode(wav).decode()

        payload = {
            "app": {
                "appid":   self._app_id,
                "token":   self._token,
                "cluster": self._cluster,
            },
            "user":  {"uid": "voice-keyboard"},
            "audio": {
                "format":   "wav",
                "rate":     SAMPLE_RATE,
                "language": self._language,
                "bits":     16,
                "channel":  1,
                "codec":    "raw",
            },
            "request": {
                "reqid":          str(uuid.uuid4()),
                "nbest":          1,
                "show_utterances": False,
                "result_type":    "single",
                "sequence":       -1,
                "audio":          audio_b64,
            },
        }
        resp = requests.post(
            self._ASR_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer; {self._token}",
                "Content-Type":  "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 1000:
            utterances = result.get("utterances") or []
            return "".join(u.get("text", "") for u in utterances).strip()
        raise RuntimeError(f"火山引擎 ASR 错误: {result.get('message', result)}")


# ── 智谱 AI GLM-4-Voice ───────────────────────────────────────────
#
# 参考：transmission_assistant 项目（github.com/wangqioo/transmission_assistant）
# 该项目使用 zhipuai SDK 与智谱 AI 交互，此处以同样方式接入语音转写能力。
#
# GLM-4-Voice 通过 chat.completions 接口接收 base64 编码的音频，
# 返回转写文字。相比其他 provider，无需额外 STT 服务，一个 API Key 全搞定。
#
# 所需配置：
#   api_key  智谱 AI API Key（https://open.bigmodel.cn/）
#   model    默认 glm-4-voice（也可指定其他支持音频的模型）
#   language 语言提示，默认 zh（仅作为 prompt 提示，不影响 API 参数）

class _ZhipuSTT:
    """
    智谱 AI GLM-4-Voice 语音转写。

    使用 zhipuai Python SDK，与 transmission_assistant 项目的集成方式一致：
      from zhipuai import ZhipuAI
      client = ZhipuAI(api_key=api_key)

    音频以 base64 WAV 格式通过 chat completions 发送给 GLM-4-Voice，
    模型直接返回转写文字。
    """

    _PROMPT_ZH = "请将这段音频转录为文字。只输出转录结果，不要添加任何解释、标点说明或前缀。"
    _PROMPT_EN = "Transcribe this audio. Output only the transcription, no explanations."

    def __init__(self, cfg: dict):
        try:
            from zhipuai import ZhipuAI
        except ImportError:
            raise ImportError(
                "使用 zhipuai provider 需要安装 zhipuai：pip install zhipuai"
            )
        self._client   = ZhipuAI(api_key=cfg["api_key"])
        self._model    = cfg.get("model", "glm-4-voice")
        self._language = cfg.get("language", "zh")

    def transcribe(self, pcm: bytes) -> str:
        wav      = _pcm_to_wav(pcm)
        audio_b64 = base64.b64encode(wav).decode()

        prompt = self._PROMPT_ZH if self._language.startswith("zh") else self._PROMPT_EN

        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data":   audio_b64,
                            "format": "wav",
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }],
        )
        return resp.choices[0].message.content.strip()


# ── 统一入口 ──────────────────────────────────────────────────────
#
# 注册新 provider：在此 dict 中添加 "name": ClassName 即可，
# config.yaml / .env 中填写对应 provider 名称后自动生效。

_PROVIDERS: dict[str, type] = {
    "openai":     _OpenAISTT,
    "aliyun":     _AliyunSTT,
    "volcengine": _VolcengineSTT,
    "zhipuai":    _ZhipuSTT,
}


class STTClient:
    def __init__(self, cfg: dict):
        provider = cfg.get("provider", "openai")
        cls = _PROVIDERS.get(provider)
        if cls is None:
            raise ValueError(
                f"未知 STT provider: {provider!r}，"
                f"支持: {', '.join(_PROVIDERS)}"
            )
        self._impl = cls(cfg)

    def transcribe(self, pcm: bytes) -> str:
        return self._impl.transcribe(pcm)
