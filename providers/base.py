"""
Provider 抽象基类 — 全流水线的类型契约。
所有外部服务（LLM/TTS/视觉）只通过这三个抽象接口被编排层调用。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TTSResult:
    audio_bytes: bytes
    fmt: str                       # "mp3" | "wav"
    duration_ms: Optional[int] = None   # 已知则填；否则由 AudioMixer 实测


class BaseTTS(ABC):
    """语音合成抽象。voice 为供应商音色标识（千问=voice 参数，Fish=reference_id）。"""

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice: str,
        *,
        speed: float = 1.0,
        emotion: str = "",
        pitch: str = "正常",
        emphasis: Optional[list] = None,
        fmt: str = "mp3",
    ) -> TTSResult:
        """合成一句台词。speed/pitch/emphasis 为配音脚本参数，供应商支持则透传。"""


@dataclass
class PageLine:
    """单句台词（视觉模型输出 / 合并后落盘结构）。bbox 预留未来图上高亮。"""
    character: str
    text: str
    type: str = "dialogue"          # dialogue | monologue | narration | inner_thought
    emotion: str = "日常"
    speed: float = 1.0
    pitch: str = "正常"
    emphasis: list = field(default_factory=list)
    pause_after_ms: int = 300
    bbox: Optional[dict] = None     # {x, y, w, h} 0-1 归一化（暂不落盘）

    def to_dict(self) -> dict:
        d = {
            "character": self.character,
            "text": self.text,
            "type": self.type,
            "emotion": self.emotion,
            "speed": self.speed,
            "pitch": self.pitch,
            "emphasis": self.emphasis,
            "pause_after_ms": self.pause_after_ms,
        }
        if self.bbox:
            d["bbox"] = self.bbox
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PageLine":
        return cls(
            character=str(d.get("character", "未知")),
            text=str(d.get("text", "")),
            type=str(d.get("type", "dialogue")),
            emotion=str(d.get("emotion", "日常")),
            speed=float(d.get("speed", 1.0)),
            pitch=str(d.get("pitch", "正常")),
            emphasis=list(d.get("emphasis", []) or []),
            pause_after_ms=int(d.get("pause_after_ms", 300)),
            bbox=d.get("bbox"),
        )


@dataclass
class PageScript:
    """单页识别结果"""
    page_num: int
    lines: list
    page_notes: str = ""
    # 本页出现的角色外观信息：[{"name": "苏晴", "gender": "女", "hint": "年轻女性，书店制服"}]
    # 由视觉模型根据画面判断，供下游合并/选角使用（性别匹配音色）
    characters: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "page_num": self.page_num,
            "lines": [item.to_dict() if isinstance(item, PageLine) else item for item in self.lines],
            "page_notes": self.page_notes,
            "characters": list(self.characters),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PageScript":
        return cls(
            page_num=int(d.get("page_num", 0)),
            lines=[PageLine.from_dict(item) if isinstance(item, dict) else item
                   for item in d.get("lines", [])],
            page_notes=str(d.get("page_notes", "")),
            characters=[c for c in (d.get("characters") or []) if isinstance(c, dict)],
        )


class BaseVision(ABC):
    """漫画页视觉识别抽象（OCR + 说话人判定）。"""

    @abstractmethod
    def analyze_page(
        self,
        image_bytes: bytes,
        *,
        page_num: int,
        prev_context: Optional[dict] = None,
    ) -> PageScript:
        """prev_context 携带前页角色清单 {"characters": [...]}，用于保证跨页命名一致。"""


class BaseLLM(ABC):
    """文本 LLM 抽象。chat_json 需保证返回可解析的 JSON dict。"""

    @abstractmethod
    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str: ...

    @abstractmethod
    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict: ...