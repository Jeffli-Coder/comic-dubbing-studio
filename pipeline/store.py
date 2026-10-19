"""
store — book 文件布局与元数据原子读写。

data/books/{book_id}/
├── meta.json               状态与进度（原子写，临时文件 + os.replace）
├── pages/001.jpg ...       上传原图
├── pages_raw/p001.json     逐页视觉识别原始结果（调试/断点）
├── script.json             按页脚本（含 voice_assignments）
├── lines/                  逐句音频缓存
├── audio/                  每页拼接音频
└── timings/                每页时间戳
"""
import json
import os
import re
import shutil
import tempfile
import threading
import uuid
from pathlib import Path

from config import BOOKS_DIR, DATA_DIR

SUPPORTED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}

# book_id 由 new_book_id() 生成，固定 12 位小写十六进制。
# 所有落盘/删除操作前都要校验，防止 ".." / "." / 绝对路径之类穿越。
_BOOK_ID_RE = re.compile(r"^[0-9a-f]{12}$")

# meta 的读-改-写需要串行化：流水线线程与 API 路由会并发写同一本书
_meta_lock = threading.RLock()

ACTIVE_STATUSES = {"queued", "ocr", "voice_pick", "tts", "concat", "resynth"}


def is_valid_book_id(book_id: str) -> bool:
    return bool(_BOOK_ID_RE.fullmatch(str(book_id or "")))


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)


def new_book_id() -> str:
    return uuid.uuid4().hex[:12]


def book_dir(book_id: str) -> Path:
    return BOOKS_DIR / book_id


def init_book(book_id: str) -> Path:
    d = book_dir(book_id)
    for sub in ("pages", "pages_raw", "lines", "audio", "timings"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def delete_book(book_id: str) -> None:
    if not is_valid_book_id(book_id):
        raise ValueError(f"非法 book_id: {book_id!r}")
    d = book_dir(book_id).resolve()
    # 双重保险：即使 id 校验被绕过，也绝不允许删除 books 目录之外的内容
    if d.parent != BOOKS_DIR.resolve():
        raise ValueError(f"拒绝删除非书籍目录: {d}")
    if d.exists():
        shutil.rmtree(d)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, OSError):
        return default


def write_json_atomic(path: Path, data) -> None:
    """临时文件 + os.replace，避免读到半截 JSON；mkstemp 避免并发同名 tmp 冲突。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def read_meta(book_id: str) -> dict:
    return read_json(book_dir(book_id) / "meta.json", default={})


def write_meta(book_id: str, patch: dict) -> dict:
    """合并写 meta（原子）。返回最新 meta。"""
    with _meta_lock:
        meta = read_meta(book_id)
        if meta.get("status") == "error" and "status" in patch and patch["status"] != "error":
            meta["error"] = None    # 重跑时清掉错误标记
        meta.update(patch)
        write_json_atomic(book_dir(book_id) / "meta.json", meta)
        return meta


def recover_incomplete() -> list:
    """启动时把上次进程中断的任务标记为 error（daemon 线程随进程结束，不会自己恢复）。

    返回被标记的 book_id 列表；用户可在网页上点「重试」断点续跑。
    """
    if not BOOKS_DIR.exists():
        return []
    recovered = []
    for d in BOOKS_DIR.iterdir():
        if not d.is_dir() or not is_valid_book_id(d.name):
            continue
        meta = read_meta(d.name)
        if meta.get("status") in ACTIVE_STATUSES:
            write_meta(d.name, {
                "status": "error",
                "error": "服务重启导致任务中断；点击「重试处理」可断点续跑（已完成部分不会重做）",
            })
            recovered.append(d.name)
    return recovered


def read_script(book_id: str) -> dict:
    return read_json(book_dir(book_id) / "script.json", default={})


def iter_page_images(book_id: str) -> list:
    """按文件名排序的页面图片路径列表。"""
    d = book_dir(book_id) / "pages"
    if not d.exists():
        return []
    return sorted(
        p for p in d.iterdir() if p.suffix.lower() in SUPPORTED_IMAGE_EXT
    )