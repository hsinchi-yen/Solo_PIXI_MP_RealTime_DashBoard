import sys
import os
import re
import shutil
import tempfile
import time
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLineEdit, QLabel,
                             QFileDialog, QTextEdit, QFrame, QSpinBox,
                             QMessageBox, QStyle, QSizePolicy)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QFont


def get_base_dir():
    if getattr(sys, '_MEIPASS', None):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_path(*parts):
    return os.path.join(get_base_dir(), *parts)


APP_ICON_PATH = get_resource_path('build_assets', 'icons', 'solo_pixi_splitter.ico')
DEFAULT_POLL_INTERVAL = 60

# ─────────────────────────────────────────────────────────────
#  Windows 11 Fluent Design stylesheet
#  Palette: #202020 titlebar · #0078D4 accent · #F3F3F3 bg
#           #107C10 success · #C50F1F error · #CA5010 warning
# ─────────────────────────────────────────────────────────────
STYLESHEET = """
QWidget {
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
    font-size: 11px;
    color: #1A1A1A;
}
QMainWindow, QWidget#root {
    background-color: #F3F3F3;
}

/* ── Header — dark titlebar style ── */
QFrame#header {
    background-color: #202020;
    border-radius: 6px;
}
QLabel#appTitle {
    color: #FFFFFF;
    font-size: 12px;
    font-weight: 600;
}
QLabel#dotIdle     { color: #9D9D9D; font-size: 15px; }
QLabel#dotWatching { color: #6CCB5F; font-size: 15px; }
QLabel#dotBusy     { color: #FCB040; font-size: 15px; }
QLabel#dotError    { color: #F04747; font-size: 15px; }
QLabel#dotState    { color: #ABABAB; font-size: 10px; }

/* ── Config panel — white card ── */
QFrame#configPanel {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 6px;
}
QLabel#rowTag {
    color: #0078D4;
    font-size: 10px;
    font-weight: 700;
    min-width: 28px;
    max-width: 28px;
}

/* ── Input fields ── */
QLineEdit {
    border: 1px solid #CECECE;
    border-radius: 4px;
    padding: 3px 7px;
    background: #FDFDFD;
    selection-background-color: #0078D4;
    color: #1A1A1A;
}
QLineEdit:hover    { border-color: #9E9E9E; }
QLineEdit:focus    { border-color: #0078D4; }
QLineEdit:disabled { background: #F5F5F5; color: #9D9D9D; border-color: #E8E8E8; }

/* ── Browse icon buttons ── */
QPushButton#browse {
    background-color: #F9F9F9;
    color: #1A1A1A;
    border: 1px solid #D1D1D1;
    border-radius: 4px;
    padding: 0px;
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
}
QPushButton#browse:hover   { background-color: #F0F0F0; border-color: #ADADAD; }
QPushButton#browse:pressed { background-color: #E8E8E8; }
QPushButton#browse:disabled { background: #F5F5F5; color: #C8C8C8; border-color: #E8E8E8; }

/* ── SpinBox ── */
QSpinBox {
    border: 1px solid #CECECE;
    border-radius: 4px;
    padding: 3px 4px;
    background: #FDFDFD;
    min-width: 54px;
    max-width: 62px;
    color: #1A1A1A;
}
QSpinBox:hover    { border-color: #9E9E9E; }
QSpinBox:focus    { border-color: #0078D4; }
QSpinBox:disabled { background: #F5F5F5; color: #9D9D9D; border-color: #E8E8E8; }

/* ── Start — Windows accent blue ── */
QPushButton#start {
    background-color: #0078D4;
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 4px 12px;
    font-weight: 600;
    font-size: 11px;
}
QPushButton#start:hover   { background-color: #106EBE; }
QPushButton#start:pressed { background-color: #005A9E; }
QPushButton#start:disabled { background-color: #C7E0F4; color: #FFFFFF; }

/* ── Stop — secondary on dark header ── */
QPushButton#stop {
    background-color: #383838;
    color: #E8E8E8;
    border: 1px solid #4D4D4D;
    border-radius: 4px;
    padding: 4px 12px;
    font-weight: 600;
    font-size: 11px;
}
QPushButton#stop:hover   { background-color: #444444; border-color: #F04747; color: #FFFFFF; }
QPushButton#stop:pressed { background-color: #4C4C4C; }
QPushButton#stop:disabled { background-color: #2C2C2C; color: #5E5E5E; border-color: #3C3C3C; }

/* ── Status strip ── */
QFrame#statusStrip {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 5px;
}
QLabel#statusKey { color: #5D5D5D; font-size: 10px; }
QLabel#statusVal { color: #1A1A1A; font-size: 11px; font-weight: 600; }
QLabel#badgeOk   { color: #107C10; font-weight: 700; font-size: 11px; }
QLabel#badgeFail { color: #C50F1F; font-weight: 700; font-size: 11px; }
QLabel#sep       { color: #D8D8D8; font-size: 11px; padding: 0 2px; }

/* ── Activity log ── */
QFrame#logPanel {
    background: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 6px;
}
QTextEdit {
    border: none;
    background: transparent;
    padding: 2px 4px;
    selection-background-color: #0078D4;
    color: #1A1A1A;
}
"""

