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
const MAX_ROWS = 50;
const TREND_WINDOW_MS = 5 * 60 * 1000;   // 5-minute comparison window
const TREND_THRESHOLD = 0.5;              // % change considered significant

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
const stopPanel     = $('stop-panel');
const stopList      = $('stop-list');
const recordsTbody  = $('records-tbody');
const failureChart  = $('failure-chart');
const hourlyChart   = $('hourly-chart');
const distChart     = $('dist-chart');
const logdirInput   = $('logdir-input');
const logdirBrowse  = $('logdir-browse');
const inputWo       = $('input-wo');
const inputTarget   = $('input-target');
const woDisplay     = $('wo-display');
const browseModal   = $('browse-modal');
const browseCurrent = $('browse-current-path');
const browseList    = $('browse-list');
const browseSelect  = $('browse-select');
const browseCancel  = $('browse-cancel');
const browseClose   = $('browse-close');

// ── Clock ────────────────────────────────────────────────────────────────────
function tickClock() {
  clock.textContent = new Date().toLocaleTimeString('en-GB', { hour12: false });
}
setInterval(tickClock, 1000);
tickClock();

// ── Work Order display ───────────────────────────────────────────────────────
inputWo.addEventListener('input', () => {
  woDisplay.textContent = inputWo.value ? `WO: ${inputWo.value}` : '';
  _saveSettings();
});
inputTarget.addEventListener('input', _saveSettings);

// ── Settings persistence (localStorage) ─────────────────────────────────────
const _SETTINGS_KEY = 'pixi_dash_settings';

function _saveSettings() {
  const settings = {
    wo:      inputWo.value,
    qty:     inputTarget.value,
    log_dir: logdirInput.value,
  };
  localStorage.setItem(_SETTINGS_KEY, JSON.stringify(settings));
}

function _saveSettingsWithFeedback() {
  _saveSettings();
  _btnFeedback($('btn-save-settings'), '✓ Saved!');
  _btnFeedback($('btn-save-logdir'),   '✓');
}

function _clearSettings() {
  localStorage.removeItem(_SETTINGS_KEY);
  inputWo.value = '';
  inputTarget.value = '100';
  woDisplay.textContent = '';
  updateCompletion();
  _btnFeedback($('btn-clear-settings'), '✓ Cleared!');
}

