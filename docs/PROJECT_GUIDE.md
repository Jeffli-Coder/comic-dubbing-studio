# 漫画配音工坊 · 项目全解（PROJECT_GUIDE）

> 本文档面向「要完全掌握这个项目的人」（含设计答辩场景），逐文件讲清：**做什么、怎么实现、为什么这么设计、优缺点**。
> 注：[archive/ARCHITECTURE-v1.md](archive/ARCHITECTURE-v1.md) 记录的是 v1（Fish Audio + Gradio 时代）的旧架构；当前 v2 架构见 [ARCHITECTURE.md](ARCHITECTURE.md)，本文档描述 v2 全部实现。

---

## 1. 项目是什么

**一句话**：一个本地运行的「漫画翻页听书」网页应用——上传漫画页图片或 PDF，系统自动 OCR 识别台词、LLM 整理剧本并选角、多音色 TTS 逐句配音，产出可翻页收听、逐句高亮、随时换音的沉浸式听书体验。

**全景数据流**：

```
上传图片/PDF
    │
    ▼
[① OCR] 千问视觉模型逐页识别台词与说话人        ── pages_raw/ 缓存
    │        (单页失败自动跳过，页码不丢)
    ▼
[② 合并] DeepSeek 整理标题/角色表/逐句演出参数   （情绪、语速、停顿、重音）
    │        (本地修复层保证 LLM 输出可信)
    ▼
[③ 选音] DeepSeek 从 50 个千问音色中为角色选角
    │
    ▼
[④ 合成] 千问 TTS 逐句合成  ──▶ lines/ 逐句缓存  ──▶ [⑤ 拼接] ffmpeg 拼页+插静音+时间戳
    │        (逐页推进：每页完成立即可播放)              audio/ 页面音频 + timings/ 时间戳
    ▼
[阅读] 浏览器 SPA：翻页动画 + 音频联动逐句高亮 + 播完自动翻页 + 音色面板
```

**关键数据**：50 个音色（从平台 597 个中精选）· 13 个 REST 端点 · 3 类 AI 能力抽象 · 6 态流水线状态机 · Python ~1600 行 + 前端 ~1000 行。

---

## 2. 技术栈与外部依赖

| 层 | 技术 | 用途 |
|---|---|---|
| Web 框架 | FastAPI + Uvicorn | REST API + 静态托管 |
| 文本 LLM | DeepSeek（OpenAI 兼容协议） | 剧本合并整理、角色选音 |
| 视觉 OCR | 千问视觉模型（`qwen3.6-flash`，OpenAI 兼容模式） | 漫画页台词识别 |
| 语音合成 | 千问 TTS（`qwen-audio-3.0-tts-plus`，DashScope WebSocket SDK） | 逐句配音 |
| 音频工程 | ffmpeg（系统安装 或 pip `imageio-ffmpeg` 自带二进制） | 解码/拼接/插静音/编码 mp3 |
| PDF 处理 | pypdfium2（PDFium，Apache-2.0/BSD-3） | PDF 逐页渲染为 JPG |
| 前端 | 原生 JavaScript + CSS 3D + HTML5 Audio | 零框架 SPA |
| 并发 | Python threading + 内存注册表 | 后台任务与进度上报 |

**设计原则**：所有外部服务都通过 Provider 抽象层接入，没有一行业务代码直接依赖具体厂商 SDK。

---

## 3. 目录结构与文件地图

```
comic_dubbing_agent/
├── config.py                 # 集中配置：.env 读取 + 50 音色清单（全局唯一数据源）
├── server.py                 # 应用装配入口（路由 + 静态托管 + 启动）
├── prompts.py                # 三组 LLM 提示词模板
├── requirements.txt          # 依赖清单
├── .env                      # 密钥与开关（不入 git）
│
├── providers/                # ★ 外部服务抽象层
│   ├── base.py               #   抽象基类 + 数据契约（TTSResult/PageLine/PageScript）
│   ├── __init__.py           #   工厂函数（含自动降级逻辑）+ ffmpeg 探测
│   ├── mock_provider.py      #   三个 Mock 实现（零依赖可运行仿真）
│   ├── deepseek_provider.py  #   DeepSeek LLM（OpenAI 协议 + 三层 JSON 容错）
│   ├── qwen_tts_provider.py  #   千问 TTS（WebSocket 合成）
│   ├── qwen_vision_provider.py # 千问视觉 OCR（图片 base64 → JSON 台词）
│   ├── image_mime.py         #   图片/PDF 魔数嗅探（校验 + 正确 MIME）
│   └── fish_tts_provider.py  #   Fish Audio 备选（含克隆能力留痕）
│
├── pipeline/                 # ★ 核心流水线
│   ├── store.py              #   存储布局 + 原子读写（tmp + os.replace）
│   ├── stages.py             #   阶段纯函数：合并、修复、选音、内心OS合并
│   ├── orchestrator.py       #   BookPipeline 状态机（串起全流程 + 断点续跑）
│   ├── tasks.py              #   后台任务注册表（线程 + 书籍级锁）
│   ├── audio.py              #   AudioMixer：ffmpeg 管子线 + 时间戳累积 + 降级
│   └── pdf_import.py         #   PDF 逐页转图（pypdfium2，自适应降采样）
│
├── api/
│   └── routes.py             # 13 个 REST 端点（全部业务接口）
│
├── static/                   # ★ 前端 SPA（零框架）
│   ├── index.html            #   单页骨架（顶栏/视图容器/音色弹窗/提示条）
│   ├── css/reader.css        #   深色主题 + 3D 翻页动画 + 全部组件样式
│   └── js/
│       ├── app.js            #   工具函数 + hash 路由 + 健康自检
│       ├── upload.js         #   上传页 + 书架页
│       ├── reader.js         #   阅读页（翻页/高亮/自动翻页/轮询）——前端核心
│       └── voices.js         #   音色面板（50 音色分组下拉 + 换音提交）
│
├── data/books/{book_id}/     # 运行时数据（每本书一个目录，见 §4；不入 git）
├── tests/                    # 离线测试（Mock provider，无外网）
├── docs/                     # 架构 / 配置 / 部署 / 项目全解
├── Dockerfile / compose      # 容器部署
├── legacy/                   # v1 退役文件（本地保留，不入 git）
└── Vol_01_pages/             # 本地测试素材（不入 git）
```

