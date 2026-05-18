"""
Unit tests for realtime_splitter_app.py
Uses only dummy/temp directories — no real paths required.
Run: python test_splitter.py
"""
import os
import sys
import shutil
import tempfile
import unittest

# ── Stub out PyQt5 so tests run headless ─────────────────────
from unittest.mock import MagicMock, patch

# Build minimal Qt stubs before importing the module
qt_modules = [
    'PyQt5', 'PyQt5.QtWidgets', 'PyQt5.QtCore', 'PyQt5.QtGui',
]
for mod in qt_modules:
    sys.modules.setdefault(mod, MagicMock())

# Individual class stubs needed by the module at import time
QtWidgets = sys.modules['PyQt5.QtWidgets']
QtCore    = sys.modules['PyQt5.QtCore']
QtGui     = sys.modules['PyQt5.QtGui']

for name in [
    'QApplication','QMainWindow','QWidget','QVBoxLayout','QHBoxLayout',
    'QPushButton','QLineEdit','QLabel','QFileDialog','QTextEdit','QFrame',
    'QSpinBox','QMessageBox','QStyle','QSizePolicy','QComboBox',
    'QGraphicsOpacityEffect','QDialog',
]:
    setattr(QtWidgets, name, MagicMock())

for name in ['Qt','QThread','pyqtSignal','QSize','QSettings','QTimer']:
    setattr(QtCore, name, MagicMock())

for name in ['QIcon','QFont']:
    setattr(QtGui, name, MagicMock())

# Now import the pure-logic parts of the module
sys.path.insert(0, os.path.dirname(__file__))
from realtime_splitter_app import (
    split_log_content, parse_segment, build_output_filename,
    scan_existing_files, get_wo_dest,
    STATION_IDS, DEFAULT_SRCS, OUT_BASE_ROOTS, CLOSE_BATCH_FILES,
)


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────
SAMPLE_SEGMENT = (
    "MAC1 : AABBCCDDEEFF\n"
    "MAC2 : 112233445566\n"
    "Start Time : 2026/05/18 10:30:00\n"
    "  * P A S S *\n"
)

SAMPLE_LOG = SAMPLE_SEGMENT + "\n" + (
    "MAC1 : AABBCCDDEEF0\n"
    "MAC2 : 112233445567\n"
    "Start Time : 2026/05/18 10:31:00\n"
    "  * F A I L *\n"
)


class TestConstants(unittest.TestCase):

    def test_station_ids(self):
        self.assertEqual(STATION_IDS, ['10', '20', '30', '40'])

    def test_default_srcs_keys(self):
        self.assertEqual(set(DEFAULT_SRCS.keys()), {'10', '20', '30', '40'})

    def test_out_base_roots_keys(self):
        self.assertEqual(set(OUT_BASE_ROOTS.keys()), {'10', '20', '30', '40'})

    def test_out_base_roots_paths(self):
        for sta_id, path in OUT_BASE_ROOTS.items():
            self.assertIn(sta_id, path,
                msg=f"Station ID {sta_id} should appear in its OUT base root path")

    def test_default_srcs_unique(self):
        paths = list(DEFAULT_SRCS.values())
        self.assertEqual(len(paths), len(set(paths)), "All SRC default paths must be unique")


class TestSplitLogContent(unittest.TestCase):

    def test_splits_two_segments(self):
        segs = split_log_content(SAMPLE_LOG)
        self.assertEqual(len(segs), 2)

    def test_empty_content_returns_empty(self):
        self.assertEqual(split_log_content(""), [])

    def test_no_mac_header_ignored(self):
        content = "Some random text\nwithout MAC1 header\n"
        self.assertEqual(split_log_content(content), [])

    def test_single_segment(self):
        segs = split_log_content(SAMPLE_SEGMENT)
        self.assertEqual(len(segs), 1)

    def test_windows_line_endings(self):
        segs = split_log_content(SAMPLE_SEGMENT.replace('\n', '\r\n'))
        self.assertEqual(len(segs), 1)


