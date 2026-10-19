/* reader.js — 阅读页：翻页动画 + 音频联动逐句高亮 + 自动翻页 + 进度轮询 */
'use strict';

const R = {
  bookId: null,
  meta: null,
  page: 0,
  pageCount: 0,
  busy: false,          // 翻页动画中
  ended: false,         // 是否已加载过第一页
  autoTurn: true,
  polling: null,
  timings: null,        // 当前页 timings
  lines: [],
  segIdx: -1,           // single 模式当前高亮句
  audio: null,
  seq: [],              // sequence 模式 [{url, pause_after_ms}]
  seqIdx: 0,
  seqTimer: null,
  playWanted: false,    // 翻页后是否自动续播
  prevTime: 0,          // 换音色后尽量续播
};

async function renderReader(bookId) {
  Object.assign(R, {
    bookId, meta: null, page: 0, pageCount: 0, busy: false, ended: false,
    timings: null, lines: [], segIdx: -1, seq: [], seqIdx: 0, seqTimer: null,
    seqDone: true, seqAudio: null, playWanted: false, prevTime: 0, lastNat: null,
  });
  clearInterval(R.polling);
  const view = $('#view');
  view.innerHTML = `
    <div class="pipeline-bar hidden" id="pbar">
      <div class="row"><span class="stage-name" id="pbar-stage"></span><span id="pbar-pct"></span></div>
      <div class="prog"><i id="pbar-fill"></i></div>
    </div>
    <div id="retry-row" class="hidden" style="margin:-6px 0 14px; display:flex; gap:10px; align-items:center">
      <button class="btn" id="retry-btn">🔄 重试处理（续跑，已完成部分不重做）</button>
      <span class="hint" id="retry-note"></span>
    </div>
    <div class="reader">
      <section class="stage">
        <h2 class="page-title" id="book-title" style="margin-top:0">…</h2>
        <div class="stage-frame" id="stage-frame">
          <span class="page-tag" id="page-tag">– / –</span>
        </div>
        <div class="stage-ctrl">
          <button class="page-btn" id="pg-prev" title="上一页">◀</button>
          <button class="play-btn" id="pg-play" title="播放/暂停">▶</button>
          <button class="page-btn" id="pg-next" title="下一页">▶</button>
          <span class="page-ind" id="page-ind">0 / 0</span>
        </div>
        <div class="stage-ctrl" style="margin-top:10px; gap:22px">
          <label class="switch"><input type="checkbox" id="auto-switch" checked> 播完自动翻页</label>
          <button class="btn ghost" id="voices-btn">🎙️ 角色音色</button>
          <button class="btn ghost" id="back-btn">← 返回书架</button>
        </div>
      </section>
      <aside class="lines-panel">
        <h3>📝 本页台词（点击句子可跳播）</h3>
        <div id="lines-box"><div class="line empty-note">加载中…</div></div>
      </aside>
      <audio id="page-audio"></audio>
    </div>
  `;

  R.audio = $('#page-audio');
  $('#pg-prev').addEventListener('click', () => goPage(R.page - 1, 'prev'));
  $('#pg-next').addEventListener('click', () => goPage(R.page + 1, 'next'));
  $('#pg-play').addEventListener('click', togglePlay);
  $('#back-btn').addEventListener('click', () => { location.hash = '#books'; });
  $('#voices-btn').addEventListener('click', () => openVoices(R.bookId));
  $('#retry-btn').addEventListener('click', async () => {
    try {
      await api(`/api/books/${R.bookId}/rerun`, { method: 'POST' });
      $('#retry-row').classList.add('hidden');
      showPbar('重新排队', '');
      startPolling();
    } catch (e) { toast(e.message, true); }
  });
  $('#auto-switch').addEventListener('change', async (e) => {
    R.autoTurn = e.target.checked;
    try { await api(`/api/books/${R.bookId}/auto-turn`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: R.autoTurn }),
    }); } catch (err) { /* 忽略 */ }
  });
  window.addEventListener('keydown', onKey);
  window.addEventListener('resynth-start', onResynthStart);

  R.audio.addEventListener('timeupdate', onTime);
  R.audio.addEventListener('ended', onEnded);
  R.audio.addEventListener('play', () => { $('#pg-play').textContent = '⏸'; });
  R.audio.addEventListener('pause', () => { $('#pg-play').textContent = '▶'; });

  // 每次重建视图时重绑（先移除旧绑定，避免重复触发）
  window.removeEventListener('keydown', onKey);
  window.removeEventListener('resynth-start', onResynthStart);
  window.removeEventListener('resize', onResize);
  window.addEventListener('keydown', onKey);
  window.addEventListener('resynth-start', onResynthStart);
  window.addEventListener('resize', onResize);

  await boot();
}

