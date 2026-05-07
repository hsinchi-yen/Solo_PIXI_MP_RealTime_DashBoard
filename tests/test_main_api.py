import json
import shutil
import uuid
from pathlib import Path

import pytest
from fastapi import Request

from app import main


def _make_base_dir():
    root = main.BASE_DIR / "tests" / f"_tmp_api_{uuid.uuid4().hex}"
    child = root / "child"
    child.mkdir(parents=True, exist_ok=True)
    return root, child


def _localhost_request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "headers": [(b"host", b"localhost:8080")],
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "path": "/",
        "query_string": b"",
        "server": ("localhost", 8080),
    }
    return Request(scope)


async def test_set_log_dir_missing_returns_400():
    resp = await main.set_log_dir(_localhost_request(), {})
    assert resp.status_code == 400


async def test_set_log_dir_rejects_outside_allowed(tmp_path):
    resp = await main.set_log_dir(_localhost_request(), {"log_dir": str(tmp_path)})
    assert resp.status_code == 403


async def test_set_log_dir_nonexistent_returns_404():
    missing = main.BASE_DIR / "tests" / f"_missing_{uuid.uuid4().hex}"
    resp = await main.set_log_dir(_localhost_request(), {"log_dir": str(missing)})
    assert resp.status_code == 404


async def test_browse_dir_outside_allowlist_falls_back(tmp_path):
    resp = await main.browse_dir(_localhost_request(), str(tmp_path))
    data = json.loads(resp.body)
    expected = main.config.paths.log_dir.resolve()
    if not expected.exists():
        expected = main.BASE_DIR.resolve()
    assert Path(data["current"]).resolve() == expected


async def test_set_log_dir_allows_within_base_dir(monkeypatch):
    root, _ = _make_base_dir()
    original = main.config.paths.log_dir

    async def _noop_scan(_):
        return None

    monkeypatch.setattr(main, "_startup_scan", _noop_scan)
    monkeypatch.setattr(main, "start_watcher", lambda *args, **kwargs: None)
    try:
        resp = await main.set_log_dir(_localhost_request(), {"log_dir": str(root)})
        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert Path(data["log_dir"]).resolve() == root.resolve()
    finally:
        main.config.paths.log_dir = original
        shutil.rmtree(root, ignore_errors=True)


async def test_set_log_dir_accepts_relative_path(monkeypatch):
    root, _ = _make_base_dir()
    original = main.config.paths.log_dir
    rel = root.relative_to(main.BASE_DIR)

    async def _noop_scan(_):
        return None

    monkeypatch.setattr(main, "_startup_scan", _noop_scan)
    monkeypatch.setattr(main, "start_watcher", lambda *args, **kwargs: None)
    try:
        resp = await main.set_log_dir(_localhost_request(), {"log_dir": str(rel)})
        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert Path(data["log_dir"]).resolve() == root.resolve()
    finally:
        main.config.paths.log_dir = original
        shutil.rmtree(root, ignore_errors=True)


