# 调整方案 — 接入千问语音模型 + 项目求职级完善计划

> 配套文档：[ARCHITECTURE.md](./ARCHITECTURE.md)（现状架构基线）
> 说明：千问三个语音模型的**接口细节（端点、参数、音色清单等）以【待填】占位**，集中在 §3「接口信息占位区」，由你自行填写；其余改造设计不依赖这些细节。

---

## 1. 调整目标

1. **TTS 迁移**：Fish Audio → 千问 `qwen-audio-3.0-tts-plus`（降本、中文效果好、接口稳定），Fish Audio 保留为备选 Provider，一键切换。
2. **新增语音识别能力**：接入 `qwen-audio-3.0-asr-flash`，做台词自动提取与配音质检。
3. **新增实时语音交互**：接入 `qwen-audio-3.0-realtime-plus`，做「与漫画角色实时对话」的亮点 Demo（求职演示最出彩的功能）。
4. **修复功能断裂**：让 emotion/speed/pitch/emphasis/pause 等参数真正作用于音频产出。
5. **工程化包装**：Provider 抽象层、配置管理、git 仓库、README、单元测试、错误重试，达到求职项目水准。

---

## 2. 千问三个语音模型在项目中的定位

| 模型 | 能力 | 在本项目中的位置 | 优先级 |
|---|---|---|---|
| `qwen-audio-3.0-tts-plus` | 语音合成 | **替换 Fish Audio**，负责步骤④逐句合成；需确认是否支持音色复刻（决定克隆功能是否一并迁移） | P0（核心） |
| `qwen-audio-3.0-asr-flash` | 语音识别 | **新增两个用途**：① 输入侧——漫改动画/番剧片段音频 → 自动转出台词草稿，加速脚本制作；② 质检侧——TTS 产物转录回文字，与原文比对，检查错读/漏字 | P1 |
| `qwen-audio-3.0-realtime-plus` | 实时语音对话 | **新增功能**：角色扮演对话 Demo——选中角色（音色+人设 prompt）后语音实时聊天，复刻「和纸片人对上话」体验 | P1 |

现有 DeepSeek 文本 LLM 的职责（脚本提取、音色规划）不变；如需统一供应商，可后续将 `llm_client.py` 换成千问文本模型（OpenAI 兼容协议下几乎零成本），此项列为 P2 可选项。

---

## 3. 千问接口信息占位区（← 你来填）

> 填写后可直接作为开发规格。不确定的项填「暂不确定」，不要留空。

### 3.1 qwen-audio-3.0-tts-plus（语音合成）

| 项目 | 填写内容 |
|---|---|
| 接入方式（HTTP REST / WebSocket / SDK） | 【待填】 |
| Base URL / 端点路径 | 【待填】 |
| 认证方式（API-Key 位置、请求头格式） | 【待填】 |
| 是否 OpenAI `/audio/speech` 兼容模式（可直接复用 openai SDK） | 【待填】 |
| 关键请求参数（文本、音色、语速、情感/语气、输出格式） | 【待填】 |
| 可用音色清单（名称 → 适合替换哪些 voice_tag） | 【待填】 |
| 是否支持**音色复刻/自定义音色**（决定 clone 功能去留） | 【待填】 |
| 单次请求文本长度上限、每秒/分钟限流 | 【待填】 |
| 计费方式与免费额度 | 【待填】 |
| 官方文档链接 | 【待填】 |

### 3.2 qwen-audio-3.0-asr-flash（语音识别）

| 项目 | 填写内容 |
|---|---|
| 接入方式（HTTP / WebSocket / 文件直传） | 【待填】 |
| Base URL / 端点路径 | 【待填】 |
| 认证方式 | 【待填】 |
| 是否 OpenAI `/audio/transcriptions` 兼容模式 | 【待填】 |
| 关键请求参数（音频格式、采样率、语言、是否返回时间戳/说话人分离） | 【待填】 |
| 是否返回**词级时间戳**（决定能否做字幕对齐/视频版） | 【待填】 |
| 音频时长与文件大小上限、限流 | 【待填】 |
| 计费方式与免费额度 | 【待填】 |
| 官方文档链接 | 【待填】 |

### 3.3 qwen-audio-3.0-realtime-plus（实时语音对话）

