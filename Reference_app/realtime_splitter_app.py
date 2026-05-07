import sys
import os
import re
import queue
import shutil
import subprocess
import tempfile
import time
import json
from datetime import datetime
import paramiko
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLineEdit, QLabel,
                             QFileDialog, QTextEdit, QFrame, QSpinBox,
                             QMessageBox, QStyle, QSizePolicy, QComboBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QSettings, QTimer
from PyQt5.QtGui import QIcon, QFont


def get_base_dir():
    if getattr(sys, '_MEIPASS', None):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_path(*parts):
    return os.path.join(get_base_dir(), *parts)


APP_ICON_PATH = get_resource_path('build_assets', 'icons', 'solo_pixi_splitter.ico')
DEFAULT_POLL_INTERVAL = 60
DEFAULT_RSYNC_PATH = 'root@192.168.100.1:/run/media/nvme0n1p1/rawlogs/'
STATION_OPTIONS = ['10', '20', '30', '40', '50', '60', '70', '80']

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
    font-size: 15px;
    font-weight: 600;
}

/* ── Collapse / Expand toggle ── */
QPushButton#collapseBtn {
    background-color: #2C2C2C;
    color: #ABABAB;
    border: 1px solid #555555;
    border-radius: 4px;
    font-weight: 700;
    font-size: 14px;
    min-width: 26px;
    max-width: 26px;
    min-height: 26px;
    max-height: 26px;
}
QPushButton#collapseBtn:hover   { background-color: #3A3A3A; color: #FFFFFF; border-color: #888888; }
QPushButton#collapseBtn:pressed { background-color: #222222; }
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

/* ── Upload Stop button ── */
QPushButton#uploadStop {
    background-color: #383838;
    color: #FCB040;
    border: 1px solid #CA5010;
    border-radius: 4px;
    padding: 4px 12px;
    font-weight: 600;
    font-size: 11px;
}
QPushButton#uploadStop:hover   { background-color: #4A3020; border-color: #E06010; color: #FFCF70; }
QPushButton#uploadStop:pressed { background-color: #5A3820; }
QPushButton#uploadStop:disabled { background-color: #2C2C2C; color: #5E5E5E; border-color: #3C3C3C; }

/* ── SSH Test button ── */
QPushButton#sshTest {
    background-color: #F9F9F9;
    color: #1A1A1A;
    border: 1px solid #D1D1D1;
    border-radius: 4px;
    padding: 0px;
    min-width: 52px;
    max-width: 52px;
    min-height: 24px;
    max-height: 24px;
    font-size: 10px;
    font-weight: 600;
}
QPushButton#sshTest:hover   { background-color: #F0F0F0; border-color: #ADADAD; }
QPushButton#sshTest:pressed { background-color: #E8E8E8; }
QPushButton#sshTest:disabled { background: #F5F5F5; color: #C8C8C8; border-color: #E8E8E8; }

/* ── SSH Status LED ── */
QLabel#sshLedIdle {
    color: #9D9D9D;
    font-size: 12px;
    min-width: 14px;
    max-width: 14px;
}
QLabel#sshLedOk {
    color: #107C10;
    font-size: 12px;
    min-width: 14px;
    max-width: 14px;
}
QLabel#sshLedFail {
    color: #C50F1F;
    font-size: 12px;
    min-width: 14px;
    max-width: 14px;
}

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

/* ── Lock & Config Action Buttons ── */
QPushButton#lockBtn {
    background-color: transparent;
    color: #ABABAB;
    border: 1px solid transparent;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 6px;
}
QPushButton#lockBtn:hover { background-color: #3A3A3A; color: #FFFFFF; }

QPushButton#configBtn {
    background-color: #F9F9F9;
    color: #1A1A1A;
    border: 1px solid #D1D1D1;
    border-radius: 4px;
    padding: 2px 8px;
    font-weight: 600;
}
QPushButton#configBtn:hover { background-color: #F0F0F0; border-color: #ADADAD; }
QPushButton#configBtn:pressed { background-color: #E8E8E8; }

QLabel#miniStats {
    color: #6CCB5F;
    font-size: 11px;
    font-weight: 700;
    padding-left: 8px;
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


def build_output_filename(parsed, station_id=None):
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
    if station_id:
        return f"STA{station_id}_{date}_{time_str}_{mac1}_{mac2}_{result}.txt"
    return f"{date}_{time_str}_{mac1}_{mac2}_{result}.txt"


def build_wo_filename(parsed, wo):
    """Build WO-prefixed filename: {wo}_{date}_{time}_{mac1}_{mac2}_{result}.txt"""
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
    return f"{wo}_{date}_{time_str}_{mac1}_{mac2}_{result}.txt"


def get_wo_dest(dest_dir, wo):
    """Return the WO upload destination at the same level as the last segment of dest_dir.
    e.g. root@host:/a/b/rawlogs/ + WO → root@host:/a/b/{wo}/
    """
    if not dest_dir or not wo:
        return None
    if is_rsync_path(dest_dir):
        user, host, remote_path = parse_remote_path(dest_dir)
        if not user:
            return None
        parent = remote_path.rstrip('/').rsplit('/', 1)[0]
        return f"{user}@{host}:{parent}/{wo}/"
    else:
        parent = os.path.dirname(dest_dir.rstrip('/\\'))
        return os.path.join(parent, wo)


def resolve_out_dir(base_out_dir, station_id):
    """When station_id is set, files go into {base_out_dir}/STA{station_id}/."""
    if not station_id:
        return base_out_dir
    return os.path.join(base_out_dir, f"STA{station_id}")


def scan_existing_files(output_dir):
    if not os.path.isdir(output_dir):
        return set()
    return {f for f in os.listdir(output_dir)
            if os.path.isfile(os.path.join(output_dir, f))}


def parse_remote_path(path):
    """Parse remote SSH path: user@host:/path
    
    Returns:
        tuple: (user, host, remote_path) or (None, None, None) if not remote
    """
    if not path or '@' not in path or ':' not in path:
        return None, None, None
    
    try:
        user_host, remote_path = path.split(':', 1)
        user, host = user_host.split('@', 1)
        return user, host, remote_path
    except ValueError:
        return None, None, None


