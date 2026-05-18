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
                             QMessageBox, QStyle, QSizePolicy, QComboBox,
                             QGraphicsOpacityEffect, QDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QSettings, QTimer
from PyQt5.QtGui import QIcon, QFont


def get_base_dir():
    if getattr(sys, '_MEIPASS', None):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_path(*parts):
    return os.path.join(get_base_dir(), *parts)


APP_ICON_PATH = get_resource_path('build_assets', 'icons', 'solo_pixi_splitter.ico')
TN_LOGO_PATH  = get_resource_path('tn_log.png')
DEFAULT_POLL_INTERVAL = 60
DEFAULT_RSYNC_PATH = 'root@192.168.100.1:/run/media/nvme0n1p1/rawlogs/'
STATION_IDS = ['10', '20', '30', '40']
DEFAULT_SRCS = {
    '10': r'D:\IQxel\ATSuite_V7_0_1_IQmeasure_3.1.2.20170623_QCA9377_V1.0.0\Release_2_RF1B\log',
    '20': r'D:\IQxel\ATSuite_V7_0_1_IQmeasure_3.1.2.20170623_QCA9377_V1.0.0\Release_RF1B\log',
    '30': r'D:\IQxel\ATSuite_V7_0_1_IQmeasure_3.1.2.20170623_QCA9377_V1.0.0\Release_RF2A\log',
    '40': r'D:\IQxel\ATSuite_V7_0_1_IQmeasure_3.1.2.20170623_QCA9377_V1.0.0\Release_RF2B\log',
}
OUT_BASE_ROOTS = {
    '10': r'E:\TN131_LOG_BACKUP\10',
    '20': r'E:\TN131_LOG_BACKUP\20',
    '30': r'E:\TN131_LOG_BACKUP\30',
    '40': r'E:\TN131_LOG_BACKUP\40',
}

# Files moved from SRC to OUT during 結批 (non-split ancillary files)
CLOSE_BATCH_FILES = frozenset({
    'Log_All.txt', 'Log_all.csv', 'log_summary.txt',
    '2412_ANT_1_CCK-11.jpg', '2412_ANT_1_MCS7.jpg',
    '2412_ANT_1_OFDM-54.jpg', '2422_ANT_1_MCS7.jpg',
    '2442_ANT_1_CCK-11.jpg', '2442_ANT_1_MCS7.jpg',
    '2442_ANT_1_OFDM-54.jpg', '2467_ANT_1_CCK-11.jpg',
    '2467_ANT_1_MCS7.jpg', '2467_ANT_1_OFDM-54.jpg',
    '5180_ANT_1_MCS7.jpg', '5180_ANT_1_OFDM-54.jpg',
    '5190_ANT_1_MCS7.jpg', '5210_ANT_1_MCS9.jpg',
    '5500_ANT_1_MCS7.jpg', '5500_ANT_1_OFDM-54.jpg',
    '5510_ANT_1_MCS7.jpg', '5530_ANT_1_MCS9.jpg',
    '5755_ANT_1_MCS7.jpg', '5765_ANT_1_MCS7.jpg',
    '5765_ANT_1_OFDM-54.jpg', '5775_ANT_1_MCS9.jpg',
})

# ── UI size tokens ────────────────────────────────────────────
_H_INPUT   = 24   # standard input / combo height
_H_BTN     = 26   # header action button height
_H_MINI    = 18   # minor clear / inline button height
_BROWSE_SZ = 24   # square browse-icon button side

# ─────────────────────────────────────────────────────────────
#  Windows 11 Fluent Design stylesheet
#  Palette: #202020 titlebar · #0078D4 accent · #F3F3F3 bg
#           #107C10 success · #C50F1F error · #CA5010 warning
# ─────────────────────────────────────────────────────────────
STYLESHEET_LIGHT = """
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

/* ── Station ID label in header ── */
QLabel#stationIdLbl {
    color: #FCB040;
    font-size: 11px;
    font-weight: 600;
    padding-left: 8px;
}

/* ── OP panel source summary ── */
QLabel#srcSummary {
    color: #7D7D7D;
    font-size: 9px;
    font-family: "Consolas", monospace;
    padding: 0px 4px 2px 33px;
}

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

/* ── Upload Stop button (lives in Upload Feed header) ── */
QPushButton#uploadStop {
    background-color: #383838;
    color: #FCB040;
    border: 1px solid #CA5010;
    border-radius: 4px;
    padding: 2px 8px;
    font-weight: 600;
    font-size: 10px;
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

/* ── Log panel title / feed labels ── */
QLabel#logTitle      { color: #5D5D5D; font-size: 10px; font-weight: 700; }
QLabel#uploadFeedDot { color: #107C10; font-size: 10px; }
QLabel#uploadFeedKey { color: #107C10; font-size: 10px; font-weight: 700; }
QLabel#uploadFeedStat{ color: #5D5D5D; font-size: 10px; }
QLabel#uploadFeedEta { color: #0078D4; font-size: 10px; font-weight: 600; }

/* ── DST hint ── */
QLabel#dstHint { color: #5D5D5D; font-size: 9px; padding-left: 33px; }

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

/* ── Theme toggle button (on dark header) ── */
QPushButton#themeBtn {
    background-color: #2C2C2C;
    color: #ABABAB;
    border: 1px solid #555555;
    border-radius: 4px;
    font-size: 14px;
    min-width: 26px;
    max-width: 26px;
    min-height: 26px;
    max-height: 26px;
    padding: 0px;
}
QPushButton#themeBtn:hover   { background-color: #3A3A3A; color: #FFFFFF; border-color: #888888; }
QPushButton#themeBtn:pressed { background-color: #222222; }

/* ── 結批 button — orange warning ── */
QPushButton#closeBatch {
    background-color: #CA5010;
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 4px 10px;
    font-weight: 600;
    font-size: 11px;
}
QPushButton#closeBatch:hover   { background-color: #B44000; }
QPushButton#closeBatch:pressed { background-color: #9A3500; }
QPushButton#closeBatch:disabled { background-color: #E8C4A0; color: #FFFFFF; }

/* ── 新增工單 button — green ── */
QPushButton#newWo {
    background-color: #107C10;
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 4px 10px;
    font-weight: 600;
    font-size: 11px;
}
QPushButton#newWo:hover   { background-color: #0A6A0A; }
QPushButton#newWo:pressed { background-color: #085A08; }
QPushButton#newWo:disabled { background-color: #A8D4A8; color: #FFFFFF; }

/* ── ComboBox ── */
QComboBox {
    border: 1px solid #CECECE;
    border-radius: 4px;
    padding: 3px 7px;
    background: #FDFDFD;
    color: #1A1A1A;
}
QComboBox:hover    { border-color: #9E9E9E; }
QComboBox:focus    { border-color: #0078D4; }
QComboBox:disabled { background: #F5F5F5; color: #9D9D9D; border-color: #E8E8E8; }
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #CECECE;
    selection-background-color: #0078D4;
    color: #1A1A1A;
}

/* ── Default (reset) button ── */
QPushButton#defaultBtn {
    background-color: #F0F0F0;
    color: #444444;
    border: 1px solid #C0C0C0;
    border-radius: 4px;
    padding: 2px 10px;
    font-size: 10px;
}
QPushButton#defaultBtn:hover   { background-color: #E0E0E0; border-color: #9E9E9E; }
QPushButton#defaultBtn:pressed { background-color: #D0D0D0; }
QPushButton#defaultBtn:disabled { color: #AAAAAA; border-color: #DCDCDC; }

/* ── Header date label ── */
QLabel#headerDate {
    color: #8A8A8A;
    font-size: 10px;
    font-family: "Consolas", monospace;
    padding-right: 2px;
}
"""