async def test_browse_dir_allowed_path_lists_children():
    root, child = _make_base_dir()
    try:
        resp = await main.browse_dir(_localhost_request(), str(root))
        data = json.loads(resp.body)
        assert Path(data["current"]).resolve() == root.resolve()
        assert child.name in data["dirs"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def test_browse_dir_walks_up_from_file():
    root, _ = _make_base_dir()
    target = root / "log.txt"
    target.write_text("dummy", encoding="utf-8")
    try:
        resp = await main.browse_dir(_localhost_request(), str(target))
        data = json.loads(resp.body)
        assert Path(data["current"]).resolve() == root.resolve()
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def test_set_log_dir_allows_within_work_order_root(monkeypatch):
    root = main.BASE_DIR / "tests" / f"_tmp_wo_{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    original = main.config.paths.log_dir

    async def _noop_scan(_):
        return None

    monkeypatch.setattr(main, "WORK_ORDER_ROOT", root)
    monkeypatch.setattr(main, "_startup_scan", _noop_scan)
    monkeypatch.setattr(main, "start_watcher", lambda *args, **kwargs: None)
    try:
        resp = await main.set_log_dir(_localhost_request(), {"log_dir": str(root)})
        assert resp.status_code == 200
    finally:
        main.config.paths.log_dir = original
        shutil.rmtree(root, ignore_errors=True)


async def test_browse_dir_defaults_to_work_order_root_when_available(monkeypatch):
    root = main.BASE_DIR / "tests" / f"_tmp_wo_browse_{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        monkeypatch.setattr(main, "WORK_ORDER_ROOT", root)
        resp = await main.browse_dir(_localhost_request(), "")
        data = json.loads(resp.body)
        assert Path(data["current"]).resolve() == root.resolve()
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# _find_wo_dir tests
# ---------------------------------------------------------------------------


def _make_wo_root(tmp_path: Path) -> Path:
    wo_root = tmp_path / f"wo_root_{uuid.uuid4().hex}"
    wo_root.mkdir(parents=True)
    return wo_root


def test_find_wo_dir_returns_none_when_root_missing(monkeypatch, tmp_path):
    missing = tmp_path / "nonexistent"
    monkeypatch.setattr(main, "WORK_ORDER_ROOT", missing)
    assert main._find_wo_dir("5101-260129012") is None


def test_find_wo_dir_matches_plain_name(monkeypatch, tmp_path):
    wo_root = _make_wo_root(tmp_path)
    wo_dir = wo_root / "5101-260129012"
    wo_dir.mkdir()
    monkeypatch.setattr(main, "WORK_ORDER_ROOT", wo_root)

    result = main._find_wo_dir("5101-260129012")
    assert result == wo_dir


def test_find_wo_dir_matches_bracket_named_dir(monkeypatch, tmp_path):
    wo_root = _make_wo_root(tmp_path)
    wo_dir = wo_root / "[5101-260129012]"
    wo_dir.mkdir()
    monkeypatch.setattr(main, "WORK_ORDER_ROOT", wo_root)

    result = main._find_wo_dir("5101-260129012")
    assert result == wo_dir


def test_find_wo_dir_bracket_with_prefix_text(monkeypatch, tmp_path):
    wo_root = _make_wo_root(tmp_path)
    wo_dir = wo_root / "WO [5101-260129012] DONE"
    wo_dir.mkdir()
    monkeypatch.setattr(main, "WORK_ORDER_ROOT", wo_root)

    result = main._find_wo_dir("5101-260129012")
    assert result == wo_dir


def test_find_wo_dir_returns_none_when_no_match(monkeypatch, tmp_path):
    wo_root = _make_wo_root(tmp_path)
    (wo_root / "[9999-000000000]").mkdir()
    monkeypatch.setattr(main, "WORK_ORDER_ROOT", wo_root)

    assert main._find_wo_dir("5101-260129012") is None


def test_find_wo_dir_ignores_files_not_dirs(monkeypatch, tmp_path):
    wo_root = _make_wo_root(tmp_path)
    (wo_root / "5101-260129012").write_text("not a dir")
    monkeypatch.setattr(main, "WORK_ORDER_ROOT", wo_root)

    assert main._find_wo_dir("5101-260129012") is None


# ---------------------------------------------------------------------------
# path_health API tests
# ---------------------------------------------------------------------------


async def test_path_health_empty_wo(monkeypatch, tmp_path):
    wo_root = _make_wo_root(tmp_path)
    monkeypatch.setattr(main, "WORK_ORDER_ROOT", wo_root)

    resp = await main.path_health(wo="")
    data = json.loads(resp.body)

    assert data["wo"] == ""
    assert data["wo_path"] == ""
    assert data["wo_path_exists"] is False


async def test_path_health_wo_found_via_bracket_dir(monkeypatch, tmp_path):
    wo_root = _make_wo_root(tmp_path)
    wo_dir = wo_root / "[5101-260129012]"
    wo_dir.mkdir()
    monkeypatch.setattr(main, "WORK_ORDER_ROOT", wo_root)

    resp = await main.path_health(wo="5101-260129012")
    data = json.loads(resp.body)

    assert data["wo"] == "5101-260129012"
    assert data["wo_path_exists"] is True
    assert Path(data["wo_path"]).resolve() == wo_dir.resolve()


async def test_path_health_wo_not_found_returns_fallback_path(monkeypatch, tmp_path):
    wo_root = _make_wo_root(tmp_path)
    monkeypatch.setattr(main, "WORK_ORDER_ROOT", wo_root)

    resp = await main.path_health(wo="5101-260129012")
    data = json.loads(resp.body)

    assert data["wo"] == "5101-260129012"
    assert data["wo_path_exists"] is False
    # Fallback path is wo_root / wo_name
    assert data["wo_path"] != ""
    assert "5101-260129012" in data["wo_path"]


async def test_path_health_wo_root_reflects_monkeypatched_root(monkeypatch, tmp_path):
    wo_root = _make_wo_root(tmp_path)
    monkeypatch.setattr(main, "WORK_ORDER_ROOT", wo_root)

    resp = await main.path_health(wo="")
    data = json.loads(resp.body)

    assert Path(data["wo_root"]).resolve() == wo_root.resolve()
    assert data["wo_root_exists"] is True


@pytest.mark.parametrize("wo_input,expected_wo", [
    ("  5101-260129012  ", "5101-260129012"),  # strips whitespace
    ("5101-260129012", "5101-260129012"),
])
async def test_path_health_strips_wo_whitespace(monkeypatch, tmp_path, wo_input, expected_wo):
    wo_root = _make_wo_root(tmp_path)
    monkeypatch.setattr(main, "WORK_ORDER_ROOT", wo_root)

    resp = await main.path_health(wo=wo_input)
    data = json.loads(resp.body)

    assert data["wo"] == expected_wo
