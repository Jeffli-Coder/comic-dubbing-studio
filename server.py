"""
漫画翻页听书 — 服务入口
启动: python server.py   →  http://127.0.0.1:8080
Docker: HOST=0.0.0.0 DATA_DIR=/data python server.py
"""
import logging
import sys

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.routes import router
from config import STATIC_DIR, __version__, settings
from pipeline import store

# Windows 英文/西欧语言控制台默认不是 UTF-8，打印中文会 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def create_app() -> FastAPI:
    store.ensure_dirs()
    recovered = store.recover_incomplete()
    if recovered:
        logging.getLogger(__name__).warning(
            "检测到 %d 个上次中断的任务，已标记为 error（可在网页点击重试续跑）", len(recovered))

    app = FastAPI(title="漫画翻页听书", version=__version__)

    @app.middleware("http")
    async def limit_upload_body(request: Request, call_next):
        """在读取整个 body 之前，用 Content-Length 挡住明显超限的上传。"""
        if request.method == "POST" and request.url.path == "/api/books":
            raw = request.headers.get("content-length")
            if raw and raw.isdigit() and int(raw) > settings.max_upload_bytes:
                return JSONResponse(
                    {"detail": f"上传内容超过 {settings.max_upload_mb} MB 上限"},
                    status_code=413,
                )
        return await call_next(request)

    app.include_router(router)
    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app


app = create_app()

if __name__ == "__main__":
    shown = "127.0.0.1" if settings.server_host in ("0.0.0.0", "::") else settings.server_host
    print("=" * 50)
    print("漫画翻页听书  http://%s:%d" % (shown, settings.server_port))
    print("  /api/health   服务与 Provider 自检")
    print("  /api/voices   50 种千问音色清单")
    if settings.mock_mode:
        print("  当前为 MOCK_MODE：无需 API Key / ffmpeg 即可体验完整流程")
    print("=" * 50)
    uvicorn.run(app, host=settings.server_host, port=settings.server_port)