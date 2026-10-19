# 🎧 漫画配音工坊 · Comic Dubbing Studio

[![CI](https://github.com/Jeffli-Coder/comic-dubbing-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/Jeffli-Coder/comic-dubbing-studio/actions/workflows/ci.yml)
[![Docker](https://github.com/Jeffli-Coder/comic-dubbing-studio/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/Jeffli-Coder/comic-dubbing-studio/actions/workflows/docker-publish.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-amd64%20%7C%20arm64-2496ED?logo=docker)](docs/DEPLOYMENT.md)

> 上传漫画页图片（或 PDF），自动完成 **OCR 识别台词 → LLM 整理剧本与选角 → 多音色语音合成**，
> 产出可翻页收听、逐句高亮、随时换音的沉浸式「听书」体验。


**English**: A self-hosted, cross-platform comic dubbing studio. Upload manga pages
or PDFs; a multimodal pipeline (vision OCR → LLM script/voice casting → multi-voice TTS)
produces a page-flipping audio reader with sentence-level highlighting and instant
voice swapping. Runs offline in mock mode, or with DeepSeek + Alibaba DashScope keys.
Deploy with one `docker compose up`.

---

## ✨ 功能特性

- **整本预合成，翻页秒播**：上传后后台完成 OCR 与配音，阅读时翻到哪页播哪页
- **逐句高亮联动**：音频播放时当前台词实时高亮，点击任意台词跳播
- **3D 翻页 + 自动翻页**：播完自动翻到下一页（可开关）
- **50 种音色选角**：LLM 根据角色人设（含从画面识别的性别）自动匹配音色
- **一键换音色**：网页上随时更换角色音色，后台只重合成该角色台词并热更新
- **封面/目录自动过滤**：只读真正的剧情台词
- **PDF 直接上传**：pypdfium2 逐页拆图进入管线
- **断点续跑 + 单页容错**：失败跳过问题页，重跑不重复调用已完成的 API
- **Provider 抽象 + 优雅降级**：LLM/TTS/视觉可切换供应商；缺 Key 自动落 Mock
- **零 Key 演示**：`MOCK_MODE=1` 无需任何 API Key / ffmpeg 即可体验完整交互
- **跨平台部署**：Docker（amd64 / arm64）、Windows、macOS、Linux 均可运行

## 🚀 30 秒体验（无需 API Key）

```bash
git clone https://github.com/Jeffli-Coder/comic-dubbing-studio.git
cd comic-dubbing-studio
MOCK_MODE=1 docker compose up --build
```

打开 **http://127.0.0.1:8080** ，上传几张图片（或 PDF），即可体验
上传 → 模拟识别 → 选角 → 合成 → 翻页播放 → 换音色 的完整流程。

> Mock 模式使用内置的模拟视觉/LLM 与静音 WAV，不消耗任何外部额度。

## 🏗️ 架构

```
上传图片/PDF
    │
    ▼
[① OCR]    千问视觉模型逐页识别台词与角色外观（性别）   ── pages_raw/ 缓存
    │
    ▼
[② 合并]   DeepSeek 整理标题 / 角色表 / 逐句演出参数
    │
    ▼
[③ 选角]   DeepSeek 从 50 音色中为角色选角（性别强制匹配）
    │
    ▼
[④ 合成]   千问 TTS 逐句合成 ──▶ lines/ 逐句缓存
    │
    ▼
[⑤ 拼接]   ffmpeg 拼页 + 插静音 + 毫秒级时间戳 ──▶ audio/ + timings/
    │
    ▼
[阅读]     浏览器 SPA：3D 翻页 + 音频联动高亮 + 自动翻页 + 音色面板
```

技术栈：**Python 3.11+ · FastAPI · Uvicorn · DeepSeek · DashScope（Qwen）·
pypdfium2 · ffmpeg · 原生 JavaScript（零构建）**。

详细设计见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 🐳 Docker 部署（推荐）

```bash
cp .env.example .env
# 填写 DEEPSEEK_API_KEY、QWEN_API_KEY、QWEN_BASE_URL、QWEN_VISION_BASE_URL，
# 并将 QWEN_TTS_ENABLED / QWEN_VISION_ENABLED 设为 1

docker compose up -d --build
```

- 数据保存在 named volume `comic_data`（`/data`），重建容器不丢书。
- 默认只绑定 `127.0.0.1:8080`；远程访问：`BIND_ADDR=0.0.0.0 docker compose up -d`
  （**应用无鉴权，公网请加反向代理认证**）。
- 国内加速：`PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple docker compose build`。
- 多架构镜像：`ghcr.io/jeffli-coder/comic-dubbing-studio:latest`（linux/amd64、linux/arm64）。

完整部署、备份、反向代理与排障见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

## 💻 原生运行

```bash
python3.12 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                # 或设 MOCK_MODE=1 直接体验
python server.py                    # http://127.0.0.1:8080
```

| 依赖 | 说明 |
|---|---|
| Python 3.11 / 3.12 | 主运行环境 |
| ffmpeg | 可选；没有时自动使用 `imageio-ffmpeg`，再不行降级为逐句播放 |
| API Key | 可选；缺失时自动 Mock，可在 `/api/health` 查看原因 |

## ⚙️ 配置

| 变量 | 默认 | 说明 |
|---|---|---|
| `MOCK_MODE` | `0` | `1` = 内置 Mock，无需任何 Key |
| `DEEPSEEK_API_KEY` | — | 剧本合并与选角 |
| `QWEN_API_KEY` | — | DashScope / 百炼（TTS + 视觉） |
| `QWEN_BASE_URL` | — | TTS WebSocket 地址（填 REST 地址会自动推导） |
| `QWEN_VISION_BASE_URL` | — | 视觉 OCR 的 OpenAI 兼容地址 |
| `QWEN_TTS_ENABLED` / `QWEN_VISION_ENABLED` | `0` | 真实接口开关 |
| `TTS_PROVIDER` / `VISION_PROVIDER` / `LLM_PROVIDER` | qwen / qwen / deepseek | `mock` 可单独关闭某类能力 |
| `HOST` / `PORT` | `127.0.0.1` / `8080` | 监听地址 |
| `DATA_DIR` | `./data` | 数据目录（Docker 为 `/data`） |
| `MAX_UPLOAD_MB` / `MAX_UPLOAD_FILES` | `256` / `500` | 上传限制 |

完整清单见 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)。
`GET /api/health` 可随时查看当前生效的引擎与降级原因。

## 🔌 API

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/books` | 上传图片/PDF，启动后台流水线 |
| `GET` | `/api/books` | 书架列表 |
| `GET` | `/api/books/{id}` | 书籍详情（角色表、音色分配） |
| `GET` | `/api/books/{id}/progress` | 进度轮询 |
| `POST` | `/api/books/{id}/rerun` | 断点续跑 |
| `DELETE` | `/api/books/{id}` | 删除书籍 |
| `GET` | `/api/books/{id}/pages/{n}` | 单页播放包（图片 + 音频 + 时间戳 + 台词） |
| `GET` | `/api/books/{id}/files/{rel}` | 文件服务（支持 Range） |
| `GET` | `/api/books/{id}/script` | 完整脚本 |
| `GET` | `/api/voices` | 50 音色清单 |
| `PUT` | `/api/books/{id}/voices` | 更换角色音色 |
| `PUT` | `/api/books/{id}/auto-turn` | 自动翻页开关 |
| `GET` | `/api/health` | 健康自检 |

## 📁 项目结构

```
├── config.py                 # 配置 + 50 音色清单（唯一数据源）
├── server.py                 # FastAPI 入口（静态托管 / 上传限流 / 重启恢复）
├── prompts.py                # LLM 提示词
├── providers/                # 外部服务抽象层
│   ├── base.py               #   接口与数据契约
│   ├── mock_provider.py      #   零依赖仿真（离线演示/测试）
│   ├── deepseek_provider.py  #   剧本 LLM
│   ├── qwen_tts_provider.py  #   语音合成
│   ├── qwen_vision_provider.py # 漫画页 OCR
│   └── image_mime.py         #   图片/PDF 魔数校验
├── pipeline/                 # 核心流水线
│   ├── orchestrator.py       #   状态机 / 断点续跑 / 换音色
│   ├── stages.py             #   合并·修复·选角
│   ├── audio.py              #   ffmpeg / WAV 拼接与时间戳
│   ├── pdf_import.py         #   PDF 拆页（pypdfium2）
│   └── store.py / tasks.py   #   原子存储 / 后台任务
├── api/routes.py             # REST 端点
├── static/                   # 零框架 SPA
├── tests/                    # 离线测试（Mock，无外网）
├── docs/                     # 架构 / 配置 / 部署 / 项目全解
├── Dockerfile / docker-compose.yml
└── .github/workflows/        # CI + 多架构镜像发布
```

## ⚠️ 已知限制

- **无鉴权**，仅适合单用户本机/内网使用；不要直接暴露公网。
- **单 worker / 单副本**：任务队列在进程内，多 worker 会状态错乱。
- OCR 对尚未登场角色的说话人可能标「未知」，随页面推进逐步纠正。
- 超大书（数百页）按 20 页分批合并，耗时与 API 用量较高。
- 真实 API 链路需要有效 Key；没有 Key 时自动 Mock，不会报错但只产出静音。

## 🧪 开发与测试

```bash
pip install -r requirements-dev.txt
MOCK_MODE=1 python server.py
pytest -q
ruff check .
```

测试完全离线，CI 在 Ubuntu / Windows / macOS 上运行。贡献流程见
[CONTRIBUTING.md](CONTRIBUTING.md)。

## 📚 文档

| 文档 | 内容 |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 当前 v2 架构、数据布局、并发与安全边界 |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | 全部环境变量 |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker / 原生部署、备份、反向代理、排障 |
| [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md) | 项目全解：逐模块实现、设计动机、踩坑记录 |
| [docs/archive/](docs/archive/) | v1 架构与历史规划（已过时，仅供追溯） |

## ⚠️ 版权说明

仓库**不包含任何漫画素材或台词**。请只上传你拥有合法使用权的图片/PDF。
`tests/` 中的素材均由程序生成（纯色图片与虚构台词）。

## 📄 License

[MIT](LICENSE)。第三方依赖与系统组件许可见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

安全问题请勿公开提 Issue，见 [SECURITY.md](SECURITY.md)。