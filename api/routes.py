"""
routes — 漫画翻页听书全部 REST 端点（FastAPI Router）。
静态页面由 server.py 挂载；书籍文件经 /files 端点带路径守卫输出。
"""
import datetime
import re
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from config import QWEN_VOICES, __version__, settings
from pipeline import store
from pipeline.orchestrator import BookPipeline
from pipeline.pdf_import import pdf_to_images
from pipeline.tasks import registry
from providers import DEGRADED, get_llm, get_tts, get_vision, has_ffmpeg
from providers.image_mime import EXT_FOR_MIME, sniff_image_mime, sniff_is_pdf

router = APIRouter(prefix="/api")

MEDIA = {
    ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
    ".json": "application/json",
}

VOICE_VALUES = {v["voice"] for v in QWEN_VOICES}

# 三位数文件名（001.jpg）最多支持 999 页
MAX_PAGE_FILES = 999


def _new_pipeline(book_id: str) -> BookPipeline:
    return BookPipeline(book_id, get_vision(), get_llm(), get_tts())


def _check_book_id(book_id: str) -> str:
    """book_id 必须是我们生成的 12 位十六进制串。

    这既是输入合法性校验，也是防止 ".." / "." 进入 store.delete_book()
    导致删除整个 data 目录的安全边界。
    """
    if not store.is_valid_book_id(book_id):
        raise HTTPException(404, "书籍不存在")
    return book_id


def _basename(name: str | None) -> str:
    """只取文件名，兼容浏览器/命令行传来的 Windows 或 POSIX 路径。"""
    return PurePosixPath((name or "").replace("\\", "/")).name


def _natural_key(name: str):
    """自然排序：2.jpg 排在 10.jpg 前面。"""
    return [(0, int(t)) if t.isdigit() else (1, t.lower())
            for t in re.split(r"(\d+)", name)]


def _resolve(book_id: str, rel: str) -> Path:
    """防目录穿越：相对路径必须落在书目录内。"""
    _check_book_id(book_id)
    base = store.book_dir(book_id).resolve()
    target = (base / rel).resolve()
    if not target.is_relative_to(base):
        raise HTTPException(400, "非法路径")
    return target


def _file_url(book_id: str, rel: str) -> str:
    return f"/api/books/{book_id}/files/{rel.replace(chr(92), '/')}"


# ══════════════════════════════════════════════════════════
# 上传 / 书架 / 详情
# ═══════════════════════════════════════════════════════════
def _persist_uploads(book_dir: Path, items: list) -> int:
    """把上传文件按顺序落盘为 pages/ 。图片直接写；PDF 逐页转图。返回页面总数。"""
    pages_dir = book_dir / "pages"
    saved = 0
    for name, data in items:
        ext = PurePosixPath(name).suffix.lower()
        if ext in store.SUPPORTED_IMAGE_EXT:
            mime = sniff_image_mime(data)
            if mime is None:
                raise ValueError(f"{name}: 不是有效的 JPG/PNG/WebP 图片")
            if saved >= MAX_PAGE_FILES:
                raise ValueError(f"页面数量超过 {MAX_PAGE_FILES} 页上限")
            # 按真实类型落盘（扩展名与内容不一致时也能正确显示）
            (pages_dir / f"{saved + 1:03d}{EXT_FOR_MIME[mime]}").write_bytes(data)
            saved += 1
        elif ext == ".pdf":
            if not sniff_is_pdf(data):
                raise ValueError(f"{name}: 不是有效的 PDF 文件")
            saved += pdf_to_images(data, pages_dir, start_index=saved + 1)
        if saved > MAX_PAGE_FILES:
            raise ValueError(f"页面数量超过 {MAX_PAGE_FILES} 页上限")
    return saved