def is_rsync_path(path):
    """Check if path is remote SSH format: user@host:/path"""
    user, host, remote_path = parse_remote_path(path)
    return user is not None


# ─────────────────────────────────────────────────────────────
#  Worker threads
# ─────────────────────────────────────────────────────────────
class SSHTestThread(QThread):
    """Test SSH connection to remote destination with auto-diagnosis."""
    test_ok = pyqtSignal()
    test_fail = pyqtSignal(str)
    diagnosis = pyqtSignal(str)  # Detailed diagnosis info

    def __init__(self, remote_path, parent=None):
        super().__init__(parent)
        self.remote_path = remote_path

    def _check_ssh_keys(self):
        """Check if SSH keys exist, return list of available key files."""
        ssh_dir = os.path.expanduser("~/.ssh")
        
        # Create .ssh directory if it doesn't exist
        if not os.path.exists(ssh_dir):
            try:
                os.makedirs(ssh_dir, mode=0o700)
                self.diagnosis.emit(f"Created SSH directory: {ssh_dir}")
            except Exception as e:
                return False, f"Failed to create .ssh directory: {e}"
        
        # Look for common SSH key files (in order of preference)
        key_candidates = [
            "id_ed25519",    # Modern Ed25519 (preferred)
            "id_ecdsa",      # ECDSA
            "id_rsa",        # Traditional RSA
            "id_dsa",        # Older DSA
        ]
        
        found_keys = []
        for key_name in key_candidates:
            key_path = os.path.join(ssh_dir, key_name)
            if os.path.exists(key_path):
                found_keys.append(key_path)
                self.diagnosis.emit(f"Found SSH key: {key_name}")
        
        if found_keys:
            return True, found_keys
        
        # No keys found - generate RSA key as fallback
        self.diagnosis.emit("No SSH keys found. Generating new RSA key pair...")
        id_rsa = os.path.join(ssh_dir, "id_rsa")
        id_rsa_pub = os.path.join(ssh_dir, "id_rsa.pub")
        
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.backends import default_backend
            
            # Generate RSA key pair
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            
            # Save private key
            with open(id_rsa, 'wb') as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.OpenSSH,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            
            # Save public key
            public_key = private_key.public_key()
            with open(id_rsa_pub, 'wb') as f:
                f.write(public_key.public_bytes(
                    encoding=serialization.Encoding.OpenSSH,
                    format=serialization.PublicFormat.OpenSSH
                ))
            
            # Set permissions
            try:
                os.chmod(id_rsa, 0o600)
                os.chmod(id_rsa_pub, 0o644)
            except:
                pass
            
            self.diagnosis.emit(f"✓ Generated new SSH key pair")
            return True, [id_rsa]
            
        except ImportError:
            return False, "Please install cryptography: pip install cryptography"
        except Exception as e:
            return False, f"Failed to generate SSH keys: {e}"

    def _try_password_auth(self, ssh_client, host, user):
        """Try password-based authentication interactively."""
        # This would require GUI password input - for now, just return False
        return False

    def run(self):
        # Parse remote path: user@host:/path
        user, host, remote_dir = parse_remote_path(self.remote_path)
        
        if not user or not host:
            self.test_fail.emit("Invalid remote path format (expected user@host:/path)")
            return
        
        self.diagnosis.emit(f"Connecting to {user}@{host}...")
        
        # Step 1: Check/find all available SSH keys
        key_ok, key_paths = self._check_ssh_keys()
        if not key_ok:
            # Keys not found but continue - server may allow none/password auth
            self.diagnosis.emit(f"⚠ {key_paths}")
            key_paths = []
        else:
            for key in key_paths:
                self.diagnosis.emit(f"Found key: {os.path.basename(key)}")
        
        ssh_client = None
        try:
            ssh_client = paramiko.SSHClient()
            
            # Auto-accept unknown host keys (for first-time connection)
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Try multiple authentication methods:
            # 1. Empty password (none auth) - common for embedded systems
            # 2. Public keys if available
            try:
                # First try: empty password without keys (embedded system auth)
                self.diagnosis.emit("Trying password-less authentication...")
                ssh_client.connect(
                    hostname=host,
                    username=user,
                    password='',          # Empty password for none auth
                    timeout=10,
                    look_for_keys=False,  # Don't try keys first
                    allow_agent=False     # Don't use agent
                )
                self.diagnosis.emit("✓ Connected with none authentication")
                
            except paramiko.AuthenticationException:
                # Second try: with public keys
                if key_paths:
                    self.diagnosis.emit("Trying public key authentication...")
                    ssh_client.close()
                    ssh_client = paramiko.SSHClient()
                    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    ssh_client.connect(
                        hostname=host,
                        username=user,
                        timeout=10,
                        key_filename=key_paths,
                        look_for_keys=True,
                        allow_agent=True,
                        auth_timeout=10
                    )
                    self.diagnosis.emit("✓ Connected with public key")
                else:
                    raise
            
            self.diagnosis.emit("✓ SSH connection established")
            
            # Test if we can access SFTP
            sftp = ssh_client.open_sftp()
            self.diagnosis.emit("✓ SFTP access verified")
            
            # Try to access the target directory
            try:
                sftp.stat(remote_dir)
                self.diagnosis.emit(f"✓ Target directory accessible: {remote_dir}")
            except FileNotFoundError:
                self.diagnosis.emit(f"⚠ Directory not found (will create): {remote_dir}")
            except Exception as e:
                self.diagnosis.emit(f"⚠ Cannot access directory: {e}")
            
            sftp.close()
            self.test_ok.emit()
            
        except paramiko.AuthenticationException as e:
            error_msg = (
                f"❌ Authentication Failed\n\n"
                f"Tried: none auth, public key auth\n\n"
                f"Server may require:\n"
                f"  • SSH keys configured on server\n"
                f"  • Password authentication\n"
                f"  • Or contact system administrator"
            )
            self.test_fail.emit(error_msg)
            
        except paramiko.SSHException as e:
            self.test_fail.emit(f"SSH protocol error: {e}")
            
        except (TimeoutError, OSError) as e:
            error_msg = (
                f"❌ Connection Failed\n\n"
                f"Cannot reach {host}.\n"
                f"Please check:\n"
                f"  • Network connection (ping {host})\n"
                f"  • Server is running and accessible\n"
                f"  • Firewall allows SSH (port 22)\n\n"
                f"Error: {e}"
            )
            self.test_fail.emit(error_msg)
            
        except Exception as e:
            self.test_fail.emit(f"Unexpected error: {type(e).__name__}: {e}")
            
        finally:
            if ssh_client:
                try:
                    ssh_client.close()
                except:
                    pass


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
    file_uploaded = pyqtSignal(str)  # only emitted when no upload_queue (no DST)

    def __init__(self, source_path, output_dir, upload_queue, seen_files,
                 station_id=None, wo=None, wo_dest=None, parent=None):
        super().__init__(parent)
        self.source_path   = source_path
        self.output_dir    = output_dir
        self._upload_queue = upload_queue  # None → no DST; Queue → hand off to UploadThread
        self.seen_files    = seen_files
        self.station_id    = station_id
        self._wo           = wo       # Work Order number string
        self._wo_dest      = wo_dest  # Upload destination for WO files

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
        new_count = skipped_count = 0
        new_file_names = []
        if self.station_id:
            actual_out_dir = os.path.join(self.output_dir, f"STA{self.station_id}")
            os.makedirs(actual_out_dir, exist_ok=True)
        else:
            actual_out_dir = self.output_dir
        real_out_dir = os.path.realpath(actual_out_dir)

        for seg in segments:
            parsed = parse_segment(seg)
            filename = build_output_filename(parsed, self.station_id)
            if filename is None:
                skipped_count += 1
                continue
            if filename in self.seen_files:
                continue

            out_path = os.path.join(actual_out_dir, filename)
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
                if self._upload_queue is not None:
                    self._upload_queue.put((filename, out_path, None))  # None → UploadThread default dest
                else:
                    self.file_uploaded.emit(filename)
            except Exception as e:
                self.copy_fail.emit(f"Write {filename}: {e}")

            # WO file — separate copy with work-order prefix, independent of normal file
            if self._wo:
                wo_filename = build_wo_filename(parsed, self._wo)
                if wo_filename:
                    wo_dir = os.path.join(self.output_dir, self._wo)
                    try:
                        os.makedirs(wo_dir, exist_ok=True)
                        wo_path = os.path.join(wo_dir, wo_filename)
                        if not os.path.exists(wo_path):
                            with open(wo_path, 'w', encoding='utf-8') as fh:
                                fh.write(seg.rstrip() + "\n\n")
                            if self._upload_queue is not None and self._wo_dest:
                                self._upload_queue.put((wo_filename, wo_path, self._wo_dest))
                            elif self._upload_queue is None:
                                self.file_uploaded.emit(wo_filename)
                    except Exception as e:
                        self.copy_fail.emit(f"Write WO {wo_filename}: {e}")

        self.split_done.emit(dict(
            new_files=new_count, skipped=skipped_count,
            total_segs=len(segments), new_file_names=new_file_names,
        ))


