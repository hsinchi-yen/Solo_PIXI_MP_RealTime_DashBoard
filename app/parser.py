import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, TypedDict

logger = logging.getLogger(__name__)

# ── filename patterns ─────────────────────────────────────────────────────────
# New format with STATION ID: STAID_YYYYMMDD_HHMMSS_MAC1_MAC2_RESULT.txt
FILENAME_RE = re.compile(
    r"^(STA\d{2})_(\d{8})_(\d{6})_([0-9A-F]{12})_([0-9A-F]{12})_(PASS|FAIL|STOP)\.txt$"
)

# WO format: WO_YYYYMMDD_HHMMSS_MAC1_MAC2_RESULT.txt
# WO token is mapped to station_id for KPI/record display grouping.
FILENAME_RE_WO = re.compile(
    r"^([A-Za-z0-9-]+)_(\d{8})_(\d{6})_([0-9A-F]{12})_([0-9A-F]{12})_(PASS|FAIL|STOP)\.txt$"
)

# Legacy format (no station ID): YYYYMMDD_HHMMSS_MAC1_MAC2_RESULT.txt
FILENAME_RE_LEGACY = re.compile(
    r"^(\d{8})_(\d{6})_([0-9A-F]{12})_([0-9A-F]{12})_(PASS|FAIL|STOP)\.txt$"
)

# ── line-level compiled patterns (module-level, instantiated once) ─────────────
# Tested against single lines — no re.MULTILINE needed.
_SERIAL_RE  = re.compile(r"Serial number:\s+(\S+)")
_TTIME_RE   = re.compile(r"^Test Time:\s+(.+)$")          # summary line only
_STEP_RE    = re.compile(r"^\d+\.\s+(\w+)")               # "5. BT_TX_BDR"
_MEASURE_RE = re.compile(                                  # TAB-indented measurement
    r"^\t+(\w[\w\s]*?)\s{2,}([-+]?\d[\d.]*)\s+(\S+)"
    r"\s+\(([-+]?\d[\d.]*)\s*~\s*([-+]?\d[\d.]*)\)\s+<-- (pass|fail)"
)


class FailedItem(TypedDict):
    step_name: str
    measurement: str
    value: float
    unit: str
    limit: str


class ParsedLog(TypedDict):
    filename: str
    station_id: str    # e.g. "STA10", WO token, or empty string for legacy files
    fixture_id: str
    datetime: str      # ISO 8601, e.g. "2026-04-17T09:20:07"
    mac1: str
    mac2: str
    result: str        # "PASS" | "FAIL" | "STOP"
    duration: str      # e.g. "01:16.7", empty string if not found
    failed_items: list[FailedItem]


def parse(filepath: str) -> Optional[ParsedLog]:
    path = Path(filepath)

    # Parse priority: STA format -> WO format -> legacy format.
    # This keeps legacy compatibility while allowing WO folders to be analyzed.
    m = FILENAME_RE.match(path.name)
    if m:
        station_id, date_str, time_str, mac1, mac2, result = m.groups()
    else:
        m = FILENAME_RE_WO.match(path.name)
        if m:
            station_id, date_str, time_str, mac1, mac2, result = m.groups()
        else:
            # Fall back to legacy format (no station ID)
            m = FILENAME_RE_LEGACY.match(path.name)
            if not m:
                logger.warning("filename does not match naming convention: %s", path.name)
                return None
            date_str, time_str, mac1, mac2, result = m.groups()
            station_id = ""  # legacy files have no station_id/WO prefix

    fixture_id_from_name: Optional[str] = None   # extracted from content

    try:
        dt = datetime.strptime(date_str + time_str, "%Y%m%d%H%M%S")
    except ValueError:
        logger.warning("invalid datetime in filename: %s", path.name)
        return None

    fixture_id, duration, failed_items = _parse_content(path, result, fixture_id_from_name)

    return ParsedLog(
        filename=path.name,
        station_id=station_id,
        fixture_id=fixture_id,
        datetime=dt.isoformat(),
        mac1=mac1,
        mac2=mac2,
        result=result,
        duration=duration,
        failed_items=failed_items,
    )


def _parse_content(
    path: Path,
    result: str,
    fixture_id_override: Optional[str],
) -> tuple[str, str, list[FailedItem]]:
    """Line-by-line parser with early exit.

    Reads the file one line at a time, extracting only the three fields we need:
    ``fixture_id`` (Serial number), ``duration`` (Test Time), and ``failed_items``
    (FAIL measurements).

    For PASS/STOP files the read stops as soon as both Serial and Test Time are
    found — typically within the first ~30 lines of the header, well before the
    bulk of measurement data.

    For FAIL files the full file is read once (no second pass), using a small
    state machine to track the current step name as measurement lines are found.
    """
    need_fail = result == "FAIL"
    # fixture_id comes from file content (Serial number line)
    fixture_id: str = fixture_id_override if fixture_id_override is not None else ""
    need_serial = fixture_id_override is None
    duration = ""
    failed_items: list[FailedItem] = []
    current_step = ""
    seen: set[str] = set()

    try:
        fh = path.open(encoding="utf-8", errors="replace")
    except OSError:
        logger.error("cannot read file: %s", path)
        return fixture_id, "", []

    with fh:
        for line in fh:
            # ── Serial number (fixture_id) — only for new-format files ──
            if need_serial and not fixture_id:
                sm = _SERIAL_RE.search(line)
                if sm:
                    fixture_id = sm.group(1)

            # ── Test Time (duration) ──
            if not duration and line.startswith("Test Time:"):
                tm = _TTIME_RE.match(line)
                if tm:
                    duration = tm.group(1).strip()

            if need_fail:
                # Dispatch on first character for minimal overhead
                first = line[0] if line else ""
                if first.isdigit():
                    sm2 = _STEP_RE.match(line)
                    if sm2:
                        current_step = sm2.group(1)
                elif first == "\t":
                    mm = _MEASURE_RE.match(line)
                    if mm:
                        raw_name, value_str, unit, upper, lower, status = mm.groups()
                        name = raw_name.strip()
                        if status == "fail" and name not in seen:
                            seen.add(name)
                            failed_items.append(FailedItem(
                                step_name=current_step,
                                measurement=name,
                                value=float(value_str),
                                unit=unit,
                                limit=f"({upper} ~ {lower})",
                            ))
            elif (not need_serial or fixture_id) and duration:
                # PASS / STOP: all required fields collected — stop reading
                break

    return fixture_id, duration, failed_items