| 项目 | 填写内容 |
|---|---|
| 接入方式与握手指令（WebSocket URL / SDK 类名） | 【待填】 |
| 认证方式 | 【待填】 |
| 消息协议格式（文本事件 / 二进制音频帧 / 中断机制） | 【待填】 |
| 是否内置 TTS（返回音频流）还是仅 STT+LLM，需另接 TTS | 【待填】 |
| 音色是否可指定（能否直接指定与 TTS 相同的角色音色） | 【待填】 |
| 是否支持 system prompt 设定角色人设、是否支持 function calling | 【待填】 |
| 单连接时长限制、并发连接数、限流 | 【待填】 |
| 计费方式与免费额度 | 【待填】 |
| 官方文档链接 | 【待填】 |

### 3.4 其他待填项

- Qwen TTS 音色与现有 10 个 `voice_tag` 的**映射表**（例如 `female_mature_sexy → 音色名 xxx`）——直接按 §4.3 的 `QWEN_VOICE_MAP` 格式列出即可。
- 千问 API 的 Key 名称与获取路径（写入 `.env` 用）。
- 若使用官方 SDK：SDK 包名与 pip 安装名（否则用 requests/openai SDK 手写客户端）。

---

## 4. 目标架构设计

### 4.1 Provider 抽象层（本次改造的核心工程决策）

把「用什么服务」与「怎么配音」解耦。访谈时可以讲的点：**策略模式 + 依赖注入，供应商可插拔、可 A/B 对比、可单测 Mock**。

```
comic_dubbing_agent/
├── config.py                       # 新增：集中配置（读 .env，pydantic-settings）
├── providers/                      # 新增：服务供应商抽象层
│   ├── __init__.py                 #   get_tts() / get_asr() / get_realtime() 工厂
│   ├── base.py                     #   BaseLLM / BaseTTS / BaseASR / BaseRealtime 抽象基类
│   ├── deepseek_provider.py        #   LLM：DeepSeek（chat / chat_json 逻辑迁移自 llm_client.py）
│   ├── qwen_provider.py            #   千问：TTS + ASR + Realtime（← 待填接口信息）
│   └── fish_provider.py            #   TTS：Fish Audio（保留为备选，含克隆）
├── manga_dubber.py                 # 改造：只依赖抽象基类，不 import 具体供应商
├── server.py                       # 改造：新增 asr / realtime 相关端点
├── client.py                       # 改造：Tab 增加试听、ASR 提取、角色对话入口
├── prompts.py                      # 不变
└── （其余、tests/、README.md、.gitignore 等见 P2）
```

### 4.2 抽象基类骨架（`providers/base.py`）

```python
class BaseTTS(ABC):
    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice_id: str,
        speed: float = 1.0,
        emotion: str = "",
        **params,                      # 供应商特有参数透传
    ) -> bytes: ...

class BaseASR(ABC):
    @abstractmethod
    def transcribe(self, audio_bytes: bytes, fmt: str = "mp3") -> dict:
        """返回 {"text": str, "segments": [{start_ms, end_ms, text}]（无时间戳则 segments 为空）}"""

class BaseLLM(ABC):
    @abstractmethod
    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str: ...
    @abstractmethod
    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict: ...

class BaseRealtime(ABC):
    @abstractmethod
    async def run_session(self, *, system_prompt: str, voice_id: str,
                          on_user_text, on_assistant_text, on_assistant_audio) -> None: ...
```

### 4.3 配置化切换（`config.py` + `.env`）

```env
# 供应商选择开关
TTS_PROVIDER=qwen            # qwen | fish
ASR_PROVIDER=qwen            # qwen | (none)
REALTIME_PROVIDER=qwen       # qwen | (none)
LLM_PROVIDER=deepseek        # deepseek | qwen | (none)

# 千问配置（3.1–3.3 填写完成后落位）
QWEN_API_KEY=【待填】
QWEN_BASE_URL=【待填】
QWEN_TTS_MODEL=qwen-audio-3.0-tts-plus
QWEN_ASR_MODEL=qwen-audio-3.0-asr-flash
QWEN_REALTIME_MODEL=qwen-audio-3.0-realtime-plus
```

音色映射从单一 `TAG_TO_VOICE_ID` 拆成**按供应商隔离**的两份映射（`voice_tag` 枚举保持不变，prompt 层零改动）：

