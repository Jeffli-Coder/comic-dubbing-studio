"""PDF 逐页转图（pypdfium2）与上传链路。"""
from io import BytesIO

from PIL import Image

from conftest import wait_ready
from pipeline.pdf_import import pdf_to_images


def make_pdf(pages: int = 1) -> bytes:
    buf = BytesIO()
    images = [Image.new("RGB", (120, 160), "white") for _ in range(pages)]
    images[0].save(buf, "PDF", save_all=True, append_images=images[1:])
    return buf.getvalue()


def test_pdf_to_images(tmp_path):
    n = pdf_to_images(make_pdf(2), tmp_path, start_index=1)
    assert n == 2
    assert (tmp_path / "001.jpg").exists()
    assert (tmp_path / "002.jpg").exists()
    with Image.open(tmp_path / "001.jpg") as img:
        assert img.format == "JPEG"
        assert img.width > 0 and img.height > 0


def test_pdf_invalid_bytes(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        pdf_to_images(b"not a pdf", tmp_path)


def test_pdf_upload_pipeline(client):
    resp = client.post("/api/books", files=[
        ("files", ("book.pdf", make_pdf(2), "application/pdf")),
    ])
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["page_count"] == 2
    assert wait_ready(client, data["book_id"])["status"] == "ready"

    page = client.get(f"/api/books/{data['book_id']}/pages/1").json()
    assert page["image_url"].endswith("/pages/001.jpg")
    assert client.get(page["image_url"]).status_code == 200