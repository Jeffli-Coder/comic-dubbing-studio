"""
stages — 流水线阶段纯函数：OCR 聚合、LLM 合并汇总、LLM 选音。
不直接写磁盘（磁盘动作由 orchestrator 负责），便于单测注入 Mock。
"""
import json
import re
from collections import Counter

from config import QWEN_VOICES
from prompts import MERGE_SYSTEM, VOICE_PICK_SYSTEM
from providers.base import BaseLLM, PageScript

EMOTIONS = ["高兴", "悲伤", "愤怒", "紧张", "惊讶", "恐惧", "温柔", "冷漠",
            "戏谑", "坚定", "犹豫", "日常"]

# 单次合并的最大页数：合并输出是整页 JSON（行数 × 每行字段），
# 页数过多会超出 max_tokens 被截断 → 分批合并后归并
MERGE_CHUNK_PAGES = 20


def body_name(name: str) -> str:
    """「林默（内心）」→「林默」（内心 OS 与本体重名同音色）。"""
    return re.sub(r"[（(]\s*内心\s*[)）]", "", str(name)).strip()


# ═══════════════════════════════════════════════════════════
# 阶段 1+2：逐页识别 → LLM 合并（分批）→ 按页脚本
# ═══════════════════════════════════════════════════════════
def run_merge(llm: BaseLLM, page_scripts: list) -> dict:
    """
    调 LLM 把逐页 PageScript 合并成完整脚本，再用原始识别行做安全修复
    （character/text/顺序以视觉识别为准，LLM 只负责润色与参数补全）。
    超过 MERGE_CHUNK_PAGES 页时分批调用，角色表跨批归并、页码顺序不变。
    返回 {title, characters, pages}。
    """
    ordered = sorted(page_scripts, key=lambda p: p.page_num)
    chunks = [ordered[i:i + MERGE_CHUNK_PAGES]
              for i in range(0, len(ordered), MERGE_CHUNK_PAGES)] or [[]]

    title = ""
    characters, seen_chars, known = [], set(), []
    pages_repaired = []

    for chunk in chunks:
        if not chunk:
            continue
        user = json.dumps(
            {"known_characters": known, "page_scripts": [ps.to_dict() for ps in chunk]},
            ensure_ascii=False,
        )
        merged = llm.chat_json(MERGE_SYSTEM, user, temperature=0.3)

        if not title and merged.get("title"):
            title = str(merged["title"])

        for c in merged.get("characters") or []:
            name = str(c.get("name") or "").strip() if isinstance(c, dict) else ""
            if name and name not in seen_chars:
                seen_chars.add(name)
                characters.append(c)
                known.append(name)

        # 本批页面的修复与落册（见下方统一循环外的实现）
        chunk_page_map = {
            p.get("page_num"): p for p in (merged.get("pages") or []) if isinstance(p, dict)
        }
        for ps in chunk:
            pages_repaired.append(_repair_page(ps, chunk_page_map.get(ps.page_num) or {}))

    if not title:
        title = "未命名漫画"

    # 视觉外观补充：从各页 characters 的性别投票中提取（多数表决），
    # 画面看到的信息比文字推断可靠，有投票时覆盖 LLM 的判断
    gender_votes: dict = {}
    for ps in ordered:
        for c in (getattr(ps, "characters", None) or []):
            nm = body_name(str(c.get("name") or ""))
            g = str(c.get("gender") or "")
            if nm and g in ("男", "女"):
                gender_votes.setdefault(nm, Counter())[g] += 1

    def vision_gender(nm: str) -> str:
        cnt = gender_votes.get(nm)
        return cnt.most_common(1)[0][0] if cnt else "未知"

    for c in characters:
        if isinstance(c, dict):
            nm = body_name(str(c.get("name") or ""))
            g = vision_gender(nm)
            if g != "未知":
                c["gender"] = g
            elif "gender" not in c:
                c["gender"] = "未知"

    # 角色表兜底：LLM 没给就从台词里聚合
    if not characters:
        seen = set()
        for p in pages_repaired:
            for ln in p["lines"]:
                b = body_name(ln["character"])
                if b and b not in seen:
                    seen.add(b)
                    characters.append({
                        "name": b,
                        "type": "旁白" if b == "旁白" else "主角" if len(seen) == 1 else "配角",
                        "gender": vision_gender(b),
                        "description": f"{b}（自动聚合）",
                    })

    return {"title": title, "characters": characters, "pages": pages_repaired}


