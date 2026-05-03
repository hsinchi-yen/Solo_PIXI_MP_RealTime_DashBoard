import pytest
from app.state import DashboardState
from app.parser import ParsedLog


# ── Fixture helpers ───────────────────────────────────────────────────────────

class _DashCfg:
    recent_records_limit = 50
    uph_window_minutes = 60
    yield_warning_threshold = 90.0
    yield_critical_threshold = 80.0

class _Cfg:
    dashboard = _DashCfg()


def _rec(mac1: str, result: str, dt: str = "2026-04-17T09:00:00",
         failed_items=None) -> ParsedLog:
    return ParsedLog(
        filename=f"f_{mac1}_{result}.txt",
        fixture_id="5101-001",
        datetime=dt,
        mac1=mac1,
        mac2="000000000000",
        result=result,
        duration="00:10.0",
        failed_items=failed_items or [],
    )


@pytest.fixture
def state():
    return DashboardState(_Cfg())


# ── Basic counts ──────────────────────────────────────────────────────────────

async def test_ingest_pass_increments_pass(state):
    await state.ingest(_rec("AA", "PASS"))
    assert state.pass_count == 1
    assert state.fail_count == 0
    assert state.stop_count == 0


async def test_ingest_fail_increments_fail(state):
    await state.ingest(_rec("AA", "FAIL"))
    assert state.fail_count == 1
    assert state.pass_count == 0


async def test_ingest_stop_increments_stop(state):
    await state.ingest(_rec("AA", "STOP"))
    assert state.stop_count == 1


# ── PASS deduplication ────────────────────────────────────────────────────────

async def test_newer_pass_replaces_older(state):
    await state.ingest(_rec("AA", "PASS", "2026-04-17T09:00:00"))
    await state.ingest(_rec("AA", "PASS", "2026-04-17T10:00:00"))
    assert state.pass_count == 1
    assert state.pass_records["AA"]["datetime"] == "2026-04-17T10:00:00"


async def test_older_pass_does_not_replace_newer(state):
    await state.ingest(_rec("AA", "PASS", "2026-04-17T10:00:00"))
    await state.ingest(_rec("AA", "PASS", "2026-04-17T09:00:00"))
    assert state.pass_count == 1
    assert state.pass_records["AA"]["datetime"] == "2026-04-17T10:00:00"


async def test_different_mac1_each_counted(state):
    await state.ingest(_rec("AA", "PASS"))
    await state.ingest(_rec("BB", "PASS"))
    assert state.pass_count == 2


# ── FAIL deduplication (new: same MAC1 = counted once) ───────────────────────

async def test_fail_same_mac_counted_once(state):
    await state.ingest(_rec("AA", "FAIL"))
    await state.ingest(_rec("AA", "FAIL"))
    assert state.fail_count == 1


async def test_fail_different_macs_each_counted(state):
    await state.ingest(_rec("AA", "FAIL"))
    await state.ingest(_rec("BB", "FAIL"))
    assert state.fail_count == 2


async def test_fail_overridden_by_pass(state):
    await state.ingest(_rec("AA", "FAIL"))
    await state.ingest(_rec("AA", "PASS"))
    assert state.pass_count == 1
    assert state.fail_count == 0
    assert state.total_count == 1


async def test_stop_overridden_by_fail(state):
    await state.ingest(_rec("AA", "STOP"))
    await state.ingest(_rec("AA", "FAIL"))
    assert state.stop_count == 0
    assert state.fail_count == 1


async def test_stop_overridden_by_pass(state):
    await state.ingest(_rec("AA", "STOP"))
    await state.ingest(_rec("AA", "PASS"))
    assert state.stop_count == 0
    assert state.pass_count == 1


async def test_pass_not_downgraded_by_fail(state):
    await state.ingest(_rec("AA", "PASS"))
    await state.ingest(_rec("AA", "FAIL"))
    assert state.pass_count == 1
    assert state.fail_count == 0


async def test_total_count_unique_macs(state):
    await state.ingest(_rec("AA", "PASS"))
    await state.ingest(_rec("AA", "FAIL"))  # same MAC, upgrade already PASS
    await state.ingest(_rec("BB", "FAIL"))
    await state.ingest(_rec("CC", "STOP"))
    assert state.total_count == 3  # AA, BB, CC


# ── Yield rate ────────────────────────────────────────────────────────────────

async def test_yield_rate_all_pass(state):
    await state.ingest(_rec("AA", "PASS"))
    await state.ingest(_rec("BB", "PASS"))
    assert state.yield_rate == 100.0


