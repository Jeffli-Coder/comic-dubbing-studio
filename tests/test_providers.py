"""Provider 细节：图片魔数、视觉请求 MIME、TTS 空响应。"""
from io import BytesIO

import pytest
from PIL import Image

from providers.image_mime import EXT_FOR_MIME, sniff_image_mime, sniff_is_pdf


def png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (2, 2), (1, 2, 3)).save(buf, "PNG")
    return buf.getvalue()


def jpeg_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (2, 2), (1, 2, 3)).save(buf, "JPEG")
    return buf.getvalue()


def test_sniff_image_mime():
    assert sniff_image_mime(png_bytes()) == "image/png"
    assert sniff_image_mime(jpeg_bytes()) == "image/jpeg"
    assert sniff_image_mime(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff_image_mime(b"not an image") is None
    assert EXT_FOR_MIME["image/png"] == ".png"


def test_sniff_pdf():
    assert sniff_is_pdf(b"%PDF-1.7\n...")
    assert not sniff_is_pdf(b"hello")


def test_vision_sends_real_mime():
    from providers.qwen_vision_provider import QwenVision

    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)

            class Message:
                content = '{"lines": [], "characters": [], "notes": "ok"}'

            class Choice:
                message = Message()

            class Resp:
                choices = [Choice()]

            return Resp()

    class FakeClient:
        class chat:
            completions = FakeCompletions()

    vision = QwenVision("key", "https://example.com/v1", client=FakeClient())
    vision.analyze_page(png_bytes(), page_num=1)
    image_url = captured["messages"][1]["content"][1]["image_url"]["url"]
    assert image_url.startswith("data:image/png;base64,")


def test_qwen_tts_rejects_empty_text_and_audio(monkeypatch):
    pytest.importorskip("dashscope")
    import providers.qwen_tts_provider as mod

    class FakeSynth:
        def __init__(self, model, voice):
            pass

        def call(self, text):
            return b""

    monkeypatch.setattr(mod, "SpeechSynthesizer", FakeSynth)
    tts = mod.QwenTTS("key", "https://example.com")

    with pytest.raises(ValueError):
        tts.synthesize("   ", "voice")
    with pytest.raises(RuntimeError):
        tts.synthesize("你好", "voice")