# ─────────────────────────────────────────────────────────────
#  Shared log-splitting logic
# ─────────────────────────────────────────────────────────────
SEGMENT_PATTERN = re.compile(r'(?=^MAC1[\t ]*:)', re.MULTILINE)
START_PATTERN = re.compile(r'(\d{4})/(\d{2})/(\d{2}).*?(\d{2}):(\d{2}):(\d{2})')

# MAC address must be exactly 12 hex digits; result must be one of three values
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


def scan_existing_files(output_dir):
    if not os.path.isdir(output_dir):
        return set()
    return {f for f in os.listdir(output_dir)
            if os.path.isfile(os.path.join(output_dir, f))}


# ─────────────────────────────────────────────────────────────
#  Worker threads
# ─────────────────────────────────────────────────────────────
class WatcherThread(QThread):
    file_changed = pyqtSignal()
    tick = pyqtSignal()  # fires on every poll regardless of change

    def __init__(self, source_path, interval, parent=None):
        super().__init__(parent)
        self.source_path = source_path
        self.interval = interval
        self._stop_flag = False
        self._last_stat = None

    def run(self):
        self._stop_flag = False
        try:
            s = os.stat(self.source_path)
            self._last_stat = (s.st_size, s.st_mtime)
        except OSError:
            self._last_stat = None

        while not self._stop_flag:
            for _ in range(self.interval):
                if self._stop_flag:
                    return
                time.sleep(1)
            if self._stop_flag:
                break
            self.tick.emit()
            try:
                s = os.stat(self.source_path)
                cur = (s.st_size, s.st_mtime)
                if cur != self._last_stat:
                    self._last_stat = cur
                    self.file_changed.emit()
            except OSError:
                pass

    def stop(self):
        self._stop_flag = True


class SplitCopyThread(QThread):
    copy_ok = pyqtSignal()
    copy_fail = pyqtSignal(str)
    split_done = pyqtSignal(dict)

    def __init__(self, source_path, output_dir, dest_dir, seen_files, parent=None):
        super().__init__(parent)
        self.source_path = source_path
        self.output_dir = output_dir
        self.dest_dir = dest_dir or ""
        self.seen_files = seen_files

    def run(self):
        temp_dir = os.path.dirname(self.output_dir) or os.path.dirname(self.source_path)
        fd, temp_path = tempfile.mkstemp(suffix=".txt", prefix="_splitter_", dir=temp_dir)
        os.close(fd)
        try:
            self._execute(temp_path)
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    def _execute(self, temp_path):
        try:
            shutil.copy2(self.source_path, temp_path)
            self.copy_ok.emit()
        except Exception as e:
            self.copy_fail.emit(f"Copy failed: {e}")
            return

        try:
            with open(temp_path, 'r', encoding='utf-8', errors='replace') as fh:
                content = fh.read()
        except Exception as e:
            self.copy_fail.emit(f"Read temp failed: {e}")
            return

        segments = split_log_content(content)
        new_count = synced_count = skipped_count = 0
        new_file_names = []

        real_out_dir = os.path.realpath(self.output_dir)
        if self.dest_dir:
            os.makedirs(self.dest_dir, exist_ok=True)

        for seg in segments:
            parsed = parse_segment(seg)
            filename = build_output_filename(parsed)
            if filename is None:
                skipped_count += 1
                continue
            if filename in self.seen_files:
                continue

            out_path = os.path.join(self.output_dir, filename)
            # Path containment guard — reject traversal attempts from log content
            if os.path.commonpath([os.path.realpath(out_path), real_out_dir]) != real_out_dir:
                self.copy_fail.emit(f"Rejected unsafe path: {filename}")
                skipped_count += 1
                continue

            try:
                with open(out_path, 'w', encoding='utf-8') as fh:
                    fh.write(seg.rstrip() + "\n\n")
                new_count += 1
                new_file_names.append(filename)
            except Exception as e:
                self.copy_fail.emit(f"Write {filename}: {e}")
                continue

            if self.dest_dir:
                try:
                    shutil.copy2(out_path, os.path.join(self.dest_dir, filename))
                    synced_count += 1
                except Exception as e:
                    self.copy_fail.emit(f"Sync {filename}: {e}")

        self.split_done.emit(dict(
            new_files=new_count, synced=synced_count,
            skipped=skipped_count, total_segs=len(segments),
            new_file_names=new_file_names,
        ))


