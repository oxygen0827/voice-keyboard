"""
LLM 文字编辑器。

接收原文 + 语音修改指令，调用 LLM 返回修改后的文字。

支持的 provider：
  openai      — GPT-4o-mini（快、便宜）
  aliyun      — 通义千问 Qwen（中文优化）
  volcengine  — 豆包 Doubao（字节跳动）
"""

_SYSTEM_PROMPT = """你是一个专业的文字编辑助手。
用户会给你一段原文和一条修改指令。
请严格按照指令修改原文，只返回修改后的结果，不要添加任何解释或标点以外的内容。
如果指令不清晰，尽量按最合理的方式理解并修改。"""


class LLMEditor:
    def __init__(self, cfg: dict):
        provider = cfg.get("provider", "openai")

        if provider == "openai":
            from openai import OpenAI
            self._client = OpenAI(api_key=cfg["api_key"])
            self._model  = cfg.get("model", "gpt-4o-mini")
            self._edit   = self._openai_edit

        elif provider == "aliyun":
            # 通义千问，兼容 OpenAI SDK
            from openai import OpenAI
            self._client = OpenAI(
                api_key=cfg["api_key"],
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            self._model = cfg.get("model", "qwen-turbo")
            self._edit  = self._openai_edit

        elif provider == "volcengine":
            # 豆包，兼容 OpenAI SDK
            from openai import OpenAI
            self._client = OpenAI(
                api_key=cfg["api_key"],
                base_url="https://ark.cn-beijing.volces.com/api/v3",
            )
            self._model = cfg.get("model", "doubao-lite-4k")
            self._edit  = self._openai_edit

        else:
            raise ValueError(
                f"未知 LLM provider: {provider!r}，支持: openai / aliyun / volcengine"
            )

    def edit(self, original: str, instruction: str) -> str:
        """用 instruction 修改 original，返回修改后的文字。"""
        return self._edit(original, instruction)

    def _openai_edit(self, original: str, instruction: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": f"原文：{original}\n\n修改指令：{instruction}"},
            ],
            temperature=0.1,
            max_tokens=2000,
        )
        return resp.choices[0].message.content.strip()