function onKey(e) {
  if (!location.hash.startsWith('#read/')) return;
  if (e.key === 'ArrowRight') goPage(R.page + 1, 'next');
  if (e.key === 'ArrowLeft') goPage(R.page - 1, 'prev');
  if (e.key === ' ') { e.preventDefault(); togglePlay(); }
}

/* ── 启动：读 meta，处理中则轮询 ─────────────────────── */
async function boot() {
  try {
    const book = await api(`/api/books/${R.bookId}`);
    R.meta = book;
    R.pageCount = book.page_count || 0;
    R.autoTurn = book.auto_turn !== false;
    $('#auto-switch').checked = R.autoTurn;
    $('#book-title').textContent = book.title || '漫画';
    const nav = document.querySelector('#nav a[data-nav="books"]');
    if (nav) nav.textContent = '📚 书架 / 上传';

    const status = book.status;
    if (status === 'ready') {
      hidePbar();
      await goPage(1, null);
    } else if (status === 'error') {
      showPbar('失败', '');
      $('#pbar-stage').textContent = `⚠ 处理失败：${book.error || '未知错误'}`;
      $('#retry-row').classList.remove('hidden');
      setRetryNote(book);
      toast('处理中断，可点击「重试处理」续跑', true);
      // 已合成的页仍可预览
      try { await goPage(1, null); } catch (e) { /* 无页可读 */ }
    } else {
      showPbar(stageCn(book.progress && book.progress.stage), '正在处理，此间已合成的页可预览');
      startPolling();
    }
  } catch (e) {
    toast(e.message, true);
    location.hash = '#books';
  }
}

function startPolling() {
  clearInterval(R.polling);
  R.polling = setInterval(async () => {
    if (!location.hash.startsWith(`#read/${R.bookId}`)) { clearInterval(R.polling); return; }
    try {
      const st = await api(`/api/books/${R.bookId}/progress`);
      if (!st.exists) { clearInterval(R.polling); return; }
      updatePbar(st.status, st.progress || {});
      if (st.status === 'ready') {
        clearInterval(R.polling);
        await boot();       // 重新加载书数据 + 第一页
        return;
      }
      if (st.status === 'error') {
        clearInterval(R.polling);
        $('#pbar-stage').textContent = `⚠ 处理失败：${st.error || '未知错误'}`;
        $('#retry-row').classList.remove('hidden');
        setRetryNote(st);
        toast('处理中断，可点击「重试处理」续跑', true);
      }
      if (!R.ended && st.status !== 'error') {
        try { await goPage(1, null); } catch (e2) { /* 第一页还没好 */ }
      }
    } catch (e) { /* 轮询失败静默 */ }
  }, 1500);
}

