"""
Fish Audio TTS Provider — 备选供应商 + 声音克隆能力留痕。

主流程（BookPipeline）只使用 synthesize()；克隆相关方法（clone_voice /
wait_for_clone / list_voices）为「接口留着便于后续升级」的留痕实现，
当前不接入任何路由。
"""
import time
import requests

from providers.base import BaseTTS, TTSResult


class FishTTS(BaseTTS):
    name = "fish"
    BASE_URL = "https://api.fish.audio"

    def __init__(self, api_key: str, model: str = "s2.1-pro-free"):
        self.api_key = api_key
        self.model = model
        self.headers = {"Authorization": f"Bearer {api_key}"}

    # ── TTS 合成（BaseTTS 契约；voice 即 Fish reference_id）──
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
        url = f"{self.BASE_URL}/v1/tts"
        payload = {"text": text, "format": fmt}
        if voice:
            payload["reference_id"] = voice
        # 注：Fish Audio TTS 不提供语速/情感参数，speed/emotion 在此供应商下被忽略
        resp = requests.post(
            url, json=payload, headers={**self.headers, "model": self.model}, timeout=60
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Fish Audio TTS 失败 (HTTP {resp.status_code}): {resp.text[:300]}")
        return TTSResult(audio_bytes=resp.content, fmt=fmt)

    # ── 声音克隆（留痕，主流程不接）──
    def clone_voice(self, audio_bytes: bytes, title: str, audio_format: str = "mp3",
                    train_mode: str = "fast") -> dict:
        url = f"{self.BASE_URL}/model"
        files = {"voices": (f"sample.{audio_format}", audio_bytes, f"audio/{audio_format}")}
        data = {
            "title": title,
            "type": "tts",
            "train_mode": train_mode,
            "enhance_audio_quality": "true",
            "visibility": "private",
        }
        resp = requests.post(url, headers=self.headers, data=data, files=files, timeout=120)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Fish Audio 克隆失败 (HTTP {resp.status_code}): {resp.text[:300]}")
        result = resp.json()
        return {
            "voice_id": result.get("_id", ""),
            "state": result.get("state", "created"),
            "title": result.get("title", title),
        }

    def wait_for_clone(self, voice_id: str, timeout: int = 300) -> dict:
        url = f"{self.BASE_URL}/model/{voice_id}"
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = requests.get(url, headers=self.headers, timeout=30)
            if resp.status_code != 200:
                raise RuntimeError(f"查询克隆状态失败: {resp.text[:200]}")
            data = resp.json()
            state = data.get("state", "")
            if state == "trained":
                return {"voice_id": voice_id, "state": "trained"}
            if state == "failed":
                raise RuntimeError(f"克隆训练失败: {data}")
            time.sleep(5)
        raise TimeoutError(f"克隆训练超时 ({timeout}s)")

    def list_voices(self, title: str = "", self_only: bool = False, page_size: int = 20) -> list:
        url = f"{self.BASE_URL}/model"
        params = {"page_size": page_size, "self_only": str(self_only).lower()}
        if title:
            params["title"] = title
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"查询声音库失败: {resp.text[:200]}")
        return resp.json().get("items", [])

    def download_audio(self, url: str) -> bytes:
        resp = requests.get(url, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f"下载音频失败 (HTTP {resp.status_code})")
        return resp.content