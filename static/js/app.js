/* app.js — 工具函数 / hash 路由 / 健康自检 */
'use strict';

const $ = (sel) => document.querySelector(sel);

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const d = await res.json(); msg = d.detail || msg; } catch (e) { /* keep */ }
    throw new Error(msg);
  }
  return res.json();
}

function toast(msg, isErr = false) {
  const el = $('#toast');
  el.textContent = msg;
  el.classList.toggle('err', isErr);
  el.classList.remove('hidden');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add('hidden'), 3200);
}

const STAGE_CN = {
  queued: '排队中', ocr: '识别漫画页', voice_pick: '角色选音',
  tts: '语音合成', concat: '拼接页面音频', ready: '已完成', resynth: '换音色重合成',
};
function stageCn(s) { return STAGE_CN[s] || (s || '…'); }

/* ── 路由：#books / #read/{id} ───────────────────────── */
async function route() {
  const hash = location.hash || '#books';
  const nav = $('#nav');
  nav.querySelectorAll('a').forEach((a) => a.classList.remove('active'));
  if (hash.startsWith('#read/')) {
    const bookId = hash.slice(6);
    const link = nav.querySelector('a[data-nav="read"]');
    if (link) link.classList.add('active');
    try { await renderReader(bookId); } catch (e) { toast(e.message, true); location.hash = '#books'; }
  } else {
    nav.querySelector('a[data-nav="books"]').classList.add('active');
    renderBooks();
  }
}
window.addEventListener('hashchange', route);

/* ── 健康自检 ────────────────────────────────────────── */
async function loadHealth() {
  const chip = $('#health');
  try {
    const h = await api('/api/health');
    if (h.mock_mode) {
      chip.textContent = 'Mock 演示模式 · 无需 API Key';
      chip.classList.remove('down');
      chip.classList.add('ok');
      chip.title = 'MOCK_MODE=1：使用内置模拟引擎，可完整体验上传 / 翻页 / 高亮 / 换音色';
      return;
    }
    const degraded = !!(h.degraded && (h.degraded.tts?.length || h.degraded.vision?.length || h.degraded.llm?.length));
    chip.textContent = `引擎 ${h.providers.tts.toUpperCase()} · 视觉 ${h.providers.vision.toUpperCase()}` +
      (h.ffmpeg ? '' : ' · 无ffmpeg(降级模式)');
    chip.classList.toggle('down', !!degraded);
    chip.classList.toggle('ok', !degraded);
    chip.title = degraded ? JSON.stringify(h.degraded, null, 2) : '全部引擎就绪';
  } catch (e) {
    chip.textContent = '服务不可用';
    chip.classList.add('down');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  route();
  loadHealth();
  $('#voice-close').addEventListener('click', closeVoices);
});