```python
# config.py
QWEN_VOICE_MAP = {            # ← 由你按 3.4 填写
    "male_youth_hot":    "【待填】",
    "male_youth_gentle": "【待填】",
    # ... 共 10 个 voice_tag
}
FISH_VOICE_MAP = TAG_TO_VOICE_ID   # 原映射原样保留
```

### 4.4 被丢弃参数的落地设计

现状 `synthesize_all()` 只传 text + reference_id。改造后按「供应商支持程度」三级落地：

1. **供应商原生支持**（如千问 TTS 若有语速/语气参数）：直接透传 `speed` / `emotion`（此条依赖 §3.1 填写结果）；
2. **文本层表达**：`emphasis` 重音词 → 供应商支持 SSML 则包裹强调标签（待填项确认）；`text` 中「｜」「···」等符号 → 加清洗函数统一转标点/停顿；
3. **音频层后处理（供应商无关，必做）**：引入 `pydub`（纯 ffmpeg 调用，无需模型）——
   - `pause_after_ms` → 句尾插入对应时长静音；
   - 按 scene 把多句音频**拼接成一集**，输出 `output/episode_01.mp3`；
   - 音量归一化（可选 BGM 混音）。

---

## 5. 分阶段实施计划

### P0 — 核心迁移：千问 TTS 替换 Fish Audio（预计 2~3 天）

| # | 任务 | 改动文件 | 验收标准 |
|---|---|---|---|
| 0.1 | 填充 §3.1 占位信息 | 本文档 | — |
| 0.2 | 建 Provider 抽象层 | 新增 `providers/base.py`、`providers/__init__.py` | 四个抽象基类 + 工厂函数 |
| 0.3 | 迁移 LLM 客户端 | 新增 `providers/deepseek_provider.py`，`llm_client.py` 转为兼容 shim 或删除 | `test_dub.py` 跑通不报错 |
| 0.4 | 迁移 Fish 客户端 | 新增 `providers/fish_provider.py` | `/api/voices/search` 等接口行为不变 |
| 0.5 | 实现千问 TTS Provider | 新增 `providers/qwen_provider.py` | 用同一句测试台词分别跑 Fish / Qwen，音频可播放，抽秒数对比记录语速差 |
| 0.6 | 配置化接入 | 新增 `config.py`，`manga_dubber.py` 改为从工厂取 Provider | 改 `.env` 的 `TTS_PROVIDER` 即可整体切换，代码零改动 |
| 0.7 | 音色映射 | `QWEN_VOICE_MAP` 按 3.4 填齐 10 个标签 | 25 句测试台词在千问下全部合成成功 |
| 0.8 | 修依赖清单 | `requirements-manga.txt` 补 `gradio`、`pydub`、`websockets`（如需）等 | `pip install -r` 一次装齐 |
| 0.9 | 同步测试入口 | `test_dub.py` 增加 `--provider` 参数 | 可一键对比双供应商输出 |

> P0 完成态：千问 TTS 成为默认引擎，Fish Audio 作为备选随时可切回，两条链路都跑通 25 句测试集。

### P1 — 新能力：ASR 质检 + 实时角色对话（预计 3~5 天）

| # | 任务 | 改动文件 | 验收标准 |
|---|---|---|---|
| 1.1 | 填充 §3.2 / §3.3 占位信息 | 本文档 | — |
| 1.2 | 新增 `/api/asr/transcribe` | `server.py` + `qwen_provider.py` | 上传音频返回识别文本 |
| 1.3 | 配音质检管线 | 新增 `pipeline/quality_check.py` | TTS 产物 → ASR → 与原文比对（编辑距离/漏字率），低置信度台词在 UI 标红 |
| 1.4 | Gradio 增强 | `client.py` | Tab①增加「上传音频提取台词草稿」；Tab②每句台词旁加▶试听按钮；新增质检结果展示 |
| 1.5 | 角色实时对话 Demo | `server.py`（WS 端点）+ `qwen_provider.py`（Realtime 实现）+ `client.py`（麦克风组件） | 「选角色 → 语音聊天」闭环可用，可录制演示视频 |
| 1.6 | 角色人设库 | `prompts.py` 复用 `characters[].description` 组装 realtime system prompt | 对话中角色不跑偏 |
| 1.7 | 音频后处理 | `providers/../` 新增 `pipeline/post_process.py` | 停顿插入（pause_after_ms 生效）、按场景拼接、`episode_01.mp3` 导出 |

