"""
Unit tests for the pure-logic functions in realtime_splitter_app.py.
Covers: split_log_content, parse_segment, build_output_filename
"""
import re
import pytest

# ── Replicate the module-level constants / functions without importing PyQt5 ──

SEGMENT_PATTERN = re.compile(r'(?=^MAC1[\t ]*:)', re.MULTILINE)
START_PATTERN = re.compile(r'(\d{4})/(\d{2})/(\d{2}).*?(\d{2}):(\d{2}):(\d{2})')
_MAC_RE = re.compile(r'^[0-9A-Fa-f]{12}$')
_VALID_RESULTS = frozenset({"PASS", "FAIL", "STOP"})


def split_log_content(content):
    n = content.replace('\r\n', '\n').replace('\r', '\n')
    return [s for s in SEGMENT_PATTERN.split(n) if re.match(r'MAC1[\t ]*:', s.strip())]


def parse_segment(segment):
    mac1 = mac2 = date_str = time_str = result = None
    for line in segment.strip().split('\n'):
        lc = line.strip()
        if lc.startswith("MAC1"):
            mac1 = lc.split(":", 1)[-1].strip()
        elif lc.startswith("MAC2"):
            mac2 = lc.split(":", 1)[-1].strip()
        elif lc.startswith("Start"):
            m = START_PATTERN.search(lc)
            if m:
                date_str = ''.join(m.group(1, 2, 3))
                time_str = ''.join(m.group(4, 5, 6))
        if "* P A S S *" in line:
            result = "PASS"
        elif "* F A I L *" in line:
            result = "FAIL"
        elif "* S T O P *" in line:
            result = "STOP"
    return dict(mac1=mac1, mac2=mac2, date=date_str, time=time_str, result=result)


def build_output_filename(parsed):
    date = parsed.get('date')
    time_str = parsed.get('time')
    mac1 = parsed.get('mac1') or ""
    mac2 = parsed.get('mac2') or ""
    result = parsed.get('result')
    if not all([date, time_str, mac1, mac2, result]):
        return None
    if not (_MAC_RE.match(mac1) and _MAC_RE.match(mac2)):
        return None
    if result not in _VALID_RESULTS:
        return None
    return f"{date}_{time_str}_{mac1}_{mac2}_{result}.txt"


# ── Fixtures ──────────────────────────────────────────────────────────────────

PASS_SEG = (
    "MAC1: 001F7B6BD20E\n"
    "MAC2: 001F7B6BD20F\n"
    "Start: 2026/01/05 17:19:00\n"
    "\n"
    "*** P A S S ***\n"
    "\n"
    "End: 2026/01/05 17:20:14\n"
)

FAIL_SEG = (
    "MAC1: 001F7B6BD21E\n"
    "MAC2: 001F7B6BD21F\n"
    "Start: 2026/01/06 09:01:40\n"
    "\n"
    "*** F A I L ***\n"
    "\n"
    "End: 2026/01/06 09:03:32\n"
)

STOP_SEG = (
    "MAC1:\tAABBCC001100\n"
    "MAC2:\tAABBCC001101\n"
    "Start:\t2026/01/06 09:05:00\n"
    "\n"
    "********************* S T O P *********************\n"
    "End:\t2026/01/06 09:05:04\n"
)


# ── split_log_content ─────────────────────────────────────────────────────────

class TestSplitLogContent:
    def test_happy_path_two_segments(self):
        content = PASS_SEG + "\n" + FAIL_SEG
        segs = split_log_content(content)
        assert len(segs) == 2
        assert all(s.strip().startswith("MAC1") for s in segs)

    def test_empty_string(self):
        assert split_log_content("") == []

    def test_no_mac1_line(self):
        assert split_log_content("no mac here\nsome other line\n") == []

    def test_crlf_line_endings(self):
        content = PASS_SEG.replace('\n', '\r\n')
        segs = split_log_content(content)
        assert len(segs) == 1

    def test_cr_only_line_endings(self):
        content = PASS_SEG.replace('\n', '\r')
        segs = split_log_content(content)
        assert len(segs) == 1

    def test_three_segments(self):
        content = PASS_SEG + "\n" + FAIL_SEG + "\n" + STOP_SEG
        segs = split_log_content(content)
        assert len(segs) == 3

    def test_preamble_before_first_segment_is_dropped(self):
        content = "file header\nsome metadata\n\n" + PASS_SEG
        segs = split_log_content(content)
        assert len(segs) == 1
        assert segs[0].strip().startswith("MAC1")


# ── parse_segment ─────────────────────────────────────────────────────────────

