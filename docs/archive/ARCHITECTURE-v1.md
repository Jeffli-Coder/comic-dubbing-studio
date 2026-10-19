# 漫画配音智能体 — 项目架构与实现细节

> 版本：v1.0（对应代码现状，2026-09-11 梳理）
> 配套文档：[IMPROVEMENT_PLAN.md](./IMPROVEMENT_PLAN.md)（千问语音模型接入与项目完善方案）

---

## 1. 项目概述

**漫画配音智能体**是一套「文本 → 配音脚本 → 分角色语音合成」的管线系统：输入漫画的文字内容（PDF/miner 提取后的 markdown 文本），由 LLM 完成角色识别、情绪推断与配音指导，再按角色分配不同音色，最终调用 TTS 服务逐句合成配音音频。

目前项目已跑通一条完整链路：以旧版示例脚本（3 个场景 / 25 句台词 / 5 个角色）为输入，成功合成 25 条 MP3（见 `output/` 目录）。

### 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 前端 UI | Gradio（`client.py`） | 双 Tab 交互界面，web 版即开即用 |
| 后端 API | FastAPI + Uvicorn（`server.py`） | RESTful 接口，运行于 `:8080` |
| 核心编排 | `manga_dubber.py` | 四步配音流水线 |
| 文本理解 LLM | DeepSeek（`llm_client.py`） | OpenAI 兼容协议，`deepseek-chat` |
| TTS / 声音克隆 | Fish Audio（`fish_audio_client.py`） | `s2.1-pro-free` 免费模型 + `/model` 克隆接口 |
| 音频输出 | MP3 文件 | `output/` 目录，按台词一句一文件 |

---

## 2. 总体架构

```
┌──────────────┐   HTTP (multipart/JSON)   ┌──────────────┐
│  client.py   │ ────────────────────────▶ │  server.py   │
│  (Gradio UI) │                           │  (FastAPI)   │
└──────────────┘                           └──────┬───────┘
                                                  │ 调用
                                         ┌────────▼────────┐
                                         │  manga_dubber.py │  ← 核心编排器
                                         │  (MangaDubber)   │
                                         └──┬──────┬───────┘
                                 调用        │      │        调用
                             ┌───────────────▼─┐  ┌─▼─────────────────┐
                             │  llm_client.py  │  │ fish_audio_client │
                             │  (LLMClient)    │  │ (FishAudioClient) │
                             └───────┬─────────┘  └────────┬──────────┘
                                     │ HTTP                │ HTTP
                              ┌──────▼──────┐       ┌──────▼──────┐
                              │ DeepSeek API│       │ Fish Audio  │
                              └─────────────┘       │     API     │
                                                    └─────────────┘
                                         输出
                                     ┌────▼────┐
                                     │ output/ │  ← line_NNN_角色.mp3
                                     └─────────┘
```

### 数据流（一次完整配音）

```
markdown 漫画文本
   │  ① extract_script（LLM）
   ▼
dialogue_script（JSON：title/characters/scenes/lines）
   │  ② build_voice_plan（LLM）
   ▼
voice_plan（角色 → voice_tag 音色标签）
   │  ③ assign_voices（本地映射表 TAG_TO_VOICE_ID）
   ▼
voice_tasks（每句台词 + reference_id 音色 ID）
   │  ④ synthesize_all（HTTP TTS；可选前置：克隆用户音色）
   ▼
output/*.mp3 + playlist（音频清单）
```

---

## 3. 目录结构（现状）