> P1 完成态：管线更完整（音频→台词、台词→音频、音频→质检），且拥有「实时角色对话」这个求职演示王牌功能。

### P2 — 工程化包装与收尾（预计 2~3 天）

| # | 任务 | 说明 |
|---|---|---|
| 2.1 | `git init` + `.gitignore` | **必须**：`.env`、`output/`、`__pycache__/`、`*.mp3`、`Vol_01_pages/`（如版权存疑）加入忽略；`.env` 内密钥已在本机明文存在过，建议在千问/DeepSeek/Fish 控制台**轮换全部密钥**后再考虑推公开仓库 |
| 2.2 | `README.md` | 中文；含 mermaid 架构图、功能截图/GIF（可用 P1 的演示录制）、快速开始、技术亮点 3 点（Provider 抽象 / 参数落地 / 实时对话） |
| 2.3 | 单元测试 `tests/` | pytest：JSON 容错解析、内心 OS 合并 `get_body`、音色分配逻辑、prompt 模板输出格式；Provider 全部 Mock 掉，`pip install pytest` 一行跑绿 |
| 2.4 | 健壮性 | TTS 逐句重试（指数退避）、失败句留痕、`state.json` 断点续传（重跑复用已生成音频） |
| 2.5 | 清理死代码 | 删除 `server.py` 未用的 `DubRequest/DubResponse`、`.env` 未用项、`client_stdout/stderr.txt` |
| 2.6 | 日志 | logging 分级输出（当前全是 print） |
| 2.7 | （可选）ans 图片→脚本闭环 | 若开通千问 VL 类模型（注：属于视觉模型，不在你说的三个之内），可用 `Vol_01_pages` 做漫画页分格识别+OCR；未开通则维持「外部工具出 markdown」并在 README 写明前置步骤 |
| 2.8 | （可选）LLM 供应商统一 | `deepseek_provider` 之外加 `qwen_provider` 的文本 LLM 实现，`LLM_PROVIDER=qwen` 一键切换 |

---

## 6. 求职展示建议

- **README 一屏讲清**：做什么 → 架构图 → 30 秒 Demo GIF（放「上传漫画脚本 → 25 句配音生成」和「角色实时对话」两段）。
- **面试话术锚点**（应对「你的项目亮点是什么」）：
  1. 设计了 Provider 抽象层，TTS 供应商（Fish Audio / 千问）可配置热切换，模型迭代不影响业务代码；
  2. 打通了「语义理解 → 音频表达」的完整链路，LLM 提取的情绪/语速/停顿参数真正落地到音频（停顿按毫秒插入、按场景拼接成集）；
  3. 用 ASR 做 TTS 的**自动质检闭环**（合成 → 转写 → 比对），体现了对 AI 产品输出质量负责的意识；
  4. 实时语音角色对话，展示了多模态 Agent 的集成能力。
- **演示环境**：面试前本地把 `output/` 清理、重新跑一遍完整链路并录屏，保证演示可复现。

---

## 7. 风险与注意事项

1. **接口细节未定**：全部集中在 §3 占位区，填完后 P0 才能动工；千问 3.0 系列若有 OpenAI 兼容模式，则 P0 开发量可再减半（现有代码已基于 openai SDK）。
2. **密钥安全（重要）**：`ARCHITECTURE.md` 与本文档均未写入任何密钥，但 `.env` 内的真实 Key 此前随对话出现过。**git init 前务必轮换 DeepSeek / Fish Audio 密钥**，并把 `.env` 加入 `.gitignore`。
3. **音色映射变更**：千问音色库与 Fish Audio 的 10 标签不一定一一对应，如某类音色缺失，可缩小 `VOICE_PLAN` 提示词的枚举范围，或允许 LLM 在千问音色清单内自由推荐（需改 prompt，工作量小）。
4. **音量/语速差异**：两供应商同文本合成时长可能不同，对比测试后把差异记录进 README（体现严谨性）。
5. **Realtime 网络长连接**：WebSocket 断连重连、麦克风授权失败、Gradio 组件兼容性需要实测处理。
6. **Flask/FastAPI 阻塞**：长耗时 TTS 若并发上升，需将同步合成丢进线程池/异步队列（P2 健壮性一并处理）。
7. **版权**：测试用漫画页面（`Vol_01_pages/`）与 `Peqi.mp3` 如为网络资源，公开仓库前确认可展示范围，Demo 建议换自绘或版权无碍的内容。