---

## 4. 核心数据模型（三份 JSON 撑起整个系统）

### 4.1 `script.json` — 按页脚本（业务核心数据）

```json
{
  "book_id": "9e17621cd953",
  "title": "示例漫画（虚构）",
  "characters": [{"name": "苏晴", "type": "配角", "description": "书店店员"}],
  "voice_assignments": {"苏晴": "qwen-audio-3.0-tts-plus-longmohuiling"},
  "pages": [{
    "page_num": 1,
    "image": "pages/001.jpg",
    "lines": [{
      "line_id": "p001_01",          // 全局唯一，格式 p{页码}_{序号}（纯 ASCII）
      "character": "苏晴",
      "text": "这是你的找零，请拿好。",
      "type": "dialogue",            // dialogue|monologue|narration|inner_thought
      "emotion": "日常",              // 12 种情绪，可带转折
      "speed": 1.0, "pitch": "正常",
      "emphasis": ["找零"], "pause_after_ms": 300
    }],
    "page_notes": "OCR 备注"
  }]
}
```

**为什么这样设计**：
- **pages 取代了 v1 的 scenes**——播放/高亮/翻页/换音色的最小单元都是「页」，用单一结构避免双轨维护；
- **line_id 用纯 ASCII**——修掉了 v1 用中文角色名做文件名的 Windows 兼容坑（非法字符、长文件名）；
- **演出参数随行**——LLM 提取的 `emotion/speed/pitch/emphasis/pause_after_ms` 一路传到 TTS 与拼接层，不是摆设（v1 的教训：提取了却全丢弃）。

### 4.2 `meta.json` — 状态与进度（轮询专用）

```json
{
  "status": "tts",            // queued|ocr|voice_pick|tts|concat|ready|error|resynth
  "progress": {"stage": "tts", "done": 120, "total": 500, "page_done": 60, "page_total": 248},
  "auto_turn": true,
  "tts_provider": "qwen",     // 记录用过的 TTS 供应商（换供应商时作缓存守卫，见 §6.2）
  "error": null,              // 失败原因
  "ocr_failed_pages": [60],   // 被内容审核等拦截、跳过的页码
  "last_voice_swap": null
}
```

### 4.3 `timings/page_NNN.json` — 行级时间戳（高亮的数据基础）

```json
{
  "page_num": 1, "audio_file": "audio/page_001.mp3", "mode": "single",
  "segments": [
    {"line_id": "p001_01", "start_ms": 0, "end_ms": 1417, "character": "苏晴", "text": "..."},
    {"line_id": "p001_02", "start_ms": 1717, "end_ms": 3134, "character": "未知", "text": "..."}
  ]
}
```
时间戳**相对本页音频**（0 起算）；句间静音体现为前句 `end_ms` 与后句 `start_ms` 的差值（上例 1717-1417=300ms = 该句的 pause_after_ms）。

### 4.4 存储布局

```
data/books/{book_id}/
├── meta.json          # 状态/进度
├── pages/001.jpg…     # 上传原图（上传时按文件名排序、PDF 拆页后统一编号）
├── pages_raw/p001.json # ★ OCR 原始结果缓存（断点续跑的第一道缓存）
├── script.json        # 按页脚本
├── lines/p001_01.mp3… # ★ 逐句音频缓存（第二道缓存，换音色时复用未变句）
├── audio/page_001.mp3 # 每页拼接后的完整音频
└── timings/page_001.json # 每页时间戳
```

---

## 5. 逐模块深潜

### 5.1 `config.py` — 集中配置

