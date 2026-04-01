/* ===== RENDERING MODULE ===== */
const Render = {};

/* ---------- AREAS LIST ---------- */
Render.renderAreas = async function () {
  try {
    const all = await db.contacts.toArray();
    const groups = {};

    all.forEach(c => {
      const a = c.area || 'Без области';
      if (!groups[a]) groups[a] = { t: 0, sent: 0, arch: 0, tg: 0, wa: 0, em: 0 };
      groups[a].t++;
      if (c.archived) groups[a].arch++;
      if (hasChannel(c, 'telegram')) groups[a].tg++;
      if (hasChannel(c, 'whatsapp')) groups[a].wa++;
      if (hasChannel(c, 'email')) groups[a].em++;
      const s = parseSt(c.status);
      if (s.includes('тг') || s.includes('wa') || s.includes('почта')) groups[a].sent++;
    });

    const el = document.getElementById('areasList');
    const keys = Object.keys(groups).sort();

    if (!keys.length) {
      el.innerHTML =
        '<div class="fl fl-col ac jc" style="padding:80px 0;color:var(--mut)">' +
        '<i class="ri-map-2-line" style="font-size:48px;margin-bottom:12px"></i>' +
        '<div style="font-size:13px;font-weight:500">Нет областей</div>' +
        '<div style="font-size:11px;margin-top:6px;opacity:.5">Загрузите CSV</div></div>';
      return;
    }

    let h = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px">';
    keys.forEach(a => {
      const d = groups[a];
      const act = d.t - d.arch;
      h += '<div class="area-card">';
      h += '<div class="fl ac jc mb3" style="position:relative">';
      h += '<div class="f1" onclick="State.goArea(\'' + escAttr(a) + '\')" style="cursor:pointer;display:flex;align-items:center;gap:8px">' +
        '<h3 style="font-size:13px;font-weight:700;color:var(--hd)">' + esc(a) + '</h3>' +
        '<i class="ri-arrow-right-s-line" style="font-size:14px;color:var(--mut)"></i></div>';
      h += '<div class="fl ac gap1" style="position:relative">' +
        '<button class="area-btn" onclick="Render.editArea(\'' + escAttr(a) + '\',event)" title="Переименовать"><i class="ri-pencil-line"></i></button>' +
        '<button class="area-btn area-btn-del" onclick="Render.deleteArea(\'' + escAttr(a) + '\',event)" title="Удалить"><i class="ri-delete-bin-line"></i></button>' +
        '</div>';
      h += '</div>';
      h += '<div class="fl gap3" style="font-size:11px;color:var(--mut)">' +
        '<span><b style="color:var(--txt)">' + act + '</b> актив.</span>' +
        '<span><i class="ri-telegram-fill" style="color:#60a5fa"></i> ' + d.tg + '</span>' +
        '<span><i class="ri-whatsapp-fill" style="color:#4ade80"></i> ' + d.wa + '</span></div>';
      h += '<div style="font-size:11px;margin-top:6px;color:var(--mut)">' +
        'Отправлено <b style="color:var(--txt)">' + d.sent + '</b>/' + act +
        (d.arch ? ' · Архив: ' + d.arch : '') + '</div>';
      h += '</div>';
    });
    h += '</div>';
    el.innerHTML = h;
  } catch (err) {
    console.error('renderAreas:', err);
    toast('Ошибка рендера областей', 'err');
  }
};

/* ---------- AREA ACTIONS ---------- */
Render.editArea = async function (oldName, event) {
  event.stopPropagation();
  const newName = prompt('Новое название области:', oldName);
  if (!newName || newName.trim() === oldName) return;
  const trimmed = newName.trim();

  try {
    const contacts = await db.contacts.where('area').equals(oldName).toArray();
    for (const c of contacts) {
      await db.contacts.update(c.id, { area: trimmed });
    }
    toast('Область переименована');
    if (State.currentArea === oldName) State.currentArea = trimmed;
    Render.renderAreas();
    saveToDbDir();
  } catch (err) {
    console.error('editArea:', err);
    toast('Ошибка переименования', 'err');
  }
};

