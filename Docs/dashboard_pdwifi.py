import sys
import os
import time
from collections import defaultdict
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
                             QHeaderView, QFrame, QFileDialog, QPushButton, QSplitter,
                             QLineEdit)
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal, QVariantAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QColor, QPalette
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


# 主題必備鍵與預設值
THEME_DEFAULTS = {
    "bg": "#222222", "card_bg": "#222222", "text": "#FFFFFF", "text_muted": "#AAAAAA",
    "border": "#444444", "chart_bg": "#222222", "split": "#444",
    "table_grid": "#444444", "table_header_bg": "#333333", "table_bg": "#222222",
    "pass": "#4CAF50", "fail": "#F44336", "term": "#9C27B0", "total": "#2196F3", "yield": "#FF9800",
    "pass_flash": "#C8E6C9", "fail_flash": "#FFCDD2", "term_flash": "#E1BEE7", "total_flash": "#BBDEFB", "yield_flash": "#FFE082",
    "table_pass_flash": "#1B5E20", "table_fail_flash": "#b71c1c", "table_term_flash": "#4A148C"
}

THEME_DARK = {
    "bg": "#121212", "card_bg": "#1E1E1E", "text": "#FFFFFF", "text_muted": "#AAAAAA",
    "border": "#333333", "chart_bg": "#1A1A1A", "split": "#333",
    "table_grid": "#2F2F2F", "table_header_bg": "#252525", "table_bg": "#1E1E1E",
    "pass": "#4CAF50", "fail": "#F44336", "term": "#9C27B0", "total": "#2196F3", "yield": "#FF9800",
    "pass_flash": "#C8E6C9", "fail_flash": "#FFCDD2", "term_flash": "#E1BEE7", "total_flash": "#BBDEFB", "yield_flash": "#FFE082",
    "table_pass_flash": "#1B5E20", "table_fail_flash": "#b71c1c", "table_term_flash": "#4A148C"
}

THEME_LIGHT = {
    "bg": "#EAEAEA", "card_bg": "#FFFFFF", "text": "#111111", "text_muted": "#555555",
    "border": "#CCCCCC", "chart_bg": "#F5F5F5", "split": "#BBB",
    "table_grid": "#D9D9D9", "table_header_bg": "#F0F0F0", "table_bg": "#FFFFFF",
    "pass": "#2E7D32", "fail": "#C62828", "term": "#6A1B9A", "total": "#1565C0", "yield": "#E65100",
    "pass_flash": "#4CAF50", "fail_flash": "#E53935", "term_flash": "#8E24AA", "total_flash": "#1E88E5", "yield_flash": "#FF9800",
    "table_pass_flash": "#A5D6A7", "table_fail_flash": "#EF9A9A", "table_term_flash": "#CE93D8"
}

# 主題完整性檢查與自動補齊
def ensure_theme_keys(theme: dict, theme_name: str = "theme"):
    missing = []
    for k, v in THEME_DEFAULTS.items():
        if k not in theme:
            theme[k] = v
            missing.append(k)
    if missing:
        print(f"[警告] {theme_name} 缺少主題鍵已自動補齊: {missing}")
    return theme

ensure_theme_keys(THEME_DARK, "THEME_DARK")
ensure_theme_keys(THEME_LIGHT, "THEME_LIGHT")

def parse_log_filename(filename):
    try:
        parts = filename.replace(".txt", "").split("_")
        if len(parts) >= 4:
            log_dt = datetime.now()
            if len(parts) >= 2:
                try:
                    log_dt = datetime.strptime(f"{parts[0]}_{parts[1]}", "%Y%m%d_%H%M%S")
                except ValueError:
                    pass
            return {
                "sn": parts[2], "result": parts[-1].upper(), "time": log_dt.strftime("%H:%M:%S"), "dt": log_dt
            }
    except Exception:
        pass
    return None

def get_documents_path():
    return os.path.join(os.path.expanduser("~"), "Documents")