# ─────────────────────────────────────────────────────────────
#  Main window  (compact, 480×270 ~ 960×540)
# ─────────────────────────────────────────────────────────────
class RealtimeSplitterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self._watcher_thread = None
        self._split_thread = None
        self._pending_split = False
        self._seen_files = set()
        self._session_written = 0
        self._session_synced = 0
        self._initUI()

    # ── UI construction ──────────────────────────────────────

    def _initUI(self):
        self.setWindowTitle('Log Splitter — Live')
        self.setMinimumSize(480, 270)
        self.setMaximumSize(960, 540)
        self.resize(720, 380)
        self.setStyleSheet(STYLESHEET)
        if os.path.exists(APP_ICON_PATH):
            self.setWindowIcon(QIcon(APP_ICON_PATH))

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        lay.addWidget(self._mk_header())
        lay.addWidget(self._mk_config())
        lay.addWidget(self._mk_status_strip())
        lay.addWidget(self._mk_log(), stretch=1)

    def _mk_header(self):
        frame = QFrame()
        frame.setObjectName("header")
        frame.setFixedHeight(34)
        h = QHBoxLayout(frame)
        h.setContentsMargins(10, 0, 8, 0)
        h.setSpacing(6)

        self._dot = QLabel("●")
        self._dot.setObjectName("dotIdle")
        self._dot_state = QLabel("Idle")
        self._dot_state.setObjectName("dotState")

        title = QLabel("Log Splitter  ·  Live")
        title.setObjectName("appTitle")

        self.btn_start = QPushButton("▶  Start")
        self.btn_start.setObjectName("start")
        self.btn_start.setFixedHeight(26)
        self.btn_start.clicked.connect(self.start_watching)

        self.btn_stop = QPushButton("■  Stop")
        self.btn_stop.setObjectName("stop")
        self.btn_stop.setFixedHeight(26)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_watching)

        h.addWidget(self._dot)
        h.addWidget(self._dot_state)
        h.addSpacing(4)
        h.addWidget(title)
        h.addStretch(1)
        h.addWidget(self.btn_start)
        h.addWidget(self.btn_stop)
        return frame

    def _mk_config(self):
        frame = QFrame()
        frame.setObjectName("configPanel")
        grid = QHBoxLayout()          # outer wrapper to get the border margins right
        grid.setContentsMargins(0, 0, 0, 0)
        frame.setLayout(grid)

        inner = QWidget()
        grid.addWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)

        def browse_btn(slot, icon_key=QStyle.SP_DirOpenIcon):
            b = QPushButton()
            b.setObjectName("browse")
            b.setIcon(self.style().standardIcon(icon_key))
            b.setIconSize(QSize(13, 13))
            b.setFixedSize(24, 24)
            b.clicked.connect(slot)
            return b

        def row(tag, edit_widget, btn):
            h = QHBoxLayout()
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(5)
            lbl = QLabel(tag)
            lbl.setObjectName("rowTag")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            h.addWidget(lbl)
            h.addWidget(edit_widget, stretch=1)
            h.addWidget(btn)
            return h

        # Row 0 — source file
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("Log_ALL.txt …")
        self.file_input.setReadOnly(True)
        self.file_input.setFixedHeight(24)
        self._btn_src = browse_btn(self.browse_source, QStyle.SP_DialogOpenButton)
        lay.addLayout(row("SRC", self.file_input, self._btn_src))

        # Row 1 — output folder
        self.dir_output_input = QLineEdit()
        self.dir_output_input.setText(
            os.path.join(os.path.expanduser('~'), 'Documents', 'Log_Output'))
        self.dir_output_input.setFixedHeight(24)
        self._btn_out = browse_btn(self.browse_output)
        lay.addLayout(row("OUT", self.dir_output_input, self._btn_out))

        # Row 2 — dest folder + poll interval (inline)
        self.dir_dest_input = QLineEdit()
        self.dir_dest_input.setPlaceholderText("Dest folder (opt) …")
        self.dir_dest_input.setFixedHeight(24)
        self._btn_dst = browse_btn(self.browse_dest)

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(10, 300)
        self.spin_interval.setValue(DEFAULT_POLL_INTERVAL)
        self.spin_interval.setSuffix(" s")
        self.spin_interval.setFixedHeight(24)
        self.spin_interval.setToolTip("Poll interval (seconds)")

        h2 = QHBoxLayout()
        h2.setContentsMargins(0, 0, 0, 0)
        h2.setSpacing(5)
        lbl_dst = QLabel("DST")
        lbl_dst.setObjectName("rowTag")
        lbl_dst.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h2.addWidget(lbl_dst)
        h2.addWidget(self.dir_dest_input, stretch=1)
        h2.addWidget(self._btn_dst)
        h2.addSpacing(4)
        h2.addWidget(self.spin_interval)
        lay.addLayout(h2)

        self._config_widgets = [
            self.file_input, self._btn_src,
            self.dir_output_input, self._btn_out,
            self.dir_dest_input, self._btn_dst,
            self.spin_interval,
        ]
        return frame

    def _mk_status_strip(self):
        frame = QFrame()
        frame.setObjectName("statusStrip")
        frame.setFixedHeight(26)
        h = QHBoxLayout(frame)
        h.setContentsMargins(10, 0, 10, 0)
        h.setSpacing(4)

        def sep():
            l = QLabel("|")
            l.setObjectName("sep")
            return l

        def kv(key, val_text, val_obj=None):
            k = QLabel(key)
            k.setObjectName("statusKey")
            v = QLabel(val_text)
            v.setObjectName(val_obj or "statusVal")
            return k, v

        self._lbl_checked_key, self._lbl_checked = kv("checked", "—")
        self._lbl_copy_result = QLabel("—")
        self._lbl_copy_result.setObjectName("statusVal")
        _, self._lbl_written = kv("", "0")
        _, self._lbl_synced = kv("", "0")

        written_icon = QLabel("↑")
        written_icon.setObjectName("statusKey")
        synced_icon = QLabel("→")
        synced_icon.setObjectName("statusKey")

        h.addWidget(self._lbl_checked_key)
        h.addWidget(self._lbl_checked)
        h.addWidget(sep())
        h.addWidget(QLabel("copy"))
        h.addWidget(self._lbl_copy_result)
        # fix: set objectName on the static "copy" label
        h.itemAt(3).widget().setObjectName("statusKey")
        h.addWidget(sep())
        h.addWidget(written_icon)
        h.addWidget(self._lbl_written)
        h.addWidget(sep())
        h.addWidget(synced_icon)
        h.addWidget(self._lbl_synced)
        h.addStretch(1)
        return frame

    def _mk_log(self):
        frame = QFrame()
        frame.setObjectName("logPanel")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(4, 4, 4, 4)

        self.activity_log = QTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setPlaceholderText("Activity log…")
        self.activity_log.document().setMaximumBlockCount(1000)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(9)
        self.activity_log.setFont(mono)
        lay.addWidget(self.activity_log)
        return frame

    # ── Browse ────────────────────────────────────────────────

    def browse_source(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Select source log file", "", "Text Files (*.txt);;All Files (*)")
        if p:
            self.file_input.setText(os.path.normpath(p))
            self._log(f"SRC → {p}")

    def browse_output(self):
        p = QFileDialog.getExistingDirectory(self, "Select output folder")
        if p:
            self.dir_output_input.setText(os.path.normpath(p))

    def browse_dest(self):
        p = QFileDialog.getExistingDirectory(self, "Select destination folder")
        if p:
            self.dir_dest_input.setText(os.path.normpath(p))

    # ── Watcher control ───────────────────────────────────────

    def _validate(self):
        src = self.file_input.text().strip()
        out = self.dir_output_input.text().strip()
        if not src:
            QMessageBox.critical(self, "Error", "Source file not set.", QMessageBox.Ok)
            return False
        if not os.path.isfile(src):
            QMessageBox.critical(self, "Error", "Source file not found.", QMessageBox.Ok)
            return False
        if not out:
            QMessageBox.critical(self, "Error", "Output folder not set.", QMessageBox.Ok)
            return False
        return True

    def start_watching(self):
        if not self._validate():
            return
        out = self.dir_output_input.text().strip()
        os.makedirs(out, exist_ok=True)
        self._seen_files = scan_existing_files(out)
        self._session_written = 0
        self._session_synced = 0
        self._lbl_written.setText("0")
        self._lbl_synced.setText("0")
        self._pending_split = False

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        for w in self._config_widgets:
            w.setEnabled(False)

        self._set_dot("watching")
        interval = self.spin_interval.value()
        self._watcher_thread = WatcherThread(
            self.file_input.text().strip(), interval)
        self._watcher_thread.file_changed.connect(self._on_file_changed)
        self._watcher_thread.tick.connect(self._on_tick)
        self._watcher_thread.start()

        src = self.file_input.text().strip()
        dst = self.dir_dest_input.text().strip()
        self._log(f"Watching  {src}  every {interval}s")
        self._log(f"OUT  {out}" + (f"  →  DST  {dst}" if dst else ""))
        self._log(f"Seeded {len(self._seen_files)} existing file(s) — will skip")

        # Run an immediate first split to catch current content right away
        self._log("Initial scan starting…")
        self._launch_split()

    def stop_watching(self):
        if self._watcher_thread:
            self._watcher_thread.stop()
            self._watcher_thread.wait(3000)
            self._watcher_thread = None
        self._pending_split = False
        self._set_dot("idle")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        for w in self._config_widgets:
            w.setEnabled(True)
        self._log("Watcher stopped.")

    # ── Helpers ───────────────────────────────────────────────

    def _set_dot(self, state):
        mapping = {
            "idle":     ("dotIdle",     "Idle"),
            "watching": ("dotWatching", "Watching"),
            "busy":     ("dotBusy",     "Splitting…"),
            "error":    ("dotError",    "Error"),
        }
        obj, text = mapping.get(state, ("dotIdle", "Idle"))
        self._dot.setObjectName(obj)
        self._dot_state.setText(text)
        for w in (self._dot, self._dot_state):
            w.style().unpolish(w)
            w.style().polish(w)

    def _set_copy_badge(self, ok):
        self._lbl_copy_result.setObjectName("badgeOk" if ok else "badgeFail")
        self._lbl_copy_result.setText("✓ OK" if ok else "✗ ERR")
        self._lbl_copy_result.style().unpolish(self._lbl_copy_result)
        self._lbl_copy_result.style().polish(self._lbl_copy_result)

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.activity_log.append(f"[{ts}]  {msg}")

    def _launch_split(self):
        self._set_dot("busy")
        self._pending_split = False
        self._split_thread = SplitCopyThread(
            self.file_input.text().strip(),
            self.dir_output_input.text().strip(),
            self.dir_dest_input.text().strip() or None,
            set(self._seen_files),
        )
        self._split_thread.copy_ok.connect(self._on_copy_ok)
        self._split_thread.copy_fail.connect(self._on_copy_fail)
        self._split_thread.split_done.connect(self._on_split_done)
        self._split_thread.finished.connect(self._on_split_thread_finished)
        self._split_thread.start()

    # ── Slots — WatcherThread ─────────────────────────────────

    def _on_tick(self):
        """Called on every poll cycle — keeps the 'checked' timestamp alive."""
        self._lbl_checked.setText(datetime.now().strftime("%H:%M:%S"))

    def _on_file_changed(self):
        self._lbl_checked.setText(datetime.now().strftime("%H:%M:%S"))
        if self._split_thread and self._split_thread.isRunning():
            self._pending_split = True
            self._log("Change detected — queued")
            return
        self._log("Change detected → splitting")
        self._launch_split()

    # ── Slots — SplitCopyThread ───────────────────────────────

    def _on_copy_ok(self):
        self._set_copy_badge(True)

    def _on_copy_fail(self, msg):
        self._set_copy_badge(False)
        self._log(f"ERR  {msg}")
        self._set_dot("error")

    def _on_split_done(self, stats):
        for name in stats.get("new_file_names", []):
            self._seen_files.add(name)
            self._session_written += 1
            self._log(f"  ↑  {name}")
        self._lbl_written.setText(str(self._session_written))
        self._session_synced += stats["synced"]
        self._lbl_synced.setText(str(self._session_synced))
        if self._watcher_thread and self._watcher_thread.isRunning():
            self._set_dot("watching")
        self._log(
            f"Done  +{stats['new_files']} new  "
            f"→{stats['synced']} synced  "
            f"skip {stats['skipped']}  "
            f"({stats['total_segs']} segs)"
        )

    def _on_split_thread_finished(self):
        self._split_thread = None
        if self._pending_split:
            self._log("Running queued split…")
            self._launch_split()

    # ── Close ─────────────────────────────────────────────────

    def closeEvent(self, event):
        split_thread = self._split_thread  # save ref before stop_watching clears state
        self.stop_watching()
        if split_thread and split_thread.isRunning():
            split_thread.wait(5000)
        event.accept()


# ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    if os.path.exists(APP_ICON_PATH):
        app.setWindowIcon(QIcon(APP_ICON_PATH))
    window = RealtimeSplitterApp()
    window.show()
    sys.exit(app.exec_())