Render.deleteArea = async function (areaName, event) {
  event.stopPropagation();
  const count = await db.contacts.where('area').equals(areaName).count();
  if (!confirm('Удалить область «' + areaName + '» и все ' + count + ' контактов?')) return;

  try {
    const contacts = await db.contacts.where('area').equals(areaName).toArray();
    for (const c of contacts) {
      await db.contacts.delete(c.id);
    }
    toast('Область удалена');
    if (State.currentArea === areaName) State.goAreas();
    else Render.renderAreas();
    saveToDbDir();
  } catch (err) {
    console.error('deleteArea:', err);
    toast('Ошибка удаления', 'err');
  }
};

/* ---------- FIELD TOGGLES ---------- */
Render.renderFieldToggles = function () {
  document.getElementById('fieldToggles').innerHTML = FIELDS.map(f => {
    const off = State.hiddenFields.has(f.k) ? ' off' : '';
    return '<span class="tog' + off + '" onclick="toggleField(\'' + f.k + '\')">' +
      '<i class="' + f.icon + '" style="font-size:11px"></i> ' + esc(f.l) + '</span>';
  }).join('');
};

/* ---------- CHANNEL TABS ---------- */
Render.renderChannelTabs = function () {
  const el = document.getElementById('channelTabs');
  el.innerHTML = CHANNELS.map(ch => {
    const act = State.currentChannel === ch.k ? ' act' : '';
    return '<button class="ch-tab' + act + '" onclick="State.setChannel(\'' + ch.k + '\');Render.renderChecklist()">' +
      '<i class="' + ch.icon + '" style="color:' + ch.color + '"></i> ' + esc(ch.l) +
      '</button>';
  }).join('');
};

/* ---------- CHECKLIST ---------- */
Render.renderChecklist = async function () {
  try {
    const list = await db.contacts.where('area').equals(State.currentArea).toArray();
    const ch = getChannel(State.currentChannel);
    if (!ch) return;

    // Apply search filter
    const filtered = State.searchQuery
      ? list.filter(c =>
          c.name.toLowerCase().includes(State.searchQuery) ||
          (c.city || '').toLowerCase().includes(State.searchQuery) ||
          (c.phone || '').toLowerCase().includes(State.searchQuery))
      : list;

    // Split into sent / unsent
    const unsent = filtered.filter(c => !c[ch.lastField]);
    const sent = filtered.filter(c => !!c[ch.lastField]);
    const total = filtered.length;
    const sentCount = sent.length;

    // Render channel tabs
    Render.renderChannelTabs();

    const board = document.getElementById('checklistContainer');
    let h = '';

    // Progress bar
    h += '<div class="ch-progress-wrap">';
    const pct = total ? Math.round(sentCount / total * 100) : 0;
    h += '<div class="ch-progress"><div class="ch-progress-bar" style="width:' + pct + '%;background:' + ch.color + '"></div></div>';
    h += '<span class="ch-progress-label">' + sentCount + '/' + total + ' (' + pct + '%)</span>';
    h += '</div>';

    // Batch action bar
    h += '<div class="ch-batch-bar">';
    h += '<button class="btn btn-s" onclick="Batch.selectUnsent(window._chkList)"><i class="ri-checkbox-multiple-line"></i> Выбрать неотправл.</button>';
    h += '<button class="btn btn-s" onclick="Batch.selectSent(window._chkList)"><i class="ri-checkbox-multiple-line"></i> Выбрать отправл.</button>';
    if (State.selectedIds.size > 0) {
      h += '<span class="ch-sel-count">' + State.selectedIds.size + ' выбрано</span>';
      h += '<button class="btn btn-s btn-p" onclick="Batch.markSelected()"><i class="ri-check-line"></i> Отметить</button>';
      h += '<button class="btn btn-s" onclick="Batch.undoSelected()"><i class="ri-arrow-go-back-line"></i> Снять</button>';
      h += '<button class="btn btn-s" onclick="State.clearSelection();Render.renderChecklist()"><i class="ri-close-line"></i> Сброс</button>';
    }
    h += '</div>';

    // Unsent section
    h += '<div class="ch-section">';
    h += '<div class="ch-section-head">' +
      '<span class="ch-section-title"><i class="ri-send-plane-2-line" style="color:' + ch.color + '"></i> Не отправлено (' + unsent.length + ')</span>' +
      '</div>';
    h += '<div class="ch-section-body">';
    if (!unsent.length) {
      h += '<div class="ch-empty">Все отправлены!</div>';
    } else {
      unsent.forEach(c => { h += Render.renderCheckRow(c, ch, false); });
    }
    h += '</div></div>';

    // Sent section
    h += '<div class="ch-section">';
    h += '<div class="ch-section-head">' +
      '<span class="ch-section-title"><i class="ri-checkbox-circle-line" style="color:#22c55e"></i> Отправлено (' + sent.length + ')</span>' +
      '</div>';
    h += '<div class="ch-section-body">';
    if (!sent.length) {
      h += '<div class="ch-empty">Пока пусто</div>';
    } else {
      sent.forEach(c => { h += Render.renderCheckRow(c, ch, true); });
    }
    h += '</div></div>';

    board.innerHTML = h;

    // Store list for batch ops
    window._chkList = filtered;

    // Stats footer
    document.getElementById('statsFooter').style.display = 'flex';
    Render.renderStats(filtered);
  } catch (err) {
    console.error('renderChecklist:', err);
    toast('Ошибка рендера чеклиста', 'err');
  }
};

