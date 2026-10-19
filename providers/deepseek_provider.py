"""
DeepSeek LLM Provider — OpenAI 兼容协议 + chat / chat_json（三层 JSON 容错解析）。

思考模式（thinking）：deepseek-v4 系为推理模型，思维链会占用输出 token 预算。
本项目的合并/选音都是结构化 JSON 任务，默认关闭思考（DEEPSEEK_THINKING=1 可开）。
client 参数可注入 Mock（单元测试用）。
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
    ):
        self.client = client or OpenAI(api_key=api_key, base_url=base_url,
                                       timeout=300.0, max_retries=2)
        self.model = model
        self.thinking = thinking
        self.max_tokens = max_tokens

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=self.max_tokens,
            extra_body={"thinking": {"type": "enabled" if self.thinking else "disabled"}},
        )
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