# 安全策略 / Security Policy

## 支持范围

项目按"单用户、本机运行"设计。最新 `main` 分支会持续修复安全问题。

## 重要警告：默认没有鉴权

本应用**没有登录、权限和多租户隔离**：

- `python server.py` 默认只监听 `127.0.0.1`；
- Docker Compose 默认只把端口绑定到 `127.0.0.1`；
- 如果你设置 `HOST=0.0.0.0` 或 `BIND_ADDR=0.0.0.0`，任何能访问该端口的人都可以上传文件、删除书籍、消耗你的 AI API 额度。

**不要把本服务直接暴露到公网。** 如确需远程访问，请在前面加带认证的反向代理（如 Nginx + Basic Auth / OAuth2 Proxy），并限制上传大小与请求频率。

## 密钥

- 所有密钥只放在 `.env`（已被 `.gitignore` 忽略），不要写进代码或提交到仓库。
- 不要把 `.env`、日志或 `/api/health` 截图发到 Issue 中；如已泄露，请立即在服务商控制台轮换。
- Docker 镜像不包含 `.env`；Compose 通过 `env_file` 在运行时注入。

## 已知边界

- 上传总大小默认限制 256 MB，单次最多 500 个文件（可通过 `MAX_UPLOAD_MB` / `MAX_UPLOAD_FILES` 调整）。
- `book_id` 仅允许 12 位十六进制；文件接口做了目录穿越校验。
- 任务队列是进程内线程，必须单 worker 运行；多 worker 会导致状态不一致。

## 报告漏洞

请通过 GitHub 的 **Private vulnerability reporting / Security Advisories** 私下报告，不要公开 Issue。请在报告中包含：

- 影响版本 / commit；
- 复现步骤或 PoC；
- 影响评估（数据泄露、RCE、DoS 等）。

我们会尽快确认并给出修复计划。