@router.post("/books")
async def upload_book(files: list[UploadFile] = File(...)):
    """上传漫画页图片或 PDF（按文件名排序，PDF 逐页展开）→ 起后台识别+配音流水线。"""
    if not files:
        raise HTTPException(400, "请选择至少一个文件")
    if len(files) > settings.max_upload_files:
        raise HTTPException(400, f"一次最多上传 {settings.max_upload_files} 个文件")

    # 先全部读入内存（await），再把落盘/转图（CPU 密集）放到线程池，避免阻塞事件循环
    read_items = []
    total = 0
    for f in sorted(files, key=lambda x: _natural_key(_basename(x.filename))):
        buf = bytearray()
        while chunk := await f.read(1024 * 1024):
            total += len(chunk)
            if total > settings.max_upload_bytes:
                raise HTTPException(413, f"上传内容超过 {settings.max_upload_mb} MB 上限")
            buf.extend(chunk)
        read_items.append((_basename(f.filename), bytes(buf)))

    store.ensure_dirs()
    book_id = store.new_book_id()
    d = store.init_book(book_id)

    try:
        saved = await run_in_threadpool(_persist_uploads, d, read_items)
    except ValueError as e:
        store.delete_book(book_id)
        raise HTTPException(400, str(e))
    if saved == 0:
        store.delete_book(book_id)
        raise HTTPException(400, "没有可用的文件（支持 jpg/jpeg/png/webp 图片，或 pdf 文档）")

    store.write_meta(book_id, {
        "book_id": book_id,
        "title": "（处理中）",
        "created_at": datetime.datetime.now().isoformat(timespec="microseconds"),
        "page_count": saved,
        "status": "queued",
        "progress": {"stage": "queued", "done": 0, "total": 0},
        "auto_turn": True,
        "error": None,
        "last_voice_swap": None,
    })
    registry.submit(book_id, _new_pipeline(book_id).run)
    return {"book_id": book_id, "page_count": saved}


@router.get("/books")
def list_books():
    store.ensure_dirs()
    items = []
    for d in store.BOOKS_DIR.iterdir():
        if not d.is_dir() or not store.is_valid_book_id(d.name):
            continue
        meta = store.read_meta(d.name)
        if not meta:
            continue
        items.append({
            "book_id": meta.get("book_id", d.name),
            "title": meta.get("title", ""),
            "status": meta.get("status", ""),
            "created_at": meta.get("created_at", ""),
            "page_count": meta.get("page_count", 0),
            "stage": (meta.get("progress") or {}).get("stage", ""),
            "alive": registry.is_running(d.name),
        })
    # 按创建时间倒序（目录名是随机 id，不能按目录名排序）
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"books": items}


@router.get("/books/{book_id}")
def get_book(book_id: str):
    _check_book_id(book_id)
    meta = store.read_meta(book_id)
    if not meta:
        raise HTTPException(404, "书籍不存在")
    script = store.read_script(book_id)
    return {
        **meta,
        "alive": registry.is_running(book_id),
        "title": script.get("title") or meta.get("title", ""),
        "characters": script.get("characters", []),
        "voice_assignments": script.get("voice_assignments", {}),
    }


@router.get("/books/{book_id}/progress")
def book_progress(book_id: str):
    _check_book_id(book_id)
    return registry.status(book_id)


@router.post("/books/{book_id}/rerun")
def rerun_book(book_id: str):
    """error 后重跑（断点续跑：已合成台词自动复用）。"""
    _check_book_id(book_id)
    if registry.is_running(book_id):
        raise HTTPException(409, "任务正在运行")
    if not store.read_meta(book_id):
        raise HTTPException(404, "书籍不存在")
    try:
        registry.submit(book_id, _new_pipeline(book_id).run)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@router.delete("/books/{book_id}")
def delete_book(book_id: str):
    _check_book_id(book_id)
    if registry.is_running(book_id):
        raise HTTPException(409, "任务正在运行，无法删除")
    try:
        store.delete_book(book_id)
    except OSError as e:
        # Windows 上文件可能仍被播放中的客户端占用
        raise HTTPException(409, f"删除失败，文件可能正在被使用: {e}")
    return {"ok": True}