function _restoreSettings() {
  try {
    const raw = localStorage.getItem(_SETTINGS_KEY);
    let s = raw ? JSON.parse(raw) : {};
    // Migrate from old per-key storage if new key is missing
    if (!s.wo  && localStorage.getItem('wo_value')  !== null) s.wo  = localStorage.getItem('wo_value');
    if (!s.qty && localStorage.getItem('qty_value') !== null) s.qty = localStorage.getItem('qty_value');
    if (s.wo)      { inputWo.value = s.wo; woDisplay.textContent = `WO: ${s.wo}`; }
    if (s.qty)     { inputTarget.value = s.qty; }
    if (s.log_dir) { logdirInput.value = s.log_dir; }
  } catch (_) {}
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

// Footer LOG DIR save/clear buttons (added by user in footer bar)
const _btnSaveLogdir  = $('btn-save-logdir');
const _btnClearLogdir = $('btn-clear-logdir');
if (_btnSaveLogdir)  _btnSaveLogdir.addEventListener('click',  _saveSettingsWithFeedback);
if (_btnClearLogdir) _btnClearLogdir.addEventListener('click', _clearSettings);

// ── Completion rate ──────────────────────────────────────────────────────────
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

// ── KPI trend tracking ────────────────────────────────────────────────────────
const _trendHistory = [];   // [{ts, yield, completion}]

function _recordTrend(yieldVal, completionVal) {
  const now = Date.now();
  _trendHistory.push({ ts: now, yield: yieldVal, completion: completionVal });
  // Keep only last 12 minutes (2× window) to bound memory
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

  // Record trend snapshot then render arrows
  updateCompletion();
  _recordTrend(y, _lastCompletionPct);
  if (kpiYieldTrend) kpiYieldTrend.innerHTML = _trendArrow('yield', y);

  // retest rate
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

// ── Hourly chart ──────────────────────────────────────────────────────────────
function renderHourlyChart(hourly) {
  if (!hourly || Object.keys(hourly).length === 0) {
    hourlyChart.innerHTML = '<div class="chart-empty">No data</div>';
    return;
  }
  const values = Object.values(hourly).map(v => Number(v) || 0);
  const max = Math.max(1, ...values);
  hourlyChart.innerHTML = '';
  for (let h = 0; h < 24; h++) {
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

// ── Failure chart ─────────────────────────────────────────────────────────────
function renderFailureChart(stats) {
  const entries = Object.entries(stats);
  if (entries.length === 0) {
    failureChart.innerHTML = '<div class="chart-empty">No failures recorded</div>';
    return;
  }
  const max = Math.max(...entries.map(([, v]) => v));
  failureChart.innerHTML = entries
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => {
      const pct = max > 0 ? Math.max((count / max) * 100, 3) : 3;
      const safeName = esc(name);
      const safeCount = esc(String(count));
      return `
        <div class="chart-row">
          <div class="chart-name" title="${safeName}">${safeName}</div>
          <div class="chart-bar-wrap">
            <div class="chart-bar" style="width:${pct}%"></div>
            <span class="chart-count">${safeCount}</span>
          </div>
        </div>`;
    }).join('');
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
  const timeStr = esc(rec.time || (rec.datetime || '').slice(11, 19));
  const failSummary = rec.failed_items && rec.failed_items.length > 0
    ? rec.failed_items.map(i => `${esc(i.step_name)}: ${esc(i.measurement)} ${esc(i.value)}${esc(i.unit)}`).join(' | ')
    : '';
  tr.innerHTML = `
    <td>${timeStr}</td>
    <td>${esc(rec.mac1)}</td>
    <td>${esc(rec.mac2)}</td>
    <td><span class="badge ${badgeClass}"><span class="result-icon">${icon}</span>${esc(rec.result)}</span></td>
    <td>${esc(rec.duration)}</td>
    <td class="fail-summary">${failSummary}</td>`;
  return tr;
}

function prependRecord(rec) {
  const tr = buildRow(rec);
  const animMap = { PASS: 'new-pass', FAIL: 'new-fail', STOP: 'new-stop' };
  if (animMap[rec.result]) {
    tr.classList.add(animMap[rec.result]);
    tr.addEventListener('animationend', () => tr.classList.remove(animMap[rec.result]), { once: true });
  }
  recordsTbody.prepend(tr);
  while (recordsTbody.rows.length > MAX_ROWS) {
    recordsTbody.deleteRow(recordsTbody.rows.length - 1);
  }
}

// ── STOP alert ────────────────────────────────────────────────────────────────
function makeStopRow(time, mac1, fixtureId) {
  const div = document.createElement('div');
  div.className = 'stop-row';
  div.innerHTML = `
    <span>${esc(time)}</span>
    <span>MAC: ${esc(mac1)}</span>
    <span>${esc(fixtureId)}</span>
    <button class="stop-ack" title="Acknowledge and close">✓ ACK</button>`;
  div.querySelector('.stop-ack').addEventListener('click', () => {
    div.classList.add('stop-acked');
    setTimeout(() => {
      div.remove();
      if (!stopList.querySelector('.stop-row')) stopPanel.classList.add('hidden');
    }, 350);
  });
  return div;
}

function showStopAlert(alert) {
  stopPanel.classList.remove('hidden');
  const time = alert.time || (alert.datetime || '').slice(11, 19);
  stopList.prepend(makeStopRow(time, alert.mac1 || '', alert.fixture_id || ''));
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
const connLabel = $('conn-label');
function setConnected(yes) {
  connDot.className = 'conn-dot ' + (yes ? 'connected' : 'disconnected');
  if (connLabel) connLabel.textContent = yes ? 'CONNECTED' : 'DISCONNECTED';
}

// ── Full snapshot render ──────────────────────────────────────────────────────
function renderSnapshot(snap) {
  updateKPI(snap.stats);
  renderFailureChart(snap.failure_stats || {});
  renderHourlyChart(snap.hourly_counts || {});
  renderDistribution(snap.result_distribution || { pass_pct: 0, fail_pct: 0, stop_pct: 0 });

  recordsTbody.innerHTML = '';
  (snap.recent_records || []).forEach(rec => recordsTbody.appendChild(buildRow(rec)));

  stopList.innerHTML = '';
  const stops = snap.stop_alerts || [];
  if (stops.length > 0) {
    stopPanel.classList.remove('hidden');
    stops.forEach(s => {
      const time = (s.datetime || '').slice(11, 19);
      stopList.appendChild(makeStopRow(time, s.mac1 || '', s.fixture_id || ''));
    });
  } else {
    stopPanel.classList.add('hidden');
  }

  if (snap.log_dir !== undefined) logdirInput.value = snap.log_dir;
}

function clearDashboard() {
  [kpiTotal, kpiPass, kpiFail, kpiStop, kpiYield, kpiCompletion, kpiRetest].forEach(el => el.textContent = '—');
  if (statUph) statUph.textContent = '—';
  if (statPpm) statPpm.textContent = '—';
  recordsTbody.innerHTML = '';
  stopList.innerHTML = '';
  stopPanel.classList.add('hidden');
  failureChart.innerHTML = '<div class="chart-empty">No failures recorded</div>';
  hourlyChart.innerHTML = '<div class="chart-empty">No data</div>';
  distChart.innerHTML = '<div class="dist-empty">No data</div>';
}

// ── Browse modal ──────────────────────────────────────────────────────────────
let _browsePath = '';

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
  browseModal.classList.remove('hidden');
  browseNavigate(logdirInput.value.trim() || '');
}
function closeBrowseModal() { browseModal.classList.add('hidden'); }

logdirBrowse.addEventListener('click', openBrowseModal);
browseClose.addEventListener('click', closeBrowseModal);
browseCancel.addEventListener('click', closeBrowseModal);
browseModal.addEventListener('click', e => { if (e.target === browseModal) closeBrowseModal(); });

browseSelect.addEventListener('click', async () => {
  if (!_browsePath) return;
  logdirInput.value = _browsePath;
  closeBrowseModal();
  await applyLogDir(_browsePath);
});

// ── Log dir apply ─────────────────────────────────────────────────────────────
async function applyLogDir(dir) {
  if (!dir) return;
  logdirBrowse.disabled = true;
  try {
    const res = await fetch('/api/config/log-dir', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ log_dir: dir }),
    });
    const data = await res.json();
    if (!res.ok) alert('Error: ' + (data.error || res.status));
    else _saveSettings();   // auto-save log_dir after successful apply
  } catch (e) {
    alert('Request failed: ' + e.message);
  } finally {
    logdirBrowse.disabled = false;
  }
}

logdirInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') applyLogDir(logdirInput.value.trim());
});

// ── Main init ─────────────────────────────────────────────────────────────────
async function init() {
  _restoreSettings();   // restore WO / QTY / LOG DIR from localStorage before anything else

  try {
    const cfg = await fetch('/api/config').then(r => r.json());
    logdirInput.value = cfg.log_dir || '';
  } catch (_) {}

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
    if (data.hourly_counts) renderHourlyChart(data.hourly_counts);
    if (data.result_distribution) renderDistribution(data.result_distribution);
  });

  es.addEventListener('new_record', e => prependRecord(JSON.parse(e.data)));
  es.addEventListener('stop_alert', e => showStopAlert(JSON.parse(e.data)));

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

  es.addEventListener('failure_update', e => renderFailureChart(JSON.parse(e.data)));
}

// ── Boot ──────────────────────────────────────────────────────────────────────
init().catch(console.error);

// ── Silent KPI polling (fallback for missed SSE events) ──────────────────────
// Every 30 s fetch a fresh snapshot and update KPI + charts without touching
// the WO / QTY inputs or reloading the page.
async function _silentRefresh() {
  try {
    const s = await fetch('/api/snapshot').then(r => r.json());
    if (!s.ready) return;
    updateKPI(s.stats);
    if (s.hourly_counts)      renderHourlyChart(s.hourly_counts);
    if (s.result_distribution) renderDistribution(s.result_distribution);
    if (s.failure_stats)       renderFailureChart(s.failure_stats);
  } catch (_) {}
}
setInterval(_silentRefresh, 30000);

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
// Restore saved preference
applyTheme(localStorage.getItem('theme') === 'light');



