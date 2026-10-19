/* voices.js — 音色面板（50 种千问音色 + 角色换音色） */
'use strict';

let voiceCatalog = null;

async function openVoices(bookId) {
  try {
    if (!voiceCatalog) voiceCatalog = (await api('/api/voices')).voices || [];
    const book = await api(`/api/books/${bookId}`);
    const chars = book.characters || [];
    const assigns = book.voice_assignments || {};

    const list = $('#voice-list');
    list.innerHTML = `<div class="resynthing" id="voice-state" hidden>🔄 正在重合成，稍候…</div>`;
    if (!chars.length) {
      list.innerHTML = '<p class="hint">脚本尚未生成</p>';
    }
    chars.forEach((c) => {
      const name = c.name;
      const cur = assigns[name] || '';
      const row = document.createElement('div');
      row.className = 'char-row';
      row.dataset.char = name;
      row.innerHTML = `
        <div class="cname">${escapeHtml(name)}<div class="hint" style="margin-top:2px">${escapeHtml(c.type || '')}</div></div>
        <div style="flex:1">
          <select>${voiceOptions(voiceCatalog, cur)}</select>
          <div class="voice-desc">${escapeHtml(voiceDesc(voiceCatalog, cur))}</div>
        </div>
        <button class="btn ghost save">保存</button>
      `;
      const sel = row.querySelector('select');
      sel.addEventListener('change', () => {
        row.querySelector('.voice-desc').textContent = voiceDesc(voiceCatalog, sel.value);
      });
      row.querySelector('.save').addEventListener('click', async () => {
        try {
          await api(`/api/books/${bookId}/voices`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ character: name, voice: sel.value }),
          });
          toast(`开始重合成「${name}」的台词…`);
          $('#voice-state').hidden = false;
          window.dispatchEvent(new CustomEvent('resynth-start', { detail: { character: name } }));
          closeVoices();
        } catch (e) {
          toast(e.message, true);
        }
      });
      list.appendChild(row);
    });
    $('#voice-modal').classList.remove('hidden');
  } catch (e) {
    toast(e.message, true);
  }
}

function closeVoices() {
  $('#voice-modal').classList.add('hidden');
}

function voiceOptions(catalog, selected) {
  const groups = [
    { label: '男 · 幼年/少年', test: (v) => v.gender === '男' && v.age <= 19 },
    { label: '男 · 青年', test: (v) => v.gender === '男' && v.age > 19 && v.age < 40 },
    { label: '男 · 中老年', test: (v) => v.gender === '男' && v.age >= 40 },
    { label: '女 · 幼年/少女', test: (v) => v.gender === '女' && v.age <= 19 },
    { label: '女 · 青年', test: (v) => v.gender === '女' && v.age > 19 && v.age < 40 },
    { label: '女 · 中老年', test: (v) => v.gender === '女' && v.age >= 40 },
  ];
  let html = '';
  groups.forEach((g) => {
    const items = catalog.filter(g.test);
    if (!items.length) return;
    html += `<optgroup label="${g.label}">`;
    items.forEach((v) => {
      html += `<option value="${escapeHtml(v.voice)}" ${v.voice === selected ? 'selected' : ''}>` +
        `${escapeHtml(v.name)} · ${v.age}岁 · ${escapeHtml(v.trait)}</option>`;
    });
    html += '</optgroup>';
  });
  return html;
}

function voiceDesc(catalog, voice) {
  const v = (catalog || []).find((x) => x.voice === voice);
  return v ? `${v.gender} · ${v.age}岁 · ${v.trait}` : '';
}