```
comic_dubbing_agent/
├── server.py                   # FastAPI 后端（5 个接口）
├── client.py                   # Gradio 前端（2 个 Tab）
├── manga_dubber.py             # 核心编排器（4 步流水线）
├── llm_client.py               # DeepSeek LLM 客户端（OpenAI 协议）
├── fish_audio_client.py        # Fish Audio TTS + 声音克隆客户端
├── prompts.py                  # 全部 LLM 提示词模板
├── test_dub.py                 # 端到端命令行测试入口
├── 示例脚本（未随公开仓库提供） # 测试用配音脚本（25 句台词）
├── requirements-manga.txt      # Python 依赖清单
├── .env                        # API 密钥与配置
├── Peqi.mp3                    # 克隆测试用声音样本（代码中未激活引用）
├── Vol_01_pages/               # 漫画第一话扫描图 17 页（JPG，代码中未使用）
└── output/                     # 已生成的 25 条台词 MP3
```

---

## 4. 核心模块详解

### 4.1 `manga_dubber.py` — 核心编排器

类 `MangaDubber`，构造时创建 `LLMClient`（DeepSeek）与 `FishAudioClient`，是整个系统的调度中枢。模块级常量 `TAG_TO_VOICE_ID` 维护 10 个「音色标签 → Fish Audio voice_id」的映射。

四个流水线步骤：

| 步骤 | 方法 | 输入 | 输出 | 依赖 |
|---|---|---|---|---|
| ① 脚本提取 | `extract_script()` | markdown 文本 | `dialogue_script` JSON | DeepSeek（`EXTRACT_SCRIPT_*` 提示词，t=0.3） |
| ② 音色规划 | `build_voice_plan()` | `dialogue_script` | `voice_plan`（角色 → voice_tag） | DeepSeek（`VOICE_PLAN_*` 提示词，t=0.1） |
| ③ 音色分配 | `assign_voices()` | script + plan + 可选克隆样本 | `voice_tasks` / `clone_list` / `voice_assignments` | 纯本地逻辑 |
| ④ 克隆+TTS | `synthesize_all()` | tasks + clone_list | `playlist` + MP3 文件 | Fish Audio HTTP |

步骤 ③ 的关键设计：

- **内心 OS 合并**：`get_body()` 将「林默（内心）」归并到本体「林默」，共用同一音色（内心独白与本体同声）。
- **克隆优先级**：用户上传声音样本（`custom_audio_bytes` + `custom_character`）时，该角色标记 `speaker_type: "cloned"`，绕过内置音色库，改用克隆 voice_id。
- 产物 `voice_tasks` 每项含：character / text / speed / emotion / reference_id / speaker_type / temperature / top_p。

步骤 ④ 的执行顺序：先逐角色调用 `/model` 提交克隆并轮询 `wait_for_clone()`（5s 间隔，300s 超时）→ 把克隆出的 voice_id 回填任务 → 逐句调用 `/v1/tts` 合成 → 写入 `output/line_NNN_角色.mp3`（文件名做 Windows 非法字符替换）→ 汇总 `playlist`。

入口方法 `dub()` 串联 ①~④，支持两种输入模式：`markdown_content`（走完整流程）或 `dialogue_script`（跳过步骤①）。

### 4.2 `llm_client.py` — LLM 客户端

对 `openai` SDK 的轻封装，`chat_json()` 提供**三层 JSON 解析容错**：

1. 直接 `json.loads`；
2. 剥离 ```json``` 代码块围栏后解析；
3. 处理 `{"output": "```json\n{...}\n```"}` 嵌套包装。

解析全部失败则抛 `ValueError`（附原文前 500 字便于排查）。

### 4.3 `fish_audio_client.py` — TTS + 声音克隆客户端

| 方法 | 端点 | 说明 |
|---|---|---|
| `synthesize()` | `POST /v1/tts` | 请求头带 `model: s2.1-pro-free`（免费模型）；body 仅 `text` + `format: mp3` + 可选 `reference_id`（指定音色） |
| `clone_voice()` | `POST /model` | multipart 上传音频样本，`train_mode: fast`（快速训练）、`enhance_audio_quality: true`、`visibility: private`；返回 voice_id + state |
| `wait_for_clone()` | `GET /model/{id}` | 轮询训练状态直到 `trained` / `failed` / 超时 |
| `list_voices()` | `GET /model` | 搜索声音库（支持 title 过滤、self_only） |
| `download_audio()` | GET 任意 URL | 通用下载，当前未在管线中使用 |