/* ---------- CHECKLIST ROW ---------- */
Render.renderCheckRow = function (c, ch, isSent) {
  const selected = State.selectedIds.has(c.id);
  const expanded = State.expandedId === c.id;
  const selClass = selected ? ' ch-row-sel' : '';
  const expClass = expanded ? ' ch-row-exp' : '';
  const sentClass = isSent ? ' ch-row-sent' : '';

  let h = '<div class="ch-row' + selClass + expClass + sentClass + '">';

  // Checkbox + main info
  h += '<div class="ch-row-main" onclick="State.toggleExpand(\'' + escAttr(c.id) + '\');Render.renderChecklist()">';
  h += '<input type="checkbox" class="ch-cb" ' + (selected ? 'checked' : '') +
    ' onclick="event.stopPropagation();State.toggleSelect(\'' + escAttr(c.id) + '\');Render.renderChecklist()">';

  // Status dot
  const dotColor = c.color_label ? 'var(--' + {red:'cr',yellow:'cy',green:'cg',blue:'cb',gray:'cv'}[c.color_label] + ')' : 'var(--bdr2)';
  h += '<span class="ch-dot" style="background:' + dotColor + '"></span>';

  // Name
  h += '<span class="ch-name">' + esc(c.name || '—') + '</span>';

  // City
  if (c.city) h += '<span class="ch-city">' + esc(c.city) + '</span>';

  // Channel value (phone/email/tg/wa) — link + copy button
  const val = c[ch.field] || '';
  if (val) {
    const displayVal = ch.k === 'email' ? val : val.replace(/^https?:\/\//, '');
    const url = Render.buildUrl(ch.k, val);
    h += '<span class="ch-val">' +
      '<a class="ch-link" href="' + escAttr(url) + '" target="_blank" rel="noopener" onclick="event.stopPropagation()">' + esc(displayVal) + '</a>' +
      '<button class="ch-copy" onclick="event.stopPropagation();Render.copyValue(\'' + escAttr(val) + '\')" title="Копировать"><i class="ri-file-copy-line"></i></button>' +
      '</span>';
  }

  // Date if sent
  if (isSent && c[ch.lastField]) {
    h += '<span class="ch-date">' + fmtDate(c[ch.lastField]) + '</span>';
  }

  // Expand icon
  h += '<i class="ri-arrow-down-s-line ch-expand" style="transform:' + (expanded ? 'rotate(180deg)' : 'rotate(0)') + '"></i>';
  h += '</div>';

  // Expanded detail
  if (expanded) {
    h += Render.renderRowDetail(c, ch);
  }

  h += '</div>';
  return h;
};

/* ---------- URL BUILDER ---------- */
Render.buildUrl = function (channel, value) {
  if (!value) return '';
  switch (channel) {
    case 'phone':    return 'tel:' + value.replace(/[\s\-\(\)]/g, '');
    case 'email':    return 'mailto:' + value;
    case 'website':  return value.startsWith('http') ? value : 'https://' + value;
    case 'telegram': return value.startsWith('http') ? value : 'https://t.me/' + value.replace('@', '');
    case 'whatsapp': return value.startsWith('http') ? value : 'https://wa.me/' + value.replace(/[\s\-\+\(\)]/g, '');
    case 'vk':       return value.startsWith('http') ? value : 'https://vk.com/' + value.replace('@', '');
    default:         return value;
  }
};

/* ---------- COPY TO CLIPBOARD ---------- */
Render.copyValue = function (value) {
  navigator.clipboard.writeText(value).then(() => {
    toast('Скопировано: ' + value);
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = value;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    toast('Скопировано: ' + value);
  });
};

/* ---------- ROW DETAIL (accordion) — VERTICAL LAYOUT ---------- */
Render.renderRowDetail = function (c, ch) {
  let h = '<div class="ch-detail">';

  // Vertical list of fields
  const fieldsToShow = ['name', 'city', 'phone', 'email', 'website', 'address', 'telegram', 'whatsapp', 'vk'];
  const fieldLabels = { name: 'Название', city: 'Город', phone: 'Телефон', email: 'Email', website: 'Сайт', address: 'Адрес', telegram: 'Telegram', whatsapp: 'WhatsApp', vk: 'VK' };
  const fieldIcons = { name: 'ri-building-line', city: 'ri-map-pin-line', phone: 'ri-phone-line', email: 'ri-mail-line', website: 'ri-global-line', address: 'ri-map-pin-2-line', telegram: 'ri-telegram-fill', whatsapp: 'ri-whatsapp-fill', vk: 'ri-brand-vk-fill' };

  fieldsToShow.forEach(fk => {
    const val = c[fk] || '';
    if (!val) return;
    const isLinkable = ['phone', 'email', 'website', 'telegram', 'whatsapp', 'vk'].includes(fk);
    h += '<div class="ch-df-v">';
    h += '<div class="ch-df-v-label"><i class="' + (fieldIcons[fk] || 'ri-information-line') + '"></i>' + esc(fieldLabels[fk] || fk) + '</div>';
    if (isLinkable) {
      const url = Render.buildUrl(fk, val);
      h += '<div class="ch-df-v-row">' +
        '<a class="ch-df-v-val ch-link" href="' + escAttr(url) + '" target="_blank" rel="noopener" onclick="event.stopPropagation()">' + esc(val) + '</a>' +
        '<button class="ch-copy" onclick="event.stopPropagation();Render.copyValue(\'' + escAttr(val) + '\')" title="Копировать"><i class="ri-file-copy-line"></i></button>' +
        '</div>';
    } else {
      h += '<div class="ch-df-v-val">' + esc(val) + '</div>';
    }
    h += '</div>';
  });

  // Note
  if (c.note) {
    h += '<div class="ch-df-v ch-df-v-note">';
    h += '<div class="ch-df-v-label"><i class="ri-sticky-note-line"></i>Заметка</div>';
    h += '<div class="ch-df-v-val">' + esc(c.note) + '</div>';
    h += '</div>';
  }

  // Touch history
  h += '<div class="ch-history">';
  h += '<div class="ch-history-title"><i class="ri-history-line"></i> История касаний</div>';
  const history = Array.isArray(c.touch_history) ? c.touch_history.slice().reverse() : [];
  if (!history.length) {
    h += '<div class="ch-history-empty">Нет касаний</div>';
  } else {
    history.forEach(t => {
      const tCh = getChannel(t.ch);
      const tColor = tCh ? tCh.color : 'var(--mut)';
      const tIcon = tCh ? tCh.icon : 'ri-send-plane-line';
      h += '<div class="ch-history-item">';
      h += '<i class="' + tIcon + '" style="color:' + tColor + '"></i>';
      h += '<span class="ch-history-date">' + fmtDate(t.at) + '</span>';
      if (t.note) {
        h += '<span class="ch-history-note">' + esc(t.note) + '</span>';
      }
      h += '</div>';
    });
  }
  h += '</div>';

  // Quick touch button
  h += '<div class="ch-detail-actions">';
  const isSent = !!c[ch.lastField];
  if (!isSent) {
    h += '<button class="btn btn-s btn-p" onclick="event.stopPropagation();Render.quickTouch(\'' + escAttr(c.id) + '\',\'' + ch.k + '\')"><i class="ri-check-line"></i> Отметить ' + esc(ch.l) + '</button>';
  } else {
    h += '<button class="btn btn-s" onclick="event.stopPropagation();Render.undoQuickTouch(\'' + escAttr(c.id) + '\',\'' + ch.k + '\')"><i class="ri-arrow-go-back-line"></i> Отменить последнее</button>';
  }
  h += '</div>';

  h += '</div>';
  return h;
};

/* ---------- QUICK TOUCH (single contact) ---------- */
Render.quickTouch = async function (id, channel) {
  const note = prompt('Заметка к касанию (необязательно):');
  if (note === null) return;

  await recordTouch(id, channel, (note || '').trim());
  toast('Отмечено');
  await Render.renderChecklist();
  saveToDbDir();
};

Render.undoQuickTouch = async function (id, channel) {
  await undoTouch(id, channel);
  toast('Отменено');
  await Render.renderChecklist();
  saveToDbDir();
};

/* ---------- POPOVER (legacy, for fallback) ---------- */
Render.renderPopover = async function (id, event) {
  try {
    const c = await db.contacts.get(id);
    if (!c) return;

    const sa = parseSt(c.status);
    let h = '';

    h += '<div class="pop-head"><div style="flex:1">' +
      '<div class="pop-name">' + esc(c.name || '—') + '</div>';
    if (c.city) h += '<div class="pop-city"><i class="ri-map-pin-line"></i> ' + esc(c.city) + '</div>';
    h += '</div><button class="pop-close" onclick="State.closePopover()"><i class="ri-close-line"></i></button></div>';

    h += '<div class="pop-sec"><div class="pop-sec-t"><i class="ri-palette-line"></i> Статус</div>' +
      '<div class="pop-colors">';
    const colors = [
      ['red', 'Отказ', 'pcsw-c-red'],
      ['yellow', 'В работе', 'pcsw-c-yellow'],
      ['green', 'Заинтерес.', 'pcsw-c-green'],
      ['blue', 'Без ответа', 'pcsw-c-blue'],
      ['gray', 'Не акт.', 'pcsw-c-gray'],
    ];
    colors.forEach(o => {
      const act = c.color_label === o[0] ? ' act' : '';
      h += '<div class="pcsw ' + o[2] + act + '" onclick="Render.popSetColor(\'' + o[0] + '\')" title="' + o[1] + '">' +
        (c.color_label === o[0] ? '<i class="ri-check-line"></i>' : '') + '</div>';
    });
    h += '<div class="pcsw pcsw-c-none' + (c.color_label ? '' : ' act') + '" ' +
      'onclick="Render.popSetColor(\'\')" title="Снять"><i class="ri-close-line"></i></div>';
    h += '</div></div>';

    h += '<div class="pop-sec"><div class="pop-sec-t"><i class="ri-send-plane-line"></i> Касания</div>' +
      '<div class="pop-sends">';
    ['telegram', 'whatsapp', 'email'].forEach((ch, i) => {
      const label = ['TG', 'WA', 'Почта'][i];
      const icon = ['ri-telegram-fill', 'ri-whatsapp-fill', 'ri-mail-fill'][i];
      const color = ['#60a5fa', '#4ade80', '#fbbf24'][i];
      const tag = ['тг', 'wa', 'почта'][i];
      const available = hasChannel(c, ch);
      const checked = sa.includes(tag) ? 'checked' : '';
      h += '<label class="pop-send' + (available ? '' : ' off') + '">' +
        '<input type="checkbox" ' + checked + ' onchange="Render.popToggleSend(\'' + tag + '\',this.checked)">' +
        '<i class="' + icon + '" style="color:' + color + '"></i> ' + label + '</label>';
    });
    h += '</div></div>';

    h += '<div class="pop-sec"><div class="pop-sec-t"><i class="ri-archive-2-line"></i> Архив</div>' +
      '<div class="pop-arch-row">' +
      '<span style="font-size:12px">' + (c.archived ? 'В архиве' : 'Активный') + '</span>' +
      '<label class="pop-toggle">' +
      '<input type="checkbox" ' + (c.archived ? 'checked' : '') + ' onchange="Render.popToggleArchive(this.checked)">' +
      '<span class="sl"></span></label></div></div>';

    h += '<div class="pop-sec"><div class="pop-sec-t"><i class="ri-sticky-note-line"></i> Заметки</div>' +
      '<textarea class="pop-note" id="popNote" placeholder="Заметка..." ' +
      'onblur="Render.popSaveNote()" ' +
      'oninput="this.style.height=\'auto\';this.style.height=this.scrollHeight+\'px\'">' +
      esc(c.note || '') + '</textarea></div>';

    h += '<div class="pop-sec"><div class="pop-sec-t"><i class="ri-database-2-line"></i> Данные</div>';
    h += '<div class="pop-frow"><div class="pop-flabel"><i class="ri-building-line"></i> Название</div>' +
      '<input class="pop-edit" value="' + escAttr(c.name || '') + '" data-field="name" onblur="Render.popSaveField(this)"></div>';
    h += '<div class="pop-frow"><div class="pop-flabel"><i class="ri-map-pin-line"></i> Город</div>' +
      '<input class="pop-edit" value="' + escAttr(c.city || '') + '" data-field="city" onblur="Render.popSaveField(this)"></div>';

    FIELDS.forEach(f => {
      const val = c[f.k] || '';
      h += '<div class="pop-frow"><div class="pop-flabel"><i class="' + f.icon + '"></i> ' + esc(f.l) + '</div>';
      h += '<input class="pop-edit" value="' + escAttr(val) + '" data-field="' + f.k + '" ' +
        'onblur="Render.popSaveField(this)" ' +
        'onkeydown="if(event.key===\'Enter\'){event.preventDefault();this.blur();}">';
      h += '</div>';
    });
    h += '</div>';

    document.getElementById('popPanel').innerHTML = h;
    document.getElementById('popOv').style.display = 'block';
    document.getElementById('popPanel').style.display = 'block';

    const pp = document.getElementById('popPanel');
    const cardEl = event.target.closest('.kcard');
    if (!cardEl) return;

    const r = cardEl.getBoundingClientRect();
    const ppH = Math.min(window.innerHeight * POPOVER_MAX_H_RATIO, POPOVER_MAX_H);
    let left = r.right + POPOVER_OFFSET;
    let top = r.top;

    if (left + POPOVER_W > window.innerWidth - POPOVER_MIN_EDGE) left = r.left - POPOVER_W - POPOVER_OFFSET;
    if (left < POPOVER_MIN_EDGE) left = POPOVER_MIN_EDGE;
    if (top + ppH > window.innerHeight - POPOVER_MIN_EDGE) top = window.innerHeight - ppH - POPOVER_MIN_EDGE;
    if (top < POPOVER_MIN_EDGE) top = POPOVER_MIN_EDGE;

    pp.style.left = left + 'px';
    pp.style.top = top + 'px';
    pp.style.maxHeight = ppH + 'px';

    setTimeout(() => {
      const ta = document.getElementById('popNote');
      if (ta) { ta.style.height = 'auto'; ta.style.height = ta.scrollHeight + 'px'; }
    }, 50);
  } catch (err) {
    console.error('renderPopover:', err);
    toast('Ошибка открытия карточки', 'err');
  }
};

/* ---------- POPOVER ACTIONS (legacy) ---------- */
Render.popSetColor = async function (label) {
  const id = State.popoverContactId;
  if (!id) return;
  try {
    const upd = { color_label: label || '' };
    if (label) upd.archived = 0;
    await db.contacts.update(id, upd);
    await Render.renderChecklist();
    await State.reopenPopover();
    saveToDbDir();
  } catch (err) {
    console.error('popSetColor:', err);
    toast('Ошибка изменения статуса', 'err');
  }
};

Render.popToggleSend = async function (tag, checked) {
  const id = State.popoverContactId;
  if (!id) return;
  try {
    const c = await db.contacts.get(id);
    if (!c) return;
    let a = parseSt(c.status);
    if (checked) {
      if (!a.includes(tag)) a.push(tag);
    } else {
      a = a.filter(x => x !== tag);
    }
    await db.contacts.update(id, { status: a.join(', ') });
    await Render.renderChecklist();
    saveToDbDir();
  } catch (err) {
    console.error('popToggleSend:', err);
    toast('Ошибка обновления касаний', 'err');
  }
};

Render.popToggleArchive = async function (checked) {
  const id = State.popoverContactId;
  if (!id) return;
  try {
    const upd = { archived: checked ? 1 : 0 };
    if (checked) upd.color_label = '';
    await db.contacts.update(id, upd);
    await Render.renderChecklist();
    saveToDbDir();
    State.closePopover();
    toast(checked ? 'В архиве' : 'Восстановлен');
  } catch (err) {
    console.error('popToggleArchive:', err);
    toast('Ошибка архивации', 'err');
  }
};

Render.popSaveNote = async function () {
  const id = State.popoverContactId;
  if (!id) return;
  const ta = document.getElementById('popNote');
  if (!ta) return;
  try {
    await db.contacts.update(id, { note: ta.value.trim() });
    await Render.renderChecklist();
    saveToDbDir();
  } catch (err) {
    console.error('popSaveNote:', err);
    toast('Ошибка сохранения заметки', 'err');
  }
};

Render.popSaveField = async function (inp) {
  const id = State.popoverContactId;
  if (!id) return;
  const field = inp.getAttribute('data-field');
  if (!field) return;
  try {
    const upd = {};
    upd[field] = (inp.value + '').trim();
    await db.contacts.update(id, upd);
    await Render.renderChecklist();
    saveToDbDir();
  } catch (err) {
    console.error('popSaveField:', err);
    toast('Ошибка сохранения поля', 'err');
  }
};

/* ---------- STATS ---------- */
Render.renderStats = function (list) {
  let wTG = 0, wWA = 0, wEM = 0, sTG = 0, sWA = 0, sEM = 0;

  list.forEach(c => {
    if (hasChannel(c, 'telegram')) wTG++;
    if (hasChannel(c, 'whatsapp')) wWA++;
    if (hasChannel(c, 'email')) wEM++;
    const s = parseSt(c.status);
    if (s.includes('тг')) sTG++;
    if (s.includes('wa')) sWA++;
    if (s.includes('почта')) sEM++;
  });

  const arch = list.filter(c => c.archived).length;

  document.getElementById('statsBar').innerHTML =
    stb(list.length, 'var(--txt)', 'Всего') +
    stb(wTG, '#60a5fa', 'TG') +
    stb(wWA, '#4ade80', 'WA') +
    stb(wEM, '#fbbf24', 'Email') +
    stb(sTG, '#38bdf8', 'ТГ↗') +
    stb(sWA, '#22c55e', 'WA↗') +
    stb(sEM, '#f59e0b', 'Почта↗') +
    stb(arch, 'var(--acc)', 'Архив');
};