def _repair_page(raw: PageScript, merged_page: dict) -> dict:
    """以原始识别行为准逐句修复 LLM 输出（数量/文本/角色不可信时兜底）。"""
    # OCR 偶尔会产出空台词（气泡没识别全 / 只有符号）；空文本不应进入配音
    raw_lines = [ln for ln in raw.lines if str(ln.text or "").strip()]
    m_lines = merged_page.get("lines") or []
    if not isinstance(m_lines, list) or len(m_lines) != len(raw_lines):
        m_lines = [{} for _ in raw_lines]
        merged_page = {**merged_page, "page_notes":
                       (str(merged_page.get("page_notes", "")) + "（行数不匹配，按原始识别修复）").strip()}

    lines = []
    for i, raw_l in enumerate(raw_lines):
        d = m_lines[i] if i < len(m_lines) and isinstance(m_lines[i], dict) else {}
        lines.append({
            "line_id": str(d.get("line_id") or f"p{raw.page_num:03d}_{i + 1:02d}"),
            "character": str(d.get("character") or raw_l.character).strip(),
            "text": str(d.get("text") or raw_l.text).strip(),
            "type": d.get("type") or raw_l.type or "dialogue",
            "emotion": d.get("emotion") or raw_l.emotion or "日常",
            "speed": _safe_float(d.get("speed"), raw_l.speed),
            "pitch": d.get("pitch") or raw_l.pitch or "正常",
            "emphasis": list(d.get("emphasis") or raw_l.emphasis or []),
            "pause_after_ms": int(d.get("pause_after_ms", raw_l.pause_after_ms) or 300),
        })
    return {
        "page_num": raw.page_num,
        "image": str(merged_page.get("image") or f"pages/{raw.page_num:03d}.jpg"),
        "lines": lines,
        "page_notes": str(merged_page.get("page_notes") or raw.page_notes or ""),
    }


def _safe_float(v, default: float) -> float:
    try:
        f = float(v)
        return min(2.0, max(0.6, f)) if f else default
    except (TypeError, ValueError):
        return default


# ═══════════════════════════════════════════════════════════
# 阶段 3：LLM 从 50 音色中选角
# ═══════════════════════════════════════════════════════════
def run_voice_pick(llm: BaseLLM, title: str, characters: list) -> dict:
    """返回 {角色本体名: voice参数}（已合并内心OS、按性别强制匹配、保证每角色有值）。"""
    char_infos, bodies, gender_of = [], [], {}
    for c in characters:
        if isinstance(c, dict):
            b = body_name(str(c.get("name") or ""))
            g = str(c.get("gender") or "未知")
            info = {"name": b, "gender": g, "type": str(c.get("type") or ""),
                    "description": str(c.get("description") or "")}
        else:
            b = body_name(str(c))
            g, info = "未知", {"name": b, "gender": "未知", "type": "", "description": ""}
        if b and b not in bodies:
            bodies.append(b)
            char_infos.append(info)
            gender_of[b] = g

    user = json.dumps(
        {"title": title, "characters": char_infos, "voices": QWEN_VOICES},
        ensure_ascii=False,
    )
    result = llm.chat_json(VOICE_PICK_SYSTEM, user, temperature=0.1)
    raw = result.get("voice_assignments") or {}
    if not isinstance(raw, dict):
        raw = {}

    voice_gender = {v["voice"]: v["gender"] for v in QWEN_VOICES}
    assignments = {}
    for body in bodies:
        voice = raw.get(body) or raw.get(body_name(body))
        g = gender_of.get(body, "未知")
        if not voice or voice not in voice_gender:
            voice = _fallback_voice(body, g)
        elif g in ("男", "女") and voice_gender.get(voice) != g:
            voice = _fallback_voice(body, g)   # LLM 选错性别 → 强制换同性别音色
        assignments[body] = voice
    return assignments


def _fallback_voice(body: str, gender: str) -> str:
    """确定性兜底选音：性别已知时只在同性别音色中取。"""
    pool = [v for v in QWEN_VOICES if gender not in ("男", "女") or v["gender"] == gender]
    pool = pool or QWEN_VOICES
    return pool[sum(ord(ch) for ch in body) % len(pool)]["voice"]


def voice_for_character(assignments: dict, character: str) -> str:
    """按角色名找音色；找不到用兜底音色。"""
    b = body_name(character)
    return assignments.get(b) or QWEN_VOICES[0]["voice"]