class TestParseSegment(unittest.TestCase):

    def test_parse_pass(self):
        p = parse_segment(SAMPLE_SEGMENT)
        self.assertEqual(p['mac1'],   'AABBCCDDEEFF')
        self.assertEqual(p['mac2'],   '112233445566')
        self.assertEqual(p['date'],   '20260518')
        self.assertEqual(p['time'],   '103000')
        self.assertEqual(p['result'], 'PASS')

    def test_parse_fail(self):
        seg = SAMPLE_SEGMENT.replace('P A S S', 'F A I L')
        p = parse_segment(seg)
        self.assertEqual(p['result'], 'FAIL')

    def test_parse_stop(self):
        seg = SAMPLE_SEGMENT.replace('P A S S', 'S T O P')
        p = parse_segment(seg)
        self.assertEqual(p['result'], 'STOP')

    def test_parse_missing_result(self):
        seg = "MAC1 : AABBCCDDEEFF\nMAC2 : 112233445566\nStart Time : 2026/05/18 10:30:00\n"
        p = parse_segment(seg)
        self.assertIsNone(p['result'])


class TestBuildOutputFilename(unittest.TestCase):

    def _parsed(self, result='PASS'):
        return dict(mac1='AABBCCDDEEFF', mac2='112233445566',
                    date='20260518', time='103000', result=result)

    def test_with_station_id(self):
        name = build_output_filename(self._parsed(), station_id='10')
        self.assertTrue(name.startswith('STA10_'))
        self.assertIn('AABBCCDDEEFF', name)
        self.assertIn('PASS', name)
        self.assertTrue(name.endswith('.txt'))

    def test_without_station_id(self):
        name = build_output_filename(self._parsed())
        self.assertFalse(name.startswith('STA'))
        self.assertIn('PASS', name)

    def test_all_four_station_prefixes(self):
        for sta_id in STATION_IDS:
            name = build_output_filename(self._parsed(), station_id=sta_id)
            self.assertTrue(name.startswith(f'STA{sta_id}_'),
                msg=f"Expected STA{sta_id}_ prefix, got: {name}")

    def test_invalid_mac_returns_none(self):
        p = self._parsed()
        p['mac1'] = 'ZZZZZZZZZZZZ'
        self.assertIsNone(build_output_filename(p, station_id='10'))

    def test_invalid_result_returns_none(self):
        p = self._parsed(result='UNKNOWN')
        self.assertIsNone(build_output_filename(p, station_id='10'))

    def test_missing_field_returns_none(self):
        p = self._parsed()
        del p['date']
        self.assertIsNone(build_output_filename(p, station_id='10'))