**做什么**：读 `.env`（`dotenv`）→ `Settings` 类暴露所有配置项；**同时持有 `QWEN_VOICES`（50 音色清单）**。

**为什么这么设计**：
- **配置集中一处**：v1 是每个模块各自 `os.getenv`，换配置源要改 N 个文件；现在全局只有 `config.py` 知道 `.env` 的存在；
- **50 音色清单放这里**：它是「LLM 选音提示词」与「网页下拉框」的**唯一数据源**——两处消费同一份数据，永远一致；扩音色只需追加一条 dict，零代码改动；
- 每个音色条目含 `name/gender/age/trait/voice`，`voice` 即 API 调用参数（如 `qwen-audio-3.0-tts-plus-longmohuiling`）。

**优缺点**：优点是简单直观、无魔法；缺点是 `Settings` 在 `import` 时实例化（配置改动需重启进程）——本地单用户场景完全可接受。

### 5.2 `providers/` — 外部服务抽象层（本项目的架构核心）

**做什么**：把「用什么服务」与「怎么用服务」解耦。三类能力各有抽象基类：

```python
BaseTTS.synthesize(text, voice, *, speed, emotion, pitch, emphasis, fmt) -> TTSResult
BaseVision.analyze_page(image_bytes, *, page_num, prev_context) -> PageScript
BaseLLM.chat_json(system_prompt, user_prompt, temperature) -> dict
```

上层（pipeline）只面向抽象编程；工厂 `get_tts()/get_vision()/get_llm()` 按 `.env` 开关实例化具体实现。

**`base.py` 中的数据类型**：
- `TTSResult(audio_bytes, fmt, duration_ms)`——TTS 返回值（时长可缺省，由音频层实测）；
- `PageLine`——单句台词结构（含 `bbox` 预留字段，未来可在图上标台词位置）；
- `PageScript`——单页识别结果。

**工厂的自动降级（`__init__.py`）**：
```python
def get_tts():
    if 配置了 qwen 且 开关打开:
        try: return QwenTTS(...)
        except Exception as e: DEGRADED["tts"].append(f"QwenTTS 不可用: {e}")
    return MockTTS()   # 任何一步不可用 → 落到 Mock，且记录原因
```
降级**不隐藏问题**：原因写进模块级 `DEGRADED` 字典，由 `GET /api/health` 暴露。

**`mock_provider.py` — 不是占位符，是可运行的仿真**：
- `MockTTS`：生成**时长随字数与语速变化的静音 WAV**（纯 stdlib `wave`）——让翻页、时间戳、高亮逻辑在没有 TTS API 时就能端到端验证；
- `MockVision`：按页码确定性生成演示台词（角色池轮换、奇数页插入内心OS），专门用于测试「内心OS合并」等逻辑；
- `MockLLM`：识别 system prompt 里的 `[TASK:MERGE]` / `[TASK:VOICE_PICK]` 标记，解析 stage 传入的结构化 JSON，做**确定性处理**（合并页面、按名字哈希选音）——与真实 LLM 输出同构。

**`deepseek_provider.py`**：OpenAI SDK 指向 DeepSeek。核心是 `chat_json` 的**三层 JSON 容错**：直接解析 → 剥 ```json 代码围栏 → 剥 `{"output": "..."}` 嵌套包装；全失败才抛错（附原文 500 字便于排查）。LLM 输出格式不稳定的现实问题在这里兜底。

**`qwen_tts_provider.py`**：DashScope `SpeechSynthesizer`（WebSocket 协议）。
- `normalize_ws_url()`：接受两种形式的地址——`wss://host/api-ws/v1/inference` 原样使用；`https://host/compatible-mode/v1`（REST 形式）**自动推导出同主机的 WebSocket 地址**。这是踩坑后的防御：用户配了 REST 地址但 TTS 走 WS 协议，自动转换避免配置错误；
- 每次 `call()` 新建 synthesizer（一次 WebSocket 握手）——已知优化点：SDK 支持复用时可缓存实例提速。

**`qwen_vision_provider.py`**：OpenAI 兼容 `chat.completions` + 图片 base64（`data:image/jpeg;base64,...`）。关键点在 **`VISION_SYSTEM` 提示词**：明确「只提取对白/独白/旁白气泡；忽略封面标题、卷号、目录、版权、拟声词；无台词页返回空数组」——这是封面/目录不配音的实现处。另把前页角色清单通过 `prev_context` 注入 user 消息，引导跨页命名一致。返回 JSON 再经本地解析成 `PageLine`。

**`fish_tts_provider.py`**：备选供应商（`TTS_PROVIDER=fish` 可切），实现同一 `BaseTTS` 接口；`clone_voice/wait_for_clone` 声音克隆方法作为能力留痕保留，主流程不接（未来升级用）。

**优缺点**：
- ✅ 换供应商零侵入（改一个 `.env` 值）；缺 key 自动降级让开发和演示不被外部依赖卡死；Mock 让单测不需要网络；
- ⚠️ 代价是抽象层代码量（~7 个文件）和一层间接调用——当供应商只有一个且永不更换时是过度设计；本项目面向「模型快速迭代」的现实（v1 用 Fish，v2 迁千问），收益远大于成本。

