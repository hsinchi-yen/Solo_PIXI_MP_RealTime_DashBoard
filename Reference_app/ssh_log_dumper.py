import sys
import os
import re
import stat
import time
import paramiko
from datetime import datetime

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLineEdit, QLabel,
                             QFileDialog, QTextEdit, QFrame, QProgressBar,
                             QMessageBox, QListWidget, QAbstractItemView,
                             QInputDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt5.QtGui import QFont, QPixmap

# ── 預設參數 ──
DEFAULT_HOST = '192.168.100.1'
DEFAULT_USER = 'root'
DEFAULT_REMOTE_ROOT = '/run/media/nvme0n1p1'
WO_PATTERN = re.compile(r'^\d{4}-\d{9}$')

# ── UI 樣式 (沿用 Fluent Design) ──
STYLESHEET_LIGHT = """
QWidget { font-family: "Segoe UI Variable", "Segoe UI", sans-serif; font-size: 11px; color: #1A1A1A; }
QMainWindow, QWidget#root { background-color: #F3F3F3; }
QFrame#panel { background-color: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 6px; }
QFrame#header { background-color: #202020; border-radius: 6px; }
QLabel#appTitle { color: #FFFFFF; font-size: 15px; font-weight: 600; }
QLabel#rowTag { color: #0078D4; font-size: 10px; font-weight: 700; min-width: 45px; max-width: 45px; }
QLineEdit { border: 1px solid #CECECE; border-radius: 4px; padding: 3px 7px; background: #FDFDFD; }
QLineEdit:focus { border-color: #0078D4; }
QPushButton { background-color: #F9F9F9; border: 1px solid #D1D1D1; border-radius: 4px; padding: 4px 12px; font-weight: 600; }
QPushButton:hover { background-color: #F0F0F0; border-color: #ADADAD; }
QPushButton#primary { background-color: #0078D4; color: #FFFFFF; border: none; }
QPushButton#primary:hover { background-color: #106EBE; }
QPushButton#danger { background-color: #FDFDFD; color: #C50F1F; border: 1px solid #D1D1D1; }
QPushButton#danger:hover { background-color: #FEE7E9; border-color: #C50F1F; }
QListWidget { border: 1px solid #CECECE; border-radius: 4px; background: #FFFFFF; padding: 2px; outline: 0; }
QListWidget::item:selected { background-color: #0078D4; color: #FFFFFF; border-radius: 2px; }
QProgressBar { border: 1px solid #CECECE; border-radius: 4px; text-align: center; background: #FDFDFD; }
QProgressBar::chunk { background-color: #0078D4; border-radius: 3px; }
QTextEdit { border: none; background: transparent; padding: 2px; color: #1A1A1A; }
"""

STYLESHEET_DARK = """
QWidget { font-family: "Segoe UI Variable", "Segoe UI", sans-serif; font-size: 11px; color: #E4E4E4; }
QMainWindow, QWidget#root { background-color: #1C1C1C; }
QFrame#panel { background-color: #252525; border: 1px solid #383838; border-radius: 6px; }
QFrame#header { background-color: #111111; border-radius: 6px; }
QLabel#appTitle { color: #FFFFFF; font-size: 15px; font-weight: 600; }
QLabel#rowTag { color: #3A9FE8; font-size: 10px; font-weight: 700; min-width: 45px; max-width: 45px; }
QLineEdit { border: 1px solid #484848; border-radius: 4px; padding: 3px 7px; background: #313131; color: #E4E4E4; }
QLineEdit:focus { border-color: #3A9FE8; }
QPushButton { background-color: #313131; border: 1px solid #484848; border-radius: 4px; padding: 4px 12px; font-weight: 600; color: #E4E4E4; }
QPushButton:hover { background-color: #3E3E3E; border-color: #666666; }
QPushButton#primary { background-color: #0078D4; color: #FFFFFF; border: none; }
QPushButton#primary:hover { background-color: #106EBE; }
QPushButton#danger { background-color: #313131; color: #F04747; border: 1px solid #484848; }
QPushButton#danger:hover { background-color: #4A2020; border-color: #F04747; }
QListWidget { border: 1px solid #484848; border-radius: 4px; background: #1E1E1E; padding: 2px; outline: 0; color: #E4E4E4; }
QListWidget::item:selected { background-color: #0078D4; color: #FFFFFF; border-radius: 2px; }
QProgressBar { border: 1px solid #484848; border-radius: 4px; text-align: center; background: #313131; color: #E4E4E4; }
QProgressBar::chunk { background-color: #3A9FE8; border-radius: 3px; }
QTextEdit { border: none; background: transparent; padding: 2px; color: #C8C8C8; }
"""