function updatePbar(status, p) {
  const stage = $('#pbar-stage');
  const fill = $('#pbar-fill');
  const pctEl = $('#pbar-pct');
  if (status === 'queued' || !p || !p.stage) {
    pctEl.textContent = '';
    return;
  }
  let pct = 0, label = '';
  if (p.stage === 'ocr') {
    pct = p.page_total ? Math.round(p.page_done * 100 / p.page_total * 0.4) : 0;
    label = `识别页面 ${p.page_done}/${p.page_total}`;
  } else if (p.stage === 'voice_pick') {
    pct = 45; label = '为角色匹配音色（LLM）';
  } else if (p.stage === 'tts') {
    pct = p.total ? 45 + Math.round(p.done * 100 / p.total * 0.4) : 45;
    label = `合成台词 ${p.done}/${p.total}`;
  } else if (p.stage === 'concat') {
    pct = p.page_total ? 85 + Math.round(p.page_done * 100 / p.page_total * 0.15) : 85;
    label = `拼接页面音频 ${p.page_done}/${p.page_total}`;
  } else if (p.stage === 'resynth') {
    pct = p.total ? Math.round(p.done * 100 / p.total * 0.9) : 0;
    label = `重合成台词 ${p.done}/${p.total}`;
  } else {
    pct = 100; label = '完成';
  }
  stage.textContent = `⏳ ${stageCn(p.stage)} · ${label}`;
  fill.style.width = `${Math.min(100, pct)}%`;
  pctEl.textContent = `${Math.min(100, pct)}%`;
}

function showPbar(stage, note) {
  $('#pbar').classList.remove('hidden');
  $('#pbar-stage').textContent = `⏳ ${stage} ${note}`;
}
function hidePbar() { $('#pbar').classList.add('hidden'); }

function setRetryNote(meta) {
  const n = $('#retry-note');
  if (!n) return;
  const p = meta.progress || {};
  const failed = (meta.ocr_failed_pages || []).length;
  if (failed) {
    n.textContent = `已识别 ${p.page_done || 0}/${p.page_total || '?'} 页，${failed} 页因内容审核等问题被跳过（重试时会重新尝试）`;
  } else if (p.page_total) {
    n.textContent = `进度：${p.page_done || 0}/${p.page_total} 页`;
  } else {
    n.textContent = '';
  }
}

/* ── 翻页 ────────────────────────────────────────────── */
async function goPage(n, dir) {
  if (R.busy || n < 1) return;
  if (R.pageCount && n > R.pageCount) return;
  R.busy = true;
  R.prevTime = R.audio.currentTime;
  pauseAll();

  try {
    const data = await api(`/api/books/${R.bookId}/pages/${n}`);
    paintPage(data, dir);
    R.page = n;
    R.ended = true;
    R.lines = data.lines || [];
    R.timings = data.timings || {};
    R.segIdx = -1;
    renderLines();

    if (R.timings.mode === 'single') {
      if (data.audio_url) { R.audio.src = data.audio_url; R.audio.load(); }
      else { R.audio.removeAttribute('src'); }   // 无台词页（封面/目录）没有音频
    } else {
      R.seq = (R.timings.segments || []).map((s) => ({
        url: `/api/books/${R.bookId}/files/${s.audio_file}`,
        pause_ms: s.pause_after_ms || 0,
      }));
      R.seqIdx = -1;
      R.audio.removeAttribute('src');   // sequence：不使用主 audio
    }

    $('#page-ind').textContent = `${n} / ${R.pageCount || n}`;
    $('#page-tag').textContent = `P.${String(n).padStart(2, '0')}`;
    preloadPage(n + 1);
  } catch (e) {
    if (dir) toast(e.message || '该页不可用', true);
  } finally {
    R.busy = false;
    if (dir) startPage();   // 翻到哪页播哪页
  }
}

/* 翻页动画：图片面板 split-flap。 */
function paintPage(data, dir) {
  const frame = $('#stage-frame');
  const img = new Image();
  img.alt = `第 ${data.page_num} 页`;
  img.onload = () => {
    R.lastNat = { w: img.naturalWidth || 3, h: img.naturalHeight || 4 };
    fitStage();
  };
  img.src = data.image_url;
  if (dir === 'next') img.className = 'sheet back';
  else if (dir === 'prev') img.className = 'sheet ghost';
  else img.className = 'sheet front';
  frame.appendChild(img);

  if (dir) {
    const old = frame.querySelector('.front');
    requestAnimationFrame(() => {
      if (old) old.classList.add(dir === 'next' ? 'out-next' : 'out-prev');
      img.classList.remove('back', 'ghost');
      img.classList.add(dir === 'next' ? 'back-in' : 'ghost-in');
      setTimeout(() => {
        img.classList.remove('back-in', 'ghost-in');
        img.classList.add('front');
        // 清掉所有旧图（按元素身份判断，避免选择器漏删）
        frame.querySelectorAll(':scope > img').forEach((el) => { if (el !== img) el.remove(); });
      }, 620);
    });
  } else {
    frame.querySelectorAll(':scope > img').forEach((el) => { if (el !== img) el.remove(); });
  }
}