### 5.3 `pipeline/store.py` — 存储层

**做什么**：book 目录布局的定义者与所有磁盘读写入口。
- `write_json_atomic()`：写临时文件 + `os.replace()` 原子替换——**防止前端/其他线程读到写了一半的 JSON**（进度轮询 1.5 秒一次，普通写会撞上半截文件导致解析失败）；
- `write_meta()` 是合并写（read-modify-write 整个 meta），进度更新全部走它；
- `iter_page_images()` 按文件名排序返回页面列表——**翻页顺序的唯一依据**（上传时已编号为 `001.jpg` 起的连续序号）。

### 5.4 `pipeline/stages.py` — 阶段纯函数

**做什么**：不碰磁盘的纯逻辑（可单测），核心三个：

1. **`run_merge(llm, page_scripts)`**——调 LLM 合并 + **本地修复层 `_repair_page`**：
   - LLM 返回的行数/文本不可全信：如果某页 LLM 返回的行数与原始识别不一致 → 整页丢弃 LLM 结果，回退到原始识别行；
   - 逐句修复策略：`character`/`text`/顺序**以视觉识别原文为准**，LLM 只提供演出参数（emotion/speed/…）。这是「LLM 幻觉」的工程化防御——**内容保真优先于润色**；
   - `speed` 经 `_safe_float` 钳制到 0.6~2.0；
   - 角色表兜底：LLM 没给就从台词里聚合。
2. **`run_voice_pick(llm, title, characters)`**——LLM 从 50 音色选角；对结果做**白名单校验**（`voice` 必须存在于 `QWEN_VOICES`），任何一个角色没拿到合法值就用确定性哈希兜底——保证「每个角色必有音色」的不变量。
3. **`body_name(name)`**——「林默（内心）」→「林默」的正则归并。内心OS与本体重名同音色，从选音到换音色到重合成，全链路以「本体名」为 key。

### 5.5 `pipeline/orchestrator.py` — BookPipeline 状态机（业务中枢）

**做什么**：`run()` 串起六阶段；`resynth_voice()` 做换音色。全部磁盘动作走 store，全部外部调用走 Provider 抽象。

**`run()` 实现要点**（按代码顺序）：
1. **供应商切换守卫**：meta 里 `tts_provider` 与当前不一致 → 清空 `lines/audio/timings` 三个目录重合成（防止 Mock 的静音缓存被当成真声音复用）；
2. **OCR 阶段**：逐页先查 `pages_raw/pNNN.json` 缓存（**命中即跳过 vision 调用——重跑不重复花钱**）；未命中的调视觉模型；**单页异常**（内容审核/网络）→ 不抛错：记为空台词页（`ocr_failed: true` 标记 + 页码照常入册），继续下一页；失败页码收集进 `meta.ocr_failed_pages`；
3. **合并 + 选音**：调 stages 的两个函数，两次写入 `script.json`；
4. **逐页推进（4+5 合并）**：对每一页——先合成该页所有台词（逐句查 `lines/` 缓存），**合成完立刻拼接该页**并写 timings → **页面渐进可播**（248 页的书不用等全部跑完，第 1 页几分钟内就能听）；
5. 全程 `_bump()` 更新 meta 进度；任何未捕获异常 → 写 `status=error` + 错误信息（前端据此显示重试按钮），可重跑续传。

**`resynth_voice(character, new_voice)` 的性价比设计**：
- 定位该角色全部 line_id（跨页）；
- **只重合成这些句**（其他角色的 lines/ 缓存原样复用）→ 覆盖逐句文件；
- 重拼**受影响的页**（从 lines/ 读回全部句，未变句零成本）；
- 更新 `script.json` 的 voice_assignments + meta 的 `last_voice_swap`。
成本从「全书重跑」降到「N 句 TTS + M 页重拼」，免费额度限流场景下的关键优化。

**`_synthesize_line()`**：先查缓存（任意扩展名 glob）；未命中调 TTS 带**三次指数退避重试**；新格式文件写入并清理旧扩展名文件。

### 5.6 `pipeline/tasks.py` — 后台任务注册表

**做什么**：`TaskRegistry.submit(book_id, target, *args)` 起 daemon 线程执行；同 book 的写操作经 `lock(book_id)` 串行化；`is_running()`/`status()` 供 API 查询。

**为什么不用 Celery**（设计问答）：
- 本地单用户、顺序处理，无水平扩展需求；
- Celery 强制引入 broker（Redis/RabbitMQ）——Windows 上多一个常驻进程的安装与排障负担；
- 任务参数含 MB 级图片 bytes，跨进程序列化/反序列化开销大；
- 进度上报用「内存标志 + meta.json 轮询」约 50 行搞定，不需要 result backend。

### 5.7 `pipeline/audio.py` — AudioMixer（音频工程层）

