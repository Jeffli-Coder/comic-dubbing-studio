"""流水线纯函数：角色名归一、空台词过滤、视觉性别投票、选音性别匹配。"""
import json

from config import QWEN_VOICES
from pipeline.stages import body_name, run_merge, run_voice_pick
from providers.base import PageLine, PageScript
from providers.mock_provider import MockLLM


def test_body_name_merges_inner_thought():
    assert body_name("林默（内心）") == "林默"
    assert body_name("林默(内心)") == "林默"
    assert body_name("旁白") == "旁白"


def test_empty_ocr_lines_are_filtered():
    page = PageScript(page_num=1, lines=[
        PageLine(character="A", text="第一句"),
        PageLine(character="A", text="   "),
        PageLine(character="B", text="第三句"),
    ])
    script = run_merge(MockLLM(), [page])
    lines = script["pages"][0]["lines"]
    assert [ln["text"] for ln in lines] == ["第一句", "第三句"]
    assert [ln["line_id"] for ln in lines] == ["p001_01", "p001_02"]


def test_vision_gender_overrides_llm_text_guess():
    class GenderLLM(MockLLM):
        def _merge(self, data):
            return {
                "title": "测试",
                "characters": [{"name": "小林", "type": "主角", "gender": "男", "description": ""}],
                "pages": [{"page_num": 1, "image": "pages/001.jpg",
                           "lines": [{"line_id": "p001_01", "character": "小林", "text": "你好"}]}],
            }

    page = PageScript(
        page_num=1,
        lines=[PageLine(character="小林", text="你好")],
        characters=[{"name": "小林", "gender": "女", "hint": "短发女生"}],
    )
    script = run_merge(GenderLLM(), [page])
    assert script["characters"][0]["gender"] == "女"


def test_voice_pick_enforces_gender():
    characters = [
        {"name": "男主", "gender": "男", "type": "主角", "description": ""},
        {"name": "女主", "gender": "女", "type": "主角", "description": ""},
    ]

    class WrongGenderLLM(MockLLM):
        def _voice_pick(self, data):
            female = next(v["voice"] for v in data["voices"] if v["gender"] == "女")
            return {"voice_assignments": {"男主": female, "女主": female}}

    assignments = run_voice_pick(WrongGenderLLM(), "测试", characters)
    genders = {v["voice"]: v["gender"] for v in QWEN_VOICES}
    assert genders[assignments["男主"]] == "男"
    assert genders[assignments["女主"]] == "女"
    assert assignments["男主"] != assignments["女主"]


def test_mock_llm_handles_json_prompt():
    llm = MockLLM()
    result = llm.chat_json(
        "[TASK:VOICE_PICK]",
        json.dumps({"characters": [{"name": "甲", "gender": "男"}],
                    "voices": QWEN_VOICES}, ensure_ascii=False),
    )
    assert result["voice_assignments"]