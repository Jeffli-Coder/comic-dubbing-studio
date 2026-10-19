"""
集中配置 — 读取 .env；50 种千问音色清单；Provider 开关与路径常量
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
# 显式指定 .env 位置，避免从其他工作目录启动时读不到；
# utf-8-sig 兼容 Windows 记事本保存的 BOM；override=False 保证环境变量优先。
load_dotenv(dotenv_path=Path(os.getenv("DOTENV_PATH") or (BASE_DIR / ".env")),
            encoding="utf-8-sig", override=False)

DATA_DIR = Path(os.getenv("DATA_DIR") or (BASE_DIR / "data")).expanduser().resolve()
BOOKS_DIR = DATA_DIR / "books"
STATIC_DIR = BASE_DIR / "static"

__version__ = "2.1.0"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def _env_json(name: str):
    """解析 JSON 对象型环境变量（如 LLM_EXTRA_BODY）；非法值返回 None。"""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None

# ═══════════════════════════════════════════════════════════
# 50 种千问音色（从 qwen-audio-3.0-tts-plus基础音色.xlsx 597 个中精选）
# voice 字段即 TTS 调用参数；网页下拉与 LLM 选音提示词共用此清单
# ═══════════════════════════════════════════════════════════
QWEN_VOICES = [
    # ── 男 · 儿童/少年（5）──
    {"name": "龙风兰潇", "voice": "qwen-audio-3.0-tts-plus-longfenglanxiao", "gender": "男", "age": 8,  "trait": "元气活力音"},
    {"name": "龙沫风烁", "voice": "qwen-audio-3.0-tts-plus-longmofengshuo",     "gender": "男", "age": 13, "trait": "自信从容音"},
    {"name": "龙玥凌嵐", "voice": "qwen-audio-3.0-tts-plus-longyuelinglan",     "gender": "男", "age": 19, "trait": "激动振奋音"},
    {"name": "龙琴鹊漪", "voice": "qwen-audio-3.0-tts-plus-longqinqueyi",       "gender": "男", "age": 16, "trait": "自然亲和音"},
    {"name": "龙鸿昕旭", "voice": "qwen-audio-3.0-tts-plus-longhongxinxu",      "gender": "男", "age": 15, "trait": "自然亲和音"},
    # ── 男 · 青年（10）──
    {"name": "龙岚煜芙", "voice": "qwen-audio-3.0-tts-plus-longlanyufu",        "gender": "男", "age": 22, "trait": "温柔亲和音"},
    {"name": "龙霓岫涟", "voice": "qwen-audio-3.0-tts-plus-longnixiulian",      "gender": "男", "age": 25, "trait": "内敛含蓄音"},
    {"name": "龙莹松柳", "voice": "qwen-audio-3.0-tts-plus-longyingsongliu",    "gender": "男", "age": 32, "trait": "爽朗利落音"},
    {"name": "龙筝瑶鹤", "voice": "qwen-audio-3.0-tts-plus-longzhengyaohe",     "gender": "男", "age": 38, "trait": "亢奋激昂音"},
    {"name": "龙风兰露", "voice": "qwen-audio-3.0-tts-plus-longfenglanlu",      "gender": "男", "age": 25, "trait": "清朗少年音"},
    {"name": "龙瑶岚萱", "voice": "qwen-audio-3.0-tts-plus-longyaolanxuan",     "gender": "男", "age": 25, "trait": "傲娇俏皮音"},
    {"name": "龙焱芷晖", "voice": "qwen-audio-3.0-tts-plus-longyanzhihui",      "gender": "男", "age": 25, "trait": "温润磁性音"},
    {"name": "龙溪凌璇", "voice": "qwen-audio-3.0-tts-plus-longxilingxuan",     "gender": "男", "age": 28, "trait": "不满犀利音"},
    {"name": "龙澄鸿蕊", "voice": "qwen-audio-3.0-tts-plus-longchenghongrui",   "gender": "男", "age": 28, "trait": "沮丧低落音"},
    {"name": "龙熠琴晖", "voice": "qwen-audio-3.0-tts-plus-longyiqinhui",       "gender": "男", "age": 26, "trait": "憨萌逗趣音"},
    # ── 男 · 中老年（6）──
    {"name": "龙涟霓蓉", "voice": "qwen-audio-3.0-tts-plus-longliannirong",     "gender": "男", "age": 42, "trait": "平稳陈述音"},
    {"name": "龙荷潇峰", "voice": "qwen-audio-3.0-tts-plus-longhexiaofeng",     "gender": "男", "age": 37, "trait": "硬朗阳刚音"},
    {"name": "龙翼暮凌", "voice": "qwen-audio-3.0-tts-plus-longyimuling",       "gender": "男", "age": 38, "trait": "沉稳有力音"},
    {"name": "龙岭芷杏", "voice": "qwen-audio-3.0-tts-plus-longlingzhixing",    "gender": "男", "age": 68, "trait": "浑厚沉稳音"},
    {"name": "龙朗涟玥", "voice": "qwen-audio-3.0-tts-plus-longlanglianyue",    "gender": "男", "age": 55, "trait": "浑厚沉稳音"},
    {"name": "龙朔辉梅", "voice": "qwen-audio-3.0-tts-plus-longshuohuimei",     "gender": "男", "age": 70, "trait": "轻松闲聊音"},
    # ── 女 · 儿童/少女（5）──
    {"name": "龙菊芙荷", "voice": "qwen-audio-3.0-tts-plus-longjufuhe",         "gender": "女", "age": 7,  "trait": "呆萌软糯音"},
    {"name": "龙兰雪珺", "voice": "qwen-audio-3.0-tts-plus-longlanxuejun",      "gender": "女", "age": 10, "trait": "温柔活泼音"},
    {"name": "龙竹泉望", "voice": "qwen-audio-3.0-tts-plus-longzhuquanwang",    "gender": "女", "age": 14, "trait": "撒娇甜蜜音"},
    {"name": "龙岚鹊焱", "voice": "qwen-audio-3.0-tts-plus-longlanqueyan",      "gender": "女", "age": 15, "trait": "动漫风格音"},
    {"name": "龙鹤澈蓉", "voice": "qwen-audio-3.0-tts-plus-longhecherong",      "gender": "女", "age": 16, "trait": "清亮明朗音"},
    # ── 女 · 青年（14）──
    {"name": "龙朗虹沫", "voice": "qwen-audio-3.0-tts-plus-longlanghongmo",     "gender": "女", "age": 25, "trait": "温柔亲和音"},
    {"name": "龙风月瑶", "voice": "qwen-audio-3.0-tts-plus-longfengyueyao",     "gender": "女", "age": 28, "trait": "直爽利落音"},
    {"name": "龙彤旭弦", "voice": "qwen-audio-3.0-tts-plus-longtongxuxian",     "gender": "女", "age": 24, "trait": "活泼灵动音"},
    {"name": "龙沫晖翎", "voice": "qwen-audio-3.0-tts-plus-longmohuiling",      "gender": "女", "age": 26, "trait": "御姐成熟音"},
    {"name": "龙萱澄蝶", "voice": "qwen-audio-3.0-tts-plus-longxuanchengdie",   "gender": "女", "age": 23, "trait": "强势霸气音"},
    {"name": "龙泉鹊凌", "voice": "qwen-audio-3.0-tts-plus-longquanqueling",    "gender": "女", "age": 23, "trait": "娇嗲甜腻音"},
    {"name": "龙羽湘芷", "voice": "qwen-audio-3.0-tts-plus-longyuxiangzhi",     "gender": "女", "age": 22, "trait": "柔弱楚楚音"},
    {"name": "龙凌瑾泉", "voice": "qwen-audio-3.0-tts-plus-longlingjinquan",    "gender": "女", "age": 24, "trait": "元气少女音"},
    {"name": "龙晴辉朗", "voice": "qwen-audio-3.0-tts-plus-longqinghuilang",    "gender": "女", "age": 24, "trait": "知性姐姐音"},
    {"name": "龙璨竹月", "voice": "qwen-audio-3.0-tts-plus-longcanzhuyue",      "gender": "女", "age": 26, "trait": "平实质朴音"},
    {"name": "龙漪羽露", "voice": "qwen-audio-3.0-tts-plus-longyiyulu",         "gender": "女", "age": 25, "trait": "阴狠毒辣音"},
    {"name": "龙岚露蓉", "voice": "qwen-audio-3.0-tts-plus-longlanlurong",      "gender": "女", "age": 25, "trait": "客观冷静音"},
    {"name": "龙煜枫沫", "voice": "qwen-audio-3.0-tts-plus-longyufengmo",       "gender": "女", "age": 22, "trait": "温柔坚韧音"},
    {"name": "龙雪霓翎", "voice": "qwen-audio-3.0-tts-plus-longxueniling",      "gender": "女", "age": 24, "trait": "电台质感音"},
    # ── 女 · 中老年（4）──
    {"name": "龙琳瑾樱", "voice": "qwen-audio-3.0-tts-plus-longlinjinying",     "gender": "女", "age": 38, "trait": "耐心温和音"},
    {"name": "龙芙晦晴", "voice": "qwen-audio-3.0-tts-plus-longfuhuiqing",      "gender": "女", "age": 38, "trait": "温柔贴心音"},
    {"name": "龙漪晴晦", "voice": "qwen-audio-3.0-tts-plus-longyiqinghui",      "gender": "女", "age": 60, "trait": "慈祥祖母音"},
    {"name": "龙岚星琳", "voice": "qwen-audio-3.0-tts-plus-longlanxinglin",     "gender": "女", "age": 42, "trait": "智慧祖母音"},
    # ── 旁白/解说（6）──
    {"name": "龙露柳澈", "voice": "qwen-audio-3.0-tts-plus-longluliuche",       "gender": "男", "age": 34, "trait": "标准播音音"},
    {"name": "龙柳旭澜", "voice": "qwen-audio-3.0-tts-plus-longliuxulan",       "gender": "女", "age": 25, "trait": "标准播音音"},
    {"name": "龙鸿芙岫", "voice": "qwen-audio-3.0-tts-plus-longhongfuxiu",      "gender": "女", "age": 42, "trait": "标准播音音"},
    {"name": "龙蓉桃涟", "voice": "qwen-audio-3.0-tts-plus-longrongtaolian",    "gender": "男", "age": 34, "trait": "冷静沉稳音·有声阅读"},
    {"name": "龙朗霁鸾", "voice": "qwen-audio-3.0-tts-plus-longlangjiluan",     "gender": "男", "age": 27, "trait": "沉稳大气音·有声阅读"},
    {"name": "龙羽瑶鸾", "voice": "qwen-audio-3.0-tts-plus-longyuyaoluan",      "gender": "女", "age": 25, "trait": "沉稳大气音·有声阅读"},
]


class Settings:
    """从 .env 读取配置（键名见 .env 注释）"""

    def __init__(self) -> None:
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.deepseek_max_tokens = _env_int("DEEPSEEK_MAX_TOKENS", 32768)
        # 结构化 JSON 任务默认关闭思考（思考会占用输出预算，见 2026-09 的截断事故）
        self.deepseek_thinking = _env_bool("DEEPSEEK_THINKING")

        self.fish_api_key = os.getenv("FISH_AUDIO_API_KEY", "")

        self.qwen_api_key = os.getenv("QWEN_API_KEY", "")
        self.qwen_vision_api_key = os.getenv("QWEN_VISION_API", "") or self.qwen_api_key
        self.qwen_base_url = os.getenv("QWEN_BASE_URL", "")
        self.qwen_tts_model = os.getenv("QWEN_TTS_MODEL", "qwen-audio-3.0-tts-plus")
        self.qwen_vision_base_url = os.getenv("QWEN_VISION_BASE_URL", "")
        self.qwen_vision_model = os.getenv("QWEN_VISION_MODEL", "qwen3.6-flash")
        # OCR 关闭思考（思考会拖慢每页识别数倍，见 2026-09 的 21秒/页事故）
        self.qwen_vision_thinking = _env_bool("QWEN_VISION_THINKING")

        # 演示模式：无 Key / 无 ffmpeg 即可跑通整条链路
        self.mock_mode = _env_bool("MOCK_MODE")

        # 通用 OpenAI 兼容 LLM（LLM_PROVIDER=openai 时使用）：
        # 可指向 DeepSeek、阿里云百炼、vLLM/Ollama 等任意兼容网关。
        self.llm_api_key = os.getenv("LLM_API_KEY", "")
        self.llm_base_url = os.getenv("LLM_BASE_URL", "")
        self.llm_model = os.getenv("LLM_MODEL") or os.getenv("LLM_MODEL_ID", "")
        self.llm_max_tokens = _env_int("LLM_MAX_TOKENS", 32768)
        # 额外请求体，JSON 对象。例：{"enable_thinking": false}
        self.llm_extra_body = _env_json("LLM_EXTRA_BODY")

        # 开关：qwen 系 Provider 未配置时自动降级 Mock
        self.tts_provider = os.getenv("TTS_PROVIDER", "qwen")
        self.vision_provider = os.getenv("VISION_PROVIDER", "qwen")
        self.llm_provider = os.getenv("LLM_PROVIDER", "deepseek")
        self.qwen_tts_enabled = _env_bool("QWEN_TTS_ENABLED")
        self.qwen_vision_enabled = _env_bool("QWEN_VISION_ENABLED")

        # 服务监听：本地默认只绑 127.0.0.1；Docker 内用 HOST=0.0.0.0
        self.server_host = os.getenv("HOST", "127.0.0.1")
        # PORT 是容器约定变量，SERVER_PORT 为向后兼容
        self.server_port = _env_int("PORT", _env_int("SERVER_PORT", 8080))

        # 上传限制（防止误传/恶意请求耗尽内存与磁盘）
        self.max_upload_mb = _env_int("MAX_UPLOAD_MB", 256)
        self.max_upload_bytes = self.max_upload_mb * 1024 * 1024
        self.max_upload_files = _env_int("MAX_UPLOAD_FILES", 500)

        # 可选：显式指定 ffmpeg；设为 off/none 可强制走纯 WAV 路径
        self.ffmpeg_bin = os.getenv("FFMPEG_BIN", "")


settings = Settings()