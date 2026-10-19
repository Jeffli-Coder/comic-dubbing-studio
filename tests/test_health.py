"""健康检查与 Mock 模式。"""
from providers import DEGRADED


def test_health_reports_mock_mode_without_duplicate_degradation(client):
    first = client.get("/api/health").json()
    assert first["mock_mode"] is True
    assert first["providers"] == {"tts": "mock", "vision": "mock", "llm": "mock"}
    assert first["version"]

    for _ in range(3):
        again = client.get("/api/health").json()
        assert again["degraded"] == first["degraded"] == DEGRADED


def test_voices_catalog(client):
    data = client.get("/api/voices").json()
    assert len(data["voices"]) == 50
    assert all({"name", "voice", "gender", "age", "trait"} <= set(v) for v in data["voices"])