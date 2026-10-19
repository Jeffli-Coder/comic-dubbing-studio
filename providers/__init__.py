"""
Provider 工厂 — 按 config 开关实例化服务，缺 key/未实现时自动降级 Mock。
降级原因记录在 DEGRADED，供 /api/health 展示。

注意：实例用 lru_cache 缓存。OpenAI/DashScope 客户端构造有成本，
且 /api/health 每次请求都会调用工厂；缓存同时保证降级原因不会重复累积。
测试可用 reset_providers() 清空缓存。
"""
import logging
import shutil
from functools import lru_cache

from config import settings
from providers.base import BaseLLM, BaseTTS, BaseVision
from providers.mock_provider import MockLLM, MockTTS, MockVision

log = logging.getLogger(__name__)

# 降级记录：启动后若外部服务不可用，写入原因
DEGRADED: dict = {"tts": [], "vision": [], "llm": []}


def _degrade(kind: str, reason: str) -> None:
    if reason not in DEGRADED[kind]:
        DEGRADED[kind].append(reason)
        log.warning("[%s] %s", kind, reason)


@lru_cache(maxsize=1)
def get_tts() -> BaseTTS:
    """TTS_PROVIDER: qwen | fish | mock；不可用则降级 MockTTS。"""
    if settings.mock_mode or settings.tts_provider == "mock":
        return MockTTS()

    if settings.tts_provider == "qwen":
        if not settings.qwen_tts_enabled:
            _degrade("tts", "QWEN_TTS_ENABLED=0")
        elif not settings.qwen_api_key or not settings.qwen_base_url:
            _degrade("tts", "缺少 QWEN_API_KEY 或 QWEN_BASE_URL")
        else:
            try:
                from providers.qwen_tts_provider import QwenTTS
                return QwenTTS(settings.qwen_api_key, settings.qwen_base_url,
                               settings.qwen_tts_model)
            except Exception as e:  # key 缺失或 SDK 初始化失败
                _degrade("tts", f"QwenTTS 不可用: {e}")
    elif settings.tts_provider == "fish":
        if settings.fish_api_key:
            try:
                from providers.fish_tts_provider import FishTTS
                return FishTTS(settings.fish_api_key)
            except Exception as e:
                _degrade("tts", f"FishTTS 不可用: {e}")
        else:
            _degrade("tts", "TTS_PROVIDER=fish 但缺少 FISH_AUDIO_API_KEY")
    else:
        _degrade("tts", f"未知 TTS_PROVIDER={settings.tts_provider!r}，默认 Mock")

    return MockTTS()


@lru_cache(maxsize=1)
def get_vision() -> BaseVision:
    """VISION_PROVIDER: qwen | mock；不可用则降级 MockVision。"""
    if settings.mock_mode or settings.vision_provider == "mock":
        return MockVision()

    if settings.vision_provider == "qwen":
        if not settings.qwen_vision_enabled:
            _degrade("vision", "QWEN_VISION_ENABLED=0")
        elif not settings.qwen_vision_api_key or not settings.qwen_vision_base_url:
            _degrade("vision", "缺少 QWEN_API_KEY 或 QWEN_VISION_BASE_URL")
        else:
            try:
                from providers.qwen_vision_provider import QwenVision
                return QwenVision(settings.qwen_vision_api_key, settings.qwen_vision_base_url,
                                  settings.qwen_vision_model, thinking=settings.qwen_vision_thinking)
            except Exception as e:
                _degrade("vision", f"QwenVision 不可用: {e}")
    else:
        _degrade("vision", f"未知 VISION_PROVIDER={settings.vision_provider!r}，默认 Mock")

    return MockVision()


@lru_cache(maxsize=1)
def get_llm() -> BaseLLM:
    """LLM_PROVIDER: deepseek | openai | mock；缺配置降级 MockLLM。

    - deepseek：使用 DEEPSEEK_*（默认官方地址，也可指向兼容网关）
    - openai  ：使用 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL，可接任意
                OpenAI 兼容服务（阿里云百炼、vLLM、Ollama、OneAPI 等）
    """
    if settings.mock_mode or settings.llm_provider == "mock":
        return MockLLM()

    provider = settings.llm_provider
    if provider == "deepseek":
        api_key = settings.deepseek_api_key
        base_url = settings.deepseek_base_url
        model = settings.deepseek_model
        thinking = settings.deepseek_thinking
        # 保持 DeepSeek 原有行为：显式关闭/开启思考；
        # LLM_EXTRA_BODY 可覆盖（包括用 {} 表示完全不发送额外字段）
        extra_body = settings.llm_extra_body
        if extra_body is None:
            extra_body = {"thinking": {"type": "enabled" if thinking else "disabled"}}
        max_tokens = settings.deepseek_max_tokens
    elif provider in ("openai", "compat", "openai_compatible"):
        api_key = settings.llm_api_key
        base_url = settings.llm_base_url
        model = settings.llm_model
        thinking = False
        # 通用网关默认不加任何厂商专属字段；需要时用 LLM_EXTRA_BODY 指定
        extra_body = settings.llm_extra_body
        max_tokens = settings.llm_max_tokens
        provider = "openai"
    else:
        _degrade("llm", f"未知 LLM_PROVIDER={settings.llm_provider!r}，默认 Mock")
        return MockLLM()

    missing = []
    if not api_key:
        missing.append("DEEPSEEK_API_KEY" if provider == "deepseek" else "LLM_API_KEY")
    if not base_url:
        missing.append("LLM_BASE_URL")
    if not model:
        missing.append("LLM_MODEL")
    if missing:
        _degrade("llm", "缺少 " + " / ".join(missing))
        return MockLLM()

    try:
        from providers.deepseek_provider import DeepSeekLLM
        return DeepSeekLLM(
            api_key, base_url, model, thinking=thinking,
            max_tokens=max_tokens, extra_body=extra_body, name=provider,
        )
    except Exception as e:
        _degrade("llm", f"{provider} LLM 不可用: {e}")
        return MockLLM()


def reset_providers() -> None:
    """清空 provider 实例缓存与降级记录（测试 / 运行时重载配置用）。"""
    get_tts.cache_clear()
    get_vision.cache_clear()
    get_llm.cache_clear()
    for kind in DEGRADED:
        DEGRADED[kind].clear()


def ffmpeg_path():
    """系统 PATH 里的 ffmpeg 优先；否则回退到 pip 包 imageio-ffmpeg 自带的二进制。

    FFMPEG_BIN 可显式覆盖；设为 off/none/0 可强制禁用（用于测试纯 WAV 路径）。
    """
    override = (settings.ffmpeg_bin or "").strip()
    if override:
        if override.lower() in {"0", "off", "none", "false", "no"}:
            return None
        return override

    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def has_ffmpeg() -> bool:
    return ffmpeg_path() is not None