**做什么**：把逐句音频拼成整页音频并产出精确时间戳。三层择优：

| 条件 | 路径 | 输出 |
|---|---|---|
| 有 ffmpeg | 全部输入解码为 **PCM（24kHz/单声道/16bit）** → 字节拼接 + 零字节插静音 → 编码 mp3 | `single` 模式，mp3 |
| 无 ffmpeg 且全 WAV | 纯 stdlib `wave` 拼接 | `single` 模式，wav |
| 其余 | 不拼接 | `sequence` 模式（前端逐行播） |

**PCM 规范化的巧妙之处**（v2 的关键重构）：
- 所有格式（mp3/wav/任意采样率）先统一成**恒定码率的 PCM**——拼接变成纯粹的字节拼接，插静音就是写 `\x00`；
- **时间戳按字节数精确计算**：`duration_ms = len(pcm) / (24000×2) × 1000`——不依赖任何解码器的时长元数据，零漂移；
- ffmpeg 通过 **stdin/stdout 管道**调用（`-i pipe:0 ... pipe:1`），不落临时文件；
- mp3 编码走临时文件（mp3 muxer 对不可寻址输出支持差）——完成后即删。

**为什么弃用 pydub**（踩坑记录）：pydub 在 Windows 上探测 ffmpeg 不可靠（找不到时静默报 warning 然后调用失败）；且它经管道读 WAV 时头部帧数字段是坏的（流式 WAV 无法回填 header，`nframes` 恒为 `0x7FFFFFFF`），时长计算全错。改成直接子进程调 ffmpeg + 自己算字节数，彻底绕开。

**`_sequence` 降级**：无 ffmpeg 且非 WAV 时，不拼接，输出每句的相对路径与停顿，前端用逐行 `<audio>` 播放——**保住了核心体验**（翻页、高亮、自动翻页全部可用），牺牲的是「单文件整页音频」与毫秒级停顿精度。

### 5.8 `pipeline/pdf_import.py` — PDF 拆页

**做什么**：pypdfium2（PDFium）把 PDF 逐页渲染为 JPG。
- `ZOOM=2.0`（约 144dpi）兼顾 OCR 清晰度与体积；`JPG_QUALITY=85`；
- **自适应降采样**：若某页渲染后长边超 `MAX_DIM=2600px`（页面尺寸异常的 PDF，如整页大图嵌入）→ 按比例缩小 zoom——防止渲染出 6000px 的巨图；
- `MAX_PAGES=500` 防误传；解析失败抛 `ValueError`（路由层转 400 并附清晰原因）；
- 选择 pypdfium2 而非 PyMuPDF：后者是 AGPL-3.0，与项目的 MIT 协议不兼容；
- 依赖惰性导入：未安装时给出「请 pip install pypdfium2 pillow」的明确提示而非崩溃。

### 5.9 `api/routes.py` — 13 个 REST 端点

| # | 方法/路径 | 功能 | 实现要点 |
|---|---|---|---|
| 1 | `POST /api/books` | 上传图片/PDF | 文件名清洗 + 自然排序 → 全部读入内存（await）→ 落盘/转图放线程池（CPU 密集不阻塞事件循环）；PDF 原位展开进页序；魔数校验真实类型，无效文件返回 400；受 `MAX_UPLOAD_MB` / `MAX_UPLOAD_FILES` 限制 |
| 2 | `GET /api/books` | 书架列表 | 汇总所有 meta 摘要 |
| 3 | `GET /api/books/{id}` | 书籍详情 | meta + 脚本里的角色表/音色分配（前端初始化用） |
| 4 | `GET /api/books/{id}/progress` | 进度轮询 | 读 meta + 线程存活标志（1.5s 一次，轻量） |
| 5 | `POST /api/books/{id}/rerun` | 重试/续跑 | 起新流水线线程；已有缓存自动复用 |
| 6 | `DELETE /api/books/{id}` | 删书 | 运行中拒绝（409） |
| 7 | `GET /api/books/{id}/pages/{n}` | **单页播放包** | 一次返回 image_url + audio_url + timings + lines，翻页时单请求拿全，播放不卡顿 |
| 8 | `GET /api/books/{id}/files/{rel}` | 文件服务 | **路径穿越守卫**（resolve 后必须落在书目录内）；带媒体类型；FileResponse 支持 HTTP Range（进度条可拖） |
| 9 | `GET /api/books/{id}/script` | 完整脚本 | 调试/导出用 |
| 10 | `GET /api/voices` | 50 音色清单 | 来自 config |
| 11 | `PUT /api/books/{id}/voices` | **换角色音色** | 白名单校验 + 状态校验（非 ready/error 时 409）+ 起重合成任务 |
| 12 | `PUT /api/books/{id}/auto-turn` | 自动翻页开关 | 持久化到 meta |
| 13 | `GET /api/health` | 健康自检 | 三个引擎名 + ffmpeg 检测 + 降级原因清单 |

