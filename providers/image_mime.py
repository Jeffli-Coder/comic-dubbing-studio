"""
image_mime — 通过文件头魔数识别图片/PDF 类型。

用途：
1. 上传时校验内容与扩展名是否一致，并按真实类型落盘（避免 .png 里塞 JPEG）；
2. 视觉模型请求时发送正确的 data:<mime>;base64（原先一律写死 image/jpeg）。
不引入额外图片库，只做几个固定字节判断。
"""

EXT_FOR_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def sniff_image_mime(data: bytes) -> str | None:
    """返回 image/jpeg | image/png | image/webp；无法识别返回 None。"""
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def sniff_is_pdf(data: bytes) -> bool:
    # PDF 规范允许 %PDF- 出现在前 1024 字节内
    return b"%PDF-" in data[:1024]