"""
pdf_import — PDF 漫画逐页转图（pypdfium2 渲染，无外部二进制依赖）

使用 pypdfium2（PDFium，Apache-2.0 / BSD-3-Clause）而非 PyMuPDF（AGPL-3.0），
以便整个项目以 MIT 协议分发。
"""
from pathlib import Path

ZOOM = 2.0        # 72dpi × 2 ≈ 144dpi，兼顾 OCR 清晰度与文件体积
MAX_DIM = 2600    # 渲染后最长边像素上限（防止页面尺寸异常的 PDF 渲染出巨图）
JPG_QUALITY = 85
MAX_PAGES = 500   # 防误传超大文档
MAX_PAGE_FILES = 999  # 三位数文件名上限


def pdf_to_images(pdf_bytes: bytes, dest_dir: Path, *, start_index: int = 1) -> int:
    """
    把 PDF 逐页渲染为 JPEG 写入 dest_dir，文件名从 {start_index:03d}.jpg 起编号。
    返回写入的页数。解析失败抛 ValueError（由路由层转 400）。
    """
    try:
        import pypdfium2 as pdfium
    except ImportError as e:
        raise ValueError("服务端未安装 PDF 支持：请执行 pip install pypdfium2 pillow") from e

    if not pdf_bytes:
        raise ValueError("PDF 文件为空")

    try:
        doc = pdfium.PdfDocument(pdf_bytes)
    except Exception as e:
        raise ValueError(f"PDF 解析失败: {e}") from e

    try:
        n = len(doc)
        if n == 0:
            raise ValueError("PDF 没有任何页面")
        if n > MAX_PAGES:
            raise ValueError(f"PDF 共 {n} 页，超过单次上限 {MAX_PAGES} 页")
        if start_index + n - 1 > MAX_PAGE_FILES:
            raise ValueError(f"页面编号超过 {MAX_PAGE_FILES}，无法使用三位文件名")

        for i in range(n):
            page = doc[i]
            try:
                width, height = page.get_size()
                long_side = max(width, height)
                scale = min(ZOOM, MAX_DIM / long_side) if long_side else ZOOM
                bitmap = page.render(scale=scale)
                try:
                    image = bitmap.to_pil().convert("RGB")
                    try:
                        image.save(str(dest_dir / f"{start_index + i:03d}.jpg"),
                                   "JPEG", quality=JPG_QUALITY)
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
        return n
    finally:
        doc.close()