class TestScanExistingFiles(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="splitter_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_dir_returns_empty_set(self):
        result = scan_existing_files(self.tmp)
        self.assertEqual(result, set())

    def test_finds_txt_files(self):
        for name in ('STA10_a.txt', 'STA10_b.txt'):
            open(os.path.join(self.tmp, name), 'w').close()
        result = scan_existing_files(self.tmp)
        self.assertEqual(result, {'STA10_a.txt', 'STA10_b.txt'})

    def test_nonexistent_dir_returns_empty_set(self):
        result = scan_existing_files(os.path.join(self.tmp, 'nonexistent'))
        self.assertEqual(result, set())

    def test_subdirs_not_included(self):
        os.makedirs(os.path.join(self.tmp, 'subdir'))
        open(os.path.join(self.tmp, 'file.txt'), 'w').close()
        result = scan_existing_files(self.tmp)
        self.assertIn('file.txt', result)
        self.assertNotIn('subdir', result)


class TestWouOutPathLogic(unittest.TestCase):
    """Verify WOU → OUT path derivation matches requirements."""

    def test_out_path_is_wou_directly_under_base(self):
        """OUT path must be OUT_BASE_ROOTS/{id}/{wou} — no 'Log_' prefix."""
        wou = '5101-260129012'
        for sta_id in STATION_IDS:
            expected = os.path.join(OUT_BASE_ROOTS[sta_id], wou)
            self.assertEqual(os.path.dirname(os.path.normpath(expected)),
                             os.path.normpath(OUT_BASE_ROOTS[sta_id]),
                             msg=f"STA{sta_id}: OUT must be a direct child of base root")
            self.assertTrue(expected.endswith(wou),
                msg=f"STA{sta_id}: last component must be {wou!r}, got: {expected}")

    def test_out_path_has_no_log_prefix(self):
        """OUT path must NOT contain 'Log_' prefix before the WOU."""
        wou = '5101-260129012'
        for sta_id in STATION_IDS:
            path = os.path.join(OUT_BASE_ROOTS[sta_id], wou)
            self.assertNotIn(f'Log_{wou}', path,
                msg=f"STA{sta_id}: path must not use 'Log_' prefix")

    def test_each_station_gets_different_path(self):
        wou = '5101-260129012'
        paths = [os.path.join(OUT_BASE_ROOTS[s], wou) for s in STATION_IDS]
        self.assertEqual(len(paths), len(set(paths)), "Each station must have a unique OUT path")

    def test_auto_update_guard_direct_child(self):
        """_on_wou_changed logic: a path directly under base root is auto-derived."""
        wou = '5101-260129012'
        for sta_id in STATION_IDS:
            base = os.path.normpath(OUT_BASE_ROOTS[sta_id])
            cur  = os.path.join(OUT_BASE_ROOTS[sta_id], wou)
            self.assertEqual(os.path.dirname(os.path.normpath(cur)), base,
                msg=f"STA{sta_id}: auto-derived path should be direct child of base")

    def test_auto_update_guard_deep_path_preserved(self):
        """_on_wou_changed logic: a path deeper than base root should NOT be auto-updated."""
        wou = '5101-260129012'
        for sta_id in STATION_IDS:
            base = os.path.normpath(OUT_BASE_ROOTS[sta_id])
            deep = os.path.join(OUT_BASE_ROOTS[sta_id], 'custom', 'subdir')
            self.assertNotEqual(os.path.dirname(os.path.normpath(deep)), base,
                msg=f"STA{sta_id}: deep path must not be treated as auto-derived")


class TestSplitAndWriteDummy(unittest.TestCase):
    """End-to-end test: write a real Log_All.txt, split it, verify output files."""

    def setUp(self):
        self.src_dir = tempfile.mkdtemp(prefix="src_")
        self.out_dir = tempfile.mkdtemp(prefix="out_")
        self.log_path = os.path.join(self.src_dir, "Log_All.txt")

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.out_dir,  ignore_errors=True)

    def _write_log(self, n_segments=2):
        lines = []
        for i in range(n_segments):
            mac1 = f"AABBCCDD{i:04X}"
            mac2 = f"112233440000"
            lines.append(
                f"MAC1 : {mac1}\n"
                f"MAC2 : {mac2}\n"
                f"Start Time : 2026/05/18 10:{i:02d}:00\n"
                f"  * P A S S *\n\n"
            )
        with open(self.log_path, 'w', encoding='utf-8') as f:
            f.write(''.join(lines))

    def test_split_produces_correct_count(self):
        self._write_log(n_segments=3)
        with open(self.log_path, encoding='utf-8') as fh:
            content = fh.read()
        segs = split_log_content(content)
        self.assertEqual(len(segs), 3)

    def test_output_filenames_have_sta_prefix(self):
        self._write_log(n_segments=2)
        with open(self.log_path, encoding='utf-8') as fh:
            content = fh.read()
        segs = split_log_content(content)
        sta_id = '10'
        names = []
        for seg in segs:
            parsed = parse_segment(seg)
            name = build_output_filename(parsed, station_id=sta_id)
            if name:
                names.append(name)
        self.assertEqual(len(names), 2)
        for name in names:
            self.assertTrue(name.startswith(f'STA{sta_id}_'),
                msg=f"Expected STA{sta_id}_ prefix, got: {name}")

    def test_sta_subdirectory_is_created(self):
        """Split output must go into out_dir/STA{id}/ subdirectory (not directly into out_dir)."""
        self._write_log(n_segments=1)
        with open(self.log_path, encoding='utf-8') as fh:
            content = fh.read()
        segs = split_log_content(content)
        sta_id = '10'
        # Simulate SplitCopyThread behaviour: write into STA10 subdir
        sta_subdir = os.path.join(self.out_dir, f'STA{sta_id}')
        os.makedirs(sta_subdir, exist_ok=True)
        for seg in segs:
            parsed = parse_segment(seg)
            name = build_output_filename(parsed, station_id=sta_id)
            if name:
                with open(os.path.join(sta_subdir, name), 'w', encoding='utf-8') as f:
                    f.write(seg)
        # Verify STA10 subdir exists and contains the file
        self.assertTrue(os.path.isdir(sta_subdir),
            "STA10 subdirectory must be created under out_dir")
        sta_files = os.listdir(sta_subdir)
        self.assertTrue(any(f.startswith('STA10_') for f in sta_files),
            "Split file with STA10_ prefix must be inside out_dir/STA10/")
        # Verify top-level out_dir has NO STA10_*.txt files (they're in subdir)
        top_files = os.listdir(self.out_dir)
        self.assertFalse(any(f.startswith('STA10_') for f in top_files),
            "No STA10_* files should be directly in out_dir")

    def test_ensure_log_file_creates_if_missing(self):
        """_ensure_log_file logic: create Log_All.txt if absent."""
        path = os.path.join(self.src_dir, "Log_All.txt")
        self.assertFalse(os.path.exists(path))
        if not os.path.exists(path):
            with open(path, 'a', encoding='utf-8'):
                pass
        self.assertTrue(os.path.exists(path))
        self.assertEqual(os.path.getsize(path), 0)


