"""
Mock Provider — 零外部依赖（无 API key、无 ffmpeg）跑通整条流水线。
千问 API 未配置 / 离线开发 / 单元测试时使用；也是 Provider 抽象价值的体现。
"""
import json
import re
import wave
from io import BytesIO

from providers.base import BaseLLM, BaseTTS, BaseVision, PageLine, PageScript, TTSResult


# ═══════════════════════════════════════════════════════════
# 工具：生成真实可播放的静音 WAV（纯 stdlib，便于验证时长/拼接）
# ═══════════════════════════════════════════════════════════
def silent_wav(duration_s: float, rate: int = 24000) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)          # 16bit
        w.setframerate(rate)
        n_frames = int(rate * duration_s)
        # 16bit 单声道静音：直接写零字节，避免 struct.pack 展开数十万个参数
        w.writeframes(b"\x00" * (n_frames * 2))
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════
# MockTTS：按文本长度生成对应时长的静音 WAV——
# 时长随字数/语速变化，可完整验证时间戳累积与逐句高亮逻辑
# ═══════════════════════════════════════════════════════════
class MockTTS(BaseTTS):
    name = "mock"

    def synthesize(
        self,
        text: str,
        voice: str,
        *,
        speed: float = 1.0,
        emotion: str = "",
        pitch: str = "正常",
        emphasis=None,
        fmt: str = "mp3",
    ) -> TTSResult:
        n_chars = max(len(re.sub(r"\s", "", text)), 1)
        dur_s = min(20.0, max(0.35, 0.3 + n_chars * 0.11 / max(speed, 0.1)))
        return TTSResult(audio_bytes=silent_wav(dur_s), fmt="wav", duration_ms=int(dur_s * 1000))


# ═══════════════════════════════════════════════════════════
# MockVision：按页码确定性生成演示台词（3 角色 + 旁白轮换，
# 奇数页插入「林默（内心）」演示内心OS合并到本体音色）
# ═══════════════════════════════════════════════════════════
class MockVision(BaseVision):
    name = "mock"

    POOL = ["林默", "苏晴", "店员A"]
    EMOTIONS = ["日常", "疑惑", "期待", "愤怒", "戏谑"]

    def analyze_page(self, image_bytes: bytes, *, page_num: int, prev_context=None) -> PageScript:
        lines = []
        n_lines = 2 if page_num % 3 == 0 else 3
        for i in range(n_lines):
            speaker = (page_num + i) % 4
            if speaker == 3:
                char = "旁白"
            else:
                char = self.POOL[(page_num + i) % len(self.POOL)]
                if char == "林默" and page_num % 2 == 1 and i == 1:
                    char = "林默（内心）"
            emo = self.EMOTIONS[(page_num + i) % len(self.EMOTIONS)]
            lines.append(PageLine(
                character=char,
                text=f"第{page_num}页第{i + 1}句：{char}的{emo}演示台词，用于验证逐句高亮。",
                type="inner_thought" if "内心" in char else ("narration" if char == "旁白" else "dialogue"),
                emotion=emo,
                speed=1.0 if page_num % 2 == 0 else 1.2,
                pitch="正常",
                emphasis=["演示台词"],
                pause_after_ms=400,
            ))
        return PageScript(page_num=page_num, lines=lines, page_notes="Mock 演示页")


# ═══════════════════════════════════════════════════════════
# MockLLM：识别 system prompt 中的 [TASK:MERGE] / [TASK:VOICE_PICK] 标记，
# 对 stage 传入的结构化 JSON user_prompt 做确定性处理（与真实 LLM 输出同构）。
# ═══════════════════════════════════════════════════════════
class MockLLM(BaseLLM):
    name = "mock"

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        return json.dumps(self.chat_json(system_prompt, user_prompt, temperature), ensure_ascii=False)

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict:
        data = _parse_user_json(user_prompt)
        if "[TASK:MERGE]" in system_prompt:
            return self._merge(data)
        if "[TASK:VOICE_PICK]" in system_prompt:
            return self._voice_pick(data)
        return {"output": "mock"}

    @staticmethod
    def _body(name: str) -> str:
        return re.sub(r"[（(]\s*内心\s*[)）]", "", name).strip()

    def _merge(self, data: dict) -> dict:
        """把逐页 PageScript 合并成按页脚本（title/characters/pages）。"""
        page_scripts = [
            PageScript.from_dict(d) for d in data.get("page_scripts", []) if isinstance(d, dict)
        ]
        characters, seen = [], set()
        pages = []
        for ps in sorted(page_scripts, key=lambda p: p.page_num):
            page_lines = []
            for idx, ln in enumerate(ps.lines, start=1):
                body = self._body(ln.character)
                if body not in seen:
                    seen.add(body)
                    characters.append({
                        "name": body,
                        "type": "旁白" if body == "旁白" else ("主角" if len(seen) == 1 else "配角"),
                        "description": f"{body}（Mock 生成的角色描述）",
                    })
                line = ln.to_dict()
                line["line_id"] = f"p{ps.page_num:03d}_{idx:02d}"
                page_lines.append(line)
            pages.append({
                "page_num": ps.page_num,
                "image": f"pages/{ps.page_num:03d}.jpg",
                "lines": page_lines,
                "page_notes": ps.page_notes,
            })
        if not pages:
            raise ValueError("MockLLM._merge: 没有可合并的页面识别结果")
        return {"title": "演示漫画（Mock 模式）", "characters": characters, "pages": pages}

    def _voice_pick(self, data: dict) -> dict:
        """确定性选音：按角色名哈希在（同性别的）音色中稳定取一个。"""
        characters = data.get("characters", [])
        voices = data.get("voices", [])
        if not voices:
            raise ValueError("MockLLM._voice_pick: 音色清单为空")
        bodies, gender_of = [], {}
        for item in characters:
            if isinstance(item, dict):
                name, g = item.get("name"), str(item.get("gender") or "未知")
            else:
                name, g = item, "未知"
            body = self._body(str(name))
            if body and body not in bodies:
                bodies.append(body)
                gender_of[body] = g
        assignments = {}
        for body in bodies:
            g = gender_of.get(body, "未知")
            pool = [v for v in voices if g not in ("男", "女") or v.get("gender") == g] or voices
            idx = sum(ord(c) for c in body) % len(pool)
            assignments[body] = pool[idx].get("voice", "")
        return {"voice_assignments": assignments, "note": "Mock 确定性选音（按性别过滤）"}


def _parse_user_json(user_prompt: str) -> dict:
    try:
        d = json.loads(user_prompt)
        return d if isinstance(d, dict) else {}
    except json.JSONDecodeError:
        pass
    # 兜底：从文本中提取第一个 {...} 块
    m = re.search(r"\{.*\}", user_prompt, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}