**设计一致性**：所有长任务接口都「起线程 + 立刻返回」，进度统一走 #4 轮询——没有 WebSocket/SSE 的特例，前端逻辑单一。

### 5.10 `server.py` — 装配入口

`create_app()`：`include_router(api)` → `StaticFiles(html=True)` 挂到 `/`（SPA 兜底），启动时调用 `store.recover_incomplete()` 把上次中断的任务标为 `error`。监听地址由 `HOST` / `PORT` 控制：本地默认 `127.0.0.1:8080`，Docker 内为 `0.0.0.0:8080`。

### 5.11 前端 SPA（static/）

**`app.js`**：`api()` fetch 封装（非 2xx 抛错并提取服务端 detail）、`toast()` 提示、`escapeHtml()`（所有用户内容渲染都经它，防 XSS）、hash 路由（`#books` / `#read/{id}`）、健康自检渲染顶栏 chip。

**`upload.js`**：拖拽/多选 → 本地缩略图预览（PDF 显示 📄 图标）→ `POST /api/books` → 跳阅读页；书架卡片显示状态徽章+进度条，有未完成任务时 2.5s 自动刷新。

**`voices.js`**：音色面板——从 `/api/voices` 拉 50 音色，按「性别 × 年龄段」分成 6 个 `<optgroup>`；每角色一行下拉+保存；保存成功 **dispatch `resynth-start` 事件**通知阅读页进入轮询模式；弹窗关闭与状态提示。

**`reader.js` — 前端核心**，逐项说明：

| 功能 | 实现 |
|---|---|
| **翻页动画** | 双 `<img class="sheet …">` 层叠：新页初始 `rotateY(±96°)` 隐藏，`requestAnimationFrame` 后加 `back-in` 过渡到 0°，旧页加 `out-next/out-prev` 转出并淡出；620ms 后按**元素身份**清理旧图（`if (el !== img) remove`——修过「选择器漏删导致旧图堆积」的坑） |
| **舞台适配** | `fitStage()`：图片 `onload` 后用 naturalWidth/Height 按比例计算舞台的精确像素尺寸（宽 ≤760px、高 ≤ 视口-250px 给控制区留位）——整页完整可见、无需滚动；`resize` 事件同步重算。（`className` 赋值覆盖导致 `.sheet` 类丢失、图片按原始像素 3052px 渲染撑爆页面——本项目最隐蔽的坑，见 §8） |
| **逐句高亮** | 音频 `timeupdate` 事件 → `currentTime×1000` 在 segments 上**二分查找**（O(log n)）→ 命中区间则高亮该句；落在句间停顿则取消高亮 |
| **面板滚动** | 只滚动台词面板自身（`scrollBy` + getBoundingClientRect 判断可见性）——**绝不动窗口滚动**（修过 `scrollIntoView` 拽走整个视口、与用户滚动打架的坑） |
| **自动翻页** | `audio.onended`（或 sequence 播完最后一句）→ `autoTurn && 有下一页` → 翻页并自动续播；**「翻到哪页播哪页」**：手动翻页后也自动 `startPage()` |
| **无台词页** | segments 为空（封面/目录）→ 播键触发 `startPage()` 时自动翻页开启则停留 1.4s 后跳过；否则提示「本页无台词」 |
| **点击台词跳播** | single 模式：`audio.currentTime = seg.start_ms/1000` 精确跳转 |
| **预加载** | 每次翻页后后台 `preloadPage(n+1)`：预取下一页数据、预解码图片、预载音频——丝滑过渡的关键 |
| **进度轮询** | 处理中每 1.5s 拉 `/progress` → 更新进度条（分阶段加权百分比）；ready → 重新 boot；error → 显示重试按钮 + 跳过页数说明 |
| **换音色联动** | 监听 `resynth-start` → 轮询至 ready → 重载当前页数据（音频+timings+台词）并**从原播放位置续播** |
| **键盘** | ←/→ 翻页、空格播放暂停 |

**为什么零框架**（设计问答）：两个视图+一个弹窗的规模，原生 JS + fetch 完全够用；无构建步骤（演示时直接开浏览器即可讲代码）；代价是手写状态管理和 DOM 操作（`R` 对象即全局状态），页面更复杂时应换框架。

### 5.12 `prompts.py` — 提示词工程

三组提示词，设计共性：
- **全部以「严格输出 JSON，无其他内容」约束**，格式在提示词里给了完整示例；
- system 开头的 `[TASK:MERGE]` / `[TASK:VOICE_PICK]` 标记是**给 MockLLM 的分支识别用**的（真实 LLM 视为普通文本无影响）——一套提示词同时服务真实与 Mock 两条路径；
- **MERGE 提示词**：任务四分（标题/角色表/演出参数/line_id 规则）+ 六条硬规则（数量顺序一致、text 不许改写、过滤封面目录等非剧情文字、空页保留空数组）；
- **VOICE_PICK 提示词**：选角规则（旁白选播音类、尽量不重复、**voice 参数必须原样照抄**）+ 用户消息携带完整 50 音色清单 JSON。

---