# ─────────────────────────────────────────────────────────────
#  Dedicated upload thread (Method C — split and upload decoupled)
# ─────────────────────────────────────────────────────────────
class UploadThread(QThread):
    file_uploaded  = pyqtSignal(str)       # filename successfully uploaded
    upload_failed  = pyqtSignal(str, str)  # filename, error message
    eta_updated    = pyqtSignal(str)       # ETA string e.g. "~12s"
    queue_stats    = pyqtSignal(int, int)  # done_count, remaining

    def __init__(self, upload_queue, dest_dir, parent=None):
        super().__init__(parent)
        self._queue      = upload_queue
        self.dest_dir    = dest_dir
        self._stop_flag  = False
        self._done_count = 0
        self._avg_secs   = None  # exponential moving average seconds/file

    def stop(self):
        self._stop_flag = True

    def run(self):
        self._stop_flag = False
        while not self._stop_flag:
            try:
                filename, out_path, dest_override = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            dest = dest_override or self.dest_dir
            t0 = time.time()
            self._upload_file(filename, out_path, dest)
            elapsed = time.time() - t0

            self._avg_secs = (elapsed if self._avg_secs is None
                              else 0.7 * self._avg_secs + 0.3 * elapsed)
            self._done_count += 1
            remaining = self._queue.qsize()
            self.queue_stats.emit(self._done_count, remaining)
            eta_str = (f"~{self._fmt_eta(remaining * self._avg_secs)}"
                       if remaining > 0 else "—")
            self.eta_updated.emit(eta_str)
            self._queue.task_done()

    def _fmt_eta(self, secs):
        if secs < 60:
            return f"{int(secs)}s"
        m, s = divmod(int(secs), 60)
        return f"{m}m {s}s" if m < 60 else f"{m // 60}h {m % 60}m"

    def _upload_file(self, filename, out_path, dest):
        if is_rsync_path(dest):
            self._upload_sftp(filename, out_path, dest)
        else:
            self._upload_local(filename, out_path, dest)

    def _upload_sftp(self, filename, out_path, dest):
        user, host, remote_dir = parse_remote_path(dest)
        if not user or not host:
            self.upload_failed.emit(filename, f"Invalid remote path: {dest}")
            return
        ssh_dir = os.path.expanduser("~/.ssh")
        key_names = ["id_ed25519", "id_ecdsa", "id_rsa", "id_dsa"]
        key_paths = [os.path.join(ssh_dir, k) for k in key_names
                     if os.path.exists(os.path.join(ssh_dir, k))]
        ssh_client = None
        try:
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh_client.connect(hostname=host, username=user, password='',
                                   timeout=10, look_for_keys=False, allow_agent=False)
            except paramiko.AuthenticationException:
                if key_paths:
                    ssh_client.close()
                    ssh_client = paramiko.SSHClient()
                    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    ssh_client.connect(hostname=host, username=user, timeout=10,
                                       key_filename=key_paths, look_for_keys=True,
                                       allow_agent=True)
                else:
                    raise
            sftp = ssh_client.open_sftp()
            try:
                sftp.stat(remote_dir)
            except FileNotFoundError:
                try:
                    sftp.mkdir(remote_dir)
                except Exception:
                    pass
            remote_file = remote_dir.rstrip('/') + '/' + filename
            try:
                sftp.stat(remote_file)  # already exists → skip
            except FileNotFoundError:
                sftp.put(out_path, remote_file)
                self.file_uploaded.emit(filename)
            sftp.close()
        except paramiko.AuthenticationException:
            self.upload_failed.emit(filename, "SSH auth failed")
        except Exception as e:
            self.upload_failed.emit(filename, f"SFTP error: {e}")
        finally:
            if ssh_client:
                try:
                    ssh_client.close()
                except Exception:
                    pass

    def _upload_local(self, filename, out_path, dest):
        try:
            os.makedirs(dest, exist_ok=True)
            dest_file = os.path.join(dest, filename)
            if not os.path.exists(dest_file):
                shutil.copy2(out_path, dest_file)
                self.file_uploaded.emit(filename)
        except Exception as e:
            self.upload_failed.emit(filename, f"Copy error: {e}")