/* 按图片原始比例把舞台适配进视口——页面完整可见，不需要上下滚动 */
function fitStage() {
  const frame = $('#stage-frame');
  if (!frame || !R.lastNat) return;
  const wrapW = (frame.parentElement ? frame.parentElement.clientWidth : window.innerWidth) - 8;
  const maxW = Math.min(wrapW, 760);
  const maxH = Math.max(280, window.innerHeight - 250);   // 预留顶部标题与下方播放控制区
  const scale = Math.min(maxW / R.lastNat.w, maxH / R.lastNat.h);
  frame.style.width = Math.round(R.lastNat.w * scale) + 'px';
  frame.style.height = Math.round(R.lastNat.h * scale) + 'px';
}

function onResize() { fitStage(); }

function renderLines() {
  const box = $('#lines-box');
  if (!R.lines.length) {
    box.innerHTML = '<div class="line empty-note">本页没有台词</div>';
    return;
  }
  box.innerHTML = '';
  R.lines.forEach((ln, i) => {
    const div = document.createElement('div');
    div.className = 'line' + (ln.type === 'narration' ? ' narration' : '') + (ln.type === 'inner_thought' ? ' narration' : '');
    div.dataset.idx = i;
    div.innerHTML = `
      <div class="who"><span>${escapeHtml(ln.character)}</span><span class="emo">${escapeHtml(ln.emotion || '')}</span></div>
      <div class="txt">${escapeHtml(ln.text)}</div>`;
    div.addEventListener('click', () => seekLine(i));
    box.appendChild(div);
  });
}

function setActiveLine(i) {
  if (i === R.segIdx) return;
  R.segIdx = i;
  const lines = document.querySelectorAll('#lines-box .line');
  lines.forEach((el, idx) => el.classList.toggle('active', idx === i));
  // 只滚动台词面板自身——绝不动窗口滚动，避免和用户滚动打架
  const panel = document.querySelector('.lines-panel');
  const active = lines[i];
  if (!panel || !active || panel.scrollHeight <= panel.clientHeight) return;
  const pRect = panel.getBoundingClientRect();
  const aRect = active.getBoundingClientRect();
  if (aRect.top < pRect.top || aRect.bottom > pRect.bottom) {
    panel.scrollBy({ top: (aRect.top - pRect.top) - panel.clientHeight / 3, behavior: 'smooth' });
  }
}

/* ── 播放控制（single / sequence 双模式）────────────── */
function togglePlay() {
  if (!R.timings) return;
  const segs = R.timings.segments || [];
  if (!segs.length) { startPage(); return; }
  if (R.timings.mode === 'single') {
    if (R.audio.paused) { R.audio.play().catch(() => {}); } else { R.audio.pause(); }
  } else {
    if (R.seqIdx >= 0 && !R.seqDone) pauseAll();
    else seqPlay(R.seqIdx + 1 < R.seq.length ? R.seqIdx + 1 : 0);
  }
}

function startPage() {
  const segs = (R.timings && R.timings.segments) || [];
  if (!segs.length) {   // 无台词页（封面/目录）：自动翻页开启时短暂停留后跳过
    if (R.autoTurn && R.page < R.pageCount) {
      R.seqTimer = setTimeout(() => goPage(R.page + 1, 'next'), 1400);
    } else {
      toast('本页无台词');
    }
    return;
  }
  if (R.timings.mode === 'single') {
    R.audio.currentTime = 0;
    R.audio.play().catch(() => {});
  } else {
    seqPlay(0);
  }
}

function pauseAll() {
  R.audio.pause();
  clearTimeout(R.seqTimer);
  if (R.seqAudio) R.seqAudio.pause();
  R.seqDone = true;
  $('#pg-play').textContent = '▶';
}

