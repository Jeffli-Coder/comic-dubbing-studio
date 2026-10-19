# Third-Party Notices

This project is licensed under the MIT License (see `LICENSE`). It depends on
the following third-party software. This list is informational and is not a
substitute for the license texts shipped with each package.

## Python dependencies

| Package | License | Purpose |
|---|---|---|
| FastAPI / Starlette / Uvicorn | MIT / BSD-3-Clause | HTTP service |
| Pydantic | MIT | Request/response models |
| python-multipart | Apache-2.0 | Multipart uploads |
| OpenAI Python SDK | Apache-2.0 | DeepSeek / Qwen OpenAI-compatible APIs |
| DashScope Python SDK | Apache-2.0 | Qwen TTS WebSocket |
| requests | Apache-2.0 | Fish Audio provider |
| python-dotenv | BSD-3-Clause | `.env` loading |
| imageio-ffmpeg | BSD-2-Clause (bundled FFmpeg binaries are GPL/LGPL) | Bundled ffmpeg fallback |
| pypdfium2 / PDFium | Apache-2.0 / BSD-3-Clause | PDF page rendering |
| Pillow | HPND | PDF page image encoding |

## System packages (Docker image)

| Package | License | Purpose |
|---|---|---|
| Debian `ffmpeg` | LGPL-2.1+ / GPL-2.0+ depending on build options | Audio decode/encode/concat |
| Debian `gosu` | Apache-2.0 | Drop privileges in the container entrypoint |
| Debian `ca-certificates` | MPL-2.0 | Outbound TLS trust store |

## AI services

The default pipeline calls external services (DeepSeek, Alibaba Cloud
DashScope/Bailian). Their terms of service, data handling, and pricing apply
to your use of those APIs. This repository does not bundle their models.

## Copyrighted content

The repository intentionally contains **no manga pages, dialogue, or audio**.
Please only upload material you have the right to use. Test fixtures in
`tests/` are generated programmatically (solid-color images and synthetic
dialogue) and are not derived from any published work.