class TestParseSegment:
    def test_pass_space_separator(self):
        p = parse_segment(PASS_SEG)
        assert p['mac1'] == "001F7B6BD20E"
        assert p['mac2'] == "001F7B6BD20F"
        assert p['date'] == "20260105"
        assert p['time'] == "171900"
        assert p['result'] == "PASS"

    def test_fail_space_separator(self):
        p = parse_segment(FAIL_SEG)
        assert p['result'] == "FAIL"
        assert p['mac1'] == "001F7B6BD21E"

    def test_stop_tab_separator(self):
        p = parse_segment(STOP_SEG)
        assert p['mac1'] == "AABBCC001100"
        assert p['mac2'] == "AABBCC001101"
        assert p['result'] == "STOP"

    def test_missing_result_marker(self):
        seg = "MAC1: 001F7B6BD20E\nMAC2: 001F7B6BD20F\nStart: 2026/01/05 17:19:00\n"
        p = parse_segment(seg)
        assert p['result'] is None

    def test_missing_mac1(self):
        seg = "MAC2: 001F7B6BD20F\nStart: 2026/01/05 17:19:00\n*** P A S S ***\n"
        p = parse_segment(seg)
        assert p['mac1'] is None

    def test_missing_start_line(self):
        seg = "MAC1: 001F7B6BD20E\nMAC2: 001F7B6BD20F\n*** P A S S ***\n"
        p = parse_segment(seg)
        assert p['date'] is None
        assert p['time'] is None

    def test_asterisk_count_three_matches(self):
        """Actual logs use *** P A S S *** (3 asterisks), not 4."""
        seg = "MAC1: AABBCC001100\nMAC2: AABBCC001101\nStart: 2026/01/01 10:00:00\n*** P A S S ***\n"
        p = parse_segment(seg)
        assert p['result'] == "PASS"

    def test_asterisk_count_many_stop_matches(self):
        """STOP uses a long line of asterisks."""
        seg = "MAC1: AABBCC001100\nMAC2: AABBCC001101\nStart: 2026/01/01 10:00:00\n" \
              "********************* S T O P *********************\n"
        p = parse_segment(seg)
        assert p['result'] == "STOP"


# ── build_output_filename ─────────────────────────────────────────────────────

class TestBuildOutputFilename:
    def _ok(self):
        return dict(date="20260105", time="171900",
                    mac1="001F7B6BD20E", mac2="001F7B6BD20F", result="PASS")

    def test_happy_path(self):
        fn = build_output_filename(self._ok())
        assert fn == "20260105_171900_001F7B6BD20E_001F7B6BD20F_PASS.txt"

    def test_all_three_results(self):
        for result in ("PASS", "FAIL", "STOP"):
            p = {**self._ok(), 'result': result}
            assert build_output_filename(p) is not None

    @pytest.mark.parametrize("missing_key", ['date', 'time', 'mac1', 'mac2', 'result'])
    def test_missing_field_returns_none(self, missing_key):
        p = {**self._ok(), missing_key: None}
        assert build_output_filename(p) is None

    def test_path_traversal_mac1_rejected(self):
        p = {**self._ok(), 'mac1': '../../evil_dir'}
        assert build_output_filename(p) is None

    def test_path_traversal_mac2_rejected(self):
        p = {**self._ok(), 'mac2': '../passwords'}
        assert build_output_filename(p) is None

    def test_invalid_result_rejected(self):
        p = {**self._ok(), 'result': 'UNKNOWN'}
        assert build_output_filename(p) is None

    def test_short_mac_rejected(self):
        p = {**self._ok(), 'mac1': 'AABBCC'}
        assert build_output_filename(p) is None

    def test_no_path_separators_in_filename(self):
        fn = build_output_filename(self._ok())
        import os
        assert os.path.basename(fn) == fn


# ── Integration: full fixture files ──────────────────────────────────────────

class TestFixtureFiles:
    def test_pass_fixture(self, tmp_path):
        import pathlib
        fixture = pathlib.Path(__file__).parent / "fixtures" / \
                  "20260105_171900_001F7B6BD20E_001F7B6BD20F_PASS.txt"
        content = fixture.read_text(encoding='utf-8')
        segs = split_log_content(content)
        assert len(segs) == 1
        p = parse_segment(segs[0])
        fn = build_output_filename(p)
        assert fn == "20260105_171900_001F7B6BD20E_001F7B6BD20F_PASS.txt"

    def test_fail_fixture(self, tmp_path):
        import pathlib
        fixture = pathlib.Path(__file__).parent / "fixtures" / \
                  "20260106_090140_001F7B6BD21E_001F7B6BD21F_FAIL.txt"
        content = fixture.read_text(encoding='utf-8')
        segs = split_log_content(content)
        assert len(segs) == 1
        p = parse_segment(segs[0])
        fn = build_output_filename(p)
        assert fn == "20260106_090140_001F7B6BD21E_001F7B6BD21F_FAIL.txt"

    def test_stop_fixture(self, tmp_path):
        import pathlib
        fixture = pathlib.Path(__file__).parent / "fixtures" / \
                  "20260106_090500_AABBCC001100_AABBCC001101_STOP.txt"
        content = fixture.read_text(encoding='utf-8')
        segs = split_log_content(content)
        assert len(segs) == 1
        p = parse_segment(segs[0])
        fn = build_output_filename(p)
        assert fn == "20260106_090500_AABBCC001100_AABBCC001101_STOP.txt"