class AnimatedNumberLabel(QLabel):
    def __init__(self, is_percent=False, base_color="#FFFFFF", flash_color="#FFFFFF", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_percent = is_percent
        self.current_val = 0.0
        self.target_val = 0.0
        self._base_color = QColor(base_color)
        self._flash_color = QColor(flash_color)
        
        self._val_anim = QVariantAnimation(self)
        self._val_anim.setDuration(1200)
        self._val_anim.setEasingCurve(QEasingCurve.OutExpo)
        self._val_anim.valueChanged.connect(self._on_val_changed)
        
        self._color_anim = QVariantAnimation(self)
        self._color_anim.setDuration(1000)
        self._color_anim.setEasingCurve(QEasingCurve.OutQuad)
        self._color_anim.valueChanged.connect(self._on_color_changed)
        self.setInitialValue(0)

    def update_colors(self, base_color, flash_color):
        self._base_color = QColor(base_color)
        self._flash_color = QColor(flash_color)
        self._on_color_changed(self._base_color)

    def _on_color_changed(self, color):
        palette = self.palette()
        palette.setColor(QPalette.WindowText, color)
        self.setPalette(palette)

    def _on_val_changed(self, val):
        self.current_val = float(val)
        if self.is_percent:
            self.setText(f"{self.current_val:.1f}%")
        else:
            self.setText(str(int(self.current_val)))

    def setValue(self, new_val):
        if abs(self.target_val - new_val) < 0.01:
            return
        self._val_anim.stop()
        self._color_anim.stop()
        self._val_anim.setStartValue(self.current_val)
        self._val_anim.setEndValue(float(new_val))
        self._val_anim.start()
        self._color_anim.setStartValue(self._flash_color)
        self._color_anim.setEndValue(self._base_color)
        self._color_anim.start()
        self.target_val = float(new_val)
        
    def setInitialValue(self, val):
        self.current_val = float(val)
        self.target_val = float(val)
        self._on_color_changed(self._base_color)
        self._on_val_changed(val)

class HourlyChart(FigureCanvasQTAgg):
    def __init__(self):
        self.fig = Figure()
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.theme = THEME_DARK
        self._style_axes()

    def set_theme(self, theme):
        self.theme = theme
        self.fig.patch.set_facecolor(self.theme["chart_bg"])
        self.ax.set_facecolor(self.theme["chart_bg"])
        self.draw()

    def _style_axes(self):
        self.fig.patch.set_facecolor(self.theme["chart_bg"])
        self.ax.set_facecolor(self.theme["chart_bg"])
        self.ax.tick_params(colors=self.theme["text_muted"], labelsize=10)
        for spine in self.ax.spines.values():
            spine.set_edgecolor(self.theme["border"])
        self.fig.tight_layout(pad=1.5)

    def update_chart(self, hourly_counts, title_date_str=""):
        self.ax.clear()
        self._style_axes()
        title = f"每小時測試數量 ({title_date_str})" if title_date_str else "每小時測試數量"
        self.ax.set_title(title, color=self.theme["text"], pad=10, fontsize=12)
        if not hourly_counts:
            self.draw()
            return
        hours = sorted(hourly_counts.keys())
        counts = [hourly_counts[h] for h in hours]
        labels = [f"{h:02d}:00" for h in hours]
        bars = self.ax.bar(labels, counts, color=self.theme["total"], width=0.6, zorder=2)
        self.ax.set_ylabel("測試筆數", color=self.theme["text_muted"], fontsize=10)
        self.ax.grid(axis="y", color=self.theme["border"], linestyle="--", alpha=0.7, zorder=1)
        self.ax.tick_params(axis="x", rotation=45, colors=self.theme["text_muted"])
        for bar, count in zip(bars, counts):
            self.ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + (max(counts)*0.02 if max(counts) > 0 else 0.1),
                str(count), ha="center", va="bottom", color=self.theme["text"], fontsize=10, fontweight='bold')
        self.fig.tight_layout(pad=1.5)
        self.draw()

class PassFailPieChart(FigureCanvasQTAgg):
    def __init__(self):
        self.fig = Figure()
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.theme = THEME_DARK
        self._style_axes()

    def set_theme(self, theme):
        self.theme = theme
        self.fig.patch.set_facecolor(self.theme["chart_bg"])
        self.ax.set_facecolor(self.theme["chart_bg"])
        self.draw()

    def _style_axes(self):
        self.fig.patch.set_facecolor(self.theme["chart_bg"])
        self.ax.set_facecolor(self.theme["chart_bg"])
        self.fig.tight_layout(pad=1.5)

    def update_chart(self, pass_count, fail_count, terminated_count):
        self.ax.clear()
        self._style_axes()
        self.ax.set_title("測試結果分布", color=self.theme["text"], pad=10, fontsize=12)
        total = pass_count + fail_count + terminated_count
        if total <= 0:
            self.ax.text(0.5, 0.5, "目前無資料", color=self.theme["text_muted"], ha="center", va="center", fontsize=12)
            self.draw()
            return

        values, labels, colors = [], [], []
        if pass_count > 0:
            values.extend([pass_count]); labels.append("PASS"); colors.append(self.theme["pass"])
        if fail_count > 0:
            values.extend([fail_count]); labels.append("FAIL"); colors.append(self.theme["fail"])
        if terminated_count > 0:
            values.extend([terminated_count]); labels.append("TERM"); colors.append(self.theme["term"])

        self.ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90, colors=colors,
                    textprops={"color": ("#FFFFFF" if self.theme==THEME_DARK else "#000000"), "fontsize": 11, "fontweight": "bold"}, explode=[0.05]*len(values))
        self.ax.axis("equal")
        self.fig.tight_layout(pad=1.5)
        self.draw()

