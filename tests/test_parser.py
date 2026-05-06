import pytest
from pathlib import Path

from app.parser import parse
from tests.conftest import PASS_FILE, FAIL_FILE, STOP_FILE


# ── Filename parsing ──────────────────────────────────────────────────────────

def test_pass_core_fields():
    r = parse(PASS_FILE)
    assert r is not None
    assert r["fixture_id"] == "IQ112EA2387"   # extracted from "Serial number:" line
    assert r["mac1"] == "001F7B6BD20E"
    assert r["mac2"] == "001F7B6BD20F"
    assert r["result"] == "PASS"
    assert r["datetime"] == "2026-01-05T17:19:00"


def test_fail_core_fields():
    r = parse(FAIL_FILE)
    assert r is not None
    assert r["mac1"] == "001F7B6BD21E"
    assert r["result"] == "FAIL"
    assert r["datetime"] == "2026-01-06T09:01:40"


def test_stop_core_fields():
    r = parse(STOP_FILE)
    assert r is not None
    assert r["result"] == "STOP"
    assert r["mac1"] == "AABBCC001100"


def test_invalid_filename_returns_none(tmp_path):
    f = tmp_path / "not_a_valid_log.txt"
    f.write_text("dummy content")
    assert parse(str(f)) is None


def test_missing_file_returns_none():
    assert parse("/nonexistent/path/file_PASS.txt") is None


# ── Duration parsing ──────────────────────────────────────────────────────────

def test_pass_duration():
    r = parse(PASS_FILE)
    assert r["duration"] == "01:14.9"


def test_fail_duration():
    r = parse(FAIL_FILE)
    assert r["duration"] == "01:52.6"


def test_stop_duration():
    r = parse(STOP_FILE)
    assert r["duration"] == "00:04.9"


# ── failed_items ──────────────────────────────────────────────────────────────

def test_pass_has_no_failed_items():
    r = parse(PASS_FILE)
    assert r["failed_items"] == []


def test_stop_has_no_failed_items():
    r = parse(STOP_FILE)
    assert r["failed_items"] == []


def test_fail_has_failed_items():
    r = parse(FAIL_FILE)
    assert len(r["failed_items"]) > 0


def test_fail_contains_per():
    r = parse(FAIL_FILE)
    names = [i["measurement"] for i in r["failed_items"]]
    assert "PER" in names


def test_fail_items_deduplicated():
    r = parse(FAIL_FILE)
    names = [i["measurement"] for i in r["failed_items"]]
    assert len(names) == len(set(names)), "failed_items should have unique measurement names"


def test_fail_item_has_correct_fields():
    r = parse(FAIL_FILE)
    item = next(i for i in r["failed_items"] if i["measurement"] == "PER")
    assert item["unit"] == "%"
    assert isinstance(item["value"], float)
    assert item["limit"] == "(8.0 ~ 0.0)"
    assert item["step_name"] == "WIFI_RX_VERIFY_PER"


def test_fail_item_value_exceeds_limit():
    r = parse(FAIL_FILE)
    item = next(i for i in r["failed_items"] if i["measurement"] == "PER")
    assert item["value"] > 8.0   # 100.0% exceeds upper limit of 8.0%


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_empty_file_returns_record_from_filename(tmp_path):
    name = "STA20_20260417_090000_AABBCC001122_AABBCC001123_PASS.txt"
    f = tmp_path / name
    f.write_text("")
    r = parse(str(f))
    assert r is not None
    assert r["station_id"] == "STA20"
    assert r["result"] == "PASS"
    assert r["duration"] == ""
    assert r["failed_items"] == []