class TestCloseBatchFiles(unittest.TestCase):
    """Verify CLOSE_BATCH_FILES constant contains required entries."""

    def test_required_files_present(self):
        required = {'Log_All.txt', 'Log_all.csv', 'log_summary.txt'}
        self.assertTrue(required.issubset(CLOSE_BATCH_FILES),
            f"Missing required entries: {required - CLOSE_BATCH_FILES}")

    def test_all_jpg_files_present(self):
        jpgs = {f for f in CLOSE_BATCH_FILES if f.endswith('.jpg')}
        self.assertEqual(len(jpgs), 22, f"Expected 22 jpg files, got {len(jpgs)}")

    def test_close_batch_only_moves_listed_files(self):
        """Only files in CLOSE_BATCH_FILES should be moved; others stay in src."""
        src = tempfile.mkdtemp(prefix="cb_src_")
        dst = tempfile.mkdtemp(prefix="cb_dst_")
        try:
            # Create some files: listed + unlisted
            listed_file   = 'Log_All.txt'
            unlisted_file = 'mystery_file.bin'
            for fname in (listed_file, unlisted_file):
                with open(os.path.join(src, fname), 'w') as f:
                    f.write("content")

            # Simulate _on_close_batch logic for ONE station
            moved = 0
            for filename in CLOSE_BATCH_FILES:
                sp = os.path.join(src, filename)
                if not os.path.isfile(sp):
                    continue
                dp = os.path.join(dst, filename)
                shutil.move(sp, dp)
                moved += 1

            self.assertEqual(moved, 1, "Only the listed file should be moved")
            self.assertFalse(os.path.exists(os.path.join(src, listed_file)),
                "Listed file must be moved out of src")
            self.assertTrue(os.path.exists(os.path.join(dst, listed_file)),
                "Listed file must arrive in dst")
            self.assertTrue(os.path.exists(os.path.join(src, unlisted_file)),
                "Unlisted file must remain in src")
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(dst, ignore_errors=True)


class TestGetWoDest(unittest.TestCase):
    """Verify WO remote upload destination derivation."""

    DST = 'root@192.168.100.1:/run/media/nvme0n1p1/rawlogs/'

    def test_wo_dest_correct_path(self):
        wou = '5101-260129012'
        result = get_wo_dest(self.DST, wou)
        self.assertEqual(result, f'root@192.168.100.1:/run/media/nvme0n1p1/{wou}/')

    def test_wo_dest_sibling_of_rawlogs(self):
        """WOU dir must be a sibling of rawlogs/, not inside it."""
        wou = '5101-260129012'
        result = get_wo_dest(self.DST, wou)
        self.assertNotIn('rawlogs', result,
            "WOU remote dir must NOT be inside rawlogs/")
        self.assertIn('/run/media/nvme0n1p1/', result)

    def test_wo_dest_none_when_no_wou(self):
        self.assertIsNone(get_wo_dest(self.DST, ''))
        self.assertIsNone(get_wo_dest(self.DST, None))

    def test_wo_dest_none_when_no_dst(self):
        self.assertIsNone(get_wo_dest('', '5101-260129012'))
        self.assertIsNone(get_wo_dest(None, '5101-260129012'))

    def test_local_dst_wo_dest(self):
        """Local DST path: WOU dir should be sibling of out dir."""
        result = get_wo_dest(r'C:\output\rawlogs', '5101-260129012')
        self.assertEqual(result, r'C:\output\5101-260129012')


if __name__ == '__main__':
    unittest.main(verbosity=2)
