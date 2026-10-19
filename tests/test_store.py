"""存储层：原子写、并发、重启恢复、删除防护。"""
import json
import threading

import pytest

from pipeline import store


def test_atomic_write_survives_concurrency(tmp_path):
    path = tmp_path / "meta.json"
    errors = []

    def worker(i):
        try:
            for j in range(50):
                store.write_json_atomic(path, {"worker": i, "seq": j})
        except Exception as e:  # pragma: no cover - 失败时用于定位
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == {"worker", "seq"}
    assert not list(tmp_path.glob("*.tmp")), "临时文件必须被清理"


def test_write_meta_merge_and_error_reset():
    book_id = store.new_book_id()
    store.init_book(book_id)

    store.write_meta(book_id, {"status": "error", "error": "boom"})
    store.write_meta(book_id, {"status": "tts"})
    meta = store.read_meta(book_id)
    assert meta["status"] == "tts"
    assert meta["error"] is None


def test_recover_incomplete_marks_active_tasks_as_error():
    book_id = store.new_book_id()
    store.init_book(book_id)
    store.write_meta(book_id, {"status": "tts"})

    recovered = store.recover_incomplete()
    assert book_id in recovered
    meta = store.read_meta(book_id)
    assert meta["status"] == "error"
    assert "中断" in meta["error"]


def test_delete_book_rejects_non_book_paths():
    for bad in ("..", ".", "/tmp", "abc", ""):
        with pytest.raises(ValueError):
            store.delete_book(bad)


def test_iter_page_images_sorted(tmp_path, monkeypatch):
    book_id = store.new_book_id()
    d = store.init_book(book_id)
    (d / "pages" / "010.png").write_bytes(b"x")
    (d / "pages" / "002.jpg").write_bytes(b"x")
    (d / "pages" / "notes.txt").write_bytes(b"x")

    names = [p.name for p in store.iter_page_images(book_id)]
    assert names == ["002.jpg", "010.png"]