### 4.4 `prompts.py` — 提示词模板

三组提示词，全部要求「严格输出 JSON，不输出其他内容」：

| 提示词组 | 角色设定 | 输出 |
|---|---|---|
| `EXTRACT_SCRIPT_SYSTEM/USER` | 资深漫画编辑兼配音导演 | 完整 dialogue_script（含 12 种情绪标签、语速 0.6–2.0 建议、音高建议、重音词、句尾停顿毫秒） |
| `VOICE_PLAN_SYSTEM/USER` | 配音选角导演 | `{voice_plan: [{character, voice_tag}], merge_note}`，voice_tag 为 10 选 1 的枚举值 |
| `SUMMARY_SYSTEM/USER` | 配音工作汇报助手 | 面向用户的自然语言汇报（非 JSON） |

### 4.5 `server.py` — API 服务（:8080）

| 接口 | 方法/路径 | 功能 |
|---|---|---|
| 1 | `POST /api/extract` | markdown 文本 → 配音脚本（附带角色/台词统计） |
| 2 | `POST /api/dub` | multipart：脚本 JSON 字符串 + 可选克隆音频 + 角色名 → 完整配音（附 LLM 生成的汇总文案） |
| 3 | `GET /api/audio/{filename}` | 下载/播放生成的音频文件 |
| 4 | `GET /api/voices` | 查看当前 voice_tag → voice_id 映射 |
| 5 | `GET /api/voices/search` | 搜索 Fish Audio 声音库 |

### 4.6 `client.py` — Gradio UI（:7860）

- **Tab ① 提取配音脚本**：粘贴 markdown → 调 `/api/extract` → 输出 JSON；「加载 Demo 脚本」按钮直接读入旧版示例脚本。
- **Tab ② 配音合成**：粘贴脚本 JSON + 可选自定义音色角色名与 PV 音频路径 → 调 `/api/dub`（timeout 600s）→ 输出汇总文案与逐句文件清单。

前端仅展示音频文件路径，暂不支持界面内在线播放。

---

## 5. 数据模型

### 5.1 `dialogue_script`（配音脚本，管线核心数据结构）

```json
{
  "title": "漫画标题",
  "characters": [
    {"name": "林默", "type": "主角", "description": "..."},
    {"name": "旁白", "type": "旁白", "description": "..."},
    {"name": "林默（内心）", "type": "内心OS", "description": "..."}
  ],
  "scenes": [
    {
      "scene_id": 1,
      "description": "场景描述",
      "mood": "整体氛围",
      "lines": [
        {
          "id": 1,
          "character": "林默（内心）",
          "target": "自己",
          "text": "台词原文",
          "type": "inner_thought",          // dialogue | monologue | narration | inner_thought
          "emotion": "期待",                 // 12 种情绪标签或复合标签（如「愤怒→激动→平静」）
          "speed": 0.9,                      // 0.6–2.0
          "pitch": "正常",                   // 提高 | 正常 | 降低
          "emphasis": ["重音词1", "重音词2"],
          "pause_after_ms": 500
        }
      ]
    }
  ]
}
```

### 5.2 其他中间结构

- `voice_plan`：`{voice_plan: [{character, voice_tag}], merge_note: "..."}`
- `voice_tasks[]`：`{character, text, speed, emotion, reference_id, speaker_type: builtin|cloned, temperature, top_p}`
- `playlist[]`：`{index, character, text, emotion, reference_id, audio_file}`
- `voice_assignments`：`{角色名 → voice_id 或 "🎤 用户自定义音色（克隆中）"}`

---

## 6. 音色体系

