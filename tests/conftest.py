"""pytest 全局配置：必须在 import config/server 之前设置环境变量。"""
import os
import shutil
import tempfile
import time

import pytest

# config.py 在 import 时读取环境变量；使用临时 DATA_DIR 避免污染仓库。
# load_dotenv(override=False) 保证开发者本地 .env 不会覆盖这里的测试配置。
_TEST_DATA_DIR = tempfile.mkdtemp(prefix="comic-dubbing-test-")
os.environ.update({
    "DATA_DIR": _TEST_DATA_DIR,
    "MOCK_MODE": "1",
    "TTS_PROVIDER": "mock",
    "VISION_PROVIDER": "mock",
    "LLM_PROVIDER": "mock",
    "HOST": "127.0.0.1",
    "PORT": "8080",
})


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from server import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_books():
    """每个测试前后等待后台任务结束并清空书籍目录。"""
    from pipeline import store
    from pipeline.tasks import registry

    registry.join_all(10)
    store.ensure_dirs()
    for d in store.BOOKS_DIR.iterdir():
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
    yield
    registry.join_all(10)


def wait_ready(client, book_id: str, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get(f"/api/books/{book_id}/progress").json()
        if status.get("status") in {"ready", "error"}:
            return status
        time.sleep(0.05)
    raise AssertionError(f"book {book_id} did not finish within {timeout}s")