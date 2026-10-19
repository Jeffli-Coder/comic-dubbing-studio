"""Qwen TTS Provider — qwen-audio-3.0-tts-plus（DashScope SpeechSynthesizer）"""
import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer

from providers.base import BaseTTS, TTSResult


def normalize_ws_url(base_url: str) -> str:
    """
    统一为 WebSocket 推理地址：
      - wss://host/api-ws/v1/inference      → 原样使用
      - https://host/compatible-mode/v1     → 推导同主机的 wss://host/api-ws/v1/inference
    """
    u = base_url.rstrip("/")
    if u.startswith(("wss://", "ws://")):
        return u
    host = u.split("//", 1)[-1].split("/", 1)[0]
    return f"wss://{host}/api-ws/v1/inference"


class QwenTTS(BaseTTS):
    name = "qwen"

    def __init__(self, api_key: str, base_url: str = "", model: str = "qwen-audio-3.0-tts-plus"):
        if not api_key or not base_url:
            raise ValueError("QwenTTS 需要 QWEN_API_KEY 与 QWEN_BASE_URL（.env）")
        self.api_key = api_key
        self.base_url = normalize_ws_url(base_url)
        self.model = model
        dashscope.api_key = self.api_key
        dashscope.base_websocket_api_url = self.base_url

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
        if not text.strip():
            raise ValueError("QwenTTS: 空文本")
        synthesizer = SpeechSynthesizer(model=self.model, voice=voice)
        audio_bytes = synthesizer.call(text)
        if not audio_bytes:
            raise RuntimeError("QwenTTS 返回空音频（内容审核、配额或连接失败）")
        return TTSResult(audio_bytes=audio_bytes, fmt="mp3")