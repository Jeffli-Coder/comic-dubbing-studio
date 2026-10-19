"""Qwen Vision Provider — 漫画页 OCR 识别（DashScope OpenAI 兼容模式）"""
import base64
import json
import re
from typing import Optional

from openai import OpenAI

from providers.base import BaseVision, PageLine, PageScript
from providers.image_mime import sniff_image_mime

VISION_SYSTEM = """你是一个漫画 OCR 与对话识别助手。你会收到一页漫画图片，请提取页面中所有正文台词。

# 只提取这些
- 角色对白气泡
- 角色内心独白气泡
- 旁白框 / 叙述文字

# 忽略这些（一律不要输出）
- 封面/扉页的标题、副标题
- 卷号、期号标记（如 "volume one"、"Vol.1"、"第1卷"）
- 目录页的条目文字
- 出版社、版权、作者署名等页脚/页边信息
- 拟声词、画面上的效果字、装饰文字

# 规则
- 按阅读顺序（从右到左、从上到下）列出所有台词
- 每句台词包含说话人（character）和文字（text）
- 不确定说话人的 character 填 "未知"
- 若本页没有任何对白/旁白（如封面、目录、纯画面页），lines 返回空数组
- 只输出 JSON，不要输出任何解释性文字

# 角色外观（重要）
另外根据画面中角色的外观（发型、体型、服装、面部特征）判断其性别与一句话特征，
列出本页出现过的所有角色：
- gender 只能取 "男" / "女" / "未知"（看不清或无法判断时用 "未知"，不要瞎猜）
- hint 是一句话外观特征（如 "年轻男性，西装上班族"）

# 输出格式
{"lines": [{"character": "角色名", "text": "台词原文", "uncertain": false}],
 "characters": [{"name": "角色名", "gender": "女", "hint": "年轻女性，书店制服"}],
 "notes": "页面的额外说明"}
"""


class QwenVision(BaseVision):
    name = "qwen"

    def __init__(self, api_key: str, base_url: str = "", model: str = "qwen3.6-flash",
                 thinking: bool = False, client: Optional[OpenAI] = None):
        if not api_key or not base_url:
            raise ValueError("QwenVision 需要 QWEN_API_KEY 与 QWEN_VISION_BASE_URL（.env）")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.thinking = thinking   # OCR 是格式化的提取任务，思考只会拖慢速度（默认关）
        self.client = client or OpenAI(api_key=api_key, base_url=base_url,
                                       timeout=120.0, max_retries=2)

    def analyze_page(self, image_bytes: bytes, *, page_num: int,
                     prev_context: dict | None = None) -> PageScript:
        if not image_bytes:
            raise ValueError(f"第 {page_num} 页图片为空")
        b64 = base64.b64encode(image_bytes).decode()
        # 按真实类型发送 data URL（PNG/WebP 不能标成 image/jpeg）
        mime = sniff_image_mime(image_bytes) or "image/jpeg"
        context_note = ""
        if prev_context and prev_context.get("characters"):
            context_note = (
                "（参考）前页已出现的角色：" + "、".join(prev_context["characters"]) +
                "。请尽量使用相同的名字称呼这些角色。\n"
            )

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{
                "role": "system",
                "content": VISION_SYSTEM,
            }, {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{context_note}第 {page_num} 页，提取所有对话："},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }],
            max_tokens=4096,
            temperature=0.1,
            extra_body={"enable_thinking": self.thinking},
        )

        raw = resp.choices[0].message.content or ""
        data = self._parse_json(raw)

        lines = []
        for item in data.get("lines", []):
            if isinstance(item, dict):
                lines.append(PageLine(
                    character=str(item.get("character", "未知")),
                    text=str(item.get("text", "")),
                    type="dialogue",
                ))

        characters = []
        for item in data.get("characters", []) or []:
            if isinstance(item, dict) and item.get("name"):
                characters.append({
                    "name": str(item["name"]),
                    "gender": str(item.get("gender") or "未知"),
                    "hint": str(item.get("hint") or ""),
                })

        notes = str(data.get("notes", ""))
        if not lines:
            notes = ("（视觉模型未识别到台词）" + notes).strip()

        return PageScript(page_num=page_num, lines=lines, page_notes=notes,
                          characters=characters)

    @staticmethod
    def _parse_json(raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
        cleaned = re.sub(r"\n?```\s*$", "", cleaned.strip())
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}