## 6. 关键机制专题（「为什么这么设计」）

### 6.1 Provider 抽象 + 优雅降级
**动机**：AI 服务商迭代快（v1 的 Fish Audio → v2 千问），业务代码不该跟着改；开发/演示时常没有可用 key。
**收益**：换供应商=改一个环境变量；无 key 时全链路照跑（Mock 仿真）；`/api/health` 透明报告降级原因。
**代价**：多一层抽象与类型契约维护；适合「外部依赖会变」的场景，不适合写死的单供应商脚本。

### 6.2 断点续跑体系（三层缓存 + 一道守卫）
| 层 | 缓存物 | 效果 |
|---|---|---|
| OCR 级 | `pages_raw/pNNN.json` | 重跑不重复调视觉 API（失败页带标记强制重试） |
| TTS 级 | `lines/{line_id}.*` | 重跑/换音色只补差异句，不重复调 TTS |
| 供应商守卫 | meta.tts_provider | 换 TTS 供应商自动清空音频缓存（防止旧供应商音频被误复用） |
失败→`status=error`→前端一键重试→从失败点继续。**成本敏感型 API 场景的标准做法**。

### 6.3 逐页推进（渐进可播）
v1 设计是「全书 TTS 完 → 全书拼接」；v2 改为**逐页交错**：每页的台词合成完立即拼接成页音频。248 页的大书不再需要等一小时才能听第一页。

### 6.4 时间戳与高亮
- 时间戳由音频层在 PCM 字节级精确累积（含 pause_after_ms 的静音段）；
- 前端二分查找定位当前句；点击台词反向 seek（时间戳→`currentTime`）——**双向映射**。

### 6.5 内容安全容错
第三方视觉 API 有内容审核（`data_inspection_failed`）。策略：**单页失败 ≠ 全书失败**——失败页记为空台词页（页码完整、图片可翻、无音频），标 `ocr_failed` 供重试。原则：**局部降级优于整体失败**。

### 6.6 原子写与并发安全
- 所有 JSON 写入 `tmp + os.replace`（读者永远拿到完整文件）；
- 同书任务经线程锁串行；接口层对「运行中」的换音色/删除/重跑返回 409。

---

## 7. 一次上传的完整生命周期（走读）

```
1. 前端 POST /api/books（multipart）
2. 路由：文件名排序 → 读入内存 → 线程池落盘（PDF 顺带拆页）→ 生成 book_id → 写初始 meta(status=queued)
3. registry.submit() 起后台线程 → 立即返回 {book_id, page_count}
4. 前端跳转 #read/{id}，读详情，发现非 ready → 开始 1.5s 轮询
5. 后台线程 BookPipeline.run()：
   OCR 逐页（读 pages_raw 缓存/调视觉模型）→ merge（DeepSeek+本地修复）→ voice_pick（DeepSeek+白名单校验）
   → 逐页 { 逐句 TTS（读 lines 缓存/调千问）→ ffmpeg 拼页 → 写 timings }
6. 每完成一页，前端即可打开该页播放（翻页/高亮/自动翻页立即可用）
7. 全部完成 → status=ready → 前端轮询到 → 收起进度条
8. 后续交互：换音色(PUT voices→resynth 线程→只重合成该角色)、换自动翻页开关、删除书籍
```

---

## 8. 踩坑与修复记录（工程成熟度的直接证据）

| # | 现象 | 根因 | 修复 |
|---|---|---|---|
| 1 | 漫画页撑爆页面，要 25% 缩放才能看 | JS 里 `img.className = 'front'` **覆盖式赋值**，元素丢失 `sheet` 类 → 整套 CSS 尺寸/动画规则全部未命中；绝对定位的替换元素 width:auto 时按**原始像素**渲染（3052px） | 改为 `'sheet front'` 保留类名；CSS 把尺寸规则直接写在 `.sheet` 元素上（原 `.sheet img` 选择器匹配的是「里面的 img」——结构性错误） |
| 2 | 逐句高亮时下滑网页被强行拽回 | `element.scrollIntoView()` 会滚动**所有可滚祖先（含窗口）**去追当前句 | 改为只滚动台词面板自身（scrollBy + 可见性判断） |
| 3 | 翻页后旧图残留、画面干扰 | 清理用 `:not(.front)` 选择器——旧图仍带 `.front` 类未匹配到 | 按元素身份清理（`if (el !== img) remove`） |
| 4 | mp3 时长全错（算出 89478 秒） | 流式 WAV（管道输出）无法回填头部，`nframes` 恒为 `0x7FFFFFFF` | 放弃从容器读时长，改为按 PCM 字节数计算 |
| 5 | pydub 找不到 ffmpeg（Windows） | pydub 的探测机制不可靠且静默失败 | 弃用 pydub，直接子进程调 ffmpeg（`imageio-ffmpeg` 兜底提供二进制） |
| 6 | 248 页的书在第 60 页整本失败 | 第三方内容审核拦截单页，旧逻辑「单页异常=全书抛错」 | 单页失败降级为空页继续；标记录供重试 |
| 7 | TTS 报 401（key 有效） | 配置的 URL 属于不同工作空间（key 与实例不匹配）；以及 REST 地址被填给了 WebSocket 协议 | URL/Key 工作空间对齐；`normalize_ws_url()` 自动从 REST 地址推导 WS 地址 |
| 8 | DeepSeek 报模型不存在 | 模型名不在账号可用列表 | 换 `deepseek-v4-pro`（API 错误信息里给出了可用列表） |
| 9 | 换 TTS 供应商后旧音频被复用 | lines 缓存不含供应商信息 | meta 记录 provider，变更时清缓存 |
| 10 | 上传接口阻塞（PDF 转图 CPU 密集） | async 端点里跑同步 CPU 任务会阻塞事件循环 | 图片读入（await）与落盘/转图（run_in_threadpool）分离 |