# ═══════════════════════════════════════════════════════════
# 单页播放包 / 文件 / 脚本
# ═══════════════════════════════════════════════════════════
@router.get("/books/{book_id}/pages/{n}")
def get_page(book_id: str, n: int):
    _check_book_id(book_id)
    timings = store.read_json(store.book_dir(book_id) / "timings" / f"page_{n:03d}.json")
    if not timings:
        raise HTTPException(404, f"第 {n} 页尚未合成")
    script = store.read_script(book_id)
    page = next((p for p in script.get("pages", []) if p.get("page_num") == n), None)
    if page is None:
        raise HTTPException(404, f"脚本中没有第 {n} 页")
    return {
        "page_num": n,
        "image_url": _file_url(book_id, page.get("image", f"pages/{n:03d}.jpg")),
        "audio_url": _file_url(book_id, timings["audio_file"]) if timings.get("audio_file") else None,
        "timings": timings,
        "lines": page.get("lines", []),
        "page_notes": page.get("page_notes", ""),
    }


@router.get("/books/{book_id}/files/{rel:path}")
def get_file(book_id: str, rel: str):
    target = _resolve(book_id, rel)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "文件不存在")
    return FileResponse(str(target),
                        media_type=MEDIA.get(target.suffix.lower(), "application/octet-stream"),
                        headers={"Cache-Control": "no-cache"})  # 强制浏览器回源校验，换音色后能拿到新音频


@router.get("/books/{book_id}/script")
def get_script(book_id: str):
    _check_book_id(book_id)
    script = store.read_script(book_id)
    if not script:
        raise HTTPException(404, "脚本尚未生成")
    return script


# ═══════════════════════════════════════════════════════════
# 音色：清单 / 换角色音色（仅重合成该角色）
# ═══════════════════════════════════════════════════════════
class VoiceBody(BaseModel):
    character: str
    voice: str


@router.get("/voices")
def list_voices():
    return {"voices": QWEN_VOICES, "note": "来自 config.QWEN_VOICES（共 %d 种）" % len(QWEN_VOICES)}


@router.put("/books/{book_id}/voices")
def swap_voice(book_id: str, body: VoiceBody):
    _check_book_id(book_id)
    if body.voice not in VOICE_VALUES:
        raise HTTPException(400, "音色不在 50 音色清单中")
    meta = store.read_meta(book_id)
    if not meta:
        raise HTTPException(404, "书籍不存在")
    if registry.is_running(book_id):
        raise HTTPException(409, "有任务正在运行，请稍候")
    if meta.get("status") not in ("ready", "error"):
        raise HTTPException(409, f"当前状态 {meta.get('status')}，合成完成后才能换音色")
    script = store.read_script(book_id)
    if not script or not script.get("pages"):
        raise HTTPException(409, "脚本尚未生成")
    try:
        registry.submit(book_id, _new_pipeline(book_id).resynth_voice, body.character, body.voice)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "character": body.character, "voice": body.voice}


class AutoTurnBody(BaseModel):
    enabled: bool


@router.put("/books/{book_id}/auto-turn")
def set_auto_turn(book_id: str, body: AutoTurnBody):
    _check_book_id(book_id)
    if not store.read_meta(book_id):
        raise HTTPException(404, "书籍不存在")
    store.write_meta(book_id, {"auto_turn": bool(body.enabled)})
    return {"ok": True, "auto_turn": bool(body.enabled)}


# ═══════════════════════════════════════════════════════════
# 健康自检
# ═══════════════════════════════════════════════════════════
@router.get("/health")
def health():
    tts, vision, llm = get_tts(), get_vision(), get_llm()
    return {
        "version": __version__,
        "providers": {"tts": tts.name, "vision": vision.name, "llm": llm.name},
        "mock_mode": settings.mock_mode,
        "ffmpeg": has_ffmpeg(),
        "data_dir": str(store.DATA_DIR),
        "max_upload_mb": settings.max_upload_mb,
        "degraded": DEGRADED,
    }