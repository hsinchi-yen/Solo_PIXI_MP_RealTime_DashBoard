import asyncio
from collections import Counter, deque
from datetime import date, datetime, timedelta
from typing import Any, Optional

from .parser import ParsedLog

_PRIORITY = {"PASS": 3, "FAIL": 2, "STOP": 1}


class DashboardState:
    def __init__(self, config: Any):
        self._cfg = config.dashboard
        self.lock = asyncio.Lock()

        # ── unique-MAC1 status tracking (source of truth for KPI counts) ──
        # Each MAC1 occupies exactly one bucket: PASS > FAIL > STOP
        # Now stores (result, datetime) tuple to support "latest test wins" logic
        self.mac_status: dict[str, tuple[str, datetime]] = {}

        # ── display records (kept for recent_records / stop_alerts / failure_stats) ──
        self.pass_records: dict[str, ParsedLog] = {}  # mac1 → newest PASS
        self.fail_records: list[ParsedLog] = []
        self.stop_records: list[ParsedLog] = []

        self.recent_records: deque[ParsedLog] = deque()

        # Failure analysis: measurement name → count (all FAIL records, diagnostic)
        self.failure_stats: Counter = Counter()

        # Retest tracking: mac1 → total test count across all results
        self.mac_test_count: Counter = Counter()

        # Rolling timestamps for UPH / pass-per-minute (actual test time, not wall clock)
        self._uph_times: deque[datetime] = deque()
        self._minute_pass_times: deque[datetime] = deque()

        # Hourly completion chart: hour(0-23) → count, filtered to _latest_date
        self.hourly_counts: Counter = Counter()
        self._latest_date: Optional[date] = None

        # Startup state
        self.ready: bool = False
        self.scan_total: int = 0
        self.scan_current: int = 0

    # ── computed properties ────────────────────────────────────────────────

    @property
    def retest_count(self) -> int:
        """Number of unique MAC1s that were tested more than once."""
        return sum(1 for c in self.mac_test_count.values() if c > 1)

    @property
    def retest_rate(self) -> float:
        """Percentage of units that required at least one retest."""
        total = self.total_count
        if total == 0:
            return 0.0
        return round(self.retest_count / total * 100, 1)

    @property
    def pass_count(self) -> int:
        return sum(1 for (s, _) in self.mac_status.values() if s == "PASS")

    @property
    def fail_count(self) -> int:
        return sum(1 for (s, _) in self.mac_status.values() if s == "FAIL")

    @property
    def stop_count(self) -> int:
        return sum(1 for (s, _) in self.mac_status.values() if s == "STOP")

    @property
    def total_count(self) -> int:
        return len(self.mac_status)

    @property
    def yield_rate(self) -> float:
        denom = self.pass_count + self.fail_count
        if denom == 0:
            return 0.0
        return round(self.pass_count / denom * 100, 1)

    @property
    def uph(self) -> int:
        if not self._uph_times:
            return 0
        # Use latest record timestamp as reference to avoid wall-clock / timezone mismatch
        # (Docker UTC vs naive log timestamps in local time).
        latest = max(self._uph_times)
        cutoff = latest - timedelta(hours=1)
        return sum(1 for t in self._uph_times if t >= cutoff)

    @property
    def minute_pass_rate(self) -> float:
        if not self._minute_pass_times:
            return 0.0
        latest = max(self._minute_pass_times)
        cutoff = latest - timedelta(hours=1)
        count = sum(1 for t in self._minute_pass_times if t >= cutoff)
        return round(count / 60, 2)

    @property
    def result_distribution(self) -> dict:
        total = self.total_count
        if total == 0:
            return {"pass_pct": 0.0, "fail_pct": 0.0, "stop_pct": 0.0}
        return {
            "pass_pct": round(self.pass_count / total * 100, 1),
            "fail_pct": round(self.fail_count / total * 100, 1),
            "stop_pct": round(self.stop_count / total * 100, 1),
        }

    # ── mutation ───────────────────────────────────────────────────────────

    def _ingest_unlocked(self, record: ParsedLog) -> None:
        result = record["result"]
        mac1 = record["mac1"]
        dt = datetime.fromisoformat(record["datetime"])

        # ── update unique MAC1 status (latest test wins; if equal time, PASS > FAIL > STOP) ──
        current = self.mac_status.get(mac1)
        should_update = False
        if current is None:
            should_update = True
        else:
            current_result, current_dt = current
            if dt > current_dt:
                # Newer test always wins
                should_update = True
            elif dt == current_dt and _PRIORITY[result] > _PRIORITY[current_result]:
                # Same time, better result wins
                should_update = True
        
        if should_update:
            self.mac_status[mac1] = (result, dt)

        # ── retest tracking: count every test event per MAC1 ──
        self.mac_test_count[mac1] += 1

        # ── update display collections ──
        if result == "PASS":
            existing = self.pass_records.get(mac1)
            if existing is None or datetime.fromisoformat(existing["datetime"]) < dt:
                self.pass_records[mac1] = record
            self._uph_times.append(dt)          # actual test time, not wall clock
            self._minute_pass_times.append(dt)

        elif result == "FAIL":
            self.fail_records.append(record)
            for item in record.get("failed_items", []):
                self.failure_stats[item["measurement"]] += 1

        elif result == "STOP":
            self.stop_records.append(record)

        self.recent_records.appendleft(record)

        # ── hourly completion chart ──
        rec_date = dt.date()
        if self._latest_date is None or rec_date > self._latest_date:
            # New most-recent date: reset hourly counts for new date
            self._latest_date = rec_date
            self.hourly_counts.clear()
        if rec_date == self._latest_date:
            self.hourly_counts[dt.hour] += 1

    async def ingest(self, record: ParsedLog) -> None:
        async with self.lock:
            self._ingest_unlocked(record)

    async def rebuild(self, records: list[ParsedLog]) -> None:
        async with self.lock:
            was_ready = self.ready
            self.reset()
            self.ready = was_ready
            for record in records:
                self._ingest_unlocked(record)
            self.ready = True

    def reset(self) -> None:
        self.mac_status.clear()
        self.mac_test_count.clear()
        self.pass_records.clear()
        self.fail_records.clear()
        self.stop_records.clear()
        self.recent_records.clear()
        self.failure_stats.clear()
        self._uph_times.clear()
        self._minute_pass_times.clear()
        self.hourly_counts.clear()
        self._latest_date = None
        self.ready = False
        self.scan_total = 0
        self.scan_current = 0

    # ── snapshot ───────────────────────────────────────────────────────────

    def get_snapshot(self) -> dict:
        return {
            "stats": {
                "pass": self.pass_count,
                "fail": self.fail_count,
                "stop": self.stop_count,
                "total": self.total_count,
                "yield": self.yield_rate,
                "uph": self.uph,
                "minute_pass_rate": self.minute_pass_rate,
                "retest_count": self.retest_count,
                "retest_rate": self.retest_rate,
            },
            "recent_records": sorted(
                list(self.recent_records),
                key=lambda r: r["datetime"],
                reverse=True
            ),
            "stop_alerts": self.stop_records[-20:],
            "failure_stats": dict(self.failure_stats.most_common(10)),
            "hourly_counts": {str(h): c for h, c in self.hourly_counts.items()},
            "result_distribution": self.result_distribution,
            "ready": self.ready,
            "scan_current": self.scan_current,
            "scan_total": self.scan_total,
        }
