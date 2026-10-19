# 配置说明

所有配置通过环境变量或项目根目录的 `.env` 读取。优先级：
**进程环境变量 > `.env` > 代码默认值**。

`.env` 从项目根目录读取（不依赖启动时的工作目录），兼容 Windows BOM。
参考模板：[.env.example](../.env.example)。

## 运行模式

| 变量 | 默认 | 说明 |
|---|---|---|
| `MOCK_MODE` | `0` | `1` 时强制使用内置 Mock（模拟 OCR/LLM + 静音 WAV），无需任何 Key 或 ffmpeg |
| `TTS_PROVIDER` | `qwen` | `qwen` / `fish` / `mock` |
| `VISION_PROVIDER` | `qwen` | `qwen` / `mock` |
| `LLM_PROVIDER` | `deepseek` | `deepseek` / `mock` |
| `QWEN_TTS_ENABLED` | `0` | 设为 `1` 才启用真实 Qwen TTS |
| `QWEN_VISION_ENABLED` | `0` | 设为 `1` 才启用真实 Qwen 视觉 OCR |

> 布尔值接受 `1/true/yes/on`（大小写不敏感），其余视为关闭。

## AI 服务

| 变量 | 默认 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | — | DeepSeek Key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容地址 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名（按你的账号可用模型填写） |
| `DEEPSEEK_THINKING` | `0` | `1` 开启思考（结构化 JSON 任务建议关闭） |
| `DEEPSEEK_MAX_TOKENS` | `32768` | 输出上限 |
| `QWEN_API_KEY` | — | DashScope / 百炼 Key（TTS 与视觉共用） |
| `QWEN_VISION_API` | — | 可选，视觉单独 Key（覆盖 `QWEN_API_KEY`） |
| `QWEN_BASE_URL` | — | TTS WebSocket 地址；填 REST 地址会自动推导 |
| `QWEN_TTS_MODEL` | `qwen-audio-3.0-tts-plus` | TTS 模型 |
| `QWEN_VISION_BASE_URL` | — | 视觉 OpenAI 兼容 REST 地址 |
| `QWEN_VISION_MODEL` | `qwen3.6-flash` | 视觉模型 |
| `QWEN_VISION_THINKING` | `0` | `1` 开启思考（OCR 建议关闭，显著更快） |
| `FISH_AUDIO_API_KEY` | — | 可选，`TTS_PROVIDER=fish` 时使用 |

## 服务与上传

| 变量 | 默认 | 说明 |
|---|---|---|
| `HOST` | `127.0.0.1` | 监听地址；Docker 镜像内为 `0.0.0.0` |
| `PORT` | `8080` | 监听端口（兼容旧变量 `SERVER_PORT`） |
| `DATA_DIR` | 项目下 `data/` | 数据根目录；Docker 中为 `/data` |
| `MAX_UPLOAD_MB` | `256` | 单次上传总大小上限 |
| `MAX_UPLOAD_FILES` | `500` | 单次上传文件数上限 |
| `FFMPEG_BIN` | 自动探测 | 指定 ffmpeg；`off/none/0` 强制禁用（走纯 WAV/逐句模式） |

## Docker Compose 变量

这些变量从**宿主环境**读取，不需要写进 `.env`：

| 变量 | 默认 | 说明 |
|---|---|---|
| `APP_PORT` | `8080` | 映射到宿主机的端口 |
| `BIND_ADDR` | `127.0.0.1` | 端口绑定地址；远程访问改为 `0.0.0.0`（注意无鉴权） |
| `MOCK_MODE` | `0` | 覆盖容器内 `MOCK_MODE` |
| `PIP_INDEX_URL` | — | 构建时 pip 镜像源，如 `https://pypi.tuna.tsinghua.edu.cn/simple` |
| `PIP_TRUSTED_HOST` | — | 镜像源对应的 trusted host |

## 健康检查

```bash
curl http://127.0.0.1:8080/api/health
```

返回当前生效的 Provider、`mock_mode`、`ffmpeg` 是否可用、`data_dir`、
上传上限，以及每个 Provider 的降级原因（`degraded`）。