"""配置解析：布尔/整数容错与测试 DATA_DIR 隔离。"""
import os

from config import DATA_DIR, _env_bool, _env_int, settings


def test_test_data_dir_is_isolated():
    assert "comic-dubbing-test-" in str(DATA_DIR)
    assert settings.mock_mode is True


def test_env_bool_accepts_common_forms(monkeypatch):
    for raw in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("X_FLAG", raw)
        assert _env_bool("X_FLAG") is True
    for raw in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("X_FLAG", raw)
        assert _env_bool("X_FLAG") is False
    monkeypatch.delenv("X_FLAG", raising=False)
    assert _env_bool("X_FLAG", default=True) is True


def test_env_int_tolerates_bad_values(monkeypatch):
    monkeypatch.setenv("X_NUM", "42")
    assert _env_int("X_NUM", 7) == 42
    monkeypatch.setenv("X_NUM", "not-a-number")
    assert _env_int("X_NUM", 7) == 7
    monkeypatch.delenv("X_NUM", raising=False)
    assert _env_int("X_NUM", 9) == 9


def test_server_defaults_are_local_only():
    assert settings.server_host == os.environ["HOST"]
    assert settings.server_port == int(os.environ["PORT"])