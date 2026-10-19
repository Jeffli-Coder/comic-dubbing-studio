# 部署指南

## 方式一：Docker Compose（推荐）

要求：Docker 20.10+、Docker Compose v2.24+（`env_file.required` 语法）。

### 1. 零配置体验（无需任何 API Key）

```bash
git clone <your-repo-url>
cd comic_dubbing_agent
MOCK_MODE=1 docker compose up --build
```

打开 http://127.0.0.1:8080 ，上传图片即可体验完整流程（模拟 OCR + 静音配音）。
`MOCK_MODE=1` 会强制使用内置 Mock，不会调用任何外部 API。

### 2. 接入真实 API

```bash
cp .env.example .env
# 编辑 .env：填写 DEEPSEEK_API_KEY、QWEN_API_KEY、QWEN_BASE_URL、
#           QWEN_VISION_BASE_URL，并把 QWEN_TTS_ENABLED / QWEN_VISION_ENABLED 设为 1
docker compose up -d --build
docker compose logs -f
```

数据保存在 named volume `comic_data` 中，容器重建不会丢失。

### 3. 国内网络加速构建

```bash
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn \
docker compose build
```

或直接使用已发布镜像：

```bash
docker pull ghcr.io/<owner>/<repo>:latest
docker run -d --name comic-dubbing \
  -p 127.0.0.1:8080:8080 \
  --env-file .env \
  -v comic_data:/data \
  ghcr.io/<owner>/<repo>:latest
```

### 4. 远程访问

默认只绑定 `127.0.0.1`。局域网访问：

```bash
BIND_ADDR=0.0.0.0 docker compose up -d
```

> ⚠️ 应用没有鉴权。公网部署请务必放在带认证的反向代理后面，见下文。

## 方式二：原生 Python

要求：Python 3.11/3.12；ffmpeg 可选（没有时会自动使用 `imageio-ffmpeg`
自带二进制，再不行降级为逐句播放）。

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # 填写 Key；或 MOCK_MODE=1 直接体验
python server.py
```

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:MOCK_MODE="1"; python server.py
```

Linux 上建议装系统 ffmpeg 以获得整页 MP3 与毫秒级时间戳：

```bash
sudo apt install ffmpeg        # Debian/Ubuntu
sudo dnf install ffmpeg        # Fedora
brew install ffmpeg            # macOS
```

## 数据卷与备份

容器内数据目录是 `/data`（`DATA_DIR`），结构见
[ARCHITECTURE.md](ARCHITECTURE.md#3-数据布局)。

```bash
# 备份
docker run --rm -v comic_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/comic-data.tgz -C /data .

# 恢复
docker run --rm -v comic_data:/data -v "$PWD":/backup alpine \
  tar xzf /backup/comic-data.tgz -C /data

# 清空全部书籍（不可恢复）
docker compose down -v
```

若想直接看到文件，可改成 bind mount；Linux 下入口脚本会自动修正属主：

```yaml
volumes:
  - ./data:/data
```

## 反向代理（Nginx 示例）

```nginx
server {
    listen 443 ssl;
    server_name comic.example.com;

    # 漫画 PDF/图片可能较大；必须大于 MAX_UPLOAD_MB
    client_max_body_size 300m;

    location / {
        # 建议加认证：auth_basic / oauth2-proxy / Cloudflare Access
        auth_basic "Comic Dubbing";
        auth_basic_user_file /etc/nginx/.htpasswd;

        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 单页 OCR + TTS 可能耗时较长
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

Nginx 默认 `client_max_body_size 1m`，不调整会导致 PDF 上传直接 413。

## 架构与资源

- 官方镜像支持 `linux/amd64` 与 `linux/arm64`（Apple Silicon / ARM 服务器直接可用）。
- 不要在 Alpine 上自行构建：pypdfium2/PDFium 无 musl wheel。
- 镜像内置 Debian ffmpeg（含 libmp3lame），因此整页 MP3 拼接可用。
- **只能单 worker / 单副本**：任务队列在进程内。不要加 `--workers N`，
  也不要同时起多个连接同一 `DATA_DIR` 的实例。

## 升级

```bash
git pull
docker compose build --pull
docker compose up -d
```

进行中的任务会因重启被标记为 `error`，在网页上点「重试处理」即可断点续跑
（已完成页面的 OCR 与逐句音频不会重复调用 API）。

## 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| `pip install` 找不到某个精确版本 | 本项目依赖使用版本区间；若仍失败，升级 pip 或换镜像源 |
| 健康检查显示 `ffmpeg: false` | 未装系统 ffmpeg 且 `imageio-ffmpeg` 不可用；安装 ffmpeg 或忽略（自动逐句播放） |
| 上传返回 413 | 超过 `MAX_UPLOAD_MB`，或反向代理限制了 body 大小 |
| 阅读页图片 404 | 旧版本 bug；当前版本会按真实扩展名回填 `script.json` |
| PDF 上传报「不是有效的 PDF」 | 文件头不是 `%PDF-`，或文件已损坏/加密 |
| 容器启动报 `/data` 权限错误 | 使用 named volume，或让入口脚本以 root 启动以修正 bind mount 属主 |
| 重启后任务一直「处理中」 | 旧版本问题；当前版本启动时会把中断任务标为 error，可点重试 |
| Windows 控制台中文乱码/报错 | 已设置 UTF-8 输出；仍异常时执行 `set PYTHONUTF8=1` |
| 换音色后仍播旧音频 | 浏览器缓存；接口已带 `Cache-Control: no-cache`，强制刷新即可 |