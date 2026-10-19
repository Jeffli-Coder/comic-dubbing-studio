# 贡献指南 / Contributing

感谢你愿意改进这个项目！以下流程适用于所有贡献者。

## 开发环境

```bash
git clone <your-fork-url>
cd comic_dubbing_agent
python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

无需任何 API Key 即可开发：

```bash
MOCK_MODE=1 python server.py
# Windows PowerShell: $env:MOCK_MODE="1"; python server.py
```

Mock 模式使用内置的模拟视觉/LLM/TTS，能完整跑通上传、翻页、逐句高亮与换音色。

## 提交前检查

```bash
pytest -q
ruff check .
docker build -t comic-dubbing-studio .        # 改了 Docker/依赖时
```

CI 会在 Linux / Windows / macOS 上运行同一套测试。

## 代码约定

- Python 3.11+，4 空格缩进，行宽 120。
- 所有外部 AI 能力必须通过 `providers/base.py` 的抽象接口调用，不要在流水线里直连 SDK。
- 修改 Provider 时请同时处理"缺 Key / 服务不可用 → 降级 Mock"的路径。
- 新增磁盘写操作请使用 `pipeline/store.py` 的原子写函数。
- 前端保持零框架、原生 JS。

## 提交 PR

1. 从 `main` 切出功能分支（`feat/xxx`、`fix/xxx`）。
2. 一个 PR 只做一件事；说明动机、改动点和验证方式。
3. 新增行为请附测试；修复 bug 请先写能复现的测试。
4. 不要在 PR 中提交：
   - `.env`、任何 API Key / token；
   - 漫画图片、PDF、台词文本或合成音频（版权风险）；
   - `data/`、`legacy/`、`Vol_01_pages/` 等本地数据。

## 报告问题

请使用 GitHub Issue 模板，并附上：

- 操作系统与 Python / Docker 版本；
- `GET /api/health` 的返回（**先删除任何密钥信息**）；
- 复现步骤与完整错误日志。

安全问题请勿公开提 Issue，见 [SECURITY.md](SECURITY.md)。