# ─────────────────────────────────────────────────────────────
#  Main window  (compact, 480×270 ~ 960×540)
# ─────────────────────────────────────────────────────────────
class RealtimeSplitterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self._watcher_thread = None
        self._split_thread   = None
        self._upload_thread  = None
        self._upload_queue   = None
        self._pending_split  = False
        self._seen_files     = set()
        self._session_written = 0
        self._session_synced  = 0
        self._is_locked       = True  # OP mode by default
        
        # SSH LED breathing animation
        self._ssh_led_timer = QTimer()
        self._ssh_led_timer.timeout.connect(self._animate_ssh_led)
        self._ssh_led_opacity = 1.0
        self._ssh_led_direction = -1  # -1 for fade out, 1 for fade in
        self._ssh_led_state = "idle"  # idle, ok, fail
        
        self._initUI()
        QTimer.singleShot(800, self._auto_ssh_test)  # auto-test after UI settles

    # ── UI construction ──────────────────────────────────────

    def _initUI(self):
        self.setWindowTitle('Log Splitter — Live')
        self.setMinimumSize(480, 297)
        self.setMaximumSize(960, 800)
        self.resize(720, 600)
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
        self._op_frame, self._eng_frame = self._mk_config_panels()
        self._status_frame      = self._mk_status_strip()
        self._log_frame         = self._mk_log()
        self._upload_log_frame  = self._mk_upload_log()
        lay.addWidget(self._op_frame)
        lay.addWidget(self._eng_frame)
        lay.addWidget(self._status_frame)
        lay.addWidget(self._log_frame, stretch=1)
        lay.addWidget(self._upload_log_frame)

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

        self._station_id_lbl = QLabel("")
        self._station_id_lbl.setStyleSheet(
            "color: #FCB040; font-size: 11px; font-weight: 600; padding-left: 8px;"
        )

        self.btn_start = QPushButton("▶  Start")
        self.btn_start.setObjectName("start")
        self.btn_start.setFixedHeight(26)
        self.btn_start.clicked.connect(self.start_watching)

        self.btn_stop = QPushButton("■  Stop")
        self.btn_stop.setObjectName("stop")
        self.btn_stop.setFixedHeight(26)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_watching)

        self.btn_upload_stop = QPushButton("⏹  Upload Stop")
        self.btn_upload_stop.setObjectName("uploadStop")
        self.btn_upload_stop.setFixedHeight(26)
        self.btn_upload_stop.setEnabled(False)
        self.btn_upload_stop.clicked.connect(self._stop_upload)

        self.btn_collapse = QPushButton("−")
        self.btn_collapse.setObjectName("collapseBtn")
        self.btn_collapse.setFixedSize(26, 26)
        self.btn_collapse.setToolTip("Hide config / log panels")
        self.btn_collapse.clicked.connect(self._collapse_ui)

        self.btn_expand = QPushButton("+")
        self.btn_expand.setObjectName("collapseBtn")
        self.btn_expand.setFixedSize(26, 26)
        self.btn_expand.setToolTip("Show config / log panels")
        self.btn_expand.setVisible(False)
        self.btn_expand.clicked.connect(self._expand_ui)

        # ── TN Logo badge (far left of header) ──
        self.tn_badge = QLabel()
        self.tn_badge.setAlignment(Qt.AlignCenter)
        self.tn_badge.setFixedSize(30, 26)
        _logo_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tn_log.png')
        if getattr(sys, 'frozen', False):
            _logo_file = os.path.join(os.path.dirname(sys.executable), 'tn_log.png')
        if os.path.exists(_logo_file):
            from PyQt5.QtGui import QPixmap
            _pm = QPixmap(_logo_file).scaled(30, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.tn_badge.setPixmap(_pm)
            self.tn_badge.setStyleSheet("background: transparent; border: none;")
        else:
            self.tn_badge.setText("TN")
            self.tn_badge.setStyleSheet(
                "background-color: #0078D4; color: #FFFFFF; font-weight: 800;"
                " border-radius: 4px; font-size: 12px; font-family: Arial;"
            )

        h.addWidget(self.tn_badge)
        h.addSpacing(4)
        h.addWidget(self._dot)
        h.addWidget(self._dot_state)
        h.addSpacing(4)
        h.addWidget(title)
        h.addWidget(self._station_id_lbl)
        h.addStretch(1)
        h.addWidget(self.btn_start)
        h.addWidget(self.btn_stop)
        h.addWidget(self.btn_upload_stop)
        h.addSpacing(6)
        h.addWidget(self.btn_collapse)
        h.addWidget(self.btn_expand)
        return frame

    def _mk_config_panels(self):
        def browse_btn(slot, icon_key=QStyle.SP_DirOpenIcon):
            b = QPushButton()
            b.setObjectName("browse")
            b.setIcon(self.style().standardIcon(icon_key))
            b.setIconSize(QSize(13, 13))
            b.setFixedSize(24, 24)
            b.clicked.connect(slot)
            return b

        def row(tag, edit_widget, btn=None):
            h = QHBoxLayout()
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(5)
            lbl = QLabel(tag)
            lbl.setObjectName("rowTag")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            h.addWidget(lbl)
            h.addWidget(edit_widget, stretch=1)
            if btn is not None:
                h.addWidget(btn)
            else:
                h.addSpacing(29)  # align with rows that have browse buttons
            return h

        # --- OP Panel ---
        op_frame = QFrame()
        op_frame.setObjectName("configPanel")
        grid_op = QHBoxLayout()
        grid_op.setContentsMargins(0, 0, 0, 0)
        op_frame.setLayout(grid_op)
        inner_op = QWidget()
        grid_op.addWidget(inner_op)
        lay_op = QVBoxLayout(inner_op)
        lay_op.setContentsMargins(8, 8, 8, 8)
        lay_op.setSpacing(8)

        # Work Order number
        self.wo_input = QLineEdit()
        self.wo_input.setPlaceholderText("Work Order …  e.g. 5101-260129012")
        self.wo_input.setFixedHeight(24)
        self.wo_input.setToolTip(
            "Work order — creates [WO]\\ subfolder with WO-prefixed files\n"
            "Format: {WO}_{date}_{time}_{MAC1}_{MAC2}_{result}.txt\n"
            "Also uploads to same level as rawlogs on remote"
        )
        self.wo_input.setClearButtonEnabled(True)
        lay_op.addLayout(row("WOU", self.wo_input))

        # STATION dropdown
        self.station_combo = QComboBox()
        self.station_combo.addItems(STATION_OPTIONS)
        self.station_combo.setFixedHeight(24)
        self.station_combo.setToolTip("Select test station ID")
        self.station_combo.currentIndexChanged.connect(self._update_station_display)
        
        h_sta = QHBoxLayout()
        h_sta.setContentsMargins(0, 0, 0, 0)
        h_sta.setSpacing(5)
        lbl_sta = QLabel("STA")
        lbl_sta.setObjectName("rowTag")
        lbl_sta.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h_sta.addWidget(lbl_sta)
        h_sta.addWidget(self.station_combo, stretch=1)
        lay_op.addLayout(h_sta)

        # --- Engineer Panel ---
        eng_frame = QFrame()
        eng_frame.setObjectName("configPanel")
        grid_eng = QHBoxLayout()
        grid_eng.setContentsMargins(0, 0, 0, 0)
        eng_frame.setLayout(grid_eng)
        inner_eng = QWidget()
        grid_eng.addWidget(inner_eng)
        lay_eng = QVBoxLayout(inner_eng)
        lay_eng.setContentsMargins(8, 8, 8, 8)
        lay_eng.setSpacing(8)
        eng_frame.setVisible(False) # Hidden by default (Locked OP mode)

        # SRC
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("Log_ALL.txt …")
        self.file_input.setReadOnly(True)
        self.file_input.setFixedHeight(24)
        self._btn_src = browse_btn(self.browse_source, QStyle.SP_DialogOpenButton)
        lay_eng.addLayout(row("SRC", self.file_input, self._btn_src))

        # OUT
        self.dir_output_input = QLineEdit()
        self.dir_output_input.setText(
            os.path.join(os.path.expanduser('~'), 'Documents', 'Log_Output'))
        self.dir_output_input.setFixedHeight(24)
        self._btn_out = browse_btn(self.browse_output)
        lay_eng.addLayout(row("OUT", self.dir_output_input, self._btn_out))

        # DST and Interval
        self.dir_dest_input = QLineEdit()
        self.dir_dest_input.setText(DEFAULT_RSYNC_PATH)
        self.dir_dest_input.setPlaceholderText("rsync destination …")
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
        
        self.btn_ssh_test = QPushButton("Test")
        self.btn_ssh_test.setObjectName("sshTest")
        self.btn_ssh_test.setFixedHeight(24)
        self.btn_ssh_test.setToolTip("Test SSH connection")
        self.btn_ssh_test.clicked.connect(self._test_ssh_connection)
        
        self._ssh_led = QLabel("●")
        self._ssh_led.setObjectName("sshLedIdle")
        self._ssh_led.setToolTip("SSH connection status")
        
        h2.addWidget(self.btn_ssh_test)
        h2.addWidget(self._ssh_led)
        h2.addSpacing(4)
        h2.addWidget(self.spin_interval)
        lay_eng.addLayout(h2)

        # Config Management Row
        h_cfg = QHBoxLayout()
        h_cfg.setContentsMargins(0, 4, 0, 0)
        h_cfg.setSpacing(8)
        h_cfg.addStretch(1)
        
        # DST hint label
        hint = QLabel("💡 Default: root@192.168.100.1:/run/media/nvme0n1p1/rawlogs/")
        hint.setObjectName("statusKey")
        hint.setStyleSheet("color: #5D5D5D; font-size: 9px; padding-left: 33px;")
        lay_eng.addWidget(hint)

        self.btn_export = QPushButton("匯出設定")
        self.btn_export.setObjectName("configBtn")
        self.btn_export.clicked.connect(self._export_config)
        
        self.btn_import = QPushButton("匯入設定")
        self.btn_import.setObjectName("configBtn")
        self.btn_import.clicked.connect(self._import_config)

        self.btn_save_station = QPushButton("儲存設定")
        self.btn_save_station.setObjectName("configBtn")
        self.btn_save_station.setToolTip("Save all settings (SRC/OUT/STA/DST/SSH)")
        self.btn_save_station.clicked.connect(self._save_all_settings)
        
        h_cfg.addWidget(self.btn_import)
        h_cfg.addWidget(self.btn_export)
        h_cfg.addWidget(self.btn_save_station)
        lay_eng.addLayout(h_cfg)

        self._config_widgets = [
            self.file_input, self._btn_src,
            self.dir_output_input, self._btn_out,
            self.wo_input,
            self.station_combo,
            self.btn_import, self.btn_export, self.btn_save_station,
            self.dir_dest_input, self._btn_dst,
            self.spin_interval,
            self.btn_ssh_test
        ]
        
        # Restore all saved settings
        self._restore_all_settings()
        self._update_station_display()
        return op_frame, eng_frame
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
        lay.setSpacing(2)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        act_title = QLabel("Activity Log")
        act_title.setStyleSheet("color: #5D5D5D; font-size: 10px; font-weight: 700;")
        btn_clear_act = QPushButton("Clear")
        btn_clear_act.setObjectName("sshTest")
        btn_clear_act.setFixedHeight(18)
        btn_clear_act.setStyleSheet(
            "font-size: 9px; min-width: 36px; max-width: 36px; min-height: 18px; max-height: 18px;"
        )
        btn_clear_act.clicked.connect(lambda: self.activity_log.clear())
        hdr.addWidget(act_title)
        hdr.addStretch(1)
        hdr.addWidget(btn_clear_act)
        lay.addLayout(hdr)

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

    def _mk_upload_log(self):
        frame = QFrame()
        frame.setObjectName("logPanel")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)

        self._upload_count = 0

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        dot = QLabel("●")
        dot.setStyleSheet("color: #107C10; font-size: 10px;")
        title = QLabel("Upload Feed")
        title.setStyleSheet("color: #107C10; font-size: 10px; font-weight: 700;")
        self._upload_count_lbl = QLabel("| Total: 0")
        self._upload_count_lbl.setStyleSheet("color: #5D5D5D; font-size: 10px;")
        self._upload_queue_lbl = QLabel("| Queue: 0")
        self._upload_queue_lbl.setStyleSheet("color: #5D5D5D; font-size: 10px;")
        self._upload_eta_lbl = QLabel("| ETA: —")
        self._upload_eta_lbl.setStyleSheet("color: #0078D4; font-size: 10px; font-weight: 600;")
        self._btn_clear_upload = QPushButton("Clear")
        self._btn_clear_upload.setObjectName("sshTest")
        self._btn_clear_upload.setFixedHeight(18)
        self._btn_clear_upload.setStyleSheet(
            "font-size: 9px; min-width: 36px; max-width: 36px; min-height: 18px; max-height: 18px;"
        )
        self._btn_clear_upload.clicked.connect(self._clear_upload_feed)
        hdr.addWidget(dot)
        hdr.addSpacing(3)
        hdr.addWidget(title)
        hdr.addSpacing(4)
        hdr.addWidget(self._upload_count_lbl)
        hdr.addSpacing(4)
        hdr.addWidget(self._upload_queue_lbl)
        hdr.addSpacing(4)
        hdr.addWidget(self._upload_eta_lbl)
        hdr.addStretch(1)
        hdr.addWidget(self._btn_clear_upload)
        lay.addLayout(hdr)

        self.upload_log = QTextEdit()
        self.upload_log.setReadOnly(True)
        self.upload_log.setPlaceholderText("Uploaded files will appear here…")
        self.upload_log.document().setMaximumBlockCount(500)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(9)
        self.upload_log.setFont(mono)
        self.upload_log.setFixedHeight(110)
        lay.addWidget(self.upload_log)
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

    # ── Station persistence ───────────────────────────────────

    def _save_all_settings(self):
        """Save all settings: SRC, OUT, STA, DST, and SSH connection state."""
        settings = QSettings("SoloPIXI", "LogSplitter")
        
        # Save paths
        settings.setValue("src_path", self.file_input.text())
        settings.setValue("out_path", self.dir_output_input.text())
        settings.setValue("dst_path", self.dir_dest_input.text())
        settings.setValue("station_id", self.station_combo.currentText())
        settings.setValue("wo", self.wo_input.text())
        
        # Save SSH LED state
        ssh_state = self._ssh_led.objectName()  # sshLedIdle, sshLedOk, sshLedFail
        settings.setValue("ssh_state", ssh_state)
        
        self._log(f"Settings saved: STA{self.station_combo.currentText()}, SRC, OUT, DST, SSH")
        
        # Visual feedback — QTimer keeps the UI thread unblocked
        orig = self.btn_save_station.text()
        self.btn_save_station.setText("✓")
        QTimer.singleShot(500, lambda: self.btn_save_station.setText(orig))

    def _restore_all_settings(self):
        """Restore all saved settings from previous session."""
        settings = QSettings("SoloPIXI", "LogSplitter")
        
        # Restore paths
        src_path = settings.value("src_path", "")
        if src_path:
            self.file_input.setText(src_path)
        
        out_path = settings.value("out_path", "")
        if out_path:
            self.dir_output_input.setText(out_path)
        
        dst_path = settings.value("dst_path", DEFAULT_RSYNC_PATH)
        if dst_path:
            self.dir_dest_input.setText(dst_path)

        wo = settings.value("wo", "")
        if wo:
            self.wo_input.setText(wo)
        
        # Restore station
        saved_station = settings.value("station_id", None)
        if saved_station and saved_station in STATION_OPTIONS:
            idx = STATION_OPTIONS.index(saved_station)
            self.station_combo.setCurrentIndex(idx)
        
        # Restore SSH LED state
        ssh_state = settings.value("ssh_state", "sshLedIdle")
        if ssh_state == "sshLedOk":
            self._set_ssh_led("ok")
        elif ssh_state == "sshLedFail":
            self._set_ssh_led("fail")
        else:
            self._set_ssh_led("idle")

    # ── Collapse / Expand ────────────────────────────────────

    def _collapse_ui(self):
        self._pre_collapse_height = self.height()
        for f in (self._op_frame, self._eng_frame, self._status_frame,
                  self._log_frame, self._upload_log_frame):
            f.hide()
        self.btn_collapse.setVisible(False)
        self.btn_expand.setVisible(True)
        self._lbl_mini_stats.setVisible(True)
        self._update_mini_stats()
        
        # Unlock min/max so the window can shrink, then lock after layout recalc
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        QTimer.singleShot(10, self._apply_collapse_height)

    def _apply_collapse_height(self):
        h = self.sizeHint().height()
        self.setMinimumHeight(h)
        self.setMaximumHeight(h)
        self.resize(self.width(), h)

    def _expand_ui(self):
        # Unlock constraints before showing widgets
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        self._op_frame.setVisible(True)
        if not getattr(self, '_is_locked', False):
            self._eng_frame.setVisible(True)
        self._status_frame.setVisible(True)
        self._log_frame.setVisible(True)
        self._upload_log_frame.setVisible(True)
        
        self.btn_expand.setVisible(False)
        self.btn_collapse.setVisible(True)
        self._lbl_mini_stats.setVisible(False)
        
        # Restore original min/max and pre-collapse height
        self.setMinimumHeight(297)
        self.setMaximumHeight(800)
        self.resize(self.width(), getattr(self, '_pre_collapse_height', 418))

    # ── Station ID header display ─────────────────────────────

    def _update_station_display(self):
        sid = self.station_combo.currentText()
        self._station_id_lbl.setText(f"STATION ID : {sid}")
        self.setWindowTitle(f"Log Splitter — Live  |  STATION ID : {sid}")

    def _toggle_lock(self):
        self._is_locked = not self._is_locked
        if self._is_locked:
            self.btn_lock.setText("🔒 OP")
            self._eng_frame.setVisible(False)
        else:
            self.btn_lock.setText("🔓 ENG")
            self._eng_frame.setVisible(True)

    def _export_config(self):
        p, _ = QFileDialog.getSaveFileName(self, "匯出設定檔", "config.json", "JSON Files (*.json)")
        if p:
            config_data = {
                "src_path": self.file_input.text(),
                "out_path": self.dir_output_input.text(),
                "dst_path": self.dir_dest_input.text(),
                "interval": self.spin_interval.value()
            }
            try:
                import json
                with open(p, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=4)
                self._log(f"設定檔已匯出至: {p}")
            except Exception as e:
                self._log(f"匯出設定檔失敗: {e}")

    def _import_config(self):
        p, _ = QFileDialog.getOpenFileName(self, "匯入設定檔", "", "JSON Files (*.json)")
        if p:
            try:
                import json
                with open(p, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                if "src_path" in config_data: self.file_input.setText(config_data["src_path"])
                if "out_path" in config_data: self.dir_output_input.setText(config_data["out_path"])
                if "dst_path" in config_data: self.dir_dest_input.setText(config_data["dst_path"])
                if "interval" in config_data: self.spin_interval.setValue(config_data["interval"])
                self._log(f"設定檔已匯入從: {p}")
            except Exception as e:
                self._log(f"匯入設定檔失敗: {e}")


    # ── Auto SSH test on startup ──────────────────────────────

    def _auto_ssh_test(self):
        remote_path = self.dir_dest_input.text().strip()
        if not remote_path or not is_rsync_path(remote_path):
            return
        self._log("Auto SSH test on startup…")
        self._set_ssh_led("testing")
        self.btn_ssh_test.setEnabled(False)
        t = SSHTestThread(remote_path)
        t.test_ok.connect(self._on_ssh_test_ok)
        t.test_fail.connect(self._on_ssh_test_fail)
        t.test_fail.connect(self._on_auto_ssh_fail_dialog)
        t.diagnosis.connect(self._on_ssh_diagnosis)
        t.finished.connect(lambda: self.btn_ssh_test.setEnabled(True))
        self._ssh_test_thread = t
        t.start()

    def _on_auto_ssh_fail_dialog(self, _):
        QMessageBox.warning(
            self,
            "SSH 連線失敗 — 請確認 DST 路徑",
            f"無法連線到：\n{self.dir_dest_input.text().strip()}\n\n"
            "請在 DST 欄位輸入正確的 SSH 路徑，\n"
            "格式：  user@host:/remote/path/",
            QMessageBox.Ok,
        )
        self.dir_dest_input.setFocus()
        self.dir_dest_input.selectAll()

    # ── SSH Connection Test ───────────────────────────────────

    def _test_ssh_connection(self):
        remote_path = self.dir_dest_input.text().strip()
        if not remote_path:
            self._log("ERR  No destination path specified")
            self._set_ssh_led("fail")
            return
        
        # Check if it's a remote path
        if not is_rsync_path(remote_path):
            self._log("INFO  Local path detected (no SSH test needed)")
            self._set_ssh_led("idle")
            return
        
        self.btn_ssh_test.setEnabled(False)
        self._set_ssh_led("testing")
        
        user, host, _ = parse_remote_path(remote_path)
        self._log(f"Testing SSH connection to {user}@{host}...")
        
        self._ssh_test_thread = SSHTestThread(remote_path)
        self._ssh_test_thread.test_ok.connect(self._on_ssh_test_ok)
        self._ssh_test_thread.test_fail.connect(self._on_ssh_test_fail)
        self._ssh_test_thread.diagnosis.connect(self._on_ssh_diagnosis)  # Connect diagnosis signal
        self._ssh_test_thread.finished.connect(lambda: self.btn_ssh_test.setEnabled(True))
        self._ssh_test_thread.start()

    def _on_ssh_diagnosis(self, msg):
        """Display SSH diagnostic messages."""
        self._log(f"      {msg}")

    def _on_ssh_test_ok(self):
        self._set_ssh_led("ok")
        self._log("SSH connection OK ✓")

    def _on_ssh_test_fail(self, error_msg):
        self._set_ssh_led("fail")
        # Log multiline error messages properly
        for line in error_msg.split('\n'):
            if line.strip():
                self._log(f"ERR   {line}")

    def _set_ssh_led(self, state):
        """Set SSH LED state: 'idle' | 'testing' | 'ok' | 'fail'"""
        self._ssh_led_state = state
        
        # Stop any existing animation
        self._ssh_led_timer.stop()
        self._ssh_led_opacity = 1.0
        
        # Set base color
        mapping = {
            "idle":    ("sshLedIdle", False),
            "testing": ("sshLedIdle", False),
            "ok":      ("sshLedOk", True),    # Green with breathing
            "fail":    ("sshLedFail", True),  # Red with breathing
        }
        obj_name, should_animate = mapping.get(state, ("sshLedIdle", False))
        self._ssh_led.setObjectName(obj_name)
        self._ssh_led.style().unpolish(self._ssh_led)
        self._ssh_led.style().polish(self._ssh_led)
        
        # Start breathing animation for ok/fail states
        if should_animate:
            self._ssh_led_direction = -1
            self._ssh_led_timer.start(50)  # 50ms interval for smooth animation

    def _animate_ssh_led(self):
        """Breathing animation for SSH LED."""
        self._ssh_led_opacity += self._ssh_led_direction * 0.05
        
        # Reverse direction at boundaries
        if self._ssh_led_opacity <= 0.3:
            self._ssh_led_opacity = 0.3
            self._ssh_led_direction = 1
        elif self._ssh_led_opacity >= 1.0:
            self._ssh_led_opacity = 1.0
            self._ssh_led_direction = -1
        
        # Apply opacity via stylesheet (color with alpha)
        if self._ssh_led_state == "ok":
            # Green breathing
            alpha = int(255 * self._ssh_led_opacity)
            self._ssh_led.setStyleSheet(
                f"color: rgba(16, 124, 16, {alpha}); font-size: 12px; min-width: 14px; max-width: 14px;"
            )
        elif self._ssh_led_state == "fail":
            # Red breathing
            alpha = int(255 * self._ssh_led_opacity)
            self._ssh_led.setStyleSheet(
                f"color: rgba(197, 15, 31, {alpha}); font-size: 12px; min-width: 14px; max-width: 14px;"
            )

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
        station_id = self.station_combo.currentText()
        effective_out = resolve_out_dir(out, station_id)
        os.makedirs(effective_out, exist_ok=True)
        self._seen_files = scan_existing_files(effective_out)
        self._session_written = 0
        self._session_synced = 0
        self._lbl_written.setText("0")
        self._lbl_synced.setText("0")
        self._pending_split = False

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        for w in self._config_widgets:
            w.setEnabled(False)

        # Start UploadThread if DST is configured
        dst = self.dir_dest_input.text().strip()
        if dst:
            self._upload_queue = queue.Queue()
            self._upload_thread = UploadThread(self._upload_queue, dst)
            self._upload_thread.file_uploaded.connect(self._on_file_uploaded)
            self._upload_thread.upload_failed.connect(self._on_upload_failed)
            self._upload_thread.eta_updated.connect(self._on_eta_updated)
            self._upload_thread.queue_stats.connect(self._on_queue_stats)
            self._upload_thread.start()
            self.btn_upload_stop.setEnabled(True)
        else:
            self._upload_queue = None
            self._upload_thread = None

        self._set_dot("watching")
        interval = self.spin_interval.value()
        self._watcher_thread = WatcherThread(
            self.file_input.text().strip(), interval)
        self._watcher_thread.file_changed.connect(self._on_file_changed)
        self._watcher_thread.tick.connect(self._on_tick)
        self._watcher_thread.start()

        src = self.file_input.text().strip()
        self._log(f"Watching  {src}  every {interval}s")
        self._log(f"OUT  {effective_out}" + (f"  →  DST  {dst}" if dst else ""))
        self._log(f"Seeded {len(self._seen_files)} existing file(s) — will skip")

        # Run an immediate first split to catch current content right away
        self._log("Initial scan starting…")
        self._launch_split()

    def stop_watching(self):
        if self._watcher_thread:
            self._watcher_thread.stop()
            self._watcher_thread.wait(3000)
            self._watcher_thread = None
        if self._upload_thread:
            self._upload_thread.stop()
            self._upload_thread.wait(3000)
            self._upload_thread = None
        self._upload_queue = None
        self._pending_split = False
        self._set_dot("idle")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_upload_stop.setEnabled(False)
        for w in self._config_widgets:
            w.setEnabled(True)
        self._on_eta_updated("—")
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

    def _update_mini_stats(self):
        if hasattr(self, '_lbl_mini_stats'):
            self._lbl_mini_stats.setText(f"| 分割: {self._session_written} | 上傳: {self._session_synced}")

    def _launch_split(self):
        self._set_dot("busy")
        self._pending_split = False
        station_id = self.station_combo.currentText()
        wo = self.wo_input.text().strip()
        wo_dest = get_wo_dest(self.dir_dest_input.text().strip(), wo) if wo else None
        self._split_thread = SplitCopyThread(
            self.file_input.text().strip(),
            self.dir_output_input.text().strip(),
            self._upload_queue,
            set(self._seen_files),
            station_id,
            wo,
            wo_dest,
        )
        self._split_thread.copy_ok.connect(self._on_copy_ok)
        self._split_thread.copy_fail.connect(self._on_copy_fail)
        self._split_thread.split_done.connect(self._on_split_done)
        self._split_thread.file_uploaded.connect(self._on_file_uploaded)  # no-DST path
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

    def _clear_upload_feed(self):
        self.upload_log.clear()
        self._upload_count = 0
        self._upload_count_lbl.setText("| Total: 0")

    def _on_file_uploaded(self, filename):
        self._upload_count += 1
        self._upload_count_lbl.setText(f"| Total: {self._upload_count}")
        ts = datetime.now().strftime("%H:%M:%S")
        self.upload_log.append(f"[{ts}]  {filename} , uploaded")
        if self._upload_thread:  # DST path — count as synced
            self._session_synced += 1
            self._lbl_synced.setText(str(self._session_synced))
            self._update_mini_stats()

    def _on_upload_failed(self, filename, error):
        self._log(f"ERR  Upload {filename}: {error}")

    def _on_eta_updated(self, eta_str):
        self._upload_eta_lbl.setText(f"| ETA: {eta_str}")

    def _on_queue_stats(self, _, remaining):
        self._upload_queue_lbl.setText(f"| Queue: {remaining}")

    def _stop_upload(self):
        if self._upload_thread:
            self._upload_thread.stop()
            self._upload_thread.wait(3000)
            self._upload_thread = None
        self.btn_upload_stop.setEnabled(False)
        self._on_eta_updated("—")
        self._on_queue_stats(0, 0)
        self._log("Upload stopped by user.")

    def _on_split_done(self, stats):
        for name in stats.get("new_file_names", []):
            self._seen_files.add(name)
            self._session_written += 1
            self._log(f"  ↑  {name}")
        self._lbl_written.setText(str(self._session_written))
        self._update_mini_stats()
        if self._watcher_thread and self._watcher_thread.isRunning():
            self._set_dot("watching")
        q_depth = self._upload_queue.qsize() if self._upload_queue else 0
        self._log(
            f"Done  +{stats['new_files']} new  "
            f"queued {q_depth}  "
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
        # Stop SSH LED animation
        if self._ssh_led_timer:
            self._ssh_led_timer.stop()
        
        split_thread  = self._split_thread   # save refs before stop_watching clears state
        upload_thread = self._upload_thread
        self.stop_watching()
        if split_thread and split_thread.isRunning():
            split_thread.wait(5000)
        if upload_thread and upload_thread.isRunning():
            upload_thread.wait(5000)
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
