# 架构说明（v2）

> 历史 v1（Gradio + Fish 声纹克隆 + `/api/extract`）的设计见
> [archive/ARCHITECTURE-v1.md](archive/ARCHITECTURE-v1.md)，仅供追溯，不代表当前实现。

## 1. 总览

```
上传图片 / PDF
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│ FastAPI（api/routes.py）                                 │
│  · 上传落盘 / PDF 拆页（pypdfium2）                       │
│  · 起后台线程（pipeline/tasks.py）                        │
│  · 静态 SPA + /files 文件服务（Range / 路径守卫）          │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│ BookPipeline（pipeline/orchestrator.py）                 │
│  ① OCR    qwen vision   → pages_raw/pNNN.json（断点缓存） │
│  ② 合并   DeepSeek LLM  → script.json（标题/角色/演出参数）│
│  ③ 选角   DeepSeek LLM  → voice_assignments              │
│  ④ 合成   qwen TTS      → lines/<line_id>.<ext>（逐句缓存）│
│  ⑤ 拼接   ffmpeg        → audio/page_NNN.mp3 + timings   │
└──────────────────────┬──────────────────────────────────┘
                       ▼
        浏览器 SPA：翻页 + 音频联动高亮 + 换音色
```

**技术栈**：Python 3.11/3.12 · FastAPI · Uvicorn · DeepSeek（OpenAI 兼容）·
DashScope（Qwen 视觉 / TTS）· pypdfium2 · ffmpeg · 原生 JavaScript。

## 2. Provider 抽象

`providers/base.py` 定义三个接口：

| 接口 | 方法 | 默认实现 | 备选 |
|---|---|---|---|
| `BaseVision` | `analyze_page(image_bytes, page_num, prev_context)` | `QwenVision` | `MockVision` |
| `BaseLLM` | `chat_json(system, user)` | `DeepSeekLLM` | `MockLLM` |
| `BaseTTS` | `synthesize(text, voice, speed, ...)` | `QwenTTS` | `FishTTS` / `MockTTS` |

工厂在 `providers/__init__.py`：

- `MOCK_MODE=1` 或 `*_PROVIDER=mock` → 直接返回 Mock；
- Key/URL 缺失、依赖初始化失败 → 自动降级 Mock，并把原因写入 `DEGRADED`，
  通过 `GET /api/health` 暴露；
- 实例用 `lru_cache` 缓存，避免每次健康检查重复构造 SDK 客户端。

**约束**：业务代码（`pipeline/`）只允许依赖 `Base*` 接口，不得直接 import 厂商 SDK。

## 3. 数据布局

```
DATA_DIR/books/{book_id}/
├── meta.json           # 状态、进度、标题、created_at（原子写）
├── pages/001.jpg       # 上传原图（PNG/WebP 保留真实扩展名）
├── pages_raw/p001.json # ① OCR 原始结果（断点续跑）
├── script.json         # ②③ 合并后的按页脚本 + 音色分配
├── lines/p001_01.mp3   # ④ 逐句音频缓存
├── audio/page_001.mp3  # ⑤ 整页拼接音频
└── timings/page_001.json  # ⑤ 逐句起止毫秒 + 音频文件
```

删除某本书只允许 12 位十六进制 `book_id`，且 `store.delete_book()` 会再次确认
目标目录的父目录就是 `BOOKS_DIR`，防止路径穿越删除整个数据目录。

## 4. 状态机与断点续跑

`meta.status`：

```
queued → ocr → voice_pick → tts → concat → ready
                                   ↘ error（可重试）
ready/error → resynth → ready        （换角色音色）
```

- **三层缓存**：`pages_raw`、`lines`、`timings` 各自落盘；重跑只补缺口。
- **逐页发布**：每页台词合成完立即拼接，大书不必等全本完成。
- **单页容错**：某页 OCR 失败记为空台词页并继续，标记 `ocr_failed` 供下次重试。
- **重启恢复**：`store.recover_incomplete()` 在启动时把 `queued/ocr/.../resynth`
  状态改为 `error`（daemon 线程随进程结束，不会自行恢复），前端可点「重试续跑」。

## 5. 并发模型（重要）

任务队列是**进程内**的 `threading.Thread` + 内存注册表（`pipeline/tasks.py`），
每本书一把锁。因此：

- **必须单 worker 运行**（Dockerfile / README 均为 `--workers 1`）；
- 不支持多副本水平扩展；
- 进程重启会中断进行中的任务（见 `recover_incomplete()`）。

要水平扩展，需要把 `TaskRegistry` 换成 Redis/Celery/RQ 等共享队列，并把
`meta.json` 换成数据库。

## 6. 音频与时间戳

`AudioMixer` 三条路径：

1. 有 ffmpeg：所有输入解码为 24kHz/单声道/16bit PCM → 拼接 + 插静音 →
   编 MP3；时间戳按 PCM 字节数精确累积。
2. 无 ffmpeg 且全部是 WAV：纯 stdlib 拼接，输出 WAV。
3. 其余：`sequence` 模式，不拼接，前端逐句播放（翻页/高亮仍可用）。

前端通过 `timings.segments` 的 `start_ms/end_ms` 做音频 ↔ 台词双向映射。

## 7. 安全边界

- 默认只监听 `127.0.0.1`；Docker 端口默认也只绑定本机。
- 上传：总大小上限、文件数上限、扩展名白名单、魔数校验、文件名 basename 清洗。
- 文件服务：`Path.is_relative_to()` 防止目录穿越与软链接逃逸。
- **没有鉴权**：不要直接暴露公网，详见 [../SECURITY.md](../SECURITY.md)。
- 图片是 `data:` URL 直接送给视觉模型；不会写入第三方对象存储。

## 8. 前端

零构建、零框架：

- `static/js/app.js`：fetch 封装、toast、hash 路由、健康 chip；
- `upload.js`：拖拽上传、缩略图、书架轮询；
- `reader.js`：3D 翻页、单/序列双模式播放、逐句高亮、自动翻页；
- `voices.js`：50 音色面板与换音色。

所有用户/模型文本渲染前都经过 `escapeHtml()`。