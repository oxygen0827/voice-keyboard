"""Factory for Voice Keyboard Engine Speech Interpretation Providers."""

from dataclasses import dataclass
from typing import Callable

from agent.personal_dictionary import PersonalDictionaryStore
from agent.typeup_backend_auth import is_typeup_backend_configured


_NO_API_KEY_STT_PROVIDERS = {"volcengine", "aliyun", "typeup_backend"}


@dataclass(frozen=True)
class ProviderReadiness:
    ready: bool
    reason: str = ""
    hint: str = ""


@dataclass(frozen=True)
class SpeechInterpretationProviderSet:
    dictation_stt: object
    utterance_stt: object
    instruction_stt: object | None
    text_operation_editor: object | None


class _PolishAwareSTT:
    def __init__(self, base_stt, polish_stt):
        self._base_stt = base_stt
        self._polish_stt = polish_stt

    def transcribe(self, pcm: bytes) -> str:
        return self._base_stt.transcribe(pcm)

    def transcribe_polished(self, pcm: bytes) -> str:
        return self._polish_stt.transcribe(pcm)


class SpeechInterpretationProviderFactory:
    """Constructs configured Speech Interpretation Provider adapters."""

    def __init__(
        self,
        *,
        stt_client_cls=None,
        llm_editor_cls=None,
        dictionary_store=None,
        log: Callable[[str], None] = print,
    ):
        self._stt_client_cls = stt_client_cls
        self._llm_editor_cls = llm_editor_cls
        self._dictionary_store = dictionary_store
        self._log = log

    def dictation_readiness(self, stt_cfg: dict) -> ProviderReadiness:
        provider = stt_cfg.get("provider", "")
        if provider == "typeup_backend" and not stt_cfg.get("access_token"):
            return ProviderReadiness(
                False,
                "[typeup-auth-required] 请先登录 TypeUp 后端账号，跳过音频 STT",
            )
        if not stt_cfg.get("api_key") and provider not in _NO_API_KEY_STT_PROVIDERS:
            return ProviderReadiness(
                False,
                "[agent] 未配置 stt.api_key，跳过音频 STT",
                "[agent] 提示: cp config.yaml.example config.yaml 然后填入 API Key",
            )
        return ProviderReadiness(True)

    def text_operation_readiness(self, llm_cfg: dict) -> ProviderReadiness:
        if is_typeup_backend_configured(llm_cfg):
            return ProviderReadiness(True)
        return ProviderReadiness(False)

    def create_dictation_stt(self, stt_cfg: dict):
        readiness = self.dictation_readiness(stt_cfg)
        if not readiness.ready:
            self._log_readiness(readiness)
            return None
        try:
            return self._stt_client(stt_cfg)
        except ImportError as e:
            self._log(f"[agent] STT 依赖缺失（{e}）")
            return None
        except Exception as e:
            self._log(f"[agent] STT 初始化失败: {e}")
            return None

    def create_text_operation_editor(self, llm_cfg: dict):
        if not self.text_operation_readiness(llm_cfg).ready:
            return None
        try:
            editor = self._llm_editor(llm_cfg)
            self._log("[agent] LLM 编辑功能已启用")
            return editor
        except Exception as e:
            import traceback

            self._log(f"[agent] LLM 初始化失败: {e}")
            traceback.print_exc()
            return None

    def create_instruction_stt(self, ai_stt_cfg: dict, dictation_stt):
        if not ai_stt_cfg:
            return dictation_stt
        try:
            ai_stt = self._stt_client(ai_stt_cfg)
            self._log(
                "[agent] AI 键 STT 使用独立 provider: "
                f"{ai_stt_cfg.get('provider', 'openai')}"
            )
            return ai_stt
        except Exception as e:
            self._log(f"[agent] AI 键 STT 初始化失败: {e}")
            return None

    def create_utterance_stt(self, dictation_stt, polish_stt_cfg: dict, llm_cfg: dict):
        if not polish_stt_cfg:
            return dictation_stt
        try:
            polish_stt = self._stt_client(polish_stt_cfg)
            self._log(
                "[agent] 微润色 STT 使用独立 provider: "
                f"{polish_stt_cfg.get('provider', 'openai')}"
            )
            return _PolishAwareSTT(dictation_stt, polish_stt)
        except Exception as e:
            self._log(f"[agent] 微润色 STT 初始化失败，回退主 STT: {e}")
            return dictation_stt

    def create_provider_set(self, cfg: dict) -> SpeechInterpretationProviderSet | None:
        dictation_stt = self.create_dictation_stt(cfg.get("stt", {}))
        if dictation_stt is None:
            return None
        editor = self.create_text_operation_editor(cfg.get("llm", {}))
        instruction_stt = None
        if editor is not None:
            instruction_stt = self.create_instruction_stt(
                cfg.get("ai_stt", {}),
                dictation_stt,
            )
        utterance_stt = self.create_utterance_stt(
            dictation_stt,
            cfg.get("polish_stt", {}),
            cfg.get("llm", {}),
        )
        return SpeechInterpretationProviderSet(
            dictation_stt=dictation_stt,
            utterance_stt=utterance_stt,
            instruction_stt=instruction_stt,
            text_operation_editor=editor,
        )

    def _stt_client(self, cfg: dict):
        if self._stt_client_cls is None:
            from agent.stt import STTClient

            self._stt_client_cls = STTClient
        return self._stt_client_cls(self._with_personal_dictionary(cfg))

    def _llm_editor(self, cfg: dict):
        if self._llm_editor_cls is None:
            from agent.llm_editor import LLMEditor

            self._llm_editor_cls = LLMEditor
        return self._llm_editor_cls(cfg)

    def _log_readiness(self, readiness: ProviderReadiness) -> None:
        if readiness.reason:
            self._log(readiness.reason)
        if readiness.hint:
            self._log(readiness.hint)

    def _with_personal_dictionary(self, cfg: dict) -> dict:
        enriched = dict(cfg or {})
        try:
            store = self._dictionary_store or PersonalDictionaryStore()
            hotwords = store.hotwords()
            prompt_hint = store.prompt_hint()
        except Exception as e:
            self._log(f"[dictionary] load failed: {e}")
            return enriched
        if hotwords and _personal_dictionary_hotwords_enabled(enriched):
            enriched["hotwords"] = _merge_hotwords(enriched.get("hotwords"), hotwords)
        if prompt_hint:
            existing_prompt = str(enriched.get("prompt") or "").strip()
            enriched["prompt"] = "\n".join(
                part for part in (existing_prompt, prompt_hint) if part
            )
        return enriched


def _merge_hotwords(configured, dictionary_words: list[str], limit: int = 100) -> list[str]:
    words = []
    if isinstance(configured, str):
        configured_words = [word.strip() for word in configured.split(",")]
    elif isinstance(configured, list):
        configured_words = configured
    else:
        configured_words = []
    for raw in [*configured_words, *dictionary_words]:
        word = str(raw or "").strip()
        if word and word not in words:
            words.append(word)
        if len(words) >= limit:
            break
    return words


def _personal_dictionary_hotwords_enabled(cfg: dict) -> bool:
    value = cfg.get("personal_dictionary_hotwords")
    if isinstance(value, bool):
        return value
    if value is None:
        value = cfg.get("dictionary_hotwords")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False