# ── SSH 輔助函式 ──
def get_ssh_client(host, user):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_dir = os.path.expanduser("~/.ssh")
    keys = [os.path.join(ssh_dir, k) for k in ["id_ed25519", "id_ecdsa", "id_rsa"] if os.path.exists(os.path.join(ssh_dir, k))]
    try:
        ssh.connect(hostname=host, username=user, password='', timeout=5, look_for_keys=False, allow_agent=False)
        return ssh
    except paramiko.AuthenticationException:
        if keys:
            ssh.connect(hostname=host, username=user, timeout=5, key_filename=keys, look_for_keys=True)
            return ssh
        raise

# ── Threads ──
class ScanThread(QThread):
    result = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, host, user, remote_root):
        super().__init__()
        self.host, self.user, self.remote_root = host, user, remote_root

    def run(self):
        ssh = sftp = None
        try:
            ssh = get_ssh_client(self.host, self.user)
            sftp = ssh.open_sftp()
            folders = []
            try:
                for attr in sftp.listdir_attr(self.remote_root):
                    if stat.S_ISDIR(attr.st_mode) and WO_PATTERN.match(attr.filename):
                        folders.append(attr.filename)
                self.result.emit(sorted(folders, reverse=True))
            except FileNotFoundError:
                self.error.emit(f"遠端目錄不存在: {self.remote_root}")
        except Exception as e:
            self.error.emit(f"掃描失敗: {str(e)}")
        finally:
            if sftp: sftp.close()
            if ssh: ssh.close()

class ManageThread(QThread):
    finished_ok = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, host, user, remote_root, action, target_name):
        super().__init__()
        self.host, self.user, self.remote_root = host, user, remote_root
        self.action = action  # 'mkdir' or 'rmdir'
        self.target_name = target_name

    def _sftp_rm_rf(self, sftp, remote_path):
        """遞迴透過 SFTP 刪除遠端目錄樹 (不呼叫 shell)"""
        for attr in sftp.listdir_attr(remote_path):
            item_path = remote_path + '/' + attr.filename
            if stat.S_ISDIR(attr.st_mode):
                self._sftp_rm_rf(sftp, item_path)
            else:
                sftp.remove(item_path)
        sftp.rmdir(remote_path)

    def run(self):
        if not WO_PATTERN.match(self.target_name):
            self.error.emit("安全攔截: 資料夾名稱不符 XXXX-XXXXXXXXX 格式")
            return

        ssh = sftp = None
        try:
            ssh = get_ssh_client(self.host, self.user)
            sftp = ssh.open_sftp()
            target_path = f"{self.remote_root.rstrip('/')}/{self.target_name}"

            if self.action == 'mkdir':
                sftp.mkdir(target_path)
                self.finished_ok.emit(f"成功建立目錄: {self.target_name}")
            elif self.action == 'rmdir':
                self._sftp_rm_rf(sftp, target_path)
                self.finished_ok.emit(f"成功刪除目錄: {self.target_name}")
        except Exception as e:
            self.error.emit(f"操作失敗: {str(e)}")
        finally:
            if sftp: sftp.close()
            if ssh: ssh.close()