`manga_dubber.py` 中的 `TAG_TO_VOICE_ID` 定义了 10 个角色音色标签，`VOICE_PLAN` 提示词要求 LLM 必须从这 10 个标签中选择：

| voice_tag | 音色描述 | 典型适用 |
|---|---|---|
| male_youth_hot | 青年男声，热血明亮 | 热血主角 |
| male_youth_gentle | 青年男声，温柔清澈 | 温柔型男主 |
| male_middle_deep | 中年男声，低沉沉稳 | 大叔/上司 |
| male_elder | 老年男声，苍老沙哑 | 长者 |
| female_youth_bright | 少女声，活泼清脆 | 活泼少女 |
| female_youth_gentle | 青年女声，温柔亲切 | 温柔女主 |
| female_mature_sexy | 御姐声，魅惑戏谑 | 御姐/戏谑角色 |
| female_mature_calm | 成熟女声，知性从容 | 知性女配 |
| narrator_male | 男声旁白，播音腔 | 旁白 |
| narrator_female | 女声旁白，知性 | 旁白 |

---

## 7. 运行方式

```powershell
pip install -r requirements-manga.txt
# 先启动后端
python server.py        # :8080
# 再启动前端（另开终端）
python client.py        # :7860
# 跳过 UI 的端到端命令行测试
python test_dub.py
```

环境变量见 `.env`：`DEEPSEEK_*`（核心 LLM）、`FISH_AUDIO_API_KEY`（TTS/克隆）。

---

## 8. 已知问题与限制（改进基线）

> 以下问题均已收录进 `IMPROVEMENT_PLAN.md` 的改造计划，此为改造前的原始基线。

| # | 问题 | 影响 |
|---|---|---|
| 1 | **图片→文本环节缺失**：`Vol_01_pages/` 17 页漫画图从未被代码引用，流程实际以「外部工具提取好的 markdown」为起点 | 管线不闭环，无法直接丢漫画图片出配音 |
| 2 | **配音参数未落地**：脚本中提取的 emotion/speed/pitch/emphasis/pause_after_ms 在 `synthesize_all()` 中全部被丢弃，只把 `text` + `reference_id` 传给 TTS | 语义理解与音频产出的断裂——语速、情绪、停顿全是摆设，求职展示时会被一眼看穿 |
| 3 | **台词文本残留 OCR 噪声**：「哇啊｜」「這」「哈合」等符号/异体字未清洗 | 合成音频出现读错或吞字 |
| 4 | **供应商硬编码耦合**：DeepSeek + Fish Audio 直接写死在编排器里，无 Provider 抽象 | 换千问等供应商需侵入式改造 |
| 5 | **无重试与断点续传**：25 句逐条串行 HTTP，任何一条失败整个请求抛 500，重跑无法复用已成功的音频 | 批量合成的稳定性差 |
| 6 | **代码卫生**：`server.py` 中定义了 `DubRequest/DubResponse` 模型但实际走 Form/File（死代码）；`requirements-manga.txt` 漏了 `gradio`；`.env` 中本地 Qwen（`LLM_MODEL_ID/LLM_BASE_URL`）与 `SERPAPI_API_KEY` 均无代码引用 | 依赖描述不准，评审观感差 |
| 7 | **无工程化设施**：没有 git 仓库、README、单元测试、日志系统；`__pycache__`、`client_stdout.txt`、`output/` 与源代码混放 | 作为求职项目风险极大（且 `.env` 内是真实密钥，提交即泄露） |
| 8 | **UI 能力单薄**：结果只显示文件路径，不支持在线试听、整集合并导出 | 演示效果打折 |
| 9 | 克隆依赖 Fish Audio 收费训练 + `wait_for_clone` 最长 300s 阻塞请求线程 | 交互体验差 |

---

*本文档为项目现状记录；改造后的目标架构见 [IMPROVEMENT_PLAN.md](./IMPROVEMENT_PLAN.md)。*