class LogWatcher(QThread):
    new_log_signal = pyqtSignal(dict)
    def __init__(self, watch_path):
        super().__init__()
        self.watch_path = watch_path
        self._running = True
        self._observer = None
    def run(self):
        event_handler = self.Handler(self.new_log_signal)
        self._observer = Observer()
        self._observer.schedule(event_handler, self.watch_path, recursive=False)
        self._observer.start()
        try:
            while self._running: time.sleep(0.2)
        finally:
            if self._observer and self._observer.is_alive():
                self._observer.stop(); self._observer.join()
    def stop(self):
        self._running = False
        if self._observer and self._observer.is_alive(): self._observer.stop()
    class Handler(FileSystemEventHandler):
        def __init__(self, signal): self.signal = signal
        def on_created(self, event):
            if not event.is_directory and event.src_path.endswith(".txt"):
                filename = os.path.basename(event.src_path)
                data = parse_log_filename(filename)
                if data: self.signal.emit(data)

class DashboardApp(QMainWindow):
    def __init__(self, watch_path):
        super().__init__()
        self.watch_path = os.path.abspath(watch_path)
        self.stats = {"total": 0, "pass": 0, "terminated": 0, "fail": 0}
        self.hourly_counts = defaultdict(int)
        self.records_by_sn = {}
        self.target_qty = 100
        self.watcher = None
        self.is_fullscreen = False
        self.theme = THEME_DARK
        
        self.needs_refresh = False
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._check_refresh)
        self.refresh_timer.start(500)
        
        self._last_rendered_sns = set()
        self._first_render_done = False
        self._row_anims = []

        self.init_ui()
        self.start_watcher()
        self.load_existing_logs()

    def init_ui(self):
        self.setWindowTitle("PIXI WiFi Module Test Dashboard (產線監控專用)")
        self.resize(1600, 900)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # === Top bar ===
        top_bar = QHBoxLayout()
        top_bar.setSpacing(15)
        
        self.header_boxes = []
        def create_header_input(label_text, placeholder, default_val=""):
            container = QFrame()
            lay = QHBoxLayout(container)
            lay.setContentsMargins(10, 5, 10, 5)
            lbl = QLabel(label_text)
            lbl.setFont(QFont("Arial", 12, QFont.Bold))
            inp = QLineEdit(default_val)
            inp.setPlaceholderText(placeholder)
            inp.setFont(QFont("Arial", 16, QFont.Bold))
            lay.addWidget(lbl)
            lay.addWidget(inp)
            self.header_boxes.append((container, lbl, inp))
            return container, inp

        prod_box, self.input_product = create_header_input("PRODUCT:", "請輸入產品名稱")
        wo_box, self.input_work_order = create_header_input("WORK ORDER:", "請輸入工單號碼")
        tgt_box, self.input_target_qty = create_header_input("TARGET QTY:", "100", "100")
        self.input_target_qty.textChanged.connect(self.apply_target_qty)

        top_bar.addWidget(prod_box)
        top_bar.addWidget(wo_box)
        top_bar.addWidget(tgt_box)
        top_bar.addStretch()

        self.lbl_clock = QLabel()
        self.lbl_clock.setFont(QFont("Courier", 24, QFont.Bold))
        self.lbl_clock.setAlignment(Qt.AlignCenter)
        top_bar.addWidget(self.lbl_clock)
        main_layout.addLayout(top_bar)

        self._tick_clock()
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._tick_clock)
        self.clock_timer.start(1000)

        # === KPI Row ===
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(15)
        self.kpi_cards = []
        
        self.lbl_total = self.create_large_kpi_card(kpi_row, "TOTAL (總計)", "total", "total_flash")
        self.lbl_pass = self.create_large_kpi_card(kpi_row, "PASS (通過)", "pass", "pass_flash")
        self.lbl_fail = self.create_large_kpi_card(kpi_row, "FAIL (失敗)", "fail", "fail_flash")
        self.lbl_terminated = self.create_large_kpi_card(kpi_row, "TERM (終止)", "term", "term_flash")
        self.lbl_yield = self.create_large_kpi_card(kpi_row, "YIELD (達成率)", "yield", "yield_flash", font_size=52, is_percent=True)
        main_layout.addLayout(kpi_row)

        # === Splitter ===
        self.splitter = QSplitter(Qt.Horizontal)
        
        self.charts_frame = QFrame()
        charts_layout = QVBoxLayout(self.charts_frame)
        self.hourly_chart = HourlyChart()
        self.pie_chart = PassFailPieChart()
        charts_h_layout = QHBoxLayout()
        charts_h_layout.addWidget(self.hourly_chart, 3)
        charts_h_layout.addWidget(self.pie_chart, 2)
        charts_layout.addLayout(charts_h_layout)
        self.splitter.addWidget(self.charts_frame)

        self.table_frame = QFrame()
        table_layout = QVBoxLayout(self.table_frame)
        self.tbl_title = QLabel("最新測試紀錄 (Latest Records)")
        self.tbl_title.setFont(QFont("Arial", 14, QFont.Bold))
        
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["日期時間 (DateTime)", "序號 (SN)", "結果 (Result)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.verticalHeader().setDefaultSectionSize(45)
        
        table_layout.addWidget(self.tbl_title)
        table_layout.addWidget(self.table)
        self.splitter.addWidget(self.table_frame)
        self.splitter.setSizes([900, 700])
        main_layout.addWidget(self.splitter, stretch=1)

        # === Bottom bar ===
        bottom_bar = QHBoxLayout()
        self.path_label = QLabel(f"監控目錄: {self.watch_path}")
        self.path_label.setFont(QFont("Arial", 10))
        
        self.btn_theme = QPushButton("切換主題 (Theme)")
        self.btn_theme.setCursor(Qt.PointingHandCursor)
        self.btn_theme.clicked.connect(self.toggle_theme)

        self.btn_choose_folder = QPushButton("📁 更改目錄")
        self.btn_choose_folder.setCursor(Qt.PointingHandCursor)
        self.btn_choose_folder.clicked.connect(self.choose_watch_folder)
        
        self.btn_toggle_fullscreen = QPushButton("⛶ 全螢幕 (F11)")
        self.btn_toggle_fullscreen.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_fullscreen.clicked.connect(self.toggle_fullscreen)
        
        bottom_bar.addWidget(self.path_label)
        bottom_bar.addStretch()
        bottom_bar.addWidget(self.btn_theme)
        bottom_bar.addWidget(self.btn_choose_folder)
        bottom_bar.addWidget(self.btn_toggle_fullscreen)
        main_layout.addLayout(bottom_bar)

        self.apply_theme(THEME_DARK)
        self.apply_target_qty()

    def _tick_clock(self):
        self.lbl_clock.setText(datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))

    def create_large_kpi_card(self, layout, title, color_key, flash_key, font_size=48, is_percent=False):
        frame = QFrame()
        vbox = QVBoxLayout(frame)
        vbox.setAlignment(Qt.AlignCenter)
        lbl_title = QLabel(title)
        lbl_title.setFont(QFont("Arial", 12, QFont.Bold))
        lbl_title.setAlignment(Qt.AlignCenter)
        
        lbl_value = AnimatedNumberLabel(is_percent=is_percent)
        lbl_value.setFont(QFont("Arial", font_size, QFont.Bold))
        lbl_value.setAlignment(Qt.AlignCenter)
        
        vbox.addWidget(lbl_title)
        vbox.addWidget(lbl_value)
        layout.addWidget(frame)
        self.kpi_cards.append((frame, lbl_title, lbl_value, color_key, flash_key))
        return lbl_value

    def toggle_theme(self):
        self.theme = THEME_LIGHT if self.theme == THEME_DARK else THEME_DARK
        self.apply_theme(self.theme)
        self.needs_refresh = True

    def apply_theme(self, t):
        self.central_widget.setStyleSheet(f"background-color: {t['bg']}; color: {t['text']}; font-family: 'Microsoft YaHei', Arial;")
        
        for container, lbl, inp in self.header_boxes:
            container.setStyleSheet(f"background-color: {t['card_bg']}; border-radius: 8px; border: 1px solid {t['border']};")
            lbl.setStyleSheet(f"color: {t['text_muted']}; border: none;")
            inp.setStyleSheet(f"background: transparent; color: {t['text']}; border: none; min-width: 150px;")
        
        self.lbl_clock.setStyleSheet(f"color: {t['total']}; background-color: {t['card_bg']}; border-radius: 8px; padding: 5px 20px; border: 1px solid {t['border']};")
        
        for frame, lbl_title, lbl_value, c_key, f_key in self.kpi_cards:
            frame.setStyleSheet(f"QFrame {{ background-color: {t['card_bg']}; border-radius: 12px; border-top: 6px solid {t[c_key]}; border-bottom: 1px solid {t['border']}; border-left: 1px solid {t['border']}; border-right: 1px solid {t['border']}; }}")
            lbl_title.setStyleSheet(f"color: {t['text_muted']}; border: none;")
            lbl_value.update_colors(t[c_key], t[f_key])

        self.splitter.setStyleSheet(f"QSplitter::handle {{ background: {t['split']}; width: 6px; border-radius: 3px; }}")
        self.charts_frame.setStyleSheet(f"background-color: {t['chart_bg']}; border-radius: 10px; border: 1px solid {t['border']};")
        self.table_frame.setStyleSheet(f"background-color: {t['card_bg']}; border-radius: 10px; border: 1px solid {t['border']};")
        self.tbl_title.setStyleSheet(f"color: {t['text']}; padding-bottom: 5px;")
        
        self.table.setStyleSheet(f"""
            QTableWidget {{ background-color: {t['card_bg']}; color: {t['text']}; gridline-color: {t['table_grid']}; border: 1px solid {t['border']}; font-size: 13pt; font-weight: bold; }}
            QHeaderView::section {{ background-color: {t['table_header_bg']}; color: {t['text_muted']}; padding: 8px; border: 1px solid {t['border']}; font-size: 12pt; }}
        """)
        
        btn_style = f"QPushButton {{ background-color: {t['table_header_bg']}; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 5px; padding: 6px 12px; font-weight: bold; }} QPushButton:hover {{ background-color: {t['border']}; }}"
        self.btn_theme.setStyleSheet(btn_style)
        self.btn_choose_folder.setStyleSheet(btn_style)
        self.btn_toggle_fullscreen.setStyleSheet(btn_style)
        self.path_label.setStyleSheet(f"color: {t['text_muted']};")

        self.hourly_chart.set_theme(t)
        self.pie_chart.set_theme(t)

    def start_watcher(self):
        self.stop_watcher()
        self.watcher = LogWatcher(self.watch_path)
        self.watcher.new_log_signal.connect(self.update_dashboard)
        self.watcher.start()

    def stop_watcher(self):
        if self.watcher and self.watcher.isRunning():
            self.watcher.stop(); self.watcher.wait(2000)

    def reset_dashboard(self):
        self.records_by_sn.clear()
        self.hourly_counts.clear()
        self.lbl_total.setInitialValue(0)
        self.lbl_pass.setInitialValue(0)
        self.lbl_terminated.setInitialValue(0)
        self.lbl_fail.setInitialValue(0)
        self.lbl_yield.setInitialValue(0)
        self._last_rendered_sns.clear()
        self._first_render_done = False
        for anim in self._row_anims: anim.stop()
        self._row_anims.clear()
        self.table.setRowCount(0)
        self.hourly_chart.update_chart({})
        self.pie_chart.update_chart(0, 0, 0)

    def switch_watch_path(self, new_path):
        self.watch_path = os.path.abspath(new_path)
        self.path_label.setText(f"監控目錄: {self.watch_path}")
        self.reset_dashboard()
        self.start_watcher()
        self.load_existing_logs()

    def choose_watch_folder(self):
        selected_dir = QFileDialog.getExistingDirectory(self, "請選擇測試紀錄檔目錄", self.watch_path, QFileDialog.ShowDirsOnly)
        if selected_dir: self.switch_watch_path(selected_dir)

    def toggle_fullscreen(self):
        if self.is_fullscreen: self.showNormal()
        else: self.showFullScreen()
        self.is_fullscreen = not self.is_fullscreen

    def load_existing_logs(self):
        txt_files = [name for name in os.listdir(self.watch_path) if name.endswith(".txt")]
        for filename in sorted(txt_files):
            data = parse_log_filename(filename)
            if data: self.update_dashboard(data, refresh=False)
        self.needs_refresh = True

    def update_dashboard(self, data, refresh=True):
        sn = data["sn"]
        dt = data.get("dt", datetime.now())
        prev = self.records_by_sn.get(sn)
        if prev and dt <= prev.get("dt", datetime.min): return
        self.records_by_sn[sn] = data
        if refresh: self.needs_refresh = True

    def _check_refresh(self):
        if self.needs_refresh:
            self.refresh_dashboard()
            self.needs_refresh = False

    def refresh_dashboard(self):
        for anim in self._row_anims: anim.stop()
        self._row_anims.clear()
        
        records = sorted(self.records_by_sn.values(), key=lambda item: item.get("dt", datetime.min), reverse=True)
        latest_date = records[0].get("dt", datetime.now()).date() if records else datetime.now().date()

        pass_count = terminated_count = fail_count = 0
        self.hourly_counts.clear()

        for record in records:
            result = record.get("result", "").upper()
            record_dt = record.get("dt", datetime.now())
            if result == "PASS": pass_count += 1
            elif result == "TERMINATED": terminated_count += 1
            else: fail_count += 1
            
            # 只採用距離最近一天(latest_date)的資料作為小時統計
            if record_dt.date() == latest_date:
                self.hourly_counts[record_dt.hour] += 1

        total_count = pass_count + terminated_count + fail_count
        yield_rate = (pass_count / self.target_qty) * 100 if self.target_qty > 0 else 0.0

        self.lbl_total.setValue(total_count)
        self.lbl_pass.setValue(pass_count)
        self.lbl_terminated.setValue(terminated_count)
        self.lbl_fail.setValue(fail_count)
        self.lbl_yield.setValue(yield_rate)

        date_str = latest_date.strftime("%Y-%m-%d")
        self.hourly_chart.update_chart(dict(self.hourly_counts), date_str)
        self.pie_chart.update_chart(pass_count, fail_count, terminated_count)

        self.table.setRowCount(0)
        new_rendered_sns = set()
        
        base_bg = QColor(self.theme["table_bg"])
        for record in records[:12]:
            sn = record.get("sn", "")
            new_rendered_sns.add(sn)
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # 結合日期與時間顯示
            dt_display = record.get("dt", datetime.now()).strftime("%m-%d %H:%M:%S")
            time_item = QTableWidgetItem(dt_display)
            time_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, time_item)
            
            sn_item = QTableWidgetItem(sn)
            sn_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, sn_item)
            
            result = record.get("result", "")
            res_item = QTableWidgetItem(result)
            res_item.setTextAlignment(Qt.AlignCenter)
            
            if result == "PASS":
                res_item.setForeground(QColor(self.theme["pass"]))
                flash_c = QColor(self.theme["table_pass_flash"])
            elif result == "TERMINATED":
                res_item.setForeground(QColor(self.theme["term"]))
                flash_c = QColor(self.theme["table_term_flash"])
            else:
                res_item.setForeground(QColor(self.theme["fail"]))
                flash_c = QColor(self.theme["table_fail_flash"])

            self.table.setItem(row, 2, res_item)
            for col in range(3): self.table.item(row, col).setBackground(base_bg)
            
            if self._first_render_done and sn not in self._last_rendered_sns:
                anim = QVariantAnimation(self.table)
                anim.setDuration(1500)
                anim.setStartValue(flash_c)
                anim.setEndValue(base_bg)
                items = [self.table.item(row, 0), self.table.item(row, 1), self.table.item(row, 2)]
                def make_updater(it_list):
                    def updater(color):
                        for it in it_list:
                            try: it.setBackground(color)
                            except RuntimeError: pass
                    return updater
                anim.valueChanged.connect(make_updater(items))
                anim.start()
                self._row_anims.append(anim)

        self._last_rendered_sns = new_rendered_sns
        self._first_render_done = True
        self._row_anims = [a for a in self._row_anims if a.state() == QVariantAnimation.Running]

    def apply_target_qty(self):
        text = self.input_target_qty.text().strip()
        try:
            value = int(text)
            self.target_qty = value if value > 0 else 100
        except ValueError: self.target_qty = 100
        self.needs_refresh = True

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F11: self.toggle_fullscreen()
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.stop_watcher()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DashboardApp(get_documents_path())
    window.show()
    sys.exit(app.exec_())