class DownloadThread(QThread):
    log_msg = pyqtSignal(str)
    stats_update = pyqtSignal(int, int, int, int) # total, copied, skipped, failed
    progress_update = pyqtSignal(int)
    finished_ok = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, host, user, remote_root, wo_folder, local_dest):
        super().__init__()
        self.host, self.user = host, user
        self.remote_path = f"{remote_root.rstrip('/')}/{wo_folder}"
        self.local_dest = os.path.join(local_dest, wo_folder)
        self._stop = False
        self._last_cb_time = 0

    def stop(self):
        self._stop = True

    def sftp_walk(self, sftp, r_path):
        files = []
        for attr in sftp.listdir_attr(r_path):
            if self._stop: break
            p = r_path + '/' + attr.filename
            if stat.S_ISDIR(attr.st_mode):
                files.extend(self.sftp_walk(sftp, p))
            else:
                files.append((p, attr.st_size))
        return files

    def run(self):
        ssh = sftp = None
        total = copied = skipped = failed = 0
        try:
            self.log_msg.emit(f"連線中... {self.host}")
            ssh = get_ssh_client(self.host, self.user)
            sftp = ssh.open_sftp()
            
            self.log_msg.emit("掃描遠端檔案結構中...")
            remote_files = self.sftp_walk(sftp, self.remote_path)
            total = len(remote_files)
            self.log_msg.emit(f"找到 {total} 個檔案，準備同步...")
            self.stats_update.emit(total, copied, skipped, failed)

            os.makedirs(self.local_dest, exist_ok=True)

            for r_file, r_size in remote_files:
                if self._stop:
                    self.log_msg.emit("使用者中斷下載。")
                    break

                rel_path = r_file[len(self.remote_path):].lstrip('/')
                l_file = os.path.join(self.local_dest, rel_path.replace('/', os.sep))
                os.makedirs(os.path.dirname(l_file), exist_ok=True)

                # 檢查是否需要 Skip (檔案存在且大小相同)
                if os.path.exists(l_file) and os.path.getsize(l_file) == r_size:
                    skipped += 1
                    self.stats_update.emit(total, copied, skipped, failed)
                    continue

                self.log_msg.emit(f"下載: {rel_path}")
                try:
                    def cb(transferred, total_bytes):
                        now = time.time()
                        # 限制進度條更新頻率，避免卡頓
                        if now - self._last_cb_time > 0.1 or transferred == total_bytes:
                            self._last_cb_time = now
                            pct = int((transferred / total_bytes) * 100) if total_bytes else 0
                            self.progress_update.emit(pct)

                    sftp.get(r_file, l_file, callback=cb)
                    copied += 1
                except Exception as e:
                    failed += 1
                    self.log_msg.emit(f"❌ 失敗 {rel_path}: {e}")
                
                self.progress_update.emit(0)
                self.stats_update.emit(total, copied, skipped, failed)

            if not self._stop:
                self.log_msg.emit("✅ 同步完成！")
                self.finished_ok.emit()

        except Exception as e:
            self.error.emit(f"下載發生錯誤: {str(e)}")
        finally:
            if sftp: sftp.close()
            if ssh: ssh.close()

