"""安全边界：book_id 校验、目录穿越、上传上限与文件名清洗。"""
from io import BytesIO

import pytest
from fastapi import HTTPException
from PIL import Image

from api.routes import _check_book_id, _resolve
from pipeline import store


def make_png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (2, 2), (0, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


@pytest.mark.parametrize("bad_id", ["..", ".", "", "../../etc", "0123456789ab/..", "ABC123456789"])
def test_book_id_validation(bad_id):
    with pytest.raises(HTTPException):
        _check_book_id(bad_id)


def test_delete_book_rejects_traversal():
    with pytest.raises(ValueError):
        store.delete_book("..")
    with pytest.raises(ValueError):
        store.delete_book(".")


def test_resolve_rejects_path_traversal():
    book_id = store.new_book_id()
    store.init_book(book_id)

    assert _resolve(book_id, "pages/001.jpg").name == "001.jpg"
    for rel in ("../../config.py", "../" + book_id + "-evil/secret.txt", "/etc/passwd"):
        with pytest.raises(HTTPException):
            _resolve(book_id, rel)


def test_upload_filename_with_path_is_sanitized(client):
    resp = client.post("/api/books", files=[
        ("files", ("../../evil.png", make_png(), "image/png")),
    ])
    assert resp.status_code == 200, resp.text
    book_id = resp.json()["book_id"]
    assert (store.book_dir(book_id) / "pages" / "001.png").exists()
    assert not (store.book_dir(book_id).parent.parent / "evil.png").exists()


def test_upload_body_limit(client, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "max_upload_bytes", 16)
    resp = client.post("/api/books", files=[
        ("files", ("a.png", make_png(), "image/png")),
    ])
    assert resp.status_code == 413


def test_delete_traversal_route_returns_404(client):
    # 即使客户端发送未归一化的 ".."，也不能删除 data 目录
    resp = client.delete("/api/books/%2E%2E")
    assert resp.status_code in (404, 405)
    assert store.BOOKS_DIR.exists()