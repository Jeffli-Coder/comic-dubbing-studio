"""上传 → 完整流水线 → 页面数据（Mock 模式，离线）。"""
from io import BytesIO

from PIL import Image

from conftest import wait_ready


def make_png(color) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (4, 4), color).save(buf, "PNG")
    return buf.getvalue()


def test_png_upload_pipeline_keeps_real_extension(client):
    blue = make_png((0, 0, 255))
    red = make_png((255, 0, 0))

    # 故意乱序上传：服务端应自然排序，2.png 成为第 1 页
    resp = client.post("/api/books", files=[
        ("files", ("10.png", red, "image/png")),
        ("files", ("2.png", blue, "image/png")),
    ])
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["page_count"] == 2
    book_id = data["book_id"]

    status = wait_ready(client, book_id)
    assert status["status"] == "ready", status.get("error")

    page = client.get(f"/api/books/{book_id}/pages/1").json()
    # 关键回归：PNG 不能被写成 pages/001.jpg
    assert page["image_url"].endswith("/pages/001.png")

    image_resp = client.get(page["image_url"])
    assert image_resp.status_code == 200
    assert image_resp.headers["content-type"] == "image/png"
    pixel = Image.open(BytesIO(image_resp.content)).convert("RGB").getpixel((0, 0))
    assert pixel[2] > 200 and pixel[0] < 50  # 第 1 页是蓝色（自然排序生效）

    assert page["timings"]["segments"], "页面时间戳不能为空"
    assert page["lines"], "Mock 视觉应生成台词"

    # 换音色：只重合成该角色，最终仍回到 ready
    character = page["lines"][0]["character"]
    voices = client.get("/api/voices").json()["voices"]
    new_voice = voices[-1]["voice"]
    swap = client.put(f"/api/books/{book_id}/voices",
                      json={"character": character, "voice": new_voice})
    assert swap.status_code == 200, swap.text
    assert wait_ready(client, book_id)["status"] == "ready"


def test_bookshelf_sorted_by_created_at(client):
    ids = []
    for _ in range(2):
        resp = client.post("/api/books", files=[
            ("files", ("1.png", make_png((0, 128, 0)), "image/png")),
        ])
        ids.append(resp.json()["book_id"])
        wait_ready(client, ids[-1])

    shelf = client.get("/api/books").json()["books"]
    assert [b["book_id"] for b in shelf][:2] == list(reversed(ids))


def test_unsupported_file_rejected(client):
    resp = client.post("/api/books", files=[("files", ("a.txt", b"hello", "text/plain"))])
    assert resp.status_code == 400


def test_fake_image_rejected(client):
    resp = client.post("/api/books", files=[("files", ("a.png", b"not really a png", "image/png"))])
    assert resp.status_code == 400