# ── Main UI ──
class SSHLogDumperApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self._dark_mode = False
        self._scan_worker = None
        self._manage_worker = None
        self._download_worker = None
        self.initUI()
        self.load_settings()

    def initUI(self):
        self.setWindowTitle('SSH Log Dumper')
        self.setMinimumSize(550, 650)
        self.setStyleSheet(STYLESHEET_LIGHT)
        
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        main_lay = QVBoxLayout(root)
        main_lay.setContentsMargins(8, 8, 8, 8)
        main_lay.setSpacing(6)

        # Header
        hdr = QFrame(); hdr.setObjectName("header"); hdr.setFixedHeight(34)
        h_lay = QHBoxLayout(hdr); h_lay.setContentsMargins(6, 0, 8, 0); h_lay.setSpacing(6)
        # Logo
        _logo_lbl = QLabel()
        _logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tn_log.png')
        _pix = QPixmap(_logo_path)
        if not _pix.isNull():
            _logo_lbl.setPixmap(_pix.scaledToHeight(24, Qt.SmoothTransformation))
        _logo_lbl.setFixedWidth(70)
        self.led = QLabel("●"); self.led.setStyleSheet("color: #9D9D9D; font-size: 15px;")
        title = QLabel("SSH Log Dumper"); title.setObjectName("appTitle")
        self.btn_theme = QPushButton("🌙")
        self.btn_theme.setFixedSize(26, 26)
        self.btn_theme.clicked.connect(self.toggle_theme)
        h_lay.addWidget(_logo_lbl); h_lay.addWidget(self.led); h_lay.addWidget(title); h_lay.addStretch(1); h_lay.addWidget(self.btn_theme)
        main_lay.addWidget(hdr)

        # Panel 1: Remote Config
        p1 = QFrame(); p1.setObjectName("panel")
        l1 = QVBoxLayout(p1)
        row1 = QHBoxLayout(); row1.setContentsMargins(0,0,0,0)
        row1.addWidget(QLabel("HOST", objectName="rowTag"))
        self.inp_host = QLineEdit(DEFAULT_HOST)
        row1.addWidget(self.inp_host, 1)
        row1.addWidget(QLabel("PATH", objectName="rowTag"))
        self.inp_remote = QLineEdit(DEFAULT_REMOTE_ROOT)
        row1.addWidget(self.inp_remote, 2)
        self.btn_scan = QPushButton("🔍 掃描遠端")
        self.btn_scan.clicked.connect(self.scan_remote)
        row1.addWidget(self.btn_scan)
        l1.addLayout(row1)

        # WO List & Manage
        row2 = QHBoxLayout(); row2.setContentsMargins(0,0,0,0)
        self.list_wo = QListWidget()
        self.list_wo.setSelectionMode(QAbstractItemView.SingleSelection)
        v_btns = QVBoxLayout()
        self.btn_add = QPushButton("+ 新增 WO")
        self.btn_add.clicked.connect(self.add_wo)
        self.btn_del = QPushButton("− 刪除 WO")
        self.btn_del.setObjectName("danger")
        self.btn_del.clicked.connect(self.del_wo)
        v_btns.addWidget(self.btn_add)
        v_btns.addWidget(self.btn_del)
        v_btns.addStretch(1)
        row2.addWidget(self.list_wo)
        row2.addLayout(v_btns)
        l1.addLayout(row2)
        main_lay.addWidget(p1, stretch=2)

        # Panel 2: Transfer Config
        p2 = QFrame(); p2.setObjectName("panel")
        l2 = QVBoxLayout(p2)
        row3 = QHBoxLayout(); row3.setContentsMargins(0,0,0,0)
        row3.addWidget(QLabel("LOCAL", objectName="rowTag"))
        self.inp_local = QLineEdit(os.path.join(os.path.expanduser('~'), 'Documents', 'Log_Downloads'))
        self.btn_browse = QPushButton("...")
        self.btn_browse.setFixedWidth(30)
        self.btn_browse.clicked.connect(self.browse_local)
        row3.addWidget(self.inp_local, 1)
        row3.addWidget(self.btn_browse)
        l2.addLayout(row3)
        main_lay.addWidget(p2)

        # Panel 3: Stats & Actions
        p3 = QFrame(); p3.setObjectName("panel")
        l3 = QVBoxLayout(p3)
        self.btn_download = QPushButton("⬇ 開始同步下載")
        self.btn_download.setObjectName("primary")
        self.btn_download.setFixedHeight(30)
        self.btn_download.clicked.connect(self.start_download)
        l3.addWidget(self.btn_download)

        self.lbl_stats = QLabel("準備就緒 | 總數: 0 | 複製: 0 | 略過: 0 | 失敗: 0")
        l3.addWidget(self.lbl_stats)

        self.prog_bar = QProgressBar()
        self.prog_bar.setValue(0)
        self.prog_bar.setTextVisible(False)
        self.prog_bar.setFixedHeight(8)
        l3.addWidget(self.prog_bar)
        main_lay.addWidget(p3)

        # Panel 4: Log
        p4 = QFrame(); p4.setObjectName("panel")
        l4 = QVBoxLayout(p4); l4.setContentsMargins(4,4,4,4)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Consolas", 9))
        l4.addWidget(self.log_box)
        main_lay.addWidget(p4, stretch=3)

    def toggle_theme(self):
        self._dark_mode = not self._dark_mode
        self.setStyleSheet(STYLESHEET_DARK if self._dark_mode else STYLESHEET_LIGHT)
        self.btn_theme.setText("☀" if self._dark_mode else "🌙")
        QSettings("SoloPIXI", "SSHDumper").setValue("dark_mode", self._dark_mode)

    def load_settings(self):
        s = QSettings("SoloPIXI", "SSHDumper")
        self.inp_host.setText(s.value("host", DEFAULT_HOST))
        self.inp_remote.setText(s.value("remote", DEFAULT_REMOTE_ROOT))
        self.inp_local.setText(s.value("local", self.inp_local.text()))
        if s.value("dark_mode", False, type=bool):
            self.toggle_theme()

    def save_settings(self):
        s = QSettings("SoloPIXI", "SSHDumper")
        s.setValue("host", self.inp_host.text())
        s.setValue("remote", self.inp_remote.text())
        s.setValue("local", self.inp_local.text())

    def log(self, msg):
        self.log_box.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def browse_local(self):
        p = QFileDialog.getExistingDirectory(self, "選擇本地儲存目錄")
        if p: self.inp_local.setText(os.path.normpath(p))

    # ── 行為邏輯 ──
    def set_ui_locked(self, locked):
        self.inp_host.setEnabled(not locked)
        self.inp_remote.setEnabled(not locked)
        self.btn_scan.setEnabled(not locked)
        self.btn_add.setEnabled(not locked)
        self.btn_del.setEnabled(not locked)
        self.btn_download.setText("⏹ 停止" if locked else "⬇ 開始同步下載")
        if not locked:
            self.btn_download.setEnabled(True)
            self.btn_download.clicked.disconnect()
            self.btn_download.clicked.connect(self.start_download)
            self.btn_download.setObjectName("primary")
        else:
            self.btn_download.clicked.disconnect()
            self.btn_download.clicked.connect(self.stop_download)
            self.btn_download.setObjectName("danger")
        self.btn_download.style().unpolish(self.btn_download); self.btn_download.style().polish(self.btn_download)

    def scan_remote(self):
        self.save_settings()
        self.list_wo.clear()
        self.log("開始掃描遠端目錄...")
        self.led.setStyleSheet("color: #FCB040; font-size: 15px;")
        self.set_ui_locked(True)
        self._scan_worker = ScanThread(self.inp_host.text(), DEFAULT_USER, self.inp_remote.text())
        self._scan_worker.result.connect(self._on_scan_ok)
        self._scan_worker.error.connect(self._on_worker_err)
        self._scan_worker.finished.connect(lambda: self.set_ui_locked(False))
        self._scan_worker.start()

    def _on_scan_ok(self, folders):
        self.led.setStyleSheet("color: #107C10; font-size: 15px;")
        self.list_wo.addItems(folders)
        self.log(f"掃描完成，找到 {len(folders)} 個 WO 資料夾")

    def add_wo(self):
        text, ok = QInputDialog.getText(self, "新增 WO 目錄", "請輸入 WO 格式 (例如: 5101-260129012):")
        if ok and text:
            if not WO_PATTERN.match(text):
                QMessageBox.warning(self, "格式錯誤", "名稱必須符合 XXXX-XXXXXXXXX 格式！")
                return
            self.log(f"正在建立目錄: {text}...")
            self._manage_worker = ManageThread(self.inp_host.text(), DEFAULT_USER, self.inp_remote.text(), 'mkdir', text)
            self._manage_worker.finished_ok.connect(self._on_manage_ok)
            self._manage_worker.error.connect(self._on_worker_err)
            self._manage_worker.start()

    def del_wo(self):
        item = self.list_wo.currentItem()
        if not item: return
        target = item.text()
        reply = QMessageBox.question(self, "刪除確認", f"確定要從遠端徹底刪除目錄\n{target}\n及裡面所有檔案嗎？(不可恢復)",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.log(f"正在刪除目錄: {target}...")
            self._manage_worker = ManageThread(self.inp_host.text(), DEFAULT_USER, self.inp_remote.text(), 'rmdir', target)
            self._manage_worker.finished_ok.connect(self._on_manage_ok)
            self._manage_worker.error.connect(self._on_worker_err)
            self._manage_worker.start()

    def _on_manage_ok(self, msg):
        self.log(f"✅ {msg}")
        self.scan_remote() # 刷新列表

    def start_download(self):
        item = self.list_wo.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "請先選擇一個 WO 資料夾")
            return
        self.save_settings()
        self.prog_bar.setValue(0)
        self.lbl_stats.setText("準備就緒 | 總數: 0 | 複製: 0 | 略過: 0 | 失敗: 0")
        self.set_ui_locked(True)
        self.log(f"=== 開始同步 WO: {item.text()} ===")
        
        self._download_worker = DownloadThread(self.inp_host.text(), DEFAULT_USER, self.inp_remote.text(), item.text(), self.inp_local.text())
        self._download_worker.log_msg.connect(self.log)
        self._download_worker.stats_update.connect(self._on_stats_update)
        self._download_worker.progress_update.connect(self.prog_bar.setValue)
        self._download_worker.error.connect(self._on_worker_err)
        self._download_worker.finished_ok.connect(self._on_download_finished)
        self._download_worker.finished.connect(lambda: self.set_ui_locked(False))
        self._download_worker.start()

    def stop_download(self):
        if self._download_worker:
            self._download_worker.stop()
            self.btn_download.setEnabled(False)
            self.btn_download.setText("正在停止...")

    def _on_stats_update(self, total, copied, skipped, failed):
        self.lbl_stats.setText(f"進度: {copied+skipped+failed}/{total} | 複製: {copied} | 略過: {skipped} | 失敗: {failed}")

    def _on_download_finished(self):
        self.prog_bar.setValue(100)
        self.log("=== 同步任務結束 ===")

    def _on_worker_err(self, err):
        self.led.setStyleSheet("color: #C50F1F; font-size: 15px;")
        self.log(f"❌ 錯誤: {err}")
        QMessageBox.critical(self, "錯誤", err)

    def closeEvent(self, event):
        if self._download_worker and self._download_worker.isRunning():
            self._download_worker.stop()
            self._download_worker.wait(2000)
        for w in (self._scan_worker, self._manage_worker):
            if w and w.isRunning():
                w.wait(2000)
        event.accept()

if __name__ == '__main__':
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    window = SSHLogDumperApp()
    window.show()
    sys.exit(app.exec_())