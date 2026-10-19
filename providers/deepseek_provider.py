"""
OpenAI 兼容 LLM Provider — 默认用于 DeepSeek，也可指向任意 OpenAI 兼容网关
（阿里云百炼、vLLM、Ollama、OneAPI 等），通过 LLM_PROVIDER=openai 配置。

思考模式（thinking）是供应商相关参数：DeepSeek 用 {"thinking": ...}，
Qwen 用 {"enable_thinking": ...}。为避免把 A 厂商字段发给 B 厂商，
本类默认不发送任何额外字段；需要时用 LLM_EXTRA_BODY 传 JSON 覆盖。
"""
import json
import re
from typing import Optional

from openai import OpenAI

from providers.base import BaseLLM


class DeepSeekLLM(BaseLLM):
    name = "deepseek"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        client: Optional[OpenAI] = None,
        thinking: bool = False,
        max_tokens: int = 32768,
        extra_body: Optional[dict] = None,
        name: Optional[str] = None,
    ):
        self.client = client or OpenAI(api_key=api_key, base_url=base_url,
                                       timeout=300.0, max_retries=2)
        self.model = model
        self.thinking = thinking
        self.max_tokens = max_tokens
        self.extra_body = extra_body
        if name:
            self.name = name

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        kwargs = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": self.max_tokens,
        }
        extra = self.extra_body
        # 兼容直接构造本类且开启思考的调用方
        if extra is None and self.thinking:
            extra = {"thinking": {"type": "enabled"}}
        if extra is not None:
            kwargs["extra_body"] = extra

        resp = self.client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        content = choice.message.content or ""
        if choice.finish_reason == "length":
            # 截断必然导致 JSON 解析失败，这里给出明确病因而不是让下游猜
            reasoning = getattr(choice.message, "reasoning_content", None) or ""
            raise RuntimeError(
                f"LLM 输出被截断：finish_reason=length, content_len={len(content)}, "
                f"reasoning_len={len(reasoning)}, max_tokens={self.max_tokens}。"
                f"若开启思考请调大 DEEPSEEK_MAX_TOKENS，或减小合并批大小 MERGE_CHUNK_PAGES"
            )
        return content

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict:
        """
        强制返回解析后的 JSON dict。
        容错链：直接解析 → 剥 markdown 围栏 → 剥 {"output": "..."} 嵌套。
        """
        raw = self.chat(system_prompt, user_prompt, temperature)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
        cleaned = re.sub(r"\n?```\s*$", "", cleaned.strip())
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        try:
            outer = json.loads(cleaned)
        except json.JSONDecodeError:
            outer = {}

        if isinstance(outer, dict) and set(outer.keys()) == {"output"}:
            inner = outer["output"]
            if isinstance(inner, str):
                inner = re.sub(r"^```(?:json)?\s*\n?", "", inner.strip())
                inner = re.sub(r"\n?```\s*$", "", inner.strip())
                try:
                    return json.loads(inner)
                except json.JSONDecodeError:
                    pass
            elif isinstance(inner, dict):
                return inner

        raise ValueError(f"无法解析 LLM 输出为 JSON:\n{raw[:500]}")