---

## 9. 优缺点总结（自我批判）

**优点**
1. **供应商完全解耦**：三类 AI 能力可独立热切换，Mock 保证任何环境可运行；
2. **成本与失败友好**：三层缓存 + 断点续跑 + 单页容错 + 逐页可播；
3. **参数真的落地**：LLM 提取的情绪/语速/停顿贯穿到音频与时间戳（不是摆设）；
4. **前端体验完整**：3D 翻页、逐句高亮、点击跳播、自动翻页、换音色续播；
5. **零构建前端**：无 Node 工具链，代码可直接演示。

**已知短板（诚实清单）**
1. **OCR 说话人归属弱**：视觉模型对未登场角色的台词常标「未知」，全靠后续出现纠正——改进方向：给视觉模型更多前文上下文/分镜信息；
2. **无明显鉴权**：默认只监听 127.0.0.1；若要联网部署需加认证与限流；
3. **TTS 每次 call 新建 WebSocket**：批量合成有握手开销，SDK 支持时可复用实例；
4. **merge 是一次性全量调用**：超大书（数百页）的提示词可能触及上下文上限——可改为分批合并+归并；
5. **进度存 meta.json**：单机够用，多进程部署需换真正的任务队列；
6. **测试覆盖有限**（`tests/` 已覆盖纯函数、存储、上传/安全、Mock 全链路；真实 API 仍需手工验证）；
7. **换音色与音频文件的服务缓存**：浏览器对同 URL 的音频可能缓存旧版本——已通过重载数据缓解，生产环境可加版本化 URL。

---

## 10. 扩展与调试指南

**加一个新 TTS 供应商**：在 `providers/` 新建 `xxx_tts_provider.py` 实现 `BaseTTS`（一个 `synthesize` 方法）→ 工厂里加一个分支 → `.env` 改 `TTS_PROVIDER`。零业务代码改动。

**调试入口**：
| 想知道什么 | 看哪里 |
|---|---|
| 引擎状态/降级原因 | `GET /api/health` |
| 某本书处理到哪了 | `GET /api/books/{id}/progress` 或直接读 `data/books/{id}/meta.json` |
| OCR 原始识别结果 | `data/books/{id}/pages_raw/pNNN.json`（含失败页标记） |
| 某句的音频与时长 | `data/books/{id}/lines/`、`timings/*.json` |
| 完整剧本与音色分配 | `GET /api/books/{id}/script` |
| 服务日志 | 启动终端输出（uvicorn 访问日志 + 流水线异常 traceback） |

**常见故障速查**：
- `401 InvalidApiKey` → key 与 URL 的工作空间不匹配 / key 过期，去百炼控制台重新生成；
- `data_inspection_failed` → 内容审核命中，页面会被跳过并列入 `ocr_failed_pages`，重试时自动再试；
- `No module named uvicorn` → 用错了 Python（系统 Python 而非项目 venv），用 `C:\Agent\.venv\Scripts\python.exe server.py` 启动；
- 无声音/音频不可播 → `GET /api/health` 看 `ffmpeg` 与 `tts` 字段；
- 前端行为异常 → Ctrl+F5 强刷（静态资源有浏览器缓存）。

**常见设计问答**：
- *「为什么不用 Celery？」* → 本地单用户、无 broker 依赖、bytes 参数跨进程开销，线程+锁+轮询 50 行搞定（§5.6）；
- *「LLM 输出不可靠怎么办？」* → 三层 JSON 容错 + 修复层以原始识别为准 + 白名单校验 + 确定性兜底（§5.4/5.2）；
- *「供应商要换怎么办？」* → Provider 抽象 + 工厂 + `.env` 开关，附带缓存守卫（§6.1/6.2）；
- *「翻页高亮怎么对齐的？」* → PCM 字节级时间戳累积 + 前端二分查找 + 双向 seek（§6.4）；
- *「一页失败整本书怎么办？」* → 单页降级为空页继续 + 失败标记 + 一键续跑（§6.5）；
- *「怎么控制成本？」* → 三层缓存、只重合成变更部分、断点续跑（§6.2/5.5）。