# ─────────────────────────────────────────────────────────────
#  Dark theme — mirrors STYLESHEET_LIGHT with inverted palette
#  Palette: #1C1C1C root · #111111 header · #252525 cards
#           #313131 inputs · #3A9FE8 accent · #E4E4E4 text
# ─────────────────────────────────────────────────────────────
STYLESHEET_DARK = """
QWidget {
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
    font-size: 11px;
    color: #E4E4E4;
}
QMainWindow, QWidget#root { background-color: #1C1C1C; }

/* ── Header ── */
QFrame#header { background-color: #111111; border-radius: 6px; }
QLabel#appTitle { color: #FFFFFF; font-size: 15px; font-weight: 600; }

/* ── Collapse / Expand / Theme ── */
QPushButton#collapseBtn, QPushButton#themeBtn {
    background-color: #252525;
    color: #8A8A8A;
    border: 1px solid #444444;
    border-radius: 4px;
    font-weight: 700;
    font-size: 14px;
    min-width: 26px; max-width: 26px;
    min-height: 26px; max-height: 26px;
    padding: 0px;
}
QPushButton#collapseBtn:hover, QPushButton#themeBtn:hover   { background-color: #3A3A3A; color: #FFFFFF; border-color: #666666; }
QPushButton#collapseBtn:pressed, QPushButton#themeBtn:pressed { background-color: #1A1A1A; }

QLabel#dotIdle     { color: #5A5A5A; font-size: 15px; }
QLabel#dotWatching { color: #6CCB5F; font-size: 15px; }
QLabel#dotBusy     { color: #FCB040; font-size: 15px; }
QLabel#dotError    { color: #F04747; font-size: 15px; }
QLabel#dotState    { color: #7A7A7A; font-size: 10px; }

QLabel#stationIdLbl { color: #FCB040; font-size: 11px; font-weight: 600; padding-left: 8px; }
QLabel#srcSummary   { color: #6A6A6A; font-size: 9px; font-family: "Consolas", monospace; padding: 0px 4px 2px 33px; }

/* ── Config panel ── */
QFrame#configPanel { background-color: #252525; border: 1px solid #383838; border-radius: 6px; }
QLabel#rowTag { color: #3A9FE8; font-size: 10px; font-weight: 700; min-width: 28px; max-width: 28px; }

/* ── Inputs ── */
QLineEdit {
    border: 1px solid #484848; border-radius: 4px; padding: 3px 7px;
    background: #313131; selection-background-color: #0078D4; color: #E4E4E4;
}
QLineEdit:hover    { border-color: #666666; }
QLineEdit:focus    { border-color: #3A9FE8; }
QLineEdit:disabled { background: #272727; color: #525252; border-color: #383838; }

/* ── Browse buttons ── */
QPushButton#browse {
    background-color: #313131; color: #C0C0C0; border: 1px solid #484848;
    border-radius: 4px; padding: 0px;
    min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px;
}
QPushButton#browse:hover   { background-color: #3E3E3E; border-color: #666666; }
QPushButton#browse:pressed { background-color: #282828; }
QPushButton#browse:disabled { background: #272727; color: #484848; border-color: #383838; }

/* ── SpinBox ── */
QSpinBox {
    border: 1px solid #484848; border-radius: 4px; padding: 3px 4px;
    background: #313131; min-width: 54px; max-width: 62px; color: #E4E4E4;
}
QSpinBox:hover    { border-color: #666666; }
QSpinBox:focus    { border-color: #3A9FE8; }
QSpinBox:disabled { background: #272727; color: #525252; border-color: #383838; }

/* ── ComboBox ── */
QComboBox {
    border: 1px solid #484848; border-radius: 4px; padding: 3px 7px;
    background: #313131; color: #E4E4E4;
}
QComboBox:hover    { border-color: #666666; }
QComboBox:focus    { border-color: #3A9FE8; }
QComboBox:disabled { background: #272727; color: #525252; border-color: #383838; }
QComboBox QAbstractItemView {
    background-color: #313131; border: 1px solid #484848;
    selection-background-color: #0078D4; color: #E4E4E4;
}

/* ── Start ── */
QPushButton#start {
    background-color: #0078D4; color: #FFFFFF; border: none;
    border-radius: 4px; padding: 4px 12px; font-weight: 600; font-size: 11px;
}
QPushButton#start:hover   { background-color: #106EBE; }
QPushButton#start:pressed { background-color: #005A9E; }
QPushButton#start:disabled { background-color: #003D6B; color: #5A8AB0; }

/* ── Stop ── */
QPushButton#stop {
    background-color: #2E2E2E; color: #C8C8C8; border: 1px solid #484848;
    border-radius: 4px; padding: 4px 12px; font-weight: 600; font-size: 11px;
}
QPushButton#stop:hover   { background-color: #3A3A3A; border-color: #F04747; color: #FFFFFF; }
QPushButton#stop:pressed { background-color: #404040; }
QPushButton#stop:disabled { background-color: #222222; color: #484848; border-color: #333333; }

/* ── Upload Stop ── */
QPushButton#uploadStop {
    background-color: #2E2E2E; color: #FCB040; border: 1px solid #CA5010;
    border-radius: 4px; padding: 2px 8px; font-weight: 600; font-size: 10px;
}
QPushButton#uploadStop:hover   { background-color: #4A3020; border-color: #E06010; color: #FFCF70; }
QPushButton#uploadStop:pressed { background-color: #5A3820; }
QPushButton#uploadStop:disabled { background-color: #222222; color: #484848; border-color: #333333; }

/* ── SSH Test ── */
QPushButton#sshTest {
    background-color: #313131; color: #C0C0C0; border: 1px solid #484848;
    border-radius: 4px; padding: 0px;
    min-width: 52px; max-width: 52px; min-height: 24px; max-height: 24px;
    font-size: 10px; font-weight: 600;
}
QPushButton#sshTest:hover   { background-color: #3E3E3E; border-color: #666666; }
QPushButton#sshTest:pressed { background-color: #282828; }
QPushButton#sshTest:disabled { background: #272727; color: #484848; border-color: #383838; }

/* ── SSH LED ── */
QLabel#sshLedIdle { color: #5A5A5A; font-size: 12px; min-width: 14px; max-width: 14px; }
QLabel#sshLedOk   { color: #6CCB5F; font-size: 12px; min-width: 14px; max-width: 14px; }
QLabel#sshLedFail { color: #F04747; font-size: 12px; min-width: 14px; max-width: 14px; }

/* ── Status strip ── */
QFrame#statusStrip { background-color: #252525; border: 1px solid #383838; border-radius: 5px; }
QLabel#statusKey { color: #7A7A7A; font-size: 10px; }
QLabel#statusVal { color: #E4E4E4; font-size: 11px; font-weight: 600; }
QLabel#badgeOk   { color: #6CCB5F; font-weight: 700; font-size: 11px; }
QLabel#badgeFail { color: #F04747; font-weight: 700; font-size: 11px; }
QLabel#sep       { color: #484848; font-size: 11px; padding: 0 2px; }

/* ── Log panels ── */
QFrame#logPanel { background: #252525; border: 1px solid #383838; border-radius: 6px; }
QTextEdit {
    border: none; background: transparent; padding: 2px 4px;
    selection-background-color: #0078D4; color: #C8C8C8;
}

QLabel#logTitle      { color: #7A7A7A; font-size: 10px; font-weight: 700; }
QLabel#uploadFeedDot { color: #6CCB5F; font-size: 10px; }
QLabel#uploadFeedKey { color: #6CCB5F; font-size: 10px; font-weight: 700; }
QLabel#uploadFeedStat{ color: #7A7A7A; font-size: 10px; }
QLabel#uploadFeedEta { color: #3A9FE8; font-size: 10px; font-weight: 600; }
QLabel#dstHint       { color: #6A6A6A; font-size: 9px; padding-left: 33px; }

/* ── Lock & Config Buttons ── */
QPushButton#lockBtn {
    background-color: transparent; color: #8A8A8A;
    border: 1px solid transparent; border-radius: 4px;
    font-size: 11px; font-weight: 600; padding: 2px 6px;
}
QPushButton#lockBtn:hover { background-color: #3A3A3A; color: #FFFFFF; }

QPushButton#configBtn {
    background-color: #313131; color: #E4E4E4; border: 1px solid #484848;
    border-radius: 4px; padding: 2px 8px; font-weight: 600;
}
QPushButton#configBtn:hover   { background-color: #3E3E3E; border-color: #666666; }
QPushButton#configBtn:pressed { background-color: #282828; }

QPushButton#closeBatch {
    background-color: #A04010; color: #FFFFFF; border: none;
    border-radius: 4px; padding: 4px 10px; font-weight: 600; font-size: 11px;
}
QPushButton#closeBatch:hover   { background-color: #B84C14; }
QPushButton#closeBatch:pressed { background-color: #883208; }
QPushButton#closeBatch:disabled { background-color: #4A2810; color: #7A5A4A; }

QPushButton#newWo {
    background-color: #0A5C0A; color: #FFFFFF; border: none;
    border-radius: 4px; padding: 4px 10px; font-weight: 600; font-size: 11px;
}
QPushButton#newWo:hover   { background-color: #136C13; }
QPushButton#newWo:pressed { background-color: #074807; }
QPushButton#newWo:disabled { background-color: #1A3A1A; color: #4A6A4A; }

/* ── Default (reset) button ── */
QPushButton#defaultBtn {
    background-color: #2A2A2A;
    color: #A0A0A0;
    border: 1px solid #484848;
    border-radius: 4px;
    padding: 2px 10px;
    font-size: 10px;
}
QPushButton#defaultBtn:hover   { background-color: #383838; border-color: #666666; color: #E0E0E0; }
QPushButton#defaultBtn:pressed { background-color: #1E1E1E; }
QPushButton#defaultBtn:disabled { color: #484848; border-color: #333333; }

/* ── Header date label ── */
QLabel#headerDate {
    color: #585858;
    font-size: 10px;
    font-family: "Consolas", monospace;
    padding-right: 2px;
}

QLabel#miniStats { color: #6CCB5F; font-size: 11px; font-weight: 700; padding-left: 8px; }
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
        # Persistent SFTP session — keyed by (host, user, remote_dir)
        self._sftp_cache: dict = {}   # key → (ssh_client, sftp)

    def stop(self):
        self._stop_flag = True

    def run(self):
        self._stop_flag = False
        try:
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
        finally:
            self._close_all_sftp()

    def _close_all_sftp(self):
        for ssh_client, sftp in self._sftp_cache.values():
            try:
                sftp.close()
            except Exception:
                pass
            try:
                ssh_client.close()
            except Exception:
                pass
        self._sftp_cache.clear()

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

    def _get_sftp(self, host, user, remote_dir):
        """Return a cached (ssh_client, sftp) for this destination, reconnecting on failure."""
        cache_key = (host, user, remote_dir)
        if cache_key in self._sftp_cache:
            ssh_client, sftp = self._sftp_cache[cache_key]
            # Probe the session with a cheap stat; reconnect if the channel is dead
            try:
                sftp.stat('.')
                return ssh_client, sftp
            except Exception:
                try:
                    sftp.close()
                except Exception:
                    pass
                try:
                    ssh_client.close()
                except Exception:
                    pass
                del self._sftp_cache[cache_key]

        ssh_dir   = os.path.expanduser("~/.ssh")
        key_names = ["id_ed25519", "id_ecdsa", "id_rsa", "id_dsa"]
        key_paths = [os.path.join(ssh_dir, k) for k in key_names
                     if os.path.exists(os.path.join(ssh_dir, k))]

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
        # Ensure remote directory exists
        try:
            sftp.stat(remote_dir)
        except FileNotFoundError:
            try:
                sftp.mkdir(remote_dir)
            except Exception:
                pass

        self._sftp_cache[cache_key] = (ssh_client, sftp)
        return ssh_client, sftp

    def _upload_sftp(self, filename, out_path, dest):
        user, host, remote_dir = parse_remote_path(dest)
        if not user or not host:
            self.upload_failed.emit(filename, f"Invalid remote path: {dest}")
            return
        try:
            _, sftp = self._get_sftp(host, user, remote_dir)
            remote_file = remote_dir.rstrip('/') + '/' + filename
            sftp.put(out_path, remote_file)
            self.file_uploaded.emit(filename)
        except paramiko.AuthenticationException:
            self.upload_failed.emit(filename, "SSH auth failed")
            # Drop cached session so next attempt reconnects clean
            self._sftp_cache.pop((host, user, remote_dir), None)
        except Exception as e:
            self.upload_failed.emit(filename, f"SFTP error: {e}")
            # Drop session on any transport error — it may be stale
            self._sftp_cache.pop((host, user, remote_dir), None)

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
#  WOU Input Dialog — mandatory or optional input
# ─────────────────────────────────────────────────────────────
class WouInputDialog(QDialog):
    def __init__(self, parent=None, current_wou="", allow_cancel=False):
        super().__init__(parent)
        self.setWindowTitle("輸入工單號碼 (WOU)")
        flags = self.windowFlags() & ~Qt.WindowContextHelpButtonHint
        if not allow_cancel:
            flags &= ~Qt.WindowCloseButtonHint
        self.setWindowFlags(flags)
        self.setModal(True)
        self.setMinimumWidth(380)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(8)

        lay.addWidget(QLabel("請輸入工單號碼 (WOU)："))

        self._input = QLineEdit()
        self._input.setPlaceholderText("e.g. 5101-260129012")
        self._input.setText(current_wou)
        self._input.setFixedHeight(28)
        self._input.returnPressed.connect(self._try_accept)
        lay.addWidget(self._input)

        self._err_lbl = QLabel("")
        self._err_lbl.setStyleSheet("color: #C50F1F; font-size: 10px;")
        self._err_lbl.setVisible(False)
        lay.addWidget(self._err_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        if allow_cancel:
            btn_cancel = QPushButton("取消")
            btn_cancel.setObjectName("configBtn")
            btn_cancel.setFixedHeight(28)
            btn_cancel.clicked.connect(self.reject)
            btn_row.addWidget(btn_cancel)
            btn_row.addSpacing(6)
        self.btn_ok = QPushButton("確認")
        self.btn_ok.setObjectName("start")
        self.btn_ok.setFixedHeight(28)
        self.btn_ok.clicked.connect(self._try_accept)
        btn_row.addWidget(self.btn_ok)
        lay.addLayout(btn_row)

    def _try_accept(self):
        val = self._input.text().strip()
        if not val:
            self._err_lbl.setText("工單號碼不得為空")
            self._err_lbl.setVisible(True)
            return
        self.accept()

    def value(self):
        return self._input.text().strip()


# ─────────────────────────────────────────────────────────────
#  Main window
# ─────────────────────────────────────────────────────────────
class RealtimeSplitterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self._watcher_threads  = {}   # {sta_id: WatcherThread}
        self._split_threads    = {}   # {sta_id: SplitCopyThread}
        self._pending_splits   = {}   # {sta_id: bool}
        self._seen_files       = {}   # {sta_id: set}
        self._upload_thread    = None
        self._upload_queue     = None
        self._session_written  = 0
        self._session_synced   = 0
        self._is_locked        = False
        self._dark_mode        = False

        self._ssh_led_effect    = None
        self._ssh_led_timer     = QTimer()
        self._ssh_led_timer.timeout.connect(self._animate_ssh_led)
        self._ssh_led_opacity   = 1.0
        self._ssh_led_direction = -1
        self._ssh_led_state     = "idle"

        self._initUI()
        QTimer.singleShot(100, self._check_wou_on_startup)
        QTimer.singleShot(800, self._auto_ssh_test)

    # ── UI construction ──────────────────────────────────────

    def _initUI(self):
        self.setWindowTitle('Log Splitter — Live')
        self.setMinimumSize(672, 400)
        self.setMaximumSize(1280, 960)
        self.resize(936, 720)
        self.setStyleSheet(STYLESHEET_LIGHT)
        _icon = TN_LOGO_PATH if os.path.exists(TN_LOGO_PATH) else APP_ICON_PATH
        if os.path.exists(_icon):
            self.setWindowIcon(QIcon(_icon))

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
        lay.addWidget(self._log_frame, stretch=3)
        lay.addWidget(self._upload_log_frame, stretch=1)

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

        title = QLabel("Log Splitter")
        title.setObjectName("appTitle")

        self.btn_lock = QPushButton("🔒 簡易功能 (OP)")
        self.btn_lock.setObjectName("lockBtn")
        self.btn_lock.setToolTip("切換 簡易/進階功能")
        self.btn_lock.clicked.connect(self._toggle_lock)

        self._station_id_lbl = QLabel("")
        self._station_id_lbl.setObjectName("stationIdLbl")

        self._lbl_mini_stats = QLabel("")
        self._lbl_mini_stats.setObjectName("miniStats")
        self._lbl_mini_stats.setVisible(False)

        self.btn_close_batch = QPushButton("結批")
        self.btn_close_batch.setObjectName("closeBatch")
        self.btn_close_batch.setFixedHeight(_H_BTN)
        self.btn_close_batch.setToolTip("將各站 log 目錄內容搬移至對應 OUT 目錄")
        self.btn_close_batch.clicked.connect(self._on_close_batch)

        self.btn_new_wo = QPushButton("新增工單 [—]")
        self.btn_new_wo.setObjectName("newWo")
        self.btn_new_wo.setFixedHeight(_H_BTN)
        self.btn_new_wo.setToolTip("輸入新工單號碼，更新所有 OUT 路徑")
        self.btn_new_wo.clicked.connect(self._on_new_wo)

        self.btn_start = QPushButton("▶  Start")
        self.btn_start.setObjectName("start")
        self.btn_start.setFixedHeight(_H_BTN)
        self.btn_start.clicked.connect(self.start_watching)

        self.btn_stop = QPushButton("■  Stop")
        self.btn_stop.setObjectName("stop")
        self.btn_stop.setFixedHeight(_H_BTN)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_watching)

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

        self._btn_theme = QPushButton("🌙")
        self._btn_theme.setObjectName("themeBtn")
        self._btn_theme.setFixedSize(26, 26)
        self._btn_theme.setToolTip("切換 深色 / 淺色 主題")
        self._btn_theme.clicked.connect(self._toggle_theme)

        today_str = datetime.now().strftime('%Y%m%d')
        self._lbl_header_date = QLabel(today_str)
        self._lbl_header_date.setObjectName("headerDate")
        self._lbl_header_date.setToolTip("Today's date")

        # Build Layout Sequence
        h.addWidget(self._dot)
        h.addWidget(self._dot_state)
        h.addSpacing(4)
        h.addWidget(title)
        h.addSpacing(6)
        h.addWidget(self._lbl_header_date)
        h.addWidget(self._station_id_lbl)
        h.addWidget(self._lbl_mini_stats)
        h.addStretch(1)
        h.addWidget(self.btn_lock)
        h.addSpacing(6)
        h.addWidget(self.btn_close_batch)
        h.addWidget(self.btn_new_wo)
        h.addSpacing(6)
        h.addWidget(self.btn_start)
        h.addWidget(self.btn_stop)
        h.addSpacing(6)
        h.addWidget(self._btn_theme)
        h.addSpacing(4)
        h.addWidget(self.btn_collapse)
        h.addWidget(self.btn_expand)
        return frame

    def _mk_op_panel(self):
        def browse_btn(slot):
            b = QPushButton()
            b.setObjectName("browse")
            b.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))
            b.setIconSize(QSize(13, 13))
            b.setFixedSize(_BROWSE_SZ, _BROWSE_SZ)
            b.clicked.connect(slot)
            return b

        def row(tag, widget, btn=None):
            h = QHBoxLayout()
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(5)
            lbl = QLabel(tag)
            lbl.setObjectName("rowTag")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            h.addWidget(lbl)
            h.addWidget(widget, stretch=1)
            if btn is not None:
                h.addWidget(btn)
            else:
                h.addSpacing(29)
            return h

        op_frame = QFrame()
        op_frame.setObjectName("configPanel")
        outer = QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        op_frame.setLayout(outer)
        inner = QWidget()
        outer.addWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # WOU
        self.wo_input = QLineEdit()
        self.wo_input.setPlaceholderText("Work Order …  e.g. 5101-260129012")
        self.wo_input.setFixedHeight(_H_INPUT)
        self.wo_input.setToolTip("工單號碼 — 決定各站 OUT 目錄名稱")
        self.wo_input.setClearButtonEnabled(True)
        self.wo_input.textChanged.connect(self._on_wou_changed)
        lay.addLayout(row("WOU", self.wo_input))

        # ── Station detail block (hidden in OP mode) ────────────
        self._station_detail_widget = QWidget()
        detail_lay = QVBoxLayout(self._station_detail_widget)
        detail_lay.setContentsMargins(0, 0, 0, 0)
        detail_lay.setSpacing(6)

        # 4× SRC
        self.src_inputs = {}
        self._btn_srcs  = {}
        for sta_id in STATION_IDS:
            edit = QLineEdit()
            edit.setText(DEFAULT_SRCS[sta_id])
            edit.setFixedHeight(_H_INPUT)
            edit.setToolTip(f"STA{sta_id} 來源目錄（程式自動找 Log_All.txt）")
            btn = browse_btn(lambda _c=False, s=sta_id: self._browse_src(s))
            self.src_inputs[sta_id] = edit
            self._btn_srcs[sta_id]  = btn
            detail_lay.addLayout(row(f"S{sta_id}", edit, btn))

        # 4× OUT
        self.out_inputs = {}
        self._btn_outs  = {}
        for sta_id in STATION_IDS:
            edit = QLineEdit()
            edit.setPlaceholderText(f"E:\\TN131_LOG_BACKUP\\{sta_id}\\<WOU>")
            edit.setFixedHeight(_H_INPUT)
            edit.setToolTip(f"STA{sta_id} 輸出目錄")
            btn = browse_btn(lambda _c=False, s=sta_id: self._browse_out(s))
            self.out_inputs[sta_id] = edit
            self._btn_outs[sta_id]  = btn
            detail_lay.addLayout(row(f"O{sta_id}", edit, btn))

        lay.addWidget(self._station_detail_widget)

        # Context summary
        self._lbl_src_summary = QLabel("—")
        self._lbl_src_summary.setObjectName("srcSummary")
        lay.addWidget(self._lbl_src_summary)

        return op_frame

    def _mk_eng_panel(self):
        def browse_btn(slot, icon_key=QStyle.SP_DirOpenIcon):
            b = QPushButton()
            b.setObjectName("browse")
            b.setIcon(self.style().standardIcon(icon_key))
            b.setIconSize(QSize(13, 13))
            b.setFixedSize(_BROWSE_SZ, _BROWSE_SZ)
            b.clicked.connect(slot)
            return b

        eng_frame = QFrame()
        eng_frame.setObjectName("configPanel")
        outer = QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        eng_frame.setLayout(outer)
        inner = QWidget()
        outer.addWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        eng_frame.setVisible(False)

        # DST + interval
        self.dir_dest_input = QLineEdit()
        self.dir_dest_input.setText(DEFAULT_RSYNC_PATH)
        self.dir_dest_input.setPlaceholderText("rsync destination …")
        self.dir_dest_input.setFixedHeight(_H_INPUT)
        self._btn_dst = browse_btn(self.browse_dest)

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(10, 300)
        self.spin_interval.setValue(DEFAULT_POLL_INTERVAL)
        self.spin_interval.setSuffix(" s")
        self.spin_interval.setFixedHeight(_H_INPUT)
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
        self.btn_ssh_test.setFixedHeight(_H_INPUT)
        self.btn_ssh_test.setToolTip("Test SSH connection")
        self.btn_ssh_test.clicked.connect(self._test_ssh_connection)

        self._ssh_led = QLabel("●")
        self._ssh_led.setObjectName("sshLedIdle")
        self._ssh_led.setToolTip("SSH connection status")
        # QGraphicsOpacityEffect for breathing animation — avoids per-frame setStyleSheet
        self._ssh_led_effect = QGraphicsOpacityEffect()
        self._ssh_led_effect.setOpacity(1.0)
        self._ssh_led.setGraphicsEffect(self._ssh_led_effect)

        h2.addWidget(self.btn_ssh_test)
        h2.addWidget(self._ssh_led)
        h2.addSpacing(4)
        h2.addWidget(self.spin_interval)
        lay.addLayout(h2)

        # DST hint
        hint = QLabel("💡 Default: root@192.168.100.1:/run/media/nvme0n1p1/rawlogs/")
        hint.setObjectName("dstHint")
        lay.addWidget(hint)

        # Config management row
        h_cfg = QHBoxLayout()
        h_cfg.setContentsMargins(0, 4, 0, 0)
        h_cfg.setSpacing(8)
        h_cfg.addStretch(1)

        self.btn_reset_defaults = QPushButton("預設路徑")
        self.btn_reset_defaults.setObjectName("configBtn")
        self.btn_reset_defaults.setToolTip("將 S10–S40 恢復預設 SRC，O10–O40 恢復 OUT_BASE_ROOT\\WOU")
        self.btn_reset_defaults.clicked.connect(self._on_reset_defaults)

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

        h_cfg.addWidget(self.btn_reset_defaults)
        h_cfg.addWidget(self.btn_import)
        h_cfg.addWidget(self.btn_export)
        h_cfg.addWidget(self.btn_save_station)
        lay.addLayout(h_cfg)

        return eng_frame

    def _mk_config_panels(self):
        op_frame  = self._mk_op_panel()
        eng_frame = self._mk_eng_panel()

        self._config_widgets = (
            list(self.src_inputs.values()) + list(self._btn_srcs.values()) +
            list(self.out_inputs.values()) + list(self._btn_outs.values()) +
            [self.wo_input, self.btn_reset_defaults,
             self.btn_import, self.btn_export, self.btn_save_station,
             self.dir_dest_input, self._btn_dst,
             self.spin_interval, self.btn_ssh_test]
        )

        self._restore_all_settings()
        self._update_src_summary()

        eng_visible = not self._is_locked
        eng_frame.setVisible(eng_visible)
        self._station_detail_widget.setVisible(eng_visible)
        self.btn_lock.setText(
            "🔒 簡易功能 (OP)" if self._is_locked else "🔓 進階功能 (ENG)"
        )
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

        copy_lbl = QLabel("copy")
        copy_lbl.setObjectName("statusKey")

        h.addWidget(self._lbl_checked_key)
        h.addWidget(self._lbl_checked)
        h.addWidget(sep())
        h.addWidget(copy_lbl)
        h.addWidget(self._lbl_copy_result)
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
        act_title.setObjectName("logTitle")
        btn_clear_act = QPushButton("Clear")
        btn_clear_act.setObjectName("sshTest")
        btn_clear_act.setFixedHeight(_H_MINI)
        btn_clear_act.setStyleSheet(
            f"font-size: 9px; min-width: 36px; max-width: 36px;"
            f" min-height: {_H_MINI}px; max-height: {_H_MINI}px;"
        )
        btn_clear_act.clicked.connect(lambda: self.activity_log.clear())
        hdr.addWidget(act_title)
        hdr.addStretch(1)
        hdr.addWidget(btn_clear_act)
        lay.addLayout(hdr)

        self.activity_log = QTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setPlaceholderText("Activity log…")
        self.activity_log.document().setMaximumBlockCount(300)
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
        dot.setObjectName("uploadFeedDot")
        title = QLabel("Upload Feed")
        title.setObjectName("uploadFeedKey")

        self._upload_count_lbl = QLabel("| Total: 0")
        self._upload_count_lbl.setObjectName("uploadFeedStat")
        self._upload_queue_lbl = QLabel("| Queue: 0")
        self._upload_queue_lbl.setObjectName("uploadFeedStat")
        self._upload_eta_lbl = QLabel("| ETA: —")
        self._upload_eta_lbl.setObjectName("uploadFeedEta")

        # Upload Stop moved here from header — contextually belongs with the feed
        self.btn_upload_stop = QPushButton("⏹ Stop Upload")
        self.btn_upload_stop.setObjectName("uploadStop")
        self.btn_upload_stop.setFixedHeight(_H_MINI)
        self.btn_upload_stop.setEnabled(False)
        self.btn_upload_stop.clicked.connect(self._stop_upload)

        self._btn_clear_upload = QPushButton("Clear")
        self._btn_clear_upload.setObjectName("sshTest")
        self._btn_clear_upload.setFixedHeight(_H_MINI)
        self._btn_clear_upload.setStyleSheet(
            f"font-size: 9px; min-width: 36px; max-width: 36px;"
            f" min-height: {_H_MINI}px; max-height: {_H_MINI}px;"
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
        hdr.addWidget(self.btn_upload_stop)
        hdr.addSpacing(4)
        hdr.addWidget(self._btn_clear_upload)
        lay.addLayout(hdr)

        self.upload_log = QTextEdit()
        self.upload_log.setReadOnly(True)
        self.upload_log.setPlaceholderText("Uploaded files will appear here…")
        self.upload_log.document().setMaximumBlockCount(200)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(9)
        self.upload_log.setFont(mono)
        # No fixed height — stretch ratio in _initUI controls proportions
        lay.addWidget(self.upload_log)
        return frame

    # ── Browse ────────────────────────────────────────────────

    def _browse_src(self, sta_id):
        p = QFileDialog.getExistingDirectory(
            self, f"選擇 STA{sta_id} 來源目錄", self.src_inputs[sta_id].text())
        if p:
            self.src_inputs[sta_id].setText(os.path.normpath(p))
            self._log(f"STA{sta_id} SRC → {p}")
            self._update_src_summary()

    def _browse_out(self, sta_id):
        p = QFileDialog.getExistingDirectory(
            self, f"選擇 STA{sta_id} 輸出目錄", self.out_inputs[sta_id].text())
        if p:
            self.out_inputs[sta_id].setText(os.path.normpath(p))

    def browse_dest(self):
        p = QFileDialog.getExistingDirectory(self, "Select destination folder")
        if p:
            self.dir_dest_input.setText(os.path.normpath(p))
            self._update_src_summary()

    # ── WOU management ───────────────────────────────────────

    def _check_wou_on_startup(self):
        saved_wou = QSettings("SoloPIXI", "LogSplitter").value("wou", "")
        if saved_wou:
            reply = QMessageBox.question(
                self, "工單號碼確認",
                f"上次使用的工單號碼：{saved_wou}\n\n"
                "是否沿用此工單？\n（按「否」可輸入新工單號碼）",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.No:
                self._prompt_wou(allow_cancel=False, current="")
            # Yes → keep saved_wou already loaded by _restore_all_settings
            return
        self._prompt_wou(allow_cancel=False)

    def _prompt_wou(self, allow_cancel=True, current=""):
        dlg = WouInputDialog(self, current_wou=current, allow_cancel=allow_cancel)
        if dlg.exec_() == QDialog.Accepted:
            wou = dlg.value()
            self.wo_input.setText(wou)
            QSettings("SoloPIXI", "LogSplitter").setValue("wou", wou)
            self._update_btn_new_wo_label()
            return wou
        return None

    def _on_wou_changed(self, text):
        wou = text.strip()
        for sta_id in STATION_IDS:
            edit = self.out_inputs[sta_id]
            cur  = edit.text().strip()
            base = os.path.normpath(OUT_BASE_ROOTS[sta_id])
            # Auto-update only when blank or the path is directly under the base root
            if not cur or os.path.dirname(os.path.normpath(cur)) == base:
                edit.setText(os.path.join(OUT_BASE_ROOTS[sta_id], wou) if wou else "")
        self._update_btn_new_wo_label()

    def _on_reset_defaults(self):
        wou = self.wo_input.text().strip()
        for sta_id in STATION_IDS:
            self.src_inputs[sta_id].setText(DEFAULT_SRCS[sta_id])
            self.out_inputs[sta_id].setText(
                os.path.join(OUT_BASE_ROOTS[sta_id], wou) if wou else "")

    def _update_btn_new_wo_label(self):
        wou = self.wo_input.text().strip() if hasattr(self, 'wo_input') else ""
        if hasattr(self, 'btn_new_wo'):
            self.btn_new_wo.setText(f"新增工單 [{wou}]" if wou else "新增工單 [—]")
        if hasattr(self, '_station_id_lbl'):
            self._station_id_lbl.setText(f"WOU : {wou}" if wou else "")
        title = f"Log Splitter — Live  |  WOU : {wou}" if wou else "Log Splitter — Live"
        self.setWindowTitle(title)

    # ── Settings persistence ──────────────────────────────────

    def _save_all_settings(self):
        s = QSettings("SoloPIXI", "LogSplitter")
        s.setValue("wou",       self.wo_input.text())
        s.setValue("dst_path",  self.dir_dest_input.text())
        s.setValue("interval",  self.spin_interval.value())
        s.setValue("ssh_state", self._ssh_led.objectName())
        s.setValue("is_locked", self._is_locked)
        s.setValue("dark_mode", self._dark_mode)
        for sta_id in STATION_IDS:
            s.setValue(f"src_{sta_id}", self.src_inputs[sta_id].text())
            s.setValue(f"out_{sta_id}", self.out_inputs[sta_id].text())
        self._log("Settings saved.")
        orig = self.btn_save_station.text()
        self.btn_save_station.setText("✓")
        QTimer.singleShot(500, lambda: self.btn_save_station.setText(orig))

    def _restore_all_settings(self):
        s = QSettings("SoloPIXI", "LogSplitter")

        wou = s.value("wou", "")
        if wou:
            self.wo_input.blockSignals(True)
            self.wo_input.setText(wou)
            self.wo_input.blockSignals(False)

        dst = s.value("dst_path", DEFAULT_RSYNC_PATH)
        self.dir_dest_input.setText(dst or DEFAULT_RSYNC_PATH)

        interval = s.value("interval", DEFAULT_POLL_INTERVAL, type=int)
        self.spin_interval.setValue(interval)

        for sta_id in STATION_IDS:
            saved_src = s.value(f"src_{sta_id}", DEFAULT_SRCS[sta_id])
            self.src_inputs[sta_id].setText(saved_src or DEFAULT_SRCS[sta_id])
            saved_out = s.value(f"out_{sta_id}", "")
            if saved_out:
                self.out_inputs[sta_id].setText(saved_out)
            elif wou:
                self.out_inputs[sta_id].setText(
                    os.path.join(OUT_BASE_ROOTS[sta_id], wou))

        ssh_state = s.value("ssh_state", "sshLedIdle")
        if ssh_state == "sshLedOk":
            self._set_ssh_led("ok")
        elif ssh_state == "sshLedFail":
            self._set_ssh_led("fail")
        else:
            self._set_ssh_led("idle")

        self._is_locked = s.value("is_locked", False, type=bool)

        saved_dark = s.value("dark_mode", False, type=bool)
        if saved_dark != self._dark_mode:
            self._dark_mode = saved_dark
            self.setStyleSheet(STYLESHEET_DARK if self._dark_mode else STYLESHEET_LIGHT)
            if hasattr(self, '_btn_theme'):
                self._btn_theme.setText("☀" if self._dark_mode else "🌙")

        self._update_btn_new_wo_label()

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
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        self._op_frame.setVisible(True)
        eng_visible = not getattr(self, '_is_locked', False)
        self._eng_frame.setVisible(eng_visible)
        self._station_detail_widget.setVisible(eng_visible)
        self._status_frame.setVisible(True)
        self._log_frame.setVisible(True)
        self._upload_log_frame.setVisible(True)
        self.btn_expand.setVisible(False)
        self.btn_collapse.setVisible(True)
        self._lbl_mini_stats.setVisible(False)
        self.setMinimumHeight(400)
        self.setMaximumHeight(960)
        self.resize(self.width(), getattr(self, '_pre_collapse_height', 720))

    def _update_src_summary(self):
        if not hasattr(self, '_lbl_src_summary'):
            return
        dst = self.dir_dest_input.text().strip() if hasattr(self, 'dir_dest_input') else ""
        if ':' in dst:
            dst_part = dst.split(':')[-1].rstrip('/')
            dst_short = ('…' + dst_part[-18:]) if len(dst_part) > 18 else dst_part
        elif dst:
            dst_short = os.path.basename(dst.rstrip('/\\')) or dst
        else:
            dst_short = "—"
        self._lbl_src_summary.setText(f"4 stations  →  DST: {dst_short}")

    def _toggle_lock(self):
        self._is_locked = not self._is_locked
        eng_visible = not self._is_locked
        self.btn_lock.setText("🔒 簡易功能 (OP)" if self._is_locked else "🔓 進階功能 (ENG)")
        self._eng_frame.setVisible(eng_visible)
        self._station_detail_widget.setVisible(eng_visible)
        QSettings("SoloPIXI", "LogSplitter").setValue("is_locked", self._is_locked)

    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        self.setStyleSheet(STYLESHEET_DARK if self._dark_mode else STYLESHEET_LIGHT)
        self._btn_theme.setText("☀" if self._dark_mode else "🌙")
        QSettings("SoloPIXI", "LogSplitter").setValue("dark_mode", self._dark_mode)

    def _export_config(self):
        p, _ = QFileDialog.getSaveFileName(self, "匯出設定檔", "config.json", "JSON Files (*.json)")
        if p:
            data = {
                "wou":      self.wo_input.text(),
                "dst_path": self.dir_dest_input.text(),
                "interval": self.spin_interval.value(),
            }
            for sta_id in STATION_IDS:
                data[f"src_{sta_id}"] = self.src_inputs[sta_id].text()
                data[f"out_{sta_id}"] = self.out_inputs[sta_id].text()
            try:
                with open(p, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                self._log(f"設定檔已匯出至: {p}")
            except Exception as e:
                self._log(f"匯出設定檔失敗: {e}")

    def _import_config(self):
        p, _ = QFileDialog.getOpenFileName(self, "匯入設定檔", "", "JSON Files (*.json)")
        if p:
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if "wou"      in data: self.wo_input.setText(data["wou"])
                if "dst_path" in data: self.dir_dest_input.setText(data["dst_path"])
                if "interval" in data: self.spin_interval.setValue(data["interval"])
                for sta_id in STATION_IDS:
                    if f"src_{sta_id}" in data:
                        self.src_inputs[sta_id].setText(data[f"src_{sta_id}"])
                    if f"out_{sta_id}" in data:
                        self.out_inputs[sta_id].setText(data[f"out_{sta_id}"])
                self._log(f"設定檔已匯入從: {p}")
                self._update_src_summary()
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
        
        if self._ssh_led_effect:
            self._ssh_led_effect.setOpacity(1.0)

        if should_animate:
            self._ssh_led_direction = -1
            self._ssh_led_timer.start(50)

    def _animate_ssh_led(self):
        self._ssh_led_opacity += self._ssh_led_direction * 0.05
        if self._ssh_led_opacity <= 0.3:
            self._ssh_led_opacity = 0.3
            self._ssh_led_direction = 1
        elif self._ssh_led_opacity >= 1.0:
            self._ssh_led_opacity = 1.0
            self._ssh_led_direction = -1
        if self._ssh_led_effect:
            self._ssh_led_effect.setOpacity(self._ssh_led_opacity)

    # ── Watcher control ───────────────────────────────────────

    def _validate(self):
        if not self.wo_input.text().strip():
            QMessageBox.critical(self, "Error", "請先設定工單號碼 (WOU)。", QMessageBox.Ok)
            return False
        for sta_id in STATION_IDS:
            src_dir = self.src_inputs[sta_id].text().strip()
            if not src_dir:
                QMessageBox.critical(self, "Error",
                    f"STA{sta_id} 來源目錄未設定。", QMessageBox.Ok)
                return False
            if not os.path.isdir(src_dir):
                QMessageBox.critical(self, "Error",
                    f"STA{sta_id} 來源目錄不存在：\n{src_dir}", QMessageBox.Ok)
                return False
            if not self.out_inputs[sta_id].text().strip():
                QMessageBox.critical(self, "Error",
                    f"STA{sta_id} 輸出目錄未設定。", QMessageBox.Ok)
                return False
        return True

    def _ensure_log_file(self, src_dir):
        path = os.path.join(src_dir, "Log_All.txt")
        if not os.path.exists(path):
            try:
                open(path, 'a', encoding='utf-8').close()
                self._log(f"Created empty {path}")
            except Exception as e:
                self._log(f"WARN  Cannot create {path}: {e}")
        return path

    def start_watching(self):
        if not self._validate():
            return

        dst = self.dir_dest_input.text().strip()
        self._session_written = 0
        self._session_synced  = 0
        self._lbl_written.setText("0")
        self._lbl_synced.setText("0")

        if dst:
            self._upload_queue  = queue.Queue()
            self._upload_thread = UploadThread(self._upload_queue, dst)
            self._upload_thread.file_uploaded.connect(self._on_file_uploaded)
            self._upload_thread.upload_failed.connect(self._on_upload_failed)
            self._upload_thread.eta_updated.connect(self._on_eta_updated)
            self._upload_thread.queue_stats.connect(self._on_queue_stats)
            self._upload_thread.start()
            self.btn_upload_stop.setEnabled(True)
        else:
            self._upload_queue  = None
            self._upload_thread = None

        interval = self.spin_interval.value()
        for sta_id in STATION_IDS:
            src_dir  = self.src_inputs[sta_id].text().strip()
            out_dir  = self.out_inputs[sta_id].text().strip()
            src_file = self._ensure_log_file(src_dir)
            os.makedirs(out_dir, exist_ok=True)
            sta_sub = os.path.join(out_dir, f"STA{sta_id}")
            self._seen_files[sta_id]     = scan_existing_files(sta_sub)
            self._pending_splits[sta_id] = False
            watcher = WatcherThread(src_file, interval)
            watcher.file_changed.connect(
                lambda _c=False, s=sta_id: self._on_file_changed(s))
            watcher.tick.connect(self._on_tick)
            watcher.start()
            self._watcher_threads[sta_id] = watcher
            self._log(f"STA{sta_id}: Watching {src_file}  →  {out_dir}")

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        for w in self._config_widgets:
            w.setEnabled(False)

        self._set_dot("watching")
        self._log(f"All 4 stations watching every {interval}s")
        for sta_id in STATION_IDS:
            self._launch_split(sta_id)

    def stop_watching(self, force: bool = False):
        if not force:
            q_depth = self._upload_queue.qsize() if self._upload_queue else 0
            if q_depth > 0:
                reply = QMessageBox.question(
                    self, "停止確認",
                    f"上傳佇列還有 {q_depth} 個檔案等待處理，確定停止？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.No:
                    return

        for sta_id in list(self._watcher_threads.keys()):
            t = self._watcher_threads.pop(sta_id, None)
            if t:
                t.stop()
                t.wait(3000)

        if self._upload_thread:
            self._upload_thread.stop()
            self._upload_thread.wait(3000)
            self._upload_thread = None
        self._upload_queue = None
        self._set_dot("idle")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_upload_stop.setEnabled(False)
        for w in self._config_widgets:
            w.setEnabled(True)
        self._on_eta_updated("—")
        self._log("All watchers stopped.")

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

    def _launch_split(self, sta_id):
        self._set_dot("busy")
        self._pending_splits[sta_id] = False
        src_file = os.path.join(self.src_inputs[sta_id].text().strip(), "Log_All.txt")
        out_dir  = self.out_inputs[sta_id].text().strip()
        wou      = self.wo_input.text().strip()
        dst      = self.dir_dest_input.text().strip()
        wo_dest  = get_wo_dest(dst, wou) if wou and dst else None
        t = SplitCopyThread(
            src_file, out_dir,
            self._upload_queue,
            set(self._seen_files.get(sta_id, set())),
            sta_id,
            wo=wou or None,
            wo_dest=wo_dest,
        )
        t.copy_ok.connect(self._on_copy_ok)
        t.copy_fail.connect(self._on_copy_fail)
        t.split_done.connect(lambda stats, s=sta_id: self._on_split_done(s, stats))
        t.file_uploaded.connect(self._on_file_uploaded)
        t.finished.connect(lambda s=sta_id: self._on_split_thread_finished(s))
        t.start()
        self._split_threads[sta_id] = t

    # ── Slots — WatcherThread ─────────────────────────────────

    def _on_tick(self):
        self._lbl_checked.setText(datetime.now().strftime("%H:%M:%S"))

    def _on_file_changed(self, sta_id):
        self._lbl_checked.setText(datetime.now().strftime("%H:%M:%S"))
        running = self._split_threads.get(sta_id)
        if running and running.isRunning():
            self._pending_splits[sta_id] = True
            self._log(f"STA{sta_id} change detected — queued")
            return
        self._log(f"STA{sta_id} change detected → splitting")
        self._launch_split(sta_id)

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
        if self._upload_thread:
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

    def _on_split_done(self, sta_id, stats):
        seen = self._seen_files.setdefault(sta_id, set())
        for name in stats.get("new_file_names", []):
            seen.add(name)
            self._session_written += 1
            self._log(f"  STA{sta_id} ↑  {name}")
        if len(seen) > 5000:
            self._seen_files[sta_id] = set(list(seen)[-3000:])
        self._lbl_written.setText(str(self._session_written))
        self._update_mini_stats()
        if any(t and t.isRunning() for t in self._watcher_threads.values()):
            self._set_dot("watching")
        q_depth = self._upload_queue.qsize() if self._upload_queue else 0
        self._log(
            f"STA{sta_id} Done  +{stats['new_files']} new  "
            f"queued {q_depth}  skip {stats['skipped']}"
        )

    def _on_split_thread_finished(self, sta_id):
        self._split_threads.pop(sta_id, None)
        if self._pending_splits.get(sta_id):
            self._log(f"STA{sta_id} running queued split…")
            self._launch_split(sta_id)

    # ── 結批 ─────────────────────────────────────────────────

    def _on_close_batch(self):
        wou = self.wo_input.text().strip()
        if not wou:
            QMessageBox.warning(self, "結批", "請先設定工單號碼 (WOU)。", QMessageBox.Ok)
            return

        if self._watcher_threads:
            reply = QMessageBox.question(
                self, "結批 — 停止監控",
                "執行結批前需停止監控。\n是否停止監控並繼續結批？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.No:
                return
            self.stop_watching(force=True)

        errors = []
        moved_sta = []
        for sta_id in STATION_IDS:
            src_dir = self.src_inputs[sta_id].text().strip()
            out_dir = self.out_inputs[sta_id].text().strip()

            if not os.path.isdir(src_dir):
                errors.append(f"STA{sta_id}: 來源目錄不存在 → {src_dir}")
                continue
            if not os.path.isdir(out_dir):
                errors.append(
                    f"STA{sta_id}: OUT 目錄不存在 → {out_dir}\n"
                    f"         （請先手動建立目錄）")
                continue

            # Only move files listed in CLOSE_BATCH_FILES
            count = 0
            for filename in CLOSE_BATCH_FILES:
                src_path = os.path.join(src_dir, filename)
                if not os.path.isfile(src_path):
                    continue  # file absent in this station — skip silently
                dst_path = os.path.join(out_dir, filename)
                try:
                    if os.path.exists(dst_path):
                        base, ext = os.path.splitext(filename)
                        dst_path = os.path.join(out_dir, f"{base}_dup{ext}")
                    shutil.move(src_path, dst_path)
                    count += 1
                except Exception as e:
                    errors.append(f"STA{sta_id}: 搬移 {filename} 失敗 — {e}")

            if count:
                self._log(f"STA{sta_id} 結批: 搬移 {count} 個檔案 → {out_dir}")
                moved_sta.append(f"STA{sta_id}({count})")
            else:
                self._log(f"STA{sta_id} 結批: 無符合檔案，跳過")

        if errors:
            QMessageBox.warning(
                self, "結批 — 部分錯誤",
                "以下站發生錯誤：\n\n" + "\n".join(errors),
                QMessageBox.Ok,
            )
        self._log(f"結批完成: {', '.join(moved_sta) if moved_sta else '無資料'}")

    # ── 新增工單 ─────────────────────────────────────────────

    def _on_new_wo(self):
        has_unarchived = []
        for sta_id in STATION_IDS:
            src_dir = self.src_inputs[sta_id].text().strip()
            log_path = os.path.join(src_dir, "Log_All.txt")
            if src_dir and os.path.isfile(log_path) and os.path.getsize(log_path) > 0:
                has_unarchived.append(f"STA{sta_id}")

        if has_unarchived:
            reply = QMessageBox.question(
                self, "新增工單 — 確認結批",
                f"以下站的 log 目錄仍有未結批的 Log_All.txt：\n"
                f"  {', '.join(has_unarchived)}\n\n"
                "請確認是否已完成結批？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.No:
                return

        new_wou = self._prompt_wou(allow_cancel=True, current="")
        if new_wou:
            self._save_all_settings()
            self._log(f"新工單設定完成: {new_wou}")

    # ── Close ─────────────────────────────────────────────────

    def closeEvent(self, event):
        if self._ssh_led_timer:
            self._ssh_led_timer.stop()
        split_threads = dict(self._split_threads)
        upload_thread = self._upload_thread
        self.stop_watching(force=True)
        for t in split_threads.values():
            if t and t.isRunning():
                t.wait(5000)
        if upload_thread and upload_thread.isRunning():
            upload_thread.wait(5000)
        event.accept()


# ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    _icon = TN_LOGO_PATH if os.path.exists(TN_LOGO_PATH) else APP_ICON_PATH
    if os.path.exists(_icon):
        app.setWindowIcon(QIcon(_icon))
    window = RealtimeSplitterApp()
    window.show()
    sys.exit(app.exec_())