async def test_yield_rate_mixed(state):
    await state.ingest(_rec("AA", "PASS"))
    await state.ingest(_rec("BB", "PASS"))
    await state.ingest(_rec("CC", "FAIL"))
    assert state.yield_rate == pytest.approx(66.7, abs=0.1)


async def test_yield_rate_no_records(state):
    assert state.yield_rate == 0.0


# ── failure_stats ─────────────────────────────────────────────────────────────

async def test_failure_stats_updated(state):
    items = [{"measurement": "Ini Freq Error", "value": -153.0, "unit": "KHz",
              "limit": "(75.0 ~ -75.0)", "step_name": "BT_TX_BDR"}]
    await state.ingest(_rec("AA", "FAIL", failed_items=items))
    assert state.failure_stats["Ini Freq Error"] == 1


async def test_failure_stats_accumulate(state):
    items = [{"measurement": "Power", "value": -1.7, "unit": "dBm",
              "limit": "(10.0 ~ 0.0)", "step_name": "BT_TX_BDR"}]
    await state.ingest(_rec("AA", "FAIL", failed_items=items))
    await state.ingest(_rec("BB", "FAIL", failed_items=items))
    assert state.failure_stats["Power"] == 2


# ── recent_records ────────────────────────────────────────────────────────────

async def test_recent_records_newest_first(state):
    await state.ingest(_rec("AA", "PASS", "2026-04-17T09:00:00"))
    await state.ingest(_rec("BB", "FAIL", "2026-04-17T10:00:00"))
    records = list(state.recent_records)
    assert records[0]["mac1"] == "BB"  # newest prepended first
    assert records[1]["mac1"] == "AA"


async def test_recent_records_maxlen(state):
    for i in range(60):
        await state.ingest(_rec(f"M{i:012d}", "PASS"))
    assert len(state.recent_records) == 50


# ── reset ─────────────────────────────────────────────────────────────────────

async def test_reset_clears_state(state):
    await state.ingest(_rec("AA", "PASS"))
    await state.ingest(_rec("BB", "FAIL"))
    state.reset()
    assert state.pass_count == 0
    assert state.fail_count == 0
    assert state.stop_count == 0
    assert len(state.recent_records) == 0
    assert len(state.failure_stats) == 0
    assert not state.ready


# ── snapshot ──────────────────────────────────────────────────────────────────

async def test_snapshot_shape(state):
    await state.ingest(_rec("AA", "PASS"))
    snap = state.get_snapshot()
    assert "stats" in snap
    assert "recent_records" in snap
    assert "failure_stats" in snap
    assert "ready" in snap
    assert "hourly_counts" in snap
    assert "result_distribution" in snap
    stats = snap["stats"]
    for key in ("pass", "fail", "stop", "yield", "uph", "total", "minute_pass_rate",
                "retest_count", "retest_rate"):
        assert key in stats


# ── retest rate ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retest_rate_no_retests(state):
    await state.ingest(_rec("AA", "PASS"))
    await state.ingest(_rec("BB", "PASS"))
    assert state.retest_count == 0
    assert state.retest_rate == 0.0


@pytest.mark.asyncio
async def test_retest_rate_one_retest(state):
    # AA tested twice (FAIL then PASS), BB tested once
    await state.ingest(_rec("AA", "FAIL"))
    await state.ingest(_rec("AA", "PASS"))
    await state.ingest(_rec("BB", "PASS"))
    assert state.retest_count == 1        # only AA was retested
    assert state.retest_rate == 50.0      # 1/2 * 100


@pytest.mark.asyncio
async def test_retest_rate_all_retested(state):
    await state.ingest(_rec("AA", "FAIL"))
    await state.ingest(_rec("AA", "PASS"))
    await state.ingest(_rec("BB", "STOP"))
    await state.ingest(_rec("BB", "FAIL"))
    assert state.retest_count == 2
    assert state.retest_rate == 100.0


@pytest.mark.asyncio
async def test_retest_rate_zero_with_no_records(state):
    assert state.retest_count == 0
    assert state.retest_rate == 0.0


@pytest.mark.asyncio
async def test_retest_rate_cleared_on_reset(state):
    await state.ingest(_rec("AA", "FAIL"))
    await state.ingest(_rec("AA", "PASS"))
    assert state.retest_count == 1
    state.reset()
    assert state.retest_count == 0
    assert state.retest_rate == 0.0

