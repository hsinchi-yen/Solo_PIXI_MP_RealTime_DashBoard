'use strict';

// ── HTML escape helper (prevents XSS from log-file content) ──────────────────
const esc = s => String(s ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;');

// ── Constants ────────────────────────────────────────────────────────────────
const YIELD_WARN = 90;
const YIELD_CRIT = 80;
const MAX_ROWS = 120;
const TREND_WINDOW_MS = 5 * 60 * 1000;
const TREND_THRESHOLD = 0.5;

// ── DOM refs ─────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const overlay       = $('overlay');
const progressBar   = $('progress-bar');
const progressText  = $('progress-text');
const clock         = $('clock');
const connDot       = $('conn-dot');
const kpiTotal      = $('kpi-total');
const kpiPass       = $('kpi-pass');
const kpiFail       = $('kpi-fail');
const kpiStop       = $('kpi-stop');
const kpiYield      = $('kpi-yield');
const kpiYieldTrend = $('kpi-yield-trend');
const kpiCompletion = $('kpi-completion');
const kpiCompTrend  = $('kpi-completion-trend');
const kpiRetest     = $('kpi-retest');
const statUph       = $('stat-uph');
const statPpm       = $('stat-ppm');
const recordsTbody  = $('records-tbody');
const hourlyChart   = $('hourly-chart');
const distChart     = $('dist-chart');
const logdirInput   = $('logdir-input');
const logdirBrowse  = $('logdir-browse');
const inputWo       = $('input-wo');
const inputWoCustom = $('input-wo-custom');
const btnWoRefresh  = $('btn-wo-refresh');
const inputTarget   = $('input-target');
const browseModal   = $('browse-modal');
const browseCurrent = $('browse-current-path');
const browseList    = $('browse-list');
const browseSelect  = $('browse-select');
const browseCancel  = $('browse-cancel');
const browseClose   = $('browse-close');
const btnSaveSettings = $('btn-save-settings');
const btnClearSettings = $('btn-clear-settings');
const btnSaveLogdir = $('btn-save-logdir');
const logSweepBtn = $('btn-log-sweep');
const toastRegion   = $('toast-region');
const confirmModal  = $('confirm-modal');
const confirmClose  = $('confirm-close');
const confirmOk     = $('confirm-ok');
const confirmCancel = $('confirm-cancel');
const confirmMsg    = $('confirm-message');
const filterStation = $('filter-station');
const filterResult  = $('filter-result');
const filterKeyword = $('filter-keyword');
const filterAnomalyBtn = $('filter-anomaly-priority');
const stationQuickChips = $('station-quick-chips');
const recordsCountMeta = $('records-count-meta');
const opsMode = $('ops-mode');
const opsWo = $('ops-wo');
const opsDb = $('ops-db');
const opsWoRoot = $('ops-wo-root');
const opsRawlogs = $('ops-rawlogs');
const logdirWoRoot = $('logdir-wo-root');
const logdirRawlogs = $('logdir-rawlogs');
const woFolderPath = $('wo-folder-path');

// Sys Metrics
const sysIp         = $('sys-ip');
const sysCpu        = $('sys-cpu');
const sysRam        = $('sys-ram');
const sysTemp       = $('sys-temp');

// DB Upload UI Elements
const btnDbSettings = $('btn-db-settings');
const dbModal = $('db-modal');
const dbClose = $('db-close');
const dbCancelBtn = $('db-cancel-btn');
const dbTestBtn = $('db-test-btn');
const dbSaveBtn = $('db-save-btn');
const dbHost = $('db-host');
const dbPort = $('db-port');
const dbName = $('db-name');
const dbUser = $('db-user');
const dbPass = $('db-pass');
const dbBreathingLight = $('db-breathing-light');
const btnUpload = $('btn-upload');
const btnAutoUpload = $('btn-auto-upload');
const uploadStatusText = $('upload-status-text');

let dbConnectionValid = false;
let dbUploadCheckInterval = null;
let recordsCache = [];
let recordsFilter = {
  station: '',
  result: '',
  keyword: '',
  anomalyFirst: false,
};
let _confirmResolve = null;

let CAN_MODIFY = false;
let CAN_DB = false;
const WO_CUSTOM_KEY = '__custom__';
const DEFAULT_WO_ROOT = '/run/media/nvme0n1p1';
const DEFAULT_LOG_DIR = '/run/media/nvme0n1p1/rawlogs';
let WO_MIN_LEN = 13;
let WO_MAX_LEN = 16;

function _shortPath(path, keep = 42) {
  const text = String(path || '').trim();
  if (!text) return '—';
  if (text.length <= keep) return text;
  return '...' + text.slice(-keep);
}

function _refreshOpsStrip() {
  if (opsMode) {
    opsMode.textContent = CAN_MODIFY ? 'LOCAL' : 'REMOTE';
    opsMode.className = `ops-value ${CAN_MODIFY ? 'ok' : 'warn'}`;
  }
  if (opsWo) {
    const wo = _getWoValue();
    opsWo.textContent = wo || '—';
    opsWo.className = `ops-value ${wo ? 'ok' : ''}`;
  }
  if (opsDb) {
    if (!CAN_DB) {
      opsDb.textContent = 'LOCKED';
      opsDb.className = 'ops-value warn';
    } else if (dbConnectionValid) {
      opsDb.textContent = 'READY';
      opsDb.className = 'ops-value ok';
    } else {
      opsDb.textContent = 'OFFLINE';
      opsDb.className = 'ops-value bad';
    }
  }
}

function _getWoFolderPath() {
  const wo = _getWoValue();
  if (!wo) return '';
  return `${DEFAULT_WO_ROOT}/${wo}`;
}

function _refreshWoPathLabel(exists = null, resolvedPath = null) {
  if (!woFolderPath) return;
  const path = resolvedPath || _getWoFolderPath();
  if (!path) {
    woFolderPath.textContent = 'WO PATH: —';
    woFolderPath.classList.remove('ok', 'bad');
    return;
  }
  woFolderPath.textContent = `WO PATH: ${_shortPath(path, 52)}`;
  woFolderPath.classList.remove('ok', 'bad');
  if (exists === true) woFolderPath.classList.add('ok');
  if (exists === false) woFolderPath.classList.add('bad');
}

function _setHealthLabel(el, ok, locked = false) {
  if (!el) return;
  el.className = 'ops-value';
  if (locked) {
    el.textContent = 'LOCKED';
    el.classList.add('warn');
    return;
  }
  el.textContent = ok ? 'READY' : 'MISSING';
  el.classList.add(ok ? 'ok' : 'bad');
}

async function _refreshPathHealth() {
  const wo = _getWoValue();
  _refreshWoPathLabel(null);

  try {
    const suffix = wo ? `?wo=${encodeURIComponent(wo)}` : '';
    const res = await fetch(`/api/path-health${suffix}`);
    if (!res.ok) throw new Error('path health unavailable');
    const data = await res.json();
    _setHealthLabel(opsWoRoot, !!data.wo_root_exists);
    _setHealthLabel(opsRawlogs, !!data.rawlogs_root_exists);
    _refreshWoPathLabel(wo ? !!data.wo_path_exists : null, data.wo_path || null);
  } catch (_) {
    _setHealthLabel(opsWoRoot, false, !CAN_MODIFY);
    _setHealthLabel(opsRawlogs, false, !CAN_MODIFY);
    _refreshWoPathLabel(null);
  }
}

function _normalizeWoCandidate(raw) {
  let text = String(raw ?? '').trim();
  if (!text) return '';
  const lb = text.indexOf('[');
  const rb = text.indexOf(']');
  if (lb >= 0 && rb > lb) {
    text = text.slice(lb + 1, rb).trim();
  }
  return text;
}

function _woLengthOk(raw) {
  const len = _normalizeWoCandidate(raw).length;
  return len >= WO_MIN_LEN && len <= WO_MAX_LEN;
}

function _setWoCustomMode(enabled) {
  if (!inputWoCustom) return;
  inputWoCustom.classList.toggle('hidden', !enabled);
  inputWoCustom.disabled = !enabled || !CAN_MODIFY;
}

function _getWoValue() {
  if (!inputWo) return '';
  if (inputWo.value === WO_CUSTOM_KEY) {
    return String(inputWoCustom?.value ?? '').trim();
  }
  return String(inputWo.value ?? '').trim();
}

function _setWoValue(value) {
  if (!inputWo) return;
  const wo = String(value ?? '').trim();
  const hasExactOption = Array.from(inputWo.options).some(opt => opt.value === wo);
  if (wo && hasExactOption) {
    inputWo.value = wo;
    _setWoCustomMode(false);
    return;
  }
  inputWo.value = WO_CUSTOM_KEY;
  if (inputWoCustom) inputWoCustom.value = wo;
  _setWoCustomMode(true);
}

function _renderWorkOrders(items) {
  if (!inputWo) return;
  const keepValue = _getWoValue();
  const unique = [...new Set((items || []).filter(Boolean))];
  inputWo.innerHTML = '';

  unique.forEach(item => {
    const opt = document.createElement('option');
    opt.value = item;
    opt.textContent = item;
    inputWo.appendChild(opt);
  });

  const custom = document.createElement('option');
  custom.value = WO_CUSTOM_KEY;
  custom.textContent = 'custom';
  inputWo.appendChild(custom);

  if (unique.length === 0) {
    inputWo.value = WO_CUSTOM_KEY;
    _setWoCustomMode(true);
  }

  _setWoValue(keepValue);
}

async function _loadWorkOrders(forceRefresh = false) {
  if (!inputWo) return;
  if (!CAN_MODIFY) {
    _renderWorkOrders([]);
    return;
  }

  try {
    const suffix = forceRefresh ? '?refresh=1' : '';
    const res = await fetch(`/api/work-orders${suffix}`);
    if (!res.ok) throw new Error('failed to load work orders');
    const data = await res.json();
    if (Number.isInteger(data.length_min)) WO_MIN_LEN = data.length_min;
    if (Number.isInteger(data.length_max)) WO_MAX_LEN = data.length_max;
    if (WO_MIN_LEN > WO_MAX_LEN) {
      const t = WO_MIN_LEN;
      WO_MIN_LEN = WO_MAX_LEN;
      WO_MAX_LEN = t;
    }
    const items = (data.items || []).filter(_woLengthOk);
    _renderWorkOrders(items);
  } catch (e) {
    console.error('Failed to load work orders:', e);
    _renderWorkOrders([]);
  }
}

function _likelyLocalHost() {
  const h = window.location.hostname;
  return h === 'localhost' || h === '127.0.0.1' || h === '::1' || h === '[::1]';
}

function _setModifyControlsEnabled(enabled) {
  const controls = [
    inputWo,
    inputWoCustom,
    btnWoRefresh,
    inputTarget,
    btnEditSettings,
    btnSaveSettings,
    btnClearSettings,
    logdirInput,
    logdirBrowse,
    browseSelect,
    browseCancel,
    browseClose,
    btnSaveLogdir,
    logSweepBtn,
    logdirWoRoot,
    logdirRawlogs,
  ];

  controls.forEach(el => {
    if (!el) return;
    el.disabled = !enabled;
    if (!enabled) {
      el.title = 'Only editable from localhost:8080';
    }
  });

  if (!enabled) {
    closeBrowseModal();
    if (browseModal) browseModal.classList.add('hidden');
    _setWoCustomMode(inputWo?.value === WO_CUSTOM_KEY);
  }
  _refreshOpsStrip();
  _refreshPathHealth();
}

async function _loadAccessPolicy() {
  CAN_MODIFY = _likelyLocalHost();
  CAN_DB = _likelyLocalHost();
  try {
    const res = await fetch('/api/access');
    if (res.ok) {
      const data = await res.json();
      CAN_MODIFY = !!data.can_modify;
    }
  } catch (_) {}
  try {
    const res = await fetch('/api/db-access');
    if (res.ok) {
      const data = await res.json();
      CAN_DB = !!data.can_db;
    }
  } catch (_) {}
  _setModifyControlsEnabled(CAN_MODIFY);  // calls _refreshOpsStrip + _refreshPathHealth
  _setDbSettingsEnabled(CAN_DB);          // calls _refreshOpsStrip
}

function _setDbSettingsEnabled(enabled) {
  if (btnDbSettings) {
    btnDbSettings.disabled = !enabled;
    btnDbSettings.title = enabled ? 'DB Settings' : 'DB Settings (LAN access only)';
  }
  _refreshOpsStrip();
}

function notify(message, type = 'info') {
  if (!toastRegion) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type === 'error' ? 'err' : (type === 'success' ? 'ok' : '')}`;
  toast.textContent = message;
  toastRegion.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 3200);
}

function _closeConfirm(result) {
  if (!confirmModal) return;
  confirmModal.classList.add('hidden');
  if (_confirmResolve) {
    _confirmResolve(result);
    _confirmResolve = null;
  }
}

function askConfirm(message, okText = 'Confirm') {
  if (!confirmModal || !confirmMsg || !confirmOk) return Promise.resolve(false);
  confirmMsg.textContent = message;
  confirmOk.textContent = okText;
  confirmModal.classList.remove('hidden');
  return new Promise(resolve => {
    _confirmResolve = resolve;
  });
}

function _uniqueStationsFromRows(rows) {
  const set = new Set();
  rows.forEach(rec => {
    const station = String(rec.station_id || '').trim();
    if (station) set.add(station);
  });
  return Array.from(set).sort();
}

function _refreshStationFilterOptions() {
  if (!filterStation) return;
  const stations = _uniqueStationsFromRows(recordsCache);
  const current = filterStation.value;
  filterStation.innerHTML = '<option value="">All Stations</option>';
  stations.forEach(st => {
    const opt = document.createElement('option');
    opt.value = st;
    opt.textContent = st;
    filterStation.appendChild(opt);
  });
  filterStation.value = stations.includes(current) ? current : '';

  if (stationQuickChips) {
    stationQuickChips.innerHTML = '';
    const allBtn = document.createElement('button');
    allBtn.className = `station-chip ${!recordsFilter.station ? 'active' : ''}`;
    allBtn.textContent = 'ALL';
    allBtn.addEventListener('click', () => {
      recordsFilter.station = '';
      filterStation.value = '';
      renderRecordsFromCache();
      _refreshStationFilterOptions();
    });
    stationQuickChips.appendChild(allBtn);

    stations.slice(0, 8).forEach(st => {
      const btn = document.createElement('button');
      btn.className = `station-chip ${recordsFilter.station === st ? 'active' : ''}`;
      btn.textContent = st;
      btn.addEventListener('click', () => {
        recordsFilter.station = st;
        filterStation.value = st;
        renderRecordsFromCache();
        _refreshStationFilterOptions();
      });
      stationQuickChips.appendChild(btn);
    });
  }
}

function _passesFilter(rec) {
  const station = String(rec.station_id || '').trim();
  if (recordsFilter.station && station !== recordsFilter.station) return false;
  if (recordsFilter.result && String(rec.result || '') !== recordsFilter.result) return false;
  if (recordsFilter.keyword) {
    const kw = recordsFilter.keyword.toLowerCase();
    const hay = [
      rec.station_id,
      rec.mac1,
      rec.mac2,
      rec.result,
      rec.duration,
      ...(rec.failed_items || []).map(i => `${i.step_name} ${i.measurement} ${i.value}${i.unit}`),
    ].join(' ').toLowerCase();
    if (!hay.includes(kw)) return false;
  }
  return true;
}

function _sortRecords(rows) {
  if (!recordsFilter.anomalyFirst) return rows;
  const rank = r => (r.result === 'STOP' ? 2 : r.result === 'FAIL' ? 1 : 0);
  return rows
    .map((r, i) => [rank(r), i, r])
    .sort((a, b) => b[0] - a[0] || a[1] - b[1])
    .map(e => e[2]);
}

function renderRecordsFromCache() {
  recordsTbody.innerHTML = '';
  const filtered = _sortRecords(recordsCache.filter(_passesFilter));
  filtered.slice(0, MAX_ROWS).forEach(rec => {
    recordsTbody.appendChild(buildRow(rec));
  });
  if (recordsCountMeta) {
    recordsCountMeta.textContent = `${Math.min(filtered.length, MAX_ROWS)} / ${filtered.length}`;
  }
}

// ── Clock + System Metrics + Init ─────────────────────────────────────────────────────────────
const dateBadge = $('date-badge');
function tickClock() {
  const now = new Date();
  if (clock) clock.textContent = now.toLocaleTimeString('en-GB', { hour12: false });
  if (dateBadge) {
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    dateBadge.textContent = `${y}-${m}-${d}`;
  }
}
setInterval(tickClock, 1000);
tickClock();

async function _fetchSystemMetrics() {
  try {
    const res = await fetch('/api/system-metrics');
    if (!res.ok) return;
    const data = await res.json();
    if (sysIp) sysIp.textContent = data.eth0_ip;
    if (sysCpu) {
      sysCpu.textContent = data.cpu_usage;
      const cpuVal = parseFloat(data.cpu_usage);
      if (!isNaN(cpuVal)) {
        sysCpu.className = cpuVal > 80 ? 'sys-value sys-warn' : 'sys-value sys-ok';
      }
    }
    if (sysRam) sysRam.textContent = data.free_mem;
    if (sysTemp) {
      sysTemp.textContent = data.cpu_temp;
      const tempVal = parseFloat(data.cpu_temp);
      if (!isNaN(tempVal)) {
        sysTemp.className = tempVal > 70 ? 'sys-value sys-warn' : 'sys-value sys-ok';
      }
    }
  } catch (err) {
    // silently fail
  }
}
_fetchSystemMetrics();
setInterval(_fetchSystemMetrics, 5000);

// ── Input lock / unlock (after Save / before Clear) ──────────────────────────
const btnEditSettings = $('btn-edit-settings');

function _lockInputs() {
  inputWo.disabled = true;
  if (inputWoCustom) inputWoCustom.disabled = true;
  if (btnWoRefresh) btnWoRefresh.disabled = true;
  inputTarget.disabled = true;
  if (btnEditSettings) btnEditSettings.classList.remove('hidden');
}

function _unlockInputs() {
  inputWo.disabled = false;
  if (btnWoRefresh) btnWoRefresh.disabled = false;
  _setWoCustomMode(inputWo?.value === WO_CUSTOM_KEY);
  inputTarget.disabled = false;
  if (btnEditSettings) btnEditSettings.classList.add('hidden');
}

function _editSettings() {
  if (!CAN_MODIFY) return;
  _unlockInputs();
  _btnFeedback(btnEditSettings, '✓ Unlocked');
}

// ── Settings persistence (server-side JSON) ───────────────────────────────────
async function _saveSettings() {
  if (!CAN_MODIFY) return false;
  const settings = {
    wo:      _getWoValue(),
    qty:     parseInt(inputTarget.value, 10) || 100,
    log_dir: logdirInput.value,
  };
  
  try {
    const response = await fetch('/api/mission', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings)
    });
    
    if (!response.ok) throw new Error('Save failed');
    return true;
  } catch (e) {
    console.error('Failed to save settings:', e);
    return false;
  }
}

async function _saveSettingsWithFeedback() {
  const success = await _saveSettings();
  if (success) {
    _lockInputs();
    _btnFeedback($('btn-save-settings'), '✓ Saved!');
    _refreshOpsStrip();
    _refreshPathHealth();
  } else {
    _btnFeedback($('btn-save-settings'), '✗ Failed');
  }
}

async function _clearSettings() {
  if (!CAN_MODIFY) return;
  try {
    await fetch('/api/mission', { method: 'DELETE' });
  } catch (e) {
    console.error('Failed to clear settings:', e);
  }
  
  _setWoValue('');
  inputTarget.value = '100';
  logdirInput.value = DEFAULT_LOG_DIR;
  _unlockInputs();
  updateCompletion();
  _refreshOpsStrip();
  _refreshPathHealth();
  _btnFeedback($('btn-clear-settings'), '✓ Cleared!');
}

async function _restoreSettings() {
  try {
    const response = await fetch('/api/mission');
    if (!response.ok) return;
    
    const s = await response.json();
    _setWoValue(s.wo || '');
    if (s.qty)     { inputTarget.value = s.qty; }
    logdirInput.value = s.log_dir || DEFAULT_LOG_DIR;
    if (s.wo || s.qty) { _lockInputs(); }
    _refreshOpsStrip();
    _refreshPathHealth();
  } catch (e) {
    console.error('Failed to restore settings:', e);
  }
}

function _btnFeedback(btn, msg) {
  if (!btn) return;
  const orig = btn.textContent;
  btn.textContent = msg;
  btn.classList.add('btn-feedback');
  setTimeout(() => { btn.textContent = orig; btn.classList.remove('btn-feedback'); }, 1500);
}

$('btn-save-settings').addEventListener('click', _saveSettingsWithFeedback);
$('btn-clear-settings').addEventListener('click', _clearSettings);
if (btnEditSettings) btnEditSettings.addEventListener('click', _editSettings);

const _btnApplyLogdir = $('btn-save-logdir');
if (_btnApplyLogdir) _btnApplyLogdir.addEventListener('click', () => applyLogDir(logdirInput.value.trim()));

if (confirmClose) confirmClose.addEventListener('click', () => _closeConfirm(false));
if (confirmCancel) confirmCancel.addEventListener('click', () => _closeConfirm(false));
if (confirmOk) confirmOk.addEventListener('click', () => _closeConfirm(true));
if (confirmModal) {
  confirmModal.addEventListener('click', e => {
    if (e.target === confirmModal) _closeConfirm(false);
  });
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    if (confirmModal && !confirmModal.classList.contains('hidden')) {
      _closeConfirm(false);
      return;
    }
    if (dbModal && !dbModal.classList.contains('hidden')) {
      closeDbModal();
      return;
    }
    if (browseModal && !browseModal.classList.contains('hidden')) {
      closeBrowseModal();
    }
  }

  if (confirmModal && !confirmModal.classList.contains('hidden')) {
    _trapFocus(confirmModal, e);
    return;
  }
  if (dbModal && !dbModal.classList.contains('hidden')) {
    _trapFocus(dbModal, e);
    return;
  }
  if (browseModal && !browseModal.classList.contains('hidden')) {
    _trapFocus(browseModal, e);
  }
});

if (filterStation) {
  filterStation.addEventListener('change', () => {
    recordsFilter.station = filterStation.value;
    renderRecordsFromCache();
  });
}
if (filterResult) {
  filterResult.addEventListener('change', () => {
    recordsFilter.result = filterResult.value;
    renderRecordsFromCache();
  });
}
if (filterKeyword) {
  filterKeyword.addEventListener('input', () => {
    recordsFilter.keyword = filterKeyword.value.trim().toLowerCase();
    renderRecordsFromCache();
  });
}
if (filterAnomalyBtn) {
  filterAnomalyBtn.addEventListener('click', () => {
    recordsFilter.anomalyFirst = !recordsFilter.anomalyFirst;
    filterAnomalyBtn.textContent = `Anomaly Priority: ${recordsFilter.anomalyFirst ? 'ON' : 'OFF'}`;
    filterAnomalyBtn.classList.toggle('active', recordsFilter.anomalyFirst);
    renderRecordsFromCache();
  });
}

if (inputWo) {
  inputWo.addEventListener('change', () => {
    _setWoCustomMode(inputWo.value === WO_CUSTOM_KEY);
    _refreshOpsStrip();
    _refreshPathHealth();
  });
}
if (inputWoCustom) {
  inputWoCustom.addEventListener('input', () => {
    _refreshOpsStrip();
    _refreshPathHealth();
  });
}

if (btnWoRefresh) {
  btnWoRefresh.addEventListener('click', () => {
    if (!CAN_MODIFY) return;
    _loadWorkOrders(true);
  });
}

// ── Completion rate ───────────────────────────────────────────────────────────
let _lastTotal = 0;
let _lastCompletionPct = 0;
function updateCompletion() {
  const target = parseInt(inputTarget.value, 10);
  if (!isNaN(target) && target > 0 && _lastTotal > 0) {
    const pct = Math.min((_lastTotal / target) * 100, 999.9);
    _lastCompletionPct = pct;
    kpiCompletion.textContent = pct.toFixed(1) + '%';
    kpiCompletion.className = 'kpi-value ' + (pct >= 100 ? 'color-pass' : 'color-info');
  } else {
    _lastCompletionPct = 0;
    kpiCompletion.textContent = '—';
    kpiCompletion.className = 'kpi-value color-info';
  }
  if (kpiCompTrend) kpiCompTrend.innerHTML = _trendArrow('completion', _lastCompletionPct);
}
inputTarget.addEventListener('input', updateCompletion);
if (logdirInput) {
  logdirInput.addEventListener('input', () => {
    _refreshOpsStrip();
    _refreshPathHealth();
  });
}

// ── KPI trend tracking ────────────────────────────────────────────────────────
const _trendHistory = [];

function _recordTrend(yieldVal, completionVal) {
  const now = Date.now();
  _trendHistory.push({ ts: now, yield: yieldVal, completion: completionVal });
  const cutoff = now - TREND_WINDOW_MS * 2.4;
  while (_trendHistory.length > 1 && _trendHistory[0].ts < cutoff) _trendHistory.shift();
}

function _trendArrow(key, currentVal) {
  if (_trendHistory.length < 2) return '';
  const windowCutoff = Date.now() - TREND_WINDOW_MS;
  const baseline = _trendHistory.find(e => e.ts >= windowCutoff);
  if (!baseline) return '';
  const delta = currentVal - baseline[key];
  if (delta >= TREND_THRESHOLD)  return '<span class="trend-up">↑</span>';
  if (delta <= -TREND_THRESHOLD) return '<span class="trend-down">↓</span>';
  return '<span class="trend-flat">→</span>';
}

// ── KPI rendering ─────────────────────────────────────────────────────────────
function updateKPI(stats) {
  _lastTotal = stats.total || 0;
  kpiTotal.textContent = stats.total;
  kpiPass.textContent  = stats.pass;
  kpiFail.textContent  = stats.fail;
  kpiStop.textContent  = stats.stop;

  if (statUph) statUph.textContent = stats.uph !== undefined ? stats.uph : '—';
  if (statPpm && stats.minute_pass_rate !== undefined) {
    statPpm.textContent = stats.minute_pass_rate.toFixed(2);
  }

  const y = stats.yield;
  kpiYield.textContent = y.toFixed(1) + '%';
  kpiYield.className = 'kpi-value ' + (
    y >= YIELD_WARN ? 'color-pass' :
    y >= YIELD_CRIT ? 'color-warn' :
                      'color-fail blink'
  );

  updateCompletion();
  _recordTrend(y, _lastCompletionPct);
  if (kpiYieldTrend) kpiYieldTrend.innerHTML = _trendArrow('yield', y);

  if (kpiRetest) {
    const rr = stats.retest_rate;
    const rc = stats.retest_count || 0;
    if (rr !== undefined) {
      kpiRetest.textContent = rr.toFixed(1) + '%';
      kpiRetest.className = 'kpi-value ' + (rr > 0 ? 'color-warn' : 'color-pass');
      kpiRetest.title = `${rc} unit(s) retested`;
    }
  }
}

// ── Hourly chart (07:00–19:00 working window) ─────────────────────────────────
const HOURLY_START = 7;
const HOURLY_END   = 19;

function renderHourlyChart(hourly) {
  if (!hourly || Object.keys(hourly).length === 0) {
    hourlyChart.innerHTML = '<div class="chart-empty">No data</div>';
    return;
  }
  const values = [];
  for (let h = HOURLY_START; h <= HOURLY_END; h++) {
    values.push(Number(hourly[String(h)] ?? hourly[h] ?? 0) || 0);
  }
  const max = Math.max(1, ...values);
  hourlyChart.innerHTML = '';
  for (let h = HOURLY_START; h <= HOURLY_END; h++) {
    const count = Number(hourly[String(h)] ?? hourly[h] ?? 0) || 0;
    const pct = count > 0 ? Math.max((count / max) * 100, 4) : 0;
    const wrap = document.createElement('div');
    wrap.className = 'hourly-bar-wrap';
    wrap.title = `${h}:00 — ${count} units`;

    const bar = document.createElement('div');
    bar.className = 'hourly-bar';
    bar.style.height = `${pct}%`;

    const label = document.createElement('div');
    label.className = 'hourly-label';
    label.textContent = String(h);

    wrap.appendChild(bar);
    wrap.appendChild(label);
    hourlyChart.appendChild(wrap);
  }
}

// ── Distribution chart ────────────────────────────────────────────────────────
function renderDistribution(dist) {
  if (!dist || (dist.pass_pct === 0 && dist.fail_pct === 0 && dist.stop_pct === 0)) {
    distChart.innerHTML = '<div class="dist-empty">No data</div>';
    return;
  }
  distChart.innerHTML = '';
  const rows = [
    { label: 'PASS', pct: dist.pass_pct, barClass: 'dist-bar-pass', color: 'var(--pass)' },
    { label: 'FAIL', pct: dist.fail_pct, barClass: 'dist-bar-fail', color: 'var(--fail)' },
    { label: 'STOP', pct: dist.stop_pct, barClass: 'dist-bar-stop', color: 'var(--stop)' },
  ];
  rows.forEach(r => {
    const pct = Math.max(0, Math.min(Number(r.pct) || 0, 100));
    const row = document.createElement('div');
    row.className = 'dist-row';

    const label = document.createElement('div');
    label.className = 'dist-label';
    label.style.color = r.color;
    label.textContent = r.label;

    const barWrap = document.createElement('div');
    barWrap.className = 'dist-bar-wrap';
    const bar = document.createElement('div');
    bar.className = `dist-bar ${r.barClass}`;
    bar.style.width = `${pct}%`;
    barWrap.appendChild(bar);

    const pctLabel = document.createElement('div');
    pctLabel.className = 'dist-pct';
    pctLabel.textContent = `${pct}%`;

    row.appendChild(label);
    row.appendChild(barWrap);
    row.appendChild(pctLabel);
    distChart.appendChild(row);
  });
}

// ── Record row ────────────────────────────────────────────────────────────────
const RESULT_ICON = { PASS: '✓', FAIL: '✗', STOP: '⊘' };

function buildRow(rec) {
  const tr = document.createElement('tr');
  tr.className = 'record-row';
  if (rec.result === 'FAIL') tr.classList.add('row-fail');
  if (rec.result === 'STOP') tr.classList.add('row-stop');
  const badgeClass = { PASS: 'badge-pass', FAIL: 'badge-fail', STOP: 'badge-stop' }[rec.result] || '';
  const icon = RESULT_ICON[rec.result] || '';
  const stationStr = (rec.station_id && rec.station_id !== '') ? esc(rec.station_id) : '—';
  const timeStr = esc(rec.time || (rec.datetime || '').slice(11, 19));
  const failSummary = rec.failed_items && rec.failed_items.length > 0
    ? rec.failed_items.map(i => `${esc(i.step_name)}: ${esc(i.measurement)} ${esc(i.value)}${esc(i.unit)}`).join(' | ')
    : '';
  tr.innerHTML = `
    <td>${stationStr}</td>
    <td>${timeStr}</td>
    <td>${esc(rec.mac1)}</td>
    <td>${esc(rec.mac2)}</td>
    <td><span class="badge ${badgeClass}"><span class="result-icon">${icon}</span>${esc(rec.result)}</span></td>
    <td>${esc(rec.duration)}</td>
    <td class="fail-summary">${failSummary}</td>`;
  if (failSummary) {
    const failCell = tr.querySelector('.fail-summary');
    if (failCell) {
      failCell.title = 'Click to expand failure details';
      failCell.addEventListener('click', () => {
        tr.classList.toggle('expanded');
      });
    }
  }
  return tr;
}

function prependRecord(rec) {
  recordsCache.unshift(rec);
  if (recordsCache.length > MAX_ROWS * 3) {
    recordsCache = recordsCache.slice(0, MAX_ROWS * 3);
  }
  _refreshStationFilterOptions();

  const tr = buildRow(rec);
  if (!_passesFilter(rec)) return;
  const animMap = { PASS: 'new-pass', FAIL: 'new-fail', STOP: 'new-stop' };
  if (animMap[rec.result]) {
    tr.classList.add(animMap[rec.result]);
    tr.addEventListener('animationend', () => tr.classList.remove(animMap[rec.result]), { once: true });
  }
  recordsTbody.prepend(tr);
  while (recordsTbody.rows.length > MAX_ROWS) {
    recordsTbody.deleteRow(recordsTbody.rows.length - 1);
  }
  if (recordsCountMeta) {
    const filtered = recordsCache.filter(_passesFilter).length;
    recordsCountMeta.textContent = `${Math.min(filtered, MAX_ROWS)} / ${filtered}`;
  }
}

// ── Progress ──────────────────────────────────────────────────────────────────
function showProgress(current, total) {
  overlay.classList.remove('hidden');
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  progressBar.style.width = pct + '%';
  progressText.textContent = `${current} / ${total}`;
}
function hideProgress() { overlay.classList.add('hidden'); }

// ── Connection ────────────────────────────────────────────────────────────────
function setConnected(yes) {
  connDot.className = 'conn-dot ' + (yes ? 'connected' : 'disconnected');
  connDot.setAttribute('aria-label', yes ? 'Connected' : 'Disconnected');
}

// ── Full snapshot render ──────────────────────────────────────────────────────
function renderSnapshot(snap) {
  updateKPI(snap.stats);
  renderHourlyChart(snap.hourly_counts || {});
  renderDistribution(snap.result_distribution || { pass_pct: 0, fail_pct: 0, stop_pct: 0 });

  recordsCache = (snap.recent_records || []).slice();
  _refreshStationFilterOptions();
  renderRecordsFromCache();

  if (snap.log_dir !== undefined) logdirInput.value = snap.log_dir || DEFAULT_LOG_DIR;
  _refreshOpsStrip();
  _refreshPathHealth();
}

function clearDashboard() {
  [kpiTotal, kpiPass, kpiFail, kpiStop, kpiYield, kpiCompletion, kpiRetest].forEach(el => el.textContent = '—');
  if (statUph) statUph.textContent = '—';
  if (statPpm) statPpm.textContent = '—';
  recordsCache = [];
  _refreshStationFilterOptions();
  recordsTbody.innerHTML = '';
  hourlyChart.innerHTML = '<div class="chart-empty">No data</div>';
  distChart.innerHTML = '<div class="dist-empty">No data</div>';
  if (recordsCountMeta) recordsCountMeta.textContent = '0 / 0';
  _refreshPathHealth();
}

// ── Browse modal ──────────────────────────────────────────────────────────────
let _browsePath = '';

function _focusableIn(container) {
  if (!container) return [];
  return Array.from(container.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'))
    .filter(el => !el.disabled && el.offsetParent !== null);
}

function _trapFocus(modal, event) {
  if (event.key !== 'Tab' || !modal || modal.classList.contains('hidden')) return;
  const focusable = _focusableIn(modal);
  if (focusable.length === 0) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

async function browseNavigate(path) {
  browseCurrent.textContent = 'Loading...';
  try {
    const res = await fetch(`/api/browse-dir?path=${encodeURIComponent(path)}`);
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.error || res.statusText);
    }
    const data = await res.json();
    if (!data.current) throw new Error('invalid response');
    _browsePath = data.current;
    browseCurrent.textContent = data.current;

    browseList.innerHTML = '';
    let itemCount = 0;
    if (data.parent !== data.current) {
      const parentItem = document.createElement('div');
      parentItem.className = 'browse-item browse-parent';
      parentItem.dataset.path = data.parent;
      parentItem.textContent = '📁 ..';
      browseList.appendChild(parentItem);
      itemCount += 1;
    }
    data.dirs.forEach(d => {
      const sep = data.current.includes('\\') ? '\\' : '/';
      const fullPath = data.current + sep + d;
      const item = document.createElement('div');
      item.className = 'browse-item';
      item.dataset.path = fullPath;
      item.textContent = `📁 ${d}`;
      browseList.appendChild(item);
      itemCount += 1;
    });
    if (itemCount === 0) {
      const empty = document.createElement('div');
      empty.className = 'chart-empty';
      empty.textContent = '(No subdirectories)';
      browseList.appendChild(empty);
    }

    browseList.querySelectorAll('.browse-item').forEach(el => {
      el.addEventListener('click', () => browseNavigate(el.dataset.path));
    });
  } catch (e) {
    browseCurrent.textContent = 'Error';
    browseList.innerHTML = `<div class="chart-empty">Error: ${esc(e.message)}</div>`;
  }
}

function openBrowseModal() {
  if (!CAN_MODIFY) return;
  browseModal.classList.remove('hidden');
  const box = browseModal.querySelector('.modal-box');
  if (box) box.focus();
  // Start from backend default root so users can switch between allowed roots.
  browseNavigate('');
}
function closeBrowseModal() { browseModal.classList.add('hidden'); }

logdirBrowse.addEventListener('click', openBrowseModal);
browseClose.addEventListener('click', closeBrowseModal);
browseCancel.addEventListener('click', closeBrowseModal);
browseModal.addEventListener('click', e => { if (e.target === browseModal) closeBrowseModal(); });

browseSelect.addEventListener('click', async () => {
  if (!CAN_MODIFY) return;
  if (!_browsePath) return;
  logdirInput.value = _browsePath;
  closeBrowseModal();
  await applyLogDir(_browsePath);
});

// ── Log dir apply ─────────────────────────────────────────────────────────────
async function applyLogDir(dir) {
  if (!CAN_MODIFY) return;
  if (!dir) return;
  logdirBrowse.disabled = true;
  try {
    const res = await fetch('/api/config/log-dir', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ log_dir: dir }),
    });
    const data = await res.json();
    if (!res.ok) {
      notify('Failed to apply log directory: ' + (data.error || res.status), 'error');
    } else {
      await _saveSettings();
      notify('Log directory applied', 'success');
      _refreshOpsStrip();
      _refreshPathHealth();
    }
  } catch (e) {
    notify('Failed to apply log directory: ' + e.message, 'error');
  } finally {
    logdirBrowse.disabled = false;
  }
}

logdirInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') applyLogDir(logdirInput.value.trim());
});

if (logdirWoRoot) {
  logdirWoRoot.addEventListener('click', () => {
    if (!CAN_MODIFY) return;
    logdirInput.value = DEFAULT_WO_ROOT;
    applyLogDir(DEFAULT_WO_ROOT);
  });
}
if (logdirRawlogs) {
  logdirRawlogs.addEventListener('click', () => {
    if (!CAN_MODIFY) return;
    logdirInput.value = DEFAULT_LOG_DIR;
    applyLogDir(DEFAULT_LOG_DIR);
  });
}

// ── Log Sweep ─────────────────────────────────────────────────────────────────
if (logSweepBtn) {
  logSweepBtn.addEventListener('click', async () => {
    if (!CAN_MODIFY) return;
    const dir = logdirInput.value.trim();
    const msg = dir
      ? `Delete ALL .txt files in:\n${dir}\n\nThis cannot be undone. Continue?`
      : 'Delete ALL .txt files in the current log directory?\n\nThis cannot be undone. Continue?';
    const ok = await askConfirm(msg, 'Delete');
    if (!ok) return;
    logSweepBtn.disabled = true;
    try {
      const res = await fetch('/api/log-sweep', { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        notify(`Sweep complete: ${data.deleted} file(s) deleted.`, 'success');
      } else {
        notify('Sweep failed: ' + (data.error || res.status), 'error');
      }
    } catch (e) {
      notify('Sweep failed: ' + e.message, 'error');
    } finally {
      logSweepBtn.disabled = false;
    }
  });
}

// ── DB Upload Modal and Settings ──────────────────────────────────────────────
async function loadDbSettings() {
  try {
    const res = await fetch('/api/db-settings');
    if (res.ok) {
      const data = await res.json();
      dbHost.value = data.DB_HOST || '';
      dbPort.value = data.DB_PORT || '';
      dbName.value = data.DB_NAME || '';
      dbUser.value = data.DB_USER || '';
      dbPass.value = data.DB_PASS || '';
    }
  } catch (e) { console.error('Failed to load DB settings:', e); }
}

async function saveDbSettings() {
  dbSaveBtn.disabled = true;
  dbSaveBtn.textContent = 'Saving...';
  try {
    const res = await fetch('/api/db-settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        DB_HOST: dbHost.value.trim(),
        DB_PORT: dbPort.value.trim(),
        DB_NAME: dbName.value.trim(),
        DB_USER: dbUser.value.trim(),
        DB_PASS: dbPass.value.trim()
      })
    });
    dbSaveBtn.textContent = res.ok ? '✓ Saved' : '✗ Failed';
    if (res.ok) testDbConnection(false); // silent check, no await
  } catch (e) {
    dbSaveBtn.textContent = '✗ Error';
  } finally {
    dbSaveBtn.disabled = false;
    setTimeout(() => { dbSaveBtn.textContent = 'Save'; }, 1500);
  }
}

async function testDbConnection(showAlert = true) {
  if (showAlert) {
    dbTestBtn.textContent = 'Testing...';
    dbTestBtn.disabled = true;
  }
  let succeeded = false;
  try {
    let res;
    if (showAlert) {
      // User-initiated: test with current form values, not saved config
      res = await fetch('/api/db-test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          DB_HOST: dbHost.value.trim(),
          DB_PORT: dbPort.value.trim(),
          DB_NAME: dbName.value.trim(),
          DB_USER: dbUser.value.trim(),
          DB_PASS: dbPass.value.trim(),
        }),
      });
    } else {
      // Silent check: use saved config on server
      res = await fetch('/api/db-test');
    }
    if (res.ok) {
      if (showAlert) notify('Database connection successful', 'success');
      setDbConnectionStatus(true);
      succeeded = true;
    } else {
      const data = await res.json().catch(() => ({}));
      if (showAlert) notify('Connection failed: ' + (data.error || 'Unknown error'), 'error');
      setDbConnectionStatus(false);
    }
  } catch (e) {
    if (showAlert) notify('Connection test request failed: ' + e.message, 'error');
    setDbConnectionStatus(false);
  } finally {
    if (showAlert) {
      dbTestBtn.disabled = false;
      dbTestBtn.textContent = succeeded ? '✓ Success' : '✗ Failed';
      setTimeout(() => { dbTestBtn.textContent = 'Test Connection'; }, 1500);
    }
  }
}

function setDbConnectionStatus(valid) {
  dbConnectionValid = valid;
  dbBreathingLight.className = valid ? 'conn-dot connected' : 'conn-dot disconnected';
  
  const hasWo = !!_getWoValue();
  const canOperate = valid && hasWo && CAN_DB;
  btnUpload.disabled = !canOperate;
  btnAutoUpload.disabled = !canOperate;
  
  if (!valid) {
    uploadStatusText.textContent = 'DB Not Connected';
  } else if (!hasWo) {
    uploadStatusText.textContent = 'Select a WO first';
  } else if (!uploadStatusText.textContent.includes('stats:')) {
    uploadStatusText.textContent = 'Ready';
  }
  _refreshOpsStrip();
}

function openDbModal() {
  if (!CAN_DB) return;
  dbModal.classList.remove('hidden');
  const box = dbModal.querySelector('.modal-box');
  if (box) box.focus();
  loadDbSettings();
}
function closeDbModal() { dbModal.classList.add('hidden'); }

btnDbSettings.addEventListener('click', openDbModal);
dbClose.addEventListener('click', closeDbModal);
dbCancelBtn.addEventListener('click', closeDbModal);
dbSaveBtn.addEventListener('click', saveDbSettings);
dbTestBtn.addEventListener('click', () => testDbConnection(true));
dbModal.addEventListener('click', e => { if (e.target === dbModal) closeDbModal(); });

// ── Upload Actions ────────────────────────────────────────────────────────────
async function triggerUpload() {
  if (!dbConnectionValid || !CAN_DB) return;
  const wo = _getWoValue();
  if (!wo) {
    notify('Please select a WO first.', 'error');
    return;
  }
  
  btnUpload.disabled = true;
  try {
    const res = await fetch('/api/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wo: wo })
    });
    const data = await res.json();
    if (!res.ok) {
      notify('Upload start failed: ' + (data.error || res.status), 'error');
    } else {
      _btnFeedback(btnUpload, 'Started');
      notify('Upload started', 'success');
    }
  } catch (e) {
    notify('Upload request failed: ' + e.message, 'error');
  }
}

async function triggerAutoUpload() {
  if (!dbConnectionValid || !CAN_DB) return;
  const wo = _getWoValue();
  if (!wo) {
    notify('Please select a WO first.', 'error');
    return;
  }
  
  btnAutoUpload.disabled = true;
  try {
    const res = await fetch('/api/auto-upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wo: wo })
    });
    const data = await res.json();
    if (res.ok) {
      if (data.auto_running) {
        btnAutoUpload.textContent = 'Auto Upload: ON';
        btnAutoUpload.classList.add('light-active');
        notify('Auto upload enabled', 'success');
      } else {
        btnAutoUpload.textContent = 'Auto Upload: OFF';
        btnAutoUpload.classList.remove('light-active');
        notify('Auto upload disabled', 'info');
      }
    } else {
      notify('Auto upload toggle failed: ' + (data.error || res.status), 'error');
    }
  } catch (e) {
    notify('Auto upload request failed: ' + e.message, 'error');
  } finally {
    setDbConnectionStatus(dbConnectionValid); // Re-evaluate disabled state
  }
}

async function pollUploadStatus() {
  if (!dbConnectionValid) return;
  try {
    const res = await fetch('/api/upload-status');
    if (res.ok) {
      const data = await res.json();
      const st = data.stats;
      
      let msg = '';
      if (data.auto_running) msg += '[Auto ON] ';
      if (data.is_uploading) msg += '[Uploading] ';
      msg += `stats: ${st.uploaded}↑ ${st.skipped}⏭ ${st.failed}✗`;
      uploadStatusText.textContent = msg;
      
      if (data.auto_running) {
        btnAutoUpload.textContent = 'Auto Upload: ON';
        btnAutoUpload.classList.add('light-active');
      } else {
        btnAutoUpload.textContent = 'Auto Upload: OFF';
        btnAutoUpload.classList.remove('light-active');
      }
      
      if (data.is_uploading) {
        btnUpload.disabled = true;
      } else {
        setDbConnectionStatus(dbConnectionValid);
      }
    }
  } catch (e) {}
}

btnUpload.addEventListener('click', triggerUpload);
btnAutoUpload.addEventListener('click', triggerAutoUpload);

// Poll upload status every 2s (DB test only runs on user action, not polled)
setInterval(pollUploadStatus, 2000);

inputWo.addEventListener('change', () => setDbConnectionStatus(dbConnectionValid));

// ── Main init ─────────────────────────────────────────────────────────────────
async function init() {
  await _loadAccessPolicy();
  await _loadWorkOrders();
  await _restoreSettings();

  try {
    const cfg = await fetch('/api/config').then(r => r.json());
    logdirInput.value = cfg.log_dir || DEFAULT_LOG_DIR;
  } catch (_) {}
  _refreshOpsStrip();
  _refreshPathHealth();

  // Run initial DB check in background — do not block page load
  testDbConnection(false);

  let snap;
  try {
    snap = await fetch('/api/snapshot').then(r => r.json());
  } catch (e) {
    console.error('snapshot fetch failed', e);
    return;
  }

  if (!snap.ready) {
    showProgress(snap.scan_current || 0, snap.scan_total || 0);
  } else {
    hideProgress();
    renderSnapshot(snap);
  }

  const es = new EventSource('/api/stream');
  es.onopen = () => setConnected(true);
  es.onerror = () => {
    setConnected(false);
    es.addEventListener('open', async () => {
      setConnected(true);
      const s = await fetch('/api/snapshot').then(r => r.json());
      hideProgress();
      renderSnapshot(s);
    }, { once: true });
  };

  es.addEventListener('stats_update', e => {
    const data = JSON.parse(e.data);
    updateKPI(data);
    if (data.hourly_counts)      renderHourlyChart(data.hourly_counts);
    if (data.result_distribution) renderDistribution(data.result_distribution);
  });

  es.addEventListener('new_record', e => prependRecord(JSON.parse(e.data)));

  es.addEventListener('init_progress', e => {
    const { current, total } = JSON.parse(e.data);
    showProgress(current, total);
  });

  es.addEventListener('init_complete', async () => {
    const s = await fetch('/api/snapshot').then(r => r.json());
    hideProgress();
    renderSnapshot(s);
  });

  es.addEventListener('reset', () => {
    clearDashboard();
    showProgress(0, 0);
  });
}

// ── Boot ──────────────────────────────────────────────────────────────────────
init().catch(console.error);

// ── Silent KPI polling (fallback for missed SSE events) ──────────────────────
async function _silentRefresh() {
  try {
    const s = await fetch('/api/snapshot').then(r => r.json());
    if (!s.ready) return;
    updateKPI(s.stats);
    if (s.hourly_counts)       renderHourlyChart(s.hourly_counts);
    if (s.result_distribution) renderDistribution(s.result_distribution);
  } catch (_) {}
}
setInterval(_silentRefresh, 30000);
setInterval(_refreshPathHealth, 15000);

// ── Theme toggle (Daylight ↔ Dark) ───────────────────────────────────────────
const themeBtn = $('theme-btn');
function applyTheme(light) {
  document.body.classList.toggle('light-mode', light);
  if (themeBtn) {
    themeBtn.textContent = light ? '🌙 DARK' : '☀ DAY';
    themeBtn.classList.toggle('light-active', light);
  }
}
function toggleTheme() {
  const light = !document.body.classList.contains('light-mode');
  applyTheme(light);
  localStorage.setItem('theme', light ? 'light' : 'dark');
}
if (themeBtn) themeBtn.addEventListener('click', toggleTheme);
applyTheme(localStorage.getItem('theme') === 'light');
