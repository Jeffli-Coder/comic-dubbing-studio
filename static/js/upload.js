/* upload.js — 书架 + 上传页 */
'use strict';

let shelfTimer = null;
let pickedFiles = [];

async function renderBooks() {
  clearInterval(shelfTimer);
  const view = $('#view');
  view.innerHTML = `
    <h2 class="page-title">📚 书架 / 上传新漫画</h2>
    <div class="dropzone" id="dropzone">
      <span class="big">📖</span>
      点击选择或拖入漫画页图片（jpg / png / webp）或 PDF 文档，按文件名排序<br>
      <span class="hint">PDF 会自动逐页拆分为单页图片；上传后自动：OCR 识别台词 → 角色选音 → 整书语音合成，合成完即可翻页听书</span>
      <input type="file" id="file-input" accept="image/*,.pdf" multiple hidden>
    </div>
    <div class="thumb-grid" id="thumbs"></div>
    <div class="actions">
      <button class="btn" id="upload-btn" disabled>🚀 上传并开始处理</button>
      <span class="hint" id="pick-count"></span>
    </div>
    <div class="shelf" id="shelf" style="margin-top:36px"></div>
  `;

  const dz = $('#dropzone');
  const input = $('#file-input');
  dz.addEventListener('click', () => input.click());
  dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('drag'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
  dz.addEventListener('drop', (e) => {
    e.preventDefault();
    dz.classList.remove('drag');
    setPicked([...e.dataTransfer.files]);
  });
  input.addEventListener('change', () => setPicked([...input.files]));

  $('#upload-btn').addEventListener('click', doUpload);
  await loadShelf();
}

function setPicked(files) {
  const imgs = files.filter((f) => /\.(jpe?g|png|webp|pdf)$/i.test(f.name))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
  if (!imgs.length) { toast('没有可用的文件（jpg / png / webp / pdf）', true); return; }
  pickedFiles = imgs;
  const grid = $('#thumbs');
  grid.innerHTML = '';
  imgs.forEach((f, i) => {
    const div = document.createElement('div');
    div.className = 'thumb';
    const isPdf = /\.pdf$/i.test(f.name);
    div.innerHTML = isPdf
      ? `<div class="thumb-doc">📄<span>PDF</span></div><span class="num">${i + 1} · ${escapeHtml(f.name)}</span>`
      : `<img src="${URL.createObjectURL(f)}" alt=""><span class="num">${i + 1} · ${escapeHtml(f.name)}</span>`;
    grid.appendChild(div);
  });
  $('#pick-count').textContent = `已选 ${imgs.length} 个文件（PDF 将在服务端逐页拆分），按文件名顺序翻页`;
  $('#upload-btn').disabled = false;
}

async function doUpload() {
  if (!pickedFiles.length) return;
  const btn = $('#upload-btn');
  btn.disabled = true;
  btn.textContent = '⏳ 上传中…';
  try {
    const fd = new FormData();
    pickedFiles.forEach((f) => fd.append('files', f));
    const res = await api('/api/books', { method: 'POST', body: fd });
    toast(`已上传 ${res.page_count} 页，开始后台处理`);
    location.hash = `#read/${res.book_id}`;
  } catch (e) {
    toast(e.message, true);
    btn.disabled = false;
    btn.textContent = '🚀 上传并开始处理';
  }
}

/* ── 书架 ───────────────────────────────────────────── */
async function loadShelf() {
  const shelf = $('#shelf');
  if (!shelf) return;
  try {
    const data = await api('/api/books');
    const alive = data.books.some((b) => b.alive || b.status !== 'ready');
    shelf.innerHTML = data.books.length ? '' : '<p class="hint" style="grid-column:1/-1">还没有漫画，上传第一本试试～</p>';
    data.books.forEach((b) => {
      const pct = pctOf(b);
      const badge = b.status === 'ready'
        ? '<span class="badge ready">✅ 可阅读</span>'
        : b.status === 'error'
          ? '<span class="badge error">⚠ 出错</span>'
          : `<span class="badge busy">⏳ ${stageCn(b.stage)}</span>`;
      const card = document.createElement('div');
      card.className = 'book-card';
      card.innerHTML = `
        <button class="book-del" title="删除这本书及其全部音频">✕</button>
        <div class="cover">🎞️</div>
        <h3>${escapeHtml(b.title)}</h3>
        <div class="meta">
          <span>${b.page_count} 页</span><span>${escapeHtml((b.created_at || '').slice(0, 16))}</span>${badge}
        </div>
        <div class="prog"><i style="width:${pct}%"></i></div>
      `;
      card.querySelector('.book-del').addEventListener('click', async (e) => {
        e.stopPropagation();   // 不能触发卡片的“进入阅读”点击
        if (!confirm(`确定删除《${b.title}》？\n已生成的全部音频将一并删除，不可恢复。`)) return;
        try {
          await api(`/api/books/${b.book_id}`, { method: 'DELETE' });
          toast('已删除');
          loadShelf();
        } catch (err) {
          toast(err.message || '删除失败', true);
        }
      });
      card.addEventListener('click', () => { location.hash = `#read/${b.book_id}`; });
      shelf.appendChild(card);
    });
    if (alive) {
      clearInterval(shelfTimer);
      shelfTimer = setInterval(() => { if (location.hash.startsWith('#books') || location.hash === '') loadShelf(); }, 2500);
    }
  } catch (e) {
    if (shelf) shelf.innerHTML = `<p class="hint">加载失败: ${escapeHtml(e.message)}</p>`;
  }
}

function pctOf(b) {
  const p = b.progress || {};
  if (b.status === 'ready') return 100;
  if (p.stage === 'tts' || p.stage === 'concat') return p.total ? Math.round(p.done * 100 / p.total) : 0;
  if (p.stage === 'ocr') return p.page_total ? Math.round(p.page_done * 100 / p.page_total / 2) : 0;
  if (p.stage === 'voice_pick') return 60;
  return 5;
}