function seekLine(i) {
  if (R.timings.mode === 'single') {
    const seg = R.timings.segments && R.timings.segments[i];
    if (!seg) return;
    R.audio.currentTime = seg.start_ms / 1000;
    R.audio.play().catch(() => {});
  } else {
    seqPlay(i);
  }
}

/* single 模式：timeupdate 二分高亮 + 播完自动翻页 */
function onTime() {
  const segs = (R.timings && R.timings.segments) || [];
  const ms = R.audio.currentTime * 1000;
  let lo = 0, hi = segs.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (segs[mid].start_ms <= ms) { ans = mid; lo = mid + 1; } else { hi = mid - 1; }
  }
  if (ans >= 0 && ms >= segs[ans].end_ms) ans = -1;   // 句间停顿
  setActiveLine(ans);
}

function onEnded() {
  if (R.autoTurn && R.page < R.pageCount) {
    R.playWanted = true;
    goPage(R.page + 1, 'next');
  } else {
    setActiveLine(-1);
    R.playWanted = false;
    $('#pg-play').textContent = '▶';
  }
}

/* sequence 模式：逐句播 + 句间 setTimeout 停顿 */
function seqPlay(i) {
  if (i < 0 || i >= R.seq.length) return;
  R.seqIdx = i;
  R.seqDone = false;
  clearTimeout(R.seqTimer);
  setActiveLine(i);
  if (!R.seqAudio) { R.seqAudio = new Audio(); }
  R.seqAudio.src = R.seq[i].url;
  R.seqAudio.onended = () => {
    if (i + 1 < R.seq.length) {
      R.seqTimer = setTimeout(() => seqPlay(i + 1), R.seq[i].pause_ms);
    } else {
      R.seqDone = true;
      setActiveLine(-1);
      $('#pg-play').textContent = '▶';
      if (R.autoTurn && R.page < R.pageCount) goPage(R.page + 1, 'next');
    }
  };
  R.seqAudio.play().catch(() => {});
  $('#pg-play').textContent = '⏸';
}

/* ── 预加载下一页（丝滑过渡的关键）────────────────── */
async function preloadPage(n) {
  if (n < 1 || (R.pageCount && n > R.pageCount)) return;
  try {
    const data = await api(`/api/books/${R.bookId}/pages/${n}`);
    const img = new Image();
    img.src = data.image_url;
    if (data.audio_url) { const a = new Audio(); a.preload = 'auto'; a.src = data.audio_url; }
    else (data.timings.segments || []).slice(0, 4).forEach((s) => { const a = new Audio(); a.preload = 'auto'; a.src = `/api/books/${R.bookId}/files/${s.audio_file}`; });
  } catch (e) { /* 下一页未就绪，忽略 */ }
}

/* ── 换音色：显示进度，完成后刷新当前页并尽量续播 ─── */
function onResynthStart() {
  clearInterval(R.polling);
  showPbar('换音色重合成', '');
  R.polling = setInterval(async () => {
    try {
      const st = await api(`/api/books/${R.bookId}/progress`);
      updatePbar(st.status, st.progress || {});
      if (st.status === 'ready') {
        clearInterval(R.polling);
        hidePbar();
        const t = R.audio.currentTime;
        setTimeout(async () => {
          try {
            const data = await api(`/api/books/${R.bookId}/pages/${R.page}`);
            R.lines = data.lines || [];
            R.timings = data.timings || {};
            renderLines();
            if (R.timings.mode === 'single') {
              if (data.audio_url) {
                R.audio.src = data.audio_url + '?v=' + Date.now();   // 换音色后强制拉新音频，绕开浏览器缓存
              } else {
                R.audio.removeAttribute('src');
              }
              R.audio.currentTime = Math.min(t, R.audio.duration || t);
              R.audio.play().catch(() => {});
            }
            toast('音色已更新 🎉');
          } catch (e2) { toast(e2.message, true); }
        }, 400);
      } else if (st.status === 'error') {
        clearInterval(R.polling);
        toast('重合成失败：' + (st.error || ''), true);
        hidePbar();
      }
    } catch (e3) { /* 静默 */ }
  }, 1200);
}