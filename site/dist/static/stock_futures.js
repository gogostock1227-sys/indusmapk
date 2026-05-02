(function () {
  const payload = window.STOCK_FUTURES_PAYLOAD || {};
  function normalizeProduct(row, idx) {
    const id = row.product_id || row.product_code || `${row.underlying_symbol || 'SF'}-${idx}`;
    return Object.assign({}, row, { product_id: id });
  }
  const rankingProducts = (payload.rows || []).map(normalizeProduct);
  const products = ((payload.selectable_products && payload.selectable_products.length ? payload.selectable_products : payload.rows) || []).map(normalizeProduct);
  const byId = new Map(products.map((row) => [row.product_id, row]));
  const topicsBySymbol = payload.company_topics || {};
  const conceptTopicSet = new Set(payload.concept_topics || []);
  const marketIndices = payload.market_indices || {};

  // 取主族群：優先非概念股題材，全是概念股時才退而求其次
  function pickPrimaryTopic(symbol) {
    const list = topicsBySymbol[symbol];
    if (!list || !list.length) return '未分類';
    const real = list.find((t) => !conceptTopicSet.has(t));
    return real || list[0];
  }

  const storeKey = 'indusmap.stockFutures.positions.v2';
  const legacyStoreKey = 'indusmap.stockFutures.positions.v1';
  const snapshotsKey = 'indusmap.stockFutures.snapshots.v1';
  const equityKey = 'indusmap.stockFutures.accountEquity.v1';
  const portfolioMetricKey = 'indusmap.stockFutures.portfolioMetric.v1';

  const T = {
    bg: '#f6f3ec', bgAlt: '#ffffff', ink: '#15181d', inkSoft: '#3b4250',
    muted: '#8b909a', border: '#e5dfd2',
    up: '#d6263c', down: '#16a070', navy: '#1d3557', gold: '#c89b3c',
    series: ['#1d3557', '#d6263c', '#16a070', '#c89b3c', '#8b6cb1', '#3b7bbf', '#d97757', '#0891b2'],
  };

  const METRIC_LABELS = {
    notional: { label: '名目曝險', short: 'NOTIONAL', color: T.navy },
    margin: { label: '保證金', short: 'MARGIN', color: T.gold },
    lots: { label: '口數', short: 'LOTS', color: T.up },
  };

  const TREND_METRICS = [
    { key: 'marginLeverage',  label: '保證金槓桿', fmt: (v) => v.toFixed(2) + 'x', get: (s) => num(s.summary.marginLeverage) },
    { key: 'equityLeverage',  label: '權益槓桿',   fmt: (v) => v.toFixed(2) + 'x', get: (s) => num(s.summary.equityLeverage) },
    { key: 'unrealizedPnl',   label: '未實現損益', fmt: (v) => money(v),           get: (s) => num(s.summary.unrealizedPnl) },
    { key: 'accountEquity',   label: '帳戶權益數', fmt: (v) => money(v),           get: (s) => num(s.accountEquity) },
    { key: 'grossExposure',   label: '總曝險',      fmt: (v) => money(v),           get: (s) => num(s.summary.grossExposure) },
    { key: 'netExposure',     label: '淨曝險',      fmt: (v) => money(v),           get: (s) => num(s.summary.netExposure) },
    { key: 'totalMargin',     label: '總保證金',    fmt: (v) => money(v),           get: (s) => num(s.summary.totalMargin) },
  ];
  const trendMetricKey = 'indusmap.stockFutures.trendMetrics.v1';
  let activeTrendMetrics = (() => {
    try { return new Set(JSON.parse(localStorage.getItem(trendMetricKey)) || ['marginLeverage']); }
    catch { return new Set(['marginLeverage']); }
  })();

  let portfolioMetric = (function () {
    const saved = (() => { try { return localStorage.getItem(portfolioMetricKey); } catch { return null; } })();
    return saved && METRIC_LABELS[saved] ? saved : 'notional';
  })();

  const colors = ['#2563eb', '#d97706', '#059669', '#dc2626', '#7c3aed', '#0891b2', '#be123c', '#4d7c0f'];
  const $ = (id) => document.getElementById(id);
  const tabs = document.querySelectorAll('#sf-tabs .filter-chip');
  const bodies = document.querySelectorAll('.sf-tab-body');

  let selectedProductId = products[0] ? products[0].product_id : null;
  let positions = loadPositions();
  let snapshots = loadSnapshots();
  let rankSort = { key: 'volume', dir: -1 };
  let currentSummary = null;

  function esc(value) {
    return String(value == null ? '' : value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function num(value) {
    if (value === '' || value == null) return null;
    const text = String(value).replaceAll(',', '').replace('%', '').trim();
    if (!text) return null;
    const n = Number(text);
    return Number.isFinite(n) ? n : null;
  }

  function importNum(value) {
    const raw = String(value == null ? '' : value).trim();
    const n = num(raw);
    if (n == null) return null;
    return raw.includes('%') ? n / 100 : n;
  }

  function money(value) {
    const n = num(value);
    return n == null ? '—' : Math.round(n).toLocaleString('zh-TW');
  }

  function price(value) {
    const n = num(value);
    if (n == null) return '—';
    return n >= 1000
      ? n.toLocaleString('zh-TW', { maximumFractionDigits: 0 })
      : n.toLocaleString('zh-TW', { maximumFractionDigits: 2 });
  }

  function pct(value) {
    const n = num(value);
    if (n == null) return '—';
    return `${n >= 0 ? '+' : ''}${(n * 100).toFixed(2)}%`;
  }

  function plainPct(value) {
    const n = num(value);
    return n == null ? '—' : `${(n * 100).toFixed(2)}%`;
  }

  function leverage(value) {
    const n = num(value);
    return n == null ? '—' : `${n.toFixed(2)}x`;
  }

  function signed(value, formatter) {
    const n = num(value);
    if (n == null) return '<span class="muted">—</span>';
    const cls = n > 0 ? 'positive' : n < 0 ? 'negative' : 'muted';
    const text = formatter ? formatter(n) : `${n >= 0 ? '+' : ''}${money(n)}`;
    return `<span class="${cls}">${text}</span>`;
  }

  function lots(value) {
    const n = num(value);
    return n == null ? null : Math.max(0, Math.floor(Math.abs(n)));
  }

  function todayIso() {
    const d = new Date();
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  }

  function normalizePosition(pos) {
    return {
      id: String(pos.id || `${Date.now()}-${Math.random().toString(16).slice(2)}`),
      productId: String(pos.productId || pos.product_id || ''),
      direction: pos.direction === 'short' ? 'short' : 'long',
      targetExposure: num(pos.targetExposure) == null ? null : num(pos.targetExposure),
      manualLots: lots(pos.manualLots),
      holdingPrice: num(pos.holdingPrice),
      note: String(pos.note || ''),
      updatedAt: pos.updatedAt || new Date().toISOString(),
    };
  }

  function loadPositions() {
    try {
      const raw = JSON.parse(localStorage.getItem(storeKey) || '[]');
      if (Array.isArray(raw)) return raw.map(normalizePosition).filter((p) => byId.has(p.productId));
    } catch {
      // 讀不到新版時嘗試舊版。
    }
    try {
      const legacy = JSON.parse(localStorage.getItem(legacyStoreKey) || '[]');
      if (Array.isArray(legacy)) {
        const migrated = legacy.map(normalizePosition).filter((p) => byId.has(p.productId));
        if (migrated.length) localStorage.setItem(storeKey, JSON.stringify(migrated));
        return migrated;
      }
    } catch {
      return [];
    }
    return [];
  }

  function savePositions() {
    localStorage.setItem(storeKey, JSON.stringify(positions));
  }

  function normalizeSnapshot(snap) {
    const summary = snap.summary || {};
    return {
      version: 1,
      date: String(snap.date || todayIso()).slice(0, 10),
      savedAt: snap.savedAt || new Date().toISOString(),
      source: snap.source || 'manual',
      priceMode: snap.priceMode === 'historic' ? 'historic' : 'current',
      accountEquity: num(snap.accountEquity),
      summary: {
        totalLong: num(summary.totalLong) || 0,
        totalShort: num(summary.totalShort) || 0,
        grossExposure: num(summary.grossExposure) || 0,
        netExposure: num(summary.netExposure) || 0,
        totalMargin: num(summary.totalMargin) || 0,
        marginUsage: num(summary.marginUsage),
        marginLeverage: num(summary.marginLeverage),
        equityLeverage: num(summary.equityLeverage),
        onePctPnl: num(summary.onePctPnl) || 0,
        positionCount: num(summary.positionCount) || 0,
        unrealizedPnl: num(summary.unrealizedPnl),
        unrealizedPnlPct: num(summary.unrealizedPnlPct),
      },
      positions: Array.isArray(snap.positions) ? snap.positions.map(normalizePosition) : [],
      positionMetrics: Array.isArray(snap.positionMetrics) ? snap.positionMetrics : [],
      marketIndices: snap.marketIndices || {},
    };
  }

  function loadSnapshots() {
    try {
      const raw = JSON.parse(localStorage.getItem(snapshotsKey) || '[]');
      return Array.isArray(raw) ? raw.map(normalizeSnapshot).sort((a, b) => a.date.localeCompare(b.date)) : [];
    } catch {
      return [];
    }
  }

  function saveSnapshots() {
    localStorage.setItem(snapshotsKey, JSON.stringify(snapshots));
  }

  function setStatus(message) {
    const el = $('sf-storage-status');
    if (el) el.textContent = message || '本機保存';
  }

  function productMatches(query) {
    const q = String(query || '').trim().toLowerCase();
    if (!q) return products.slice(0, 8);
    const terms = q.split(/\s+/).filter(Boolean);
    return products.filter((row) => {
      const key = `${row.search_key || ''} ${row.product_id || ''}`.toLowerCase();
      return terms.every((term) => key.includes(term));
    }).slice(0, 12);
  }

  function renderMatches() {
    const box = $('sf-product-matches');
    const input = $('sf-product-query');
    if (!box || !input) return;
    const matches = productMatches(input.value);
    if (!matches.length) {
      box.innerHTML = '<span class="muted">找不到符合的股票期貨商品</span>';
      selectedProductId = null;
      return;
    }
    if (!matches.some((row) => row.product_id === selectedProductId)) selectedProductId = matches[0].product_id;
    box.innerHTML = matches.map((row) => `
      <button type="button" class="sf-match ${row.product_id === selectedProductId ? 'active' : ''}" data-id="${esc(row.product_id)}">
        <strong>${esc(row.product_name)}</strong>
        <small>${esc(row.underlying_symbol)}${row.product_code ? ' · ' + esc(row.product_code) : ''} · ${esc(row.type_label || '')}</small>
      </button>
    `).join('');
    box.querySelectorAll('.sf-match').forEach((btn) => {
      btn.addEventListener('click', () => {
        selectedProductId = btn.dataset.id;
        const row = byId.get(selectedProductId);
        if (row) input.value = `${row.underlying_symbol} ${row.product_name}${row.product_code ? ' ' + row.product_code : ''}`;
        renderMatches();
      });
    });
  }

  function calcPosition(pos, opts) {
    const product = byId.get(pos.productId);
    if (!product) return null;
    const overridePrice = opts && opts.priceOverride;
    const hasOverride = overridePrice != null && Number.isFinite(overridePrice);
    const futurePrice = hasOverride ? overridePrice : num(product.future_price);
    const multiplier = num(product.contract_multiplier) || 0;
    // 有 override 時必須重算 notional（product.notional 是站台 build 時用最新價預算好的，會失真）
    const notional = hasOverride
      ? (futurePrice || 0) * multiplier
      : (num(product.notional) || ((futurePrice || 0) * multiplier));
    const margin = num(product.initial_margin) || 0;
    const target = num(pos.targetExposure);
    const manual = lots(pos.manualLots);
    const suggested = target == null || notional <= 0 ? 0 : Math.floor(Math.abs(target) / notional);
    const used = manual != null ? manual : suggested;
    const gross = used * notional;
    const signedExposure = pos.direction === 'short' ? -gross : gross;
    const cost = num(pos.holdingPrice);
    const sideSign = pos.direction === 'short' ? -1 : 1;
    const unrealizedPnl = (cost == null || futurePrice == null || !used)
      ? null
      : (futurePrice - cost) * multiplier * used * sideSign;
    const costBasis = (cost == null || !used) ? null : cost * multiplier * used;
    const unrealizedPnlPct = (unrealizedPnl == null || !costBasis) ? null : unrealizedPnl / Math.abs(costBasis);
    return {
      position: pos,
      product,
      target,
      manual,
      suggested,
      used,
      totalMargin: used * margin,
      grossExposure: gross,
      netExposure: signedExposure,
      singleLeverage: margin ? notional / margin : null,
      onePctPnl: signedExposure * 0.01,
      holdingPrice: cost,
      futurePrice,
      multiplier,
      unrealizedPnl,
      unrealizedPnlPct,
      costBasis,
    };
  }

  function computeSummary(opts) {
    const overrides = (opts && opts.priceOverrides) || null;
    const details = positions.map((pos) => calcPosition(pos, {
      priceOverride: overrides ? overrides[pos.productId] : null,
    })).filter(Boolean);
    let totalLong = 0;
    let totalShort = 0;
    let totalMargin = 0;
    let net = 0;
    let onePct = 0;
    let unrealizedPnl = 0;
    let costBasisTotal = 0;
    let pnlCount = 0;
    details.forEach((c) => {
      if (c.netExposure >= 0) totalLong += c.netExposure;
      else totalShort += Math.abs(c.netExposure);
      totalMargin += c.totalMargin;
      net += c.netExposure;
      onePct += c.onePctPnl;
      if (c.unrealizedPnl != null) {
        unrealizedPnl += c.unrealizedPnl;
        pnlCount += 1;
      }
      if (c.costBasis != null) costBasisTotal += Math.abs(c.costBasis);
    });
    const gross = totalLong + totalShort;
    const equity = num($('sf-account-equity') && $('sf-account-equity').value);
    return {
      details,
      totalLong,
      totalShort,
      grossExposure: gross,
      netExposure: net,
      totalMargin,
      marginUsage: equity && totalMargin ? totalMargin / equity : null,
      marginLeverage: totalMargin ? gross / totalMargin : null,
      equityLeverage: equity ? gross / equity : null,
      onePctPnl: onePct,
      accountEquity: equity,
      positionCount: positions.length,
      unrealizedPnl: pnlCount ? unrealizedPnl : null,
      unrealizedPnlPct: pnlCount && costBasisTotal ? unrealizedPnl / costBasisTotal : null,
      pnlCoverage: pnlCount,
    };
  }

  function renderPositions() {
    const tbody = document.querySelector('#sf-position-table tbody');
    if (!tbody) return;
    const summary = computeSummary();
    currentSummary = summary;
    const rows = summary.details.map((c) => {
      const pos = c.position;
      return `
        <tr data-pos-row="${esc(pos.id)}">
          <td><strong>${esc(c.product.product_name)}</strong><small>${esc(c.product.underlying_symbol)} ${esc(c.product.product_code || '')}</small></td>
          <td>
            <select class="sf-inline-control" data-edit-id="${esc(pos.id)}" data-field="direction">
              <option value="long"${pos.direction === 'long' ? ' selected' : ''}>買進(多)</option>
              <option value="short"${pos.direction === 'short' ? ' selected' : ''}>賣出(空)</option>
            </select>
          </td>
          <td><input class="sf-inline-control sf-inline-number" type="number" step="1000" value="${pos.targetExposure == null ? '' : esc(pos.targetExposure)}" data-edit-id="${esc(pos.id)}" data-field="targetExposure"></td>
          <td><input class="sf-inline-control sf-inline-number" type="number" min="0" step="1" value="${pos.manualLots == null ? '' : esc(pos.manualLots)}" data-edit-id="${esc(pos.id)}" data-field="manualLots"></td>
          <td data-cell="suggested">${money(c.suggested)}</td>
          <td data-cell="used"><strong>${money(c.used)}</strong></td>
          <td data-cell="futurePrice">${price(c.product.future_price)}</td>
          <td><input class="sf-inline-control sf-inline-number" inputmode="decimal" type="text" pattern="[0-9]*\\.?[0-9]*" value="${pos.holdingPrice == null ? '' : esc(pos.holdingPrice)}" data-edit-id="${esc(pos.id)}" data-field="holdingPrice"></td>
          <td data-cell="unrealizedPnl">${c.unrealizedPnl == null ? '<span class="muted">—</span>' : signed(c.unrealizedPnl, money)}</td>
          <td data-cell="unrealizedPnlPct">${c.unrealizedPnlPct == null ? '<span class="muted">—</span>' : signed(c.unrealizedPnlPct, pct)}</td>
          <td data-cell="contractMultiplier">${money(c.product.contract_multiplier)}</td>
          <td data-cell="initialMargin">${money(c.product.initial_margin)}</td>
          <td data-cell="totalMargin">${money(c.totalMargin)}</td>
          <td data-cell="grossExposure">${money(c.grossExposure)}</td>
          <td data-cell="netExposure">${signed(c.netExposure, money)}</td>
          <td data-cell="singleLeverage">${leverage(c.singleLeverage)}</td>
          <td data-cell="onePctPnl">${signed(c.onePctPnl, money)}</td>
          <td data-cell="volume">${money(c.product.volume)}</td>
          <td data-cell="openInterest">${money(c.product.open_interest)}</td>
          <td data-cell="dataTime">${esc(c.product.data_time || payload.as_of || '')}</td>
          <td><input class="sf-inline-control sf-note-input" type="text" value="${esc(pos.note || '')}" data-edit-id="${esc(pos.id)}" data-field="note"></td>
          <td><button type="button" class="sf-row-btn" data-remove="${esc(pos.id)}">刪除</button></td>
        </tr>`;
    }).join('');
    tbody.innerHTML = rows || '<tr><td colspan="22" class="muted">尚未建立部位</td></tr>';

    tbody.querySelectorAll('[data-remove]').forEach((btn) => {
      btn.addEventListener('click', () => {
        positions = positions.filter((pos) => pos.id !== btn.dataset.remove);
        savePositions();
        renderPositions();
      });
    });
    tbody.querySelectorAll('[data-edit-id][data-field]').forEach((el) => {
      const eventName = el.tagName === 'SELECT' ? 'change' : 'input';
      el.addEventListener(eventName, () => editPosition(el));
    });

    refreshSummaryKpis(summary);
    renderPortfolio();
  }

  // 表格行內的「下游 read-only 單元格」surgical refresh — 不動 input，避免 caret 重置
  function refreshPositionRow(rowEl, c) {
    if (!rowEl || !c) return;
    const set = (key, html, useInner) => {
      const td = rowEl.querySelector(`[data-cell="${key}"]`);
      if (!td) return;
      if (useInner) td.innerHTML = html; else td.textContent = html;
    };
    set('suggested', money(c.suggested));
    const usedEl = rowEl.querySelector('[data-cell="used"]');
    if (usedEl) usedEl.innerHTML = `<strong>${money(c.used)}</strong>`;
    set('futurePrice', price(c.product.future_price));
    set('unrealizedPnl', c.unrealizedPnl == null ? '<span class="muted">—</span>' : signed(c.unrealizedPnl, money), true);
    set('unrealizedPnlPct', c.unrealizedPnlPct == null ? '<span class="muted">—</span>' : signed(c.unrealizedPnlPct, pct), true);
    set('contractMultiplier', money(c.product.contract_multiplier));
    set('initialMargin', money(c.product.initial_margin));
    set('totalMargin', money(c.totalMargin));
    set('grossExposure', money(c.grossExposure));
    set('netExposure', signed(c.netExposure, money), true);
    set('singleLeverage', leverage(c.singleLeverage));
    set('onePctPnl', signed(c.onePctPnl, money), true);
  }

  function refreshSummaryKpis(summary) {
    const s = summary || computeSummary();
    currentSummary = s;
    if ($('sf-position-count')) $('sf-position-count').textContent = `${positions.length} 筆`;
    if ($('sf-total-long')) $('sf-total-long').textContent = money(s.totalLong);
    if ($('sf-total-short')) $('sf-total-short').textContent = money(s.totalShort);
    if ($('sf-gross-exposure')) $('sf-gross-exposure').textContent = money(s.grossExposure);
    if ($('sf-net-exposure')) $('sf-net-exposure').innerHTML = signed(s.netExposure, money);
    if ($('sf-total-margin')) $('sf-total-margin').textContent = money(s.totalMargin);
    if ($('sf-margin-usage')) $('sf-margin-usage').textContent = s.marginUsage == null ? '—' : plainPct(s.marginUsage);
    if ($('sf-margin-leverage')) $('sf-margin-leverage').textContent = leverage(s.marginLeverage);
    if ($('sf-equity-leverage')) $('sf-equity-leverage').textContent = leverage(s.equityLeverage);
    if ($('sf-onepct-pnl')) $('sf-onepct-pnl').innerHTML = signed(s.onePctPnl, money);
  }

  function editPosition(el) {
    const id = el.dataset.editId;
    const field = el.dataset.field;
    const pos = positions.find((item) => item.id === id);
    if (!pos) return;
    if (field === 'direction') pos.direction = el.value === 'short' ? 'short' : 'long';
    if (field === 'targetExposure') pos.targetExposure = num(el.value);
    if (field === 'manualLots') pos.manualLots = lots(el.value);
    if (field === 'holdingPrice') pos.holdingPrice = num(el.value);
    if (field === 'note') pos.note = el.value;
    pos.updatedAt = new Date().toISOString();
    savePositions();
    // ⚠️ 不重建 tbody — 改成「外科手術式」更新該 row 的 read-only 單元格 + 上方 KPI
    const rowEl = el.closest('[data-pos-row]');
    const c = calcPosition(pos);
    if (rowEl && c) refreshPositionRow(rowEl, c);
    refreshSummaryKpis();
    // Portfolio tab 仍要 refresh，但只在它可見時做（避免無謂計算 + 動畫）
    const portfolioBody = document.querySelector('[data-body="portfolio"]');
    if (portfolioBody && !portfolioBody.hidden) renderPortfolio();
  }

  function addPosition() {
    const product = byId.get(selectedProductId);
    if (!product) {
      setStatus('請先選擇商品');
      return;
    }
    const manualValue = $('sf-manual-lots').value;
    const targetValue = $('sf-target-exposure').value;
    const holdingValue = $('sf-holding-price') && $('sf-holding-price').value;
    positions.push({
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      productId: product.product_id,
      direction: $('sf-direction').value === 'short' ? 'short' : 'long',
      targetExposure: targetValue === '' ? null : Number(targetValue),
      manualLots: manualValue === '' ? null : lots(manualValue),
      holdingPrice: holdingValue == null || holdingValue === '' ? null : num(holdingValue),
      note: $('sf-note').value.trim(),
      updatedAt: new Date().toISOString(),
    });
    savePositions();
    renderPositions();
    $('sf-note').value = '';
    if ($('sf-holding-price')) $('sf-holding-price').value = '';
    setStatus('部位已加入');
  }

  function indexForDate(date) {
    const history = Array.isArray(marketIndices.history) ? marketIndices.history : [];
    const exactOrBefore = history.filter((row) => row.date && row.date <= date).slice(-1)[0];
    const current = marketIndices.current || {};
    return {
      date: exactOrBefore ? exactOrBefore.date : (current.taiex && current.taiex.date) || payload.as_of || date,
      taiex: num(exactOrBefore && exactOrBefore.taiex) ?? num(current.taiex && current.taiex.value),
      tpex: num(exactOrBefore && exactOrBefore.tpex) ?? num(current.tpex && current.tpex.value),
    };
  }

  function makeSnapshot(date, source, overrides) {
    const summary = computeSummary({ priceOverrides: overrides });
    const hasOverrides = !!(overrides && Object.keys(overrides).some((k) => Number.isFinite(num(overrides[k]))));
    return normalizeSnapshot({
      version: 1,
      date,
      savedAt: new Date().toISOString(),
      source: source || 'manual',
      priceMode: hasOverrides ? 'historic' : 'current',
      accountEquity: summary.accountEquity,
      summary: {
        totalLong: summary.totalLong,
        totalShort: summary.totalShort,
        grossExposure: summary.grossExposure,
        netExposure: summary.netExposure,
        totalMargin: summary.totalMargin,
        marginUsage: summary.marginUsage,
        marginLeverage: summary.marginLeverage,
        equityLeverage: summary.equityLeverage,
        onePctPnl: summary.onePctPnl,
        positionCount: positions.length,
        unrealizedPnl: summary.unrealizedPnl,
        unrealizedPnlPct: summary.unrealizedPnlPct,
      },
      positions: positions.map((pos) => Object.assign({}, pos)),
      positionMetrics: summary.details.map((c) => ({
        productId: c.product.product_id,
        productName: c.product.product_name,
        underlyingSymbol: c.product.underlying_symbol,
        underlyingName: c.product.underlying_short_name || c.product.underlying_name || c.product.underlying_symbol,
        direction: c.position.direction,
        lots: c.used,
        futurePrice: c.futurePrice,
        initialMargin: num(c.product.initial_margin),
        contractMultiplier: num(c.product.contract_multiplier),
        grossExposure: c.grossExposure,
        netExposure: c.netExposure,
        totalMargin: c.totalMargin,
        holdingPrice: c.holdingPrice,
        unrealizedPnl: c.unrealizedPnl,
        unrealizedPnlPct: c.unrealizedPnlPct,
      })),
      marketIndices: indexForDate(date),
    });
  }

  function upsertSnapshot(snapshot) {
    snapshots = snapshots.filter((item) => item.date !== snapshot.date);
    snapshots.push(snapshot);
    snapshots.sort((a, b) => a.date.localeCompare(b.date));
    saveSnapshots();
    renderPortfolio();
  }

  function saveSnapshotForDate(date, label, overrides) {
    if (!date) {
      setStatus('請先選擇快照日期');
      return;
    }
    const existed = snapshots.some((item) => item.date === date);
    upsertSnapshot(makeSnapshot(date, label || 'manual', overrides));
    const tag = overrides && Object.keys(overrides).length ? '（歷史價）' : '';
    setStatus(`${date} 快照已${existed ? '覆蓋' : '新增'}${tag}`);
  }

  // ===========================================================
  // 歷史價格補登面板 — 解決 backfill 用今天價的失真問題
  // ===========================================================

  function openHistoricPanel() {
    const date = $('sf-backfill-date') && $('sf-backfill-date').value;
    if (!date) {
      setStatus('請先選擇補登日期');
      return;
    }
    if (!positions.length) {
      setStatus('沒有持倉可補登，請先新增部位');
      return;
    }
    const panel = $('sf-historic-panel');
    if (!panel) return;
    panel.hidden = false;
    const dateEl = $('sf-historic-date');
    if (dateEl) dateEl.textContent = date;
    renderHistoricPanelTable();
  }

  function closeHistoricPanel() {
    const panel = $('sf-historic-panel');
    if (panel) panel.hidden = true;
  }

  function renderHistoricPanelTable() {
    const tbody = document.querySelector('#sf-historic-price-table tbody');
    if (!tbody) return;
    const summary = computeSummary();
    tbody.innerHTML = summary.details.map((c) => {
      const pos = c.position;
      const currentPrice = num(c.product.future_price);
      return `
        <tr data-historic-row data-product-id="${esc(pos.productId)}">
          <td><strong>${esc(c.product.product_name)}</strong><small>${esc(c.product.underlying_symbol)} ${esc(c.product.product_code || '')}</small></td>
          <td>${pos.direction === 'short' ? '賣出(空)' : '買進(多)'}</td>
          <td>${money(c.used)}</td>
          <td>${price(currentPrice)}</td>
          <td>${pos.holdingPrice == null ? '<span class="muted">—</span>' : price(pos.holdingPrice)}</td>
          <td><input class="sf-inline-control sf-inline-number" type="number" min="0" step="0.01" data-historic-price="${esc(pos.productId)}" placeholder="${currentPrice == null ? '0' : currentPrice}"></td>
          <td data-historic-gross>${money(c.grossExposure)}</td>
          <td data-historic-pnl>${c.unrealizedPnl == null ? '<span class="muted">—</span>' : signed(c.unrealizedPnl, money)}</td>
        </tr>`;
    }).join('') || '<tr><td colspan="8" class="muted">尚未持倉</td></tr>';
    tbody.querySelectorAll('input[data-historic-price]').forEach((input) => {
      input.addEventListener('input', updateHistoricRowPreview);
    });
  }

  function updateHistoricRowPreview(ev) {
    const input = ev.target;
    const row = input.closest('[data-historic-row]');
    if (!row) return;
    const productId = row.dataset.productId;
    const pos = positions.find((p) => p.productId === productId);
    if (!pos) return;
    const overridePrice = num(input.value);
    const c = calcPosition(pos, { priceOverride: overridePrice });
    if (!c) return;
    const grossEl = row.querySelector('[data-historic-gross]');
    const pnlEl = row.querySelector('[data-historic-pnl]');
    if (grossEl) grossEl.textContent = money(c.grossExposure);
    if (pnlEl) pnlEl.innerHTML = c.unrealizedPnl == null ? '<span class="muted">—</span>' : signed(c.unrealizedPnl, money);
  }

  function collectHistoricOverrides() {
    const overrides = {};
    document.querySelectorAll('#sf-historic-price-table input[data-historic-price]').forEach((input) => {
      const productId = input.dataset.historicPrice;
      const v = num(input.value);
      if (productId && Number.isFinite(v) && v > 0) {
        overrides[productId] = v;
      }
    });
    return overrides;
  }

  function saveHistoricSnapshot() {
    const date = $('sf-backfill-date') && $('sf-backfill-date').value;
    if (!date) {
      setStatus('請先選擇補登日期');
      return;
    }
    const overrides = collectHistoricOverrides();
    const filledCount = Object.keys(overrides).length;
    if (filledCount === 0) {
      setStatus('請至少填入一個商品的歷史價，或直接按「舊日期新增/覆蓋」用今天價');
      return;
    }
    saveSnapshotForDate(date, 'manual-historic', overrides);
    closeHistoricPanel();
    if (typeof renderPortfolio === 'function') renderPortfolio();
  }

  // ===========================================================
  // 一鍵以 FinLab 歷史價修正所有快照
  // ===========================================================

  const futuresHistory = payload.futures_history || {};

  function lookupHistoricPrice(productId, date) {
    const m = futuresHistory[productId];
    if (!m) return null;
    const v = num(m[date]);
    return Number.isFinite(v) && v > 0 ? v : null;
  }

  function previewHistoricCorrections() {
    const corrections = [];
    const missing = [];
    snapshots.forEach((snap) => {
      (snap.positionMetrics || []).forEach((m) => {
        if (!m || !m.productId) return;
        const newP = lookupHistoricPrice(m.productId, snap.date);
        if (newP == null) {
          missing.push({ snapDate: snap.date, productId: m.productId, productName: m.productName || '' });
          return;
        }
        const oldP = num(m.futurePrice);
        if (oldP != null && Math.abs(newP - oldP) < 0.001) return; // 已對齊
        corrections.push({
          snapDate: snap.date,
          productId: m.productId,
          productName: m.productName || m.productId,
          oldPrice: oldP,
          newPrice: newP,
          diffPct: oldP ? ((newP - oldP) / oldP) * 100 : null,
        });
      });
    });
    return { corrections, missing };
  }

  function recomputeSummaryFromMetrics(snap) {
    let totalLong = 0, totalShort = 0, totalMargin = 0, net = 0;
    let unreal = 0, costBasis = 0, pnlCount = 0;
    (snap.positionMetrics || []).forEach((m) => {
      const exp = num(m.netExposure) || 0;
      if (exp >= 0) totalLong += exp; else totalShort += Math.abs(exp);
      totalMargin += num(m.totalMargin) || 0;
      net += exp;
      const pnl = num(m.unrealizedPnl);
      if (pnl != null) {
        unreal += pnl;
        pnlCount += 1;
        const cost = num(m.holdingPrice);
        const mult = num(m.contractMultiplier) || 0;
        const lt = num(m.lots) || 0;
        if (cost != null && mult && lt) costBasis += Math.abs(cost * mult * lt);
      }
    });
    const gross = totalLong + totalShort;
    if (!snap.summary) snap.summary = {};
    Object.assign(snap.summary, {
      totalLong, totalShort, grossExposure: gross, netExposure: net, totalMargin,
      marginUsage: snap.accountEquity && totalMargin ? totalMargin / snap.accountEquity : null,
      marginLeverage: totalMargin ? gross / totalMargin : null,
      equityLeverage: snap.accountEquity ? gross / snap.accountEquity : null,
      onePctPnl: net * 0.01,
      unrealizedPnl: pnlCount ? unreal : null,
      unrealizedPnlPct: pnlCount && costBasis ? unreal / costBasis : null,
    });
  }

  function applyHistoricCorrections(corrections) {
    const byDate = new Map();
    corrections.forEach((c) => {
      if (!byDate.has(c.snapDate)) byDate.set(c.snapDate, []);
      byDate.get(c.snapDate).push(c);
    });
    let mutatedSnapshots = 0;
    let mutatedMetrics = 0;
    byDate.forEach((list, snapDate) => {
      const snap = snapshots.find((s) => s.date === snapDate);
      if (!snap) return;
      list.forEach((c) => {
        const m = (snap.positionMetrics || []).find((mm) => mm.productId === c.productId);
        if (!m) return;
        const mult = num(m.contractMultiplier) || 0;
        const lots = num(m.lots) || 0;
        const sideSign = m.direction === 'short' ? -1 : 1;
        const cost = num(m.holdingPrice);
        m.futurePrice = c.newPrice;
        m.grossExposure = c.newPrice * mult * lots;
        m.netExposure = sideSign * m.grossExposure;
        if (cost != null && lots) {
          m.unrealizedPnl = (c.newPrice - cost) * mult * lots * sideSign;
          const basis = Math.abs(cost * mult * lots);
          m.unrealizedPnlPct = basis ? m.unrealizedPnl / basis : null;
        }
        mutatedMetrics += 1;
      });
      recomputeSummaryFromMetrics(snap);
      snap.priceMode = 'historic';
      snap.savedAt = new Date().toISOString();
      mutatedSnapshots += 1;
    });
    saveSnapshots();
    return { mutatedSnapshots, mutatedMetrics };
  }

  function showHistoricCorrectModal() {
    if (!snapshots.length) {
      setStatus('尚無歷史明細可修正');
      return;
    }
    if (Object.keys(futuresHistory).length === 0) {
      setStatus('FinLab 歷史價資料未載入（請重新 build site，確認 .cache_stock_futures_finlab_history.json 存在）');
      return;
    }
    const { corrections, missing } = previewHistoricCorrections();
    if (corrections.length === 0) {
      setStatus(missing.length
        ? `所有快照已對齊歷史價（${missing.length} 筆找不到 FinLab 資料）`
        : '所有快照已對齊歷史價，無需修正');
      return;
    }
    const overlay = document.createElement('div');
    overlay.className = 'sf-modal-overlay';
    const previewLimit = 12;
    const shown = corrections.slice(0, previewLimit);
    const moreCount = corrections.length - shown.length;
    const previewRows = shown.map((c) => {
      const diffCls = c.diffPct == null ? '' : (c.diffPct >= 0 ? 'diff-up' : 'diff-down');
      const diffTxt = c.diffPct == null ? '—' : `${c.diffPct >= 0 ? '+' : ''}${c.diffPct.toFixed(2)}%`;
      return `<tr>
        <td>${esc(c.snapDate)}</td>
        <td><strong>${esc(c.productId)}</strong> <small>${esc(c.productName)}</small></td>
        <td>${c.oldPrice == null ? '—' : esc(c.oldPrice)}</td>
        <td><strong>${esc(c.newPrice)}</strong></td>
        <td class="${diffCls}">${esc(diffTxt)}</td>
      </tr>`;
    }).join('');
    const missingHtml = missing.length === 0 ? '' : `
      <div class="sf-correct-warning">
        ⚠️ 有 ${missing.length} 筆找不到 FinLab 歷史價（極端冷門商品 / 已下市），會略過：
        ${missing.slice(0, 5).map((m) => `${esc(m.snapDate)} ${esc(m.productId)}`).join('、')}${missing.length > 5 ? ` 等 ${missing.length} 筆` : ''}
      </div>`;
    overlay.innerHTML = `
      <div class="sf-modal" role="dialog" aria-modal="true" style="max-width: 720px;">
        <h3 class="sf-modal__title">以 FinLab 歷史價修正 — 預覽</h3>
        <div class="sf-modal__body">
          <p>共 <strong>${corrections.length}</strong> 個欄位將被修正（涵蓋 <strong>${new Set(corrections.map((c) => c.snapDate)).size}</strong> 筆快照）。</p>
          <div class="sf-correct-preview">
            <table>
              <thead><tr><th>日期</th><th>商品</th><th>原價</th><th>歷史價</th><th>差異</th></tr></thead>
              <tbody>${previewRows}</tbody>
            </table>
          </div>
          ${moreCount > 0 ? `<p class="sf-modal__hint">…另有 ${moreCount} 筆未顯示，套用後會一起修正。</p>` : ''}
          ${missingHtml}
        </div>
        <div class="sf-modal__actions">
          <button type="button" class="sf-text-btn" data-choice="cancel">取消</button>
          <button type="button" class="sf-add-btn" data-choice="apply">套用修正</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    const close = () => {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      document.removeEventListener('keydown', onKey);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') close();
    };
    document.addEventListener('keydown', onKey);
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) close();
    });
    overlay.querySelector('[data-choice="cancel"]').addEventListener('click', close);
    overlay.querySelector('[data-choice="apply"]').addEventListener('click', () => {
      const result = applyHistoricCorrections(corrections);
      close();
      renderSnapshotTable();
      const portfolioBody = document.querySelector('[data-body="portfolio"]');
      if (portfolioBody && !portfolioBody.hidden) renderPortfolio();
      setStatus(`已修正 ${result.mutatedSnapshots} 筆快照, ${result.mutatedMetrics} 個欄位${missing.length ? `（${missing.length} 筆無歷史價已略過）` : ''}`);
    });
  }

  function loadSnapshotAsCurrent(date) {
    const snap = snapshots.find((item) => item.date === date);
    if (!snap) return;
    if (!snap.positions || !snap.positions.length) {
      setStatus('這筆快照沒有持倉明細，無法載入為目前部位');
      return;
    }
    positions = snap.positions.map(normalizePosition).filter((pos) => byId.has(pos.productId));
    savePositions();
    if ($('sf-account-equity')) {
      $('sf-account-equity').value = snap.accountEquity == null ? '' : snap.accountEquity;
      localStorage.setItem(equityKey, $('sf-account-equity').value);
    }
    renderPositions();
    setStatus(`${date} 已載入為目前部位`);
  }

  function allocationByNotional() {
    const summary = currentSummary || computeSummary();
    const map = new Map();
    summary.details.forEach((c) => {
      if (!c.grossExposure) return;
      const sym = c.product.underlying_symbol || c.product.product_code || c.product.product_id;
      const prev = map.get(sym) || {
        symbol: sym,
        name: c.product.underlying_short_name || c.product.underlying_name || c.product.product_name,
        value: 0,
      };
      prev.value += Math.abs(c.grossExposure);
      map.set(sym, prev);
    });
    return Array.from(map.values()).sort((a, b) => b.value - a.value);
  }

  function topicAllocationByMargin() {
    const summary = currentSummary || computeSummary();
    const map = new Map();
    summary.details.forEach((c) => {
      if (c.product.category === 'index_future') return;
      if (!c.totalMargin) return;
      const sym = c.product.underlying_symbol;
      const rawTopics = topicsBySymbol[sym] && topicsBySymbol[sym].length ? topicsBySymbol[sym] : ['未分類'];
      const topics = rawTopics.filter((t) => !conceptTopicSet.has(t));
      const finalTopics = topics.length ? topics : ['未分類'];
      finalTopics.forEach((topic) => map.set(topic, (map.get(topic) || 0) + c.totalMargin));
    });
    return Array.from(map.entries()).map(([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value);
  }

  function emptyState(text) {
    return `<div class="sf-empty">${esc(text)}</div>`;
  }

  function lineChart(id, series, options) {
    const el = $(id);
    if (!el) return;
    const all = [];
    series.forEach((s) => s.values.forEach((p) => {
      if (num(p.value) != null) all.push({ date: p.date, value: num(p.value) });
    }));
    if (!all.length) {
      el.innerHTML = emptyState(options && options.empty ? options.empty : '尚無資料');
      return;
    }
    const dates = Array.from(new Set(all.map((p) => p.date))).sort();
    const values = all.map((p) => p.value);
    let min = Math.min(...values);
    let max = Math.max(...values);
    if (min === max) {
      min -= Math.abs(min || 1) * 0.1;
      max += Math.abs(max || 1) * 0.1;
    }
    const pad = (max - min) * 0.12;
    min -= pad;
    max += pad;
    const w = 720;
    const h = 260;
    const left = 58;
    const right = 18;
    const top = 24;
    const bottom = 42;
    const x = (date) => {
      const idx = dates.indexOf(date);
      return dates.length <= 1 ? (left + (w - right)) / 2 : left + (idx / (dates.length - 1)) * (w - left - right);
    };
    const y = (value) => top + ((max - value) / (max - min)) * (h - top - bottom);
    const fmt = options && options.format ? options.format : price;
    const grid = [0, 0.25, 0.5, 0.75, 1].map((t) => {
      const gy = top + t * (h - top - bottom);
      const value = max - t * (max - min);
      return `<line x1="${left}" x2="${w - right}" y1="${gy}" y2="${gy}" class="sf-grid-line"></line><text x="8" y="${gy + 4}" class="sf-axis-text">${esc(fmt(value))}</text>`;
    }).join('');
    const paths = series.map((s, idx) => {
      const points = s.values.filter((p) => num(p.value) != null).map((p) => [x(p.date), y(num(p.value))]);
      if (!points.length) return '';
      const path = points.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
      const dots = points.map((p) => `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="3"></circle>`).join('');
      return `<g class="sf-line-series" style="--series-color:${s.color || colors[idx % colors.length]}"><path d="${path}"></path>${dots}</g>`;
    }).join('');
    const legend = series.map((s, idx) => `<span><i style="background:${s.color || colors[idx % colors.length]}"></i>${esc(s.name)}</span>`).join('');
    const tickDates = dates.length > 6 ? [dates[0], dates[Math.floor(dates.length / 2)], dates[dates.length - 1]] : dates;
    const xTicks = tickDates.map((d) => `<text x="${x(d)}" y="${h - 14}" text-anchor="middle" class="sf-axis-text">${esc(d.slice(5))}</text>`).join('');
    el.innerHTML = `
      <svg class="sf-line-chart" viewBox="0 0 ${w} ${h}" role="img">
        ${grid}
        ${paths}
        ${xTicks}
      </svg>
      <div class="sf-chart-legend">${legend}</div>`;
  }

  function dualAxisLineChart(id, leftSeries, rightSeries, options) {
    const el = $(id);
    if (!el) return;
    const allSeries = leftSeries.concat(rightSeries);
    const dates = Array.from(new Set(allSeries.flatMap((s) => s.values.map((p) => p.date)))).filter(Boolean).sort();
    const leftValues = leftSeries.flatMap((s) => s.values.map((p) => num(p.value))).filter((v) => v != null);
    const rightValues = rightSeries.flatMap((s) => s.values.map((p) => num(p.value))).filter((v) => v != null);
    if (!dates.length || (!leftValues.length && !rightValues.length)) {
      el.innerHTML = emptyState(options && options.empty ? options.empty : '尚無資料');
      return;
    }
    const domain = (values) => {
      if (!values.length) return [0, 1];
      let min = Math.min(...values);
      let max = Math.max(...values);
      if (min === max) {
        min -= Math.abs(min || 1) * 0.1;
        max += Math.abs(max || 1) * 0.1;
      }
      const pad = (max - min) * 0.12;
      return [min - pad, max + pad];
    };
    const [leftMin, leftMax] = domain(leftValues);
    const [rightMin, rightMax] = domain(rightValues);
    const w = 720;
    const h = 280;
    const left = 58;
    const right = 76;
    const top = 24;
    const bottom = 42;
    const x = (date) => {
      const idx = dates.indexOf(date);
      return dates.length <= 1 ? (left + (w - right)) / 2 : left + (idx / (dates.length - 1)) * (w - left - right);
    };
    const yLeft = (value) => top + ((leftMax - value) / (leftMax - leftMin)) * (h - top - bottom);
    const yRight = (value) => top + ((rightMax - value) / (rightMax - rightMin)) * (h - top - bottom);
    const leftFmt = options && options.leftFormat ? options.leftFormat : leverage;
    const rightFmt = options && options.rightFormat ? options.rightFormat : price;
    const grid = [0, 0.25, 0.5, 0.75, 1].map((t) => {
      const gy = top + t * (h - top - bottom);
      const lv = leftMax - t * (leftMax - leftMin);
      const rv = rightMax - t * (rightMax - rightMin);
      return `<line x1="${left}" x2="${w - right}" y1="${gy}" y2="${gy}" class="sf-grid-line"></line>
        <text x="8" y="${gy + 4}" class="sf-axis-text">${esc(leftFmt(lv))}</text>
        <text x="${w - 8}" y="${gy + 4}" text-anchor="end" class="sf-axis-text">${esc(rightFmt(rv))}</text>`;
    }).join('');
    const draw = (series, axis, offset) => series.map((s, idx) => {
      const y = axis === 'right' ? yRight : yLeft;
      const points = s.values.filter((p) => num(p.value) != null).map((p) => [x(p.date), y(num(p.value))]);
      if (!points.length) return '';
      const path = points.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
      const dots = points.map((p) => `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="3"></circle>`).join('');
      return `<g class="sf-line-series" style="--series-color:${s.color || colors[(idx + offset) % colors.length]}"><path d="${path}"></path>${dots}</g>`;
    }).join('');
    const legend = allSeries.map((s, idx) => `<span><i style="background:${s.color || colors[idx % colors.length]}"></i>${esc(s.name)}</span>`).join('');
    const tickDates = dates.length > 6 ? [dates[0], dates[Math.floor(dates.length / 2)], dates[dates.length - 1]] : dates;
    const xTicks = tickDates.map((d) => `<text x="${x(d)}" y="${h - 14}" text-anchor="middle" class="sf-axis-text">${esc(d.slice(5))}</text>`).join('');
    el.innerHTML = `
      <svg class="sf-line-chart" viewBox="0 0 ${w} ${h}" role="img">
        ${grid}
        ${draw(leftSeries, 'left', 0)}
        ${draw(rightSeries, 'right', leftSeries.length)}
        ${xTicks}
      </svg>
      <div class="sf-chart-legend">${legend}</div>`;
  }

  function renderPie() {
    const el = $('sf-position-pie');
    if (!el) return;
    const data = allocationByNotional().filter((item) => item.value > 0);
    const total = data.reduce((sum, item) => sum + item.value, 0);
    if (!data.length || !total) {
      el.innerHTML = emptyState('目前沒有可計算名目曝險占比的持倉');
      return;
    }
    let angle = -Math.PI / 2;
    const cx = 110;
    const cy = 110;
    const r = 88;
    const slices = data.map((item, idx) => {
      const portion = item.value / total;
      if (data.length === 1) {
        return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${colors[idx % colors.length]}"></circle>`;
      }
      const start = angle;
      const end = angle + portion * Math.PI * 2;
      angle = end;
      const x1 = cx + Math.cos(start) * r;
      const y1 = cy + Math.sin(start) * r;
      const x2 = cx + Math.cos(end) * r;
      const y2 = cy + Math.sin(end) * r;
      const large = end - start > Math.PI ? 1 : 0;
      return `<path d="M${cx},${cy} L${x1.toFixed(2)},${y1.toFixed(2)} A${r},${r} 0 ${large},1 ${x2.toFixed(2)},${y2.toFixed(2)} Z" fill="${colors[idx % colors.length]}"></path>`;
    }).join('');
    const legend = data.map((item, idx) => {
      const portion = item.value / total;
      return `<div class="sf-pie-row"><i style="background:${colors[idx % colors.length]}"></i><span>${esc(item.name)} <b>${plainPct(portion)}</b></span><em>${money(item.value)}</em></div>`;
    }).join('');
    el.innerHTML = `
      <svg class="sf-pie" viewBox="0 0 220 220" role="img">${slices}<circle cx="${cx}" cy="${cy}" r="42" fill="var(--panel-bg, #fff)"></circle></svg>
      <div class="sf-pie-legend">${legend}</div>`;
  }

  function renderHeatmap() {
    const el = $('sf-topic-heatmap');
    if (!el) return;
    const data = topicAllocationByMargin().filter((item) => item.value > 0).slice(0, 18);
    if (!data.length) {
      el.innerHTML = emptyState('目前持倉尚未對應到族群');
      return;
    }
    const max = Math.max(...data.map((item) => item.value));
    el.innerHTML = data.map((item, idx) => {
      const pctValue = max ? item.value / max : 0;
      return `<div class="sf-topic-tile" style="--tile-color:${colors[idx % colors.length]}; --heat-border:${Math.round(22 + pctValue * 35)}%; --heat-bg:${Math.round(10 + pctValue * 26)}%;">
        <strong>${esc(item.name)}</strong>
        <span>${money(item.value)}</span>
      </div>`;
    }).join('');
  }

  function renderSnapshotTable() {
    const tbody = document.querySelector('#sf-snapshot-table tbody');
    if (!tbody) return;
    const sorted = snapshots.slice().sort((a, b) => b.date.localeCompare(a.date));
    if ($('sf-snapshot-count')) $('sf-snapshot-count').textContent = `${snapshots.length} 筆`;
    tbody.innerHTML = sorted.map((snap) => {
      const hasPositions = snap.positions && snap.positions.length;
      return `<tr>
        <td><strong>${esc(snap.date)}</strong></td>
        <td>${money(snap.accountEquity)}</td>
        <td>${money(snap.summary.grossExposure)}</td>
        <td>${signed(snap.summary.netExposure, money)}</td>
        <td>${money(snap.summary.totalMargin)}</td>
        <td>${leverage(snap.summary.marginLeverage)}</td>
        <td>${leverage(snap.summary.equityLeverage)}</td>
        <td>${snap.summary.unrealizedPnl == null ? '<span class="muted">—</span>' : signed(snap.summary.unrealizedPnl, money)}</td>
        <td>${money(snap.summary.positionCount || (snap.positions || []).length)}</td>
        <td>${snap.source === 'xlsx' ? 'Excel 快照' : snap.source === 'json' ? 'JSON 匯入' : snap.source === 'manual-historic' ? '<span class="sf-snap-historic">部位快照·歷史價</span>' : snap.priceMode === 'historic' ? '<span class="sf-snap-historic">部位快照·歷史價</span>' : '部位快照'}</td>
        <td><button type="button" class="sf-row-btn" data-load-snapshot="${esc(snap.date)}" ${hasPositions ? '' : 'disabled'}>載入為目前部位</button></td>
      </tr>`;
    }).join('') || '<tr><td colspan="11" class="muted">尚未儲存歷史明細</td></tr>';
    tbody.querySelectorAll('[data-load-snapshot]').forEach((btn) => {
      btn.addEventListener('click', () => loadSnapshotAsCurrent(btn.dataset.loadSnapshot));
    });
  }

  // ===========================================================
  // 「檢視部位」儀表板 — vanilla JS 重寫 SfPortfolioA
  // ===========================================================

  const SVG_NS = 'http://www.w3.org/2000/svg';

  function svgEl(tag, attrs) {
    const el = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      Object.keys(attrs).forEach((k) => {
        if (attrs[k] != null) el.setAttribute(k, attrs[k]);
      });
    }
    return el;
  }

  function fmtMoneySigned(n) {
    if (n == null || !Number.isFinite(n)) return '—';
    const sign = n > 0 ? '+' : n < 0 ? '−' : '';
    return `${sign}${Math.abs(Math.round(n)).toLocaleString('zh-TW')}`;
  }

  function fmtCompact(n) {
    if (n == null || !Number.isFinite(n)) return '—';
    const abs = Math.abs(n);
    const sign = n < 0 ? '-' : '';
    if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}億`;
    if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(2)}萬`;
    return `${sign}${Math.round(abs).toLocaleString('zh-TW')}`;
  }

  function metricValueOf(detail, metricKey) {
    if (metricKey === 'margin') return Math.abs(num(detail.totalMargin) || 0);
    if (metricKey === 'lots') return Math.abs(num(detail.used) || 0);
    return Math.abs(num(detail.grossExposure) || 0);
  }

  function metricFormatter(metricKey) {
    if (metricKey === 'lots') return (v) => `${Math.round(v)} 口`;
    return (v) => fmtCompact(v);
  }

  function animateNumber(el, from, to, opts) {
    if (!el) return;
    const dur = (opts && opts.dur) || 900;
    const formatter = (opts && opts.formatter) || ((v) => Math.round(v).toLocaleString('zh-TW'));
    if (!Number.isFinite(from)) from = 0;
    if (!Number.isFinite(to)) {
      el.textContent = '—';
      return;
    }
    // 先把終值同步寫進 DOM（即使 RAF 被 throttle 也保證 UI 不空白）
    el.textContent = formatter(to);
    if (from === to) return;
    const t0 = performance.now();
    if (el._sfRaf) cancelAnimationFrame(el._sfRaf);
    function tick(now) {
      const p = Math.min(1, (now - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      const v = from + (to - from) * eased;
      el.textContent = formatter(v);
      if (p < 1) el._sfRaf = requestAnimationFrame(tick);
    }
    el._sfRaf = requestAnimationFrame(tick);
  }

  function drawSparkline(container, data, color) {
    if (!container) return;
    container.innerHTML = '';
    const safe = (data || []).filter((v) => Number.isFinite(v));
    if (safe.length < 2) {
      container.innerHTML = '<svg width="100%" height="36"></svg>';
      return;
    }
    const w = 240, h = 36;
    const min = Math.min(...safe);
    const max = Math.max(...safe);
    const range = max - min || 1;
    const pts = safe.map((d, i) => [
      (i / (safe.length - 1)) * w,
      h - ((d - min) / range) * (h - 8) - 4,
    ]);
    const path = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
    const area = `${path} L${w},${h} L0,${h} Z`;
    const head = pts[pts.length - 1];
    const gradId = `sfA-spark-${color.replace('#', '')}-${Math.random().toString(16).slice(2, 8)}`;
    const svg = svgEl('svg', { viewBox: `0 0 ${w} ${h}`, width: '100%', height: h, preserveAspectRatio: 'none' });
    svg.style.display = 'block';
    svg.style.overflow = 'visible';
    const defs = svgEl('defs');
    const grad = svgEl('linearGradient', { id: gradId, x1: 0, y1: 0, x2: 0, y2: 1 });
    grad.appendChild(svgEl('stop', { offset: '0%', 'stop-color': color, 'stop-opacity': '0.24' }));
    grad.appendChild(svgEl('stop', { offset: '100%', 'stop-color': color, 'stop-opacity': '0' }));
    defs.appendChild(grad);
    svg.appendChild(defs);
    svg.appendChild(svgEl('path', { d: area, fill: `url(#${gradId})` }));
    svg.appendChild(svgEl('path', { d: path, fill: 'none', stroke: color, 'stroke-width': '1.6', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
    svg.appendChild(svgEl('circle', { cx: head[0].toFixed(1), cy: head[1].toFixed(1), r: '3.2', fill: color }));
    const pulse = svgEl('circle', { cx: head[0].toFixed(1), cy: head[1].toFixed(1), r: '4', fill: color, opacity: '0.18' });
    const animR = svgEl('animate', { attributeName: 'r', values: '4;9;4', dur: '1.6s', repeatCount: 'indefinite' });
    const animO = svgEl('animate', { attributeName: 'opacity', values: '0.3;0;0.3', dur: '1.6s', repeatCount: 'indefinite' });
    pulse.appendChild(animR);
    pulse.appendChild(animO);
    svg.appendChild(pulse);
    container.appendChild(svg);
  }

  function drawGauge(container, value, max, color) {
    if (!container) return;
    container.innerHTML = '';
    const cx = 80, cy = 80, r = 60;
    const a0 = Math.PI * 0.85;
    const sweep = Math.PI * 1.3;
    const safeValue = Number.isFinite(value) ? value : 0;
    const pct = Math.min(1, Math.max(0, safeValue / max));
    const polar = (ang, rr) => [cx + Math.cos(ang) * rr, cy + Math.sin(ang) * rr];
    const trackS = polar(a0, r);
    const trackE = polar(a0 + sweep, r);
    const svg = svgEl('svg', { viewBox: '0 0 160 110', width: '100%', height: '110' });
    svg.appendChild(svgEl('path', {
      d: `M${trackS[0].toFixed(2)},${trackS[1].toFixed(2)} A${r},${r} 0 1 1 ${trackE[0].toFixed(2)},${trackE[1].toFixed(2)}`,
      stroke: T.border, 'stroke-width': '8', fill: 'none', 'stroke-linecap': 'round',
    }));
    // Final-state arc / needle，先同步畫出來，避免 RAF 被 throttle 時呈空白
    const finalA1 = a0 + sweep * pct;
    const [finalSx, finalSy] = polar(a0, r);
    const [finalEx, finalEy] = polar(finalA1, r);
    const finalLarge = sweep * pct > Math.PI ? 1 : 0;
    const arc = svgEl('path', {
      stroke: color, 'stroke-width': '8', fill: 'none', 'stroke-linecap': 'round',
      d: pct > 0 ? `M${finalSx.toFixed(2)},${finalSy.toFixed(2)} A${r},${r} 0 ${finalLarge} 1 ${finalEx.toFixed(2)},${finalEy.toFixed(2)}` : '',
    });
    svg.appendChild(arc);
    for (let i = 0; i <= 10; i++) {
      const ang = a0 + sweep * (i / 10);
      const [x1, y1] = polar(ang, r - 12);
      const [x2, y2] = polar(ang, r - 18);
      svg.appendChild(svgEl('line', { x1, y1, x2, y2, stroke: T.muted, 'stroke-width': '1', opacity: '0.5' }));
    }
    const needle = svgEl('line', {
      x1: cx, y1: cy, x2: finalEx.toFixed(2), y2: finalEy.toFixed(2),
      stroke: T.ink, 'stroke-width': '2', 'stroke-linecap': 'round',
    });
    svg.appendChild(needle);
    svg.appendChild(svgEl('circle', { cx, cy, r: '5', fill: T.bgAlt, stroke: T.ink, 'stroke-width': '1.5' }));
    const text = svgEl('text', { x: cx, y: cy + 30, 'text-anchor': 'middle', 'font-family': "'JetBrains Mono', ui-monospace, monospace", 'font-size': '26', 'font-weight': '600', fill: T.ink });
    text.textContent = safeValue.toFixed(2);
    svg.appendChild(text);
    container.appendChild(svg);
    const t0 = performance.now();
    let raf;
    function tick(now) {
      const p = Math.min(1, (now - t0) / 1200);
      const eased = 1 - Math.pow(1 - p, 3);
      const cur = pct * eased;
      const a1 = a0 + sweep * cur;
      const [sx, sy] = polar(a0, r);
      const [ex, ey] = polar(a1, r);
      const large = sweep * cur > Math.PI ? 1 : 0;
      arc.setAttribute('d', `M${sx.toFixed(2)},${sy.toFixed(2)} A${r},${r} 0 ${large} 1 ${ex.toFixed(2)},${ey.toFixed(2)}`);
      needle.setAttribute('x2', ex.toFixed(2));
      needle.setAttribute('y2', ey.toFixed(2));
      text.textContent = (safeValue * eased).toFixed(2);
      if (p < 1) raf = requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);
  }

  function drawFlowBar(container, items) {
    if (!container) return;
    container.innerHTML = '';
    const total = items.reduce((s, it) => s + Math.abs(it.value), 0);
    if (!total) {
      container.innerHTML = '<div class="sf-portfolio-empty">尚未持倉，無族群分布</div>';
      return;
    }
    items.forEach((it, i) => {
      const seg = document.createElement('div');
      seg.className = 'sf-flowbar__seg';
      seg.title = `${it.label} ${fmtCompact(it.value)}`;
      const pct = (Math.abs(it.value) / total) * 100;
      seg.style.width = pct.toFixed(2) + '%';
      seg.style.background = it.color;
      seg.style.animationDelay = `${i * 0.4}s`;
      if (pct > 6) seg.textContent = it.label;
      container.appendChild(seg);
    });
  }

  function drawDonut(container, items, opts) {
    if (!container) return null;
    container.innerHTML = '';
    container.style.position = 'relative';
    const size = (opts && opts.size) || 220;
    const thickness = (opts && opts.thickness) || 36;
    const formatter = (opts && opts.formatter) || fmtCompact;
    const totalLabel = (opts && opts.totalLabel) || '總計';
    if (!items.length) {
      container.innerHTML = '<div class="sf-portfolio-empty" style="width:' + size + 'px; height:' + size + 'px;">尚無持倉</div>';
      return null;
    }
    const total = items.reduce((s, d) => s + d.value, 0);
    const cx = size / 2, cy = size / 2;
    const rOut = size / 2 - 4;
    const rIn = rOut - thickness;
    const polar = (a, rr) => [cx + Math.cos(a) * rr, cy + Math.sin(a) * rr];
    const svg = svgEl('svg', { viewBox: `0 0 ${size} ${size}` });
    svg.style.width = size + 'px';
    svg.style.height = size + 'px';
    svg.style.overflow = 'visible';
    svg.style.display = 'block';
    svg.style.border = 'none';
    svg.style.outline = 'none';
    svg.style.background = 'transparent';
    const arcs = [];
    let acc = -Math.PI / 2;
    items.forEach((d, i) => {
      const span = (d.value / total) * Math.PI * 2;
      const a0 = acc;
      const a1 = acc + span;
      acc = a1;
      arcs.push({ a0, a1, mid: (a0 + a1) / 2, color: d.color, label: d.label, value: d.value, pct: d.value / total, idx: i });
    });
    function arcPath(aStart, aEnd) {
      const [x0, y0] = polar(aStart, rOut);
      const [x1, y1] = polar(aEnd, rOut);
      const [x2, y2] = polar(aEnd, rIn);
      const [x3, y3] = polar(aStart, rIn);
      const large = (aEnd - aStart) > Math.PI ? 1 : 0;
      return `M${x0.toFixed(2)},${y0.toFixed(2)} A${rOut},${rOut} 0 ${large} 1 ${x1.toFixed(2)},${y1.toFixed(2)} L${x2.toFixed(2)},${y2.toFixed(2)} A${rIn},${rIn} 0 ${large} 0 ${x3.toFixed(2)},${y3.toFixed(2)} Z`;
    }
    const paths = arcs.map((a) => {
      // Final-state path（避免 RAF 被 throttle 時 SVG 呈空白）
      const path = svgEl('path', { fill: a.color, opacity: '1', d: arcPath(a.a0, a.a1) });
      svg.appendChild(path);
      return path;
    });
    container.appendChild(svg);

    // 中央顯示：預設顯示「總計 + 加總值」；hover 時切換成 hovered 切片資訊
    const centerEl = document.createElement('div');
    centerEl.className = 'sf-donut__center';
    centerEl.style.position = 'absolute';
    centerEl.style.left = '0';
    centerEl.style.top = '0';
    centerEl.style.width = size + 'px';
    centerEl.style.height = size + 'px';
    centerEl.style.display = 'flex';
    centerEl.style.flexDirection = 'column';
    centerEl.style.alignItems = 'center';
    centerEl.style.justifyContent = 'center';
    centerEl.style.pointerEvents = 'none';
    centerEl.style.textAlign = 'center';
    container.appendChild(centerEl);

    function setCenter(label, valueText, color) {
      centerEl.innerHTML = `
        <div class="sf-donut__center-label" style="font-size: 13px; color: var(--sfA-muted); letter-spacing: 0.1em;">${esc(label)}</div>
        <div class="sf-donut__center-value" style="font-size: 1.3rem; font-weight: 600; font-family: var(--sfA-font-mono); color: ${color || 'var(--sfA-ink)'}; margin-top: 6px; max-width: ${size - 60}px; line-height: 1.25; word-break: break-word;">${esc(valueText)}</div>
      `;
    }
    function resetCenter() {
      setCenter(totalLabel, formatter(total));
    }
    resetCenter();

    const t0 = performance.now();
    let raf;
    function tick(now) {
      const p = Math.min(1, (now - t0) / 1400);
      const eased = 1 - Math.pow(1 - p, 3);
      arcs.forEach((a, i) => {
        const aStart = a.a0;
        const aEnd = a.a0 + (a.a1 - a.a0) * eased;
        paths[i].setAttribute('d', arcPath(aStart, aEnd));
      });
      if (p < 1) raf = requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);

    function activate(i) {
      const a = arcs[i];
      paths.forEach((p, j) => p.setAttribute('opacity', i === j ? '1' : '0.32'));
      paths[i].style.transform = `translate(${(Math.cos(a.mid) * 6).toFixed(2)}px, ${(Math.sin(a.mid) * 6).toFixed(2)}px)`;
      const pctText = `${(a.pct * 100).toFixed(1)}%`;
      const valText = formatter(a.value);
      // Label 在上方，數值 + % 並排在下方
      centerEl.innerHTML = `
        <div class="sf-donut__center-label" style="font-size: 13px; color: var(--sfA-muted); letter-spacing: 0.1em; max-width: ${size - 60}px;">${esc(a.label)}</div>
        <div class="sf-donut__center-value" style="font-size: 1.85rem; font-weight: 700; font-family: var(--sfA-font-mono); color: ${a.color}; margin-top: 6px; line-height: 1;">${esc(pctText)}</div>
        <div style="font-size: 14px; color: var(--sfA-ink-soft); font-family: var(--sfA-font-mono); margin-top: 6px;">${esc(valText)}</div>
      `;
    }
    function deactivate() {
      paths.forEach((p) => {
        p.setAttribute('opacity', '1');
        p.style.transform = 'none';
      });
      resetCenter();
    }

    paths.forEach((path, i) => {
      path.style.cursor = 'pointer';
      path.style.transformOrigin = `${cx}px ${cy}px`;
      path.style.transition = 'transform 0.25s ease-out, opacity 0.2s';
      path.addEventListener('mouseenter', () => activate(i));
      path.addEventListener('mouseleave', deactivate);
      path.addEventListener('focus', () => activate(i));
      path.addEventListener('blur', deactivate);
    });

    return { arcs, paths, activate, deactivate, formatter, total };
  }

  function drawLiquidBar(container, pct, color, label, valueLabel) {
    if (!container) return;
    container.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'sf-liquid';
    const head = document.createElement('div');
    head.className = 'sf-liquid__head';
    head.innerHTML = `<span>${esc(label)}</span><span>${esc(valueLabel)}</span>`;
    wrap.appendChild(head);
    const w = 320, h = 44;
    const safePct = Math.max(0, Math.min(1, Number.isFinite(pct) ? pct : 0));
    const svg = svgEl('svg', { viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: 'none' });
    const back = svgEl('path', { fill: color, opacity: '0.28' });
    const front = svgEl('path', { fill: color, opacity: '0.85' });
    svg.appendChild(back);
    svg.appendChild(front);
    [0.25, 0.5, 0.75].forEach((g) => {
      svg.appendChild(svgEl('line', {
        x1: 0, x2: w, y1: h * (1 - g), y2: h * (1 - g),
        stroke: T.border, 'stroke-width': '0.5', 'stroke-dasharray': '2,3', opacity: '0.6',
      }));
    });
    wrap.appendChild(svg);
    container.appendChild(wrap);
    let phase = 0, grow = 1;
    function wave(offset, amp) {
      const fillH = h * safePct * grow;
      const pts = [];
      for (let i = 0; i <= w; i += 6) {
        const y = h - fillH + Math.sin((i / w) * Math.PI * 4 + (phase + offset) * 0.05) * amp;
        pts.push([i, y]);
      }
      let d = `M0,${h}`;
      pts.forEach((p) => { d += ` L${p[0]},${p[1].toFixed(2)}`; });
      d += ` L${w},${h} Z`;
      return d;
    }
    // Final-state（grow=1）先同步畫上；RAF 接管後做波浪 + grow 動畫
    back.setAttribute('d', wave(0, 3));
    front.setAttribute('d', wave(180, 2));
    grow = 0;
    const t0 = performance.now();
    function tick(now) {
      // 如果 SVG 已從 DOM 卸下（重新渲染），停止動畫避免洩漏
      if (!svg.isConnected) return;
      phase = (now / 60) % 360;
      const p = Math.min(1, (now - t0) / 1200);
      grow = 1 - Math.pow(1 - p, 3);
      back.setAttribute('d', wave(0, 3));
      front.setAttribute('d', wave(180, 2));
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function drawTreemap(container, data, width, height) {
    if (!container) return;
    container.innerHTML = '';
    const w = width || 1180;
    const h = height || 220;
    if (!data.length) {
      container.innerHTML = '<div class="sf-portfolio-empty">尚未持倉，無族群熱力</div>';
      return;
    }
    const sorted = [...data].sort((a, b) => b.value - a.value);
    function layout(items, x, y, ww, hh) {
      if (!items.length) return [];
      if (items.length === 1) return [Object.assign({}, items[0], { x, y, w: ww, h: hh })];
      const sum = items.reduce((s, d) => s + d.value, 0);
      let acc = 0, split = items.length;
      for (let i = 0; i < items.length; i++) {
        acc += items[i].value;
        if (acc >= sum * 0.5 || i === items.length - 1) { split = i + 1; break; }
      }
      const head = items.slice(0, split);
      const tail = items.slice(split);
      const headSum = head.reduce((s, d) => s + d.value, 0);
      if (ww >= hh) {
        const hw = ww * (headSum / sum);
        const out = [];
        let yy = y;
        head.forEach((it) => {
          const hh2 = hh * (it.value / headSum);
          out.push(Object.assign({}, it, { x, y: yy, w: hw, h: hh2 }));
          yy += hh2;
        });
        return out.concat(layout(tail, x + hw, y, ww - hw, hh));
      } else {
        const hh2 = hh * (headSum / sum);
        const out = [];
        let xx = x;
        head.forEach((it) => {
          const ww2 = ww * (it.value / headSum);
          out.push(Object.assign({}, it, { x: xx, y, w: ww2, h: hh2 }));
          xx += ww2;
        });
        return out.concat(layout(tail, x, y + hh2, ww, hh - hh2));
      }
    }
    const cells = layout(sorted, 0, 0, w, h);
    const cellColor = (perf) => {
      const a = Math.min(0.85, Math.max(0.18, Math.abs(perf || 0) / 4));
      return (perf || 0) >= 0
        ? `oklch(62% ${(0.16 * a + 0.04).toFixed(3)} 22)`
        : `oklch(62% ${(0.16 * a + 0.04).toFixed(3)} 158)`;
    };
    const svg = svgEl('svg', { viewBox: `0 0 ${w} ${h}`, class: 'sf-treemap-svg' });
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    cells.forEach((r, i) => {
      const g = svgEl('g', { class: 'sf-treemap-cell', style: `animation: sfA-fadein 0.4s ${i * 0.04}s both` });
      g.appendChild(svgEl('rect', {
        x: r.x.toFixed(2), y: r.y.toFixed(2), width: r.w.toFixed(2), height: r.h.toFixed(2),
        fill: cellColor(r.perf), stroke: T.bgAlt, 'stroke-width': '1.5',
      }));
      const big = r.w > 70 && r.h > 42;
      const med = r.w > 46 && r.h > 28;
      if (big || med) {
        const labelText = svgEl('text', {
          x: (r.x + 10).toFixed(2), y: (r.y + 22).toFixed(2),
          fill: '#fff', 'font-size': big ? '15' : '13', 'font-weight': '600',
        });
        labelText.textContent = r.label;
        g.appendChild(labelText);
      }
      if (big) {
        const valText = svgEl('text', {
          x: (r.x + 10).toFixed(2), y: (r.y + r.h - 10).toFixed(2),
          fill: 'rgba(255,255,255,0.88)', 'font-size': '13',
        });
        valText.textContent = fmtCompact(r.value);
        g.appendChild(valText);
        if (Number.isFinite(r.perf)) {
          const perfText = svgEl('text', {
            x: (r.x + r.w - 10).toFixed(2), y: (r.y + r.h - 10).toFixed(2),
            fill: 'rgba(255,255,255,0.95)', 'font-size': '13', 'text-anchor': 'end', 'font-weight': '600',
          });
          perfText.textContent = `${r.perf >= 0 ? '+' : ''}${r.perf.toFixed(2)}%`;
          g.appendChild(perfText);
        }
      }
      svg.appendChild(g);
    });
    container.appendChild(svg);
  }

  function drawLeverageTrend(container, sorted) {
    if (!container) return;
    container.innerHTML = '';
    const w = 880, h = 200;
    const active = TREND_METRICS.filter((m) => activeTrendMetrics.has(m.key));

    // 以後台大盤歷史為 X 軸主幹，補入快照日期
    const idxHistory = Array.isArray(marketIndices.history) ? marketIndices.history : [];
    const snapByDate = new Map(sorted.map((s) => [s.date, s]));
    const allDates = [...new Set([
      ...idxHistory.map((r) => r.date),
      ...sorted.map((s) => s.date),
    ])].sort();

    if (allDates.length < 2) {
      container.innerHTML = '<div class="sf-portfolio-empty">至少需要 2 筆資料才能畫趨勢</div>';
      const axis = $('sf-leverage-axis');
      if (axis) axis.innerHTML = '<span>—</span><span>—</span><span>—</span><span>—</span>';
      return;
    }

    // 建立大盤 date->value map（history + current 補齊）
    const idxByDate = new Map(idxHistory.map((r) => [r.date, num(r.taiex)]));
    const cur = marketIndices.current || {};
    if (cur.taiex && cur.taiex.date && cur.taiex.value != null) idxByDate.set(cur.taiex.date, num(cur.taiex.value));

    const N = allDates.length;
    const py = (v, mn, mx) => h - ((v - mn) / ((mx - mn) || 1)) * (h - 30) - 16;
    const px = (i) => (i / (N - 1)) * w;

    // 大盤陣列（每個日期一個點，後台無資料則 null）
    const idx = allDates.map((d) => idxByDate.get(d) ?? null);
    const filteredIdx = idx.filter((v) => Number.isFinite(v));
    const minI = filteredIdx.length ? Math.min(...filteredIdx) : 0;
    const maxI = filteredIdx.length ? Math.max(...filteredIdx) : 1;

    // 大盤路徑（null 點斷開）
    let idxPath = '';
    let idxSeg = '';
    idx.forEach((v, i) => {
      if (!Number.isFinite(v)) { if (idxSeg) { idxPath += idxSeg + ' '; idxSeg = ''; } return; }
      idxSeg += `${idxSeg ? 'L' : 'M'}${px(i).toFixed(1)},${py(v, minI, maxI).toFixed(1)} `;
    });
    if (idxSeg) idxPath += idxSeg;

    const svg = svgEl('svg', { viewBox: `0 0 ${w} ${h}`, class: 'sf-leverage-chart-svg', preserveAspectRatio: 'none' });
    svg.setAttribute('height', h);
    const defs = svgEl('defs');
    defs.appendChild((function () {
      const pat = svgEl('pattern', { id: 'sfA-lvmGrid', width: w / 6, height: h / 4, patternUnits: 'userSpaceOnUse' });
      pat.appendChild(svgEl('path', { d: `M 0 0 L 0 ${h / 4} M 0 0 L ${w / 6} 0`, fill: 'none', stroke: T.border, 'stroke-width': '0.5' }));
      return pat;
    })());
    const firstColor = active.length ? T.series[TREND_METRICS.findIndex((m) => m.key === active[0].key) % T.series.length] : T.navy;
    defs.appendChild((function () {
      const grad = svgEl('linearGradient', { id: 'sfA-lvmFill', x1: 0, y1: 0, x2: 0, y2: 1 });
      grad.appendChild(svgEl('stop', { offset: '0%', 'stop-color': firstColor, 'stop-opacity': '0.12' }));
      grad.appendChild(svgEl('stop', { offset: '100%', 'stop-color': firstColor, 'stop-opacity': '0' }));
      return grad;
    })());
    svg.appendChild(defs);
    svg.appendChild(svgEl('rect', { width: w, height: h, fill: 'url(#sfA-lvmGrid)' }));

    // 大盤線（先畫，讓指標線蓋在上面）
    if (idxPath.trim()) svg.appendChild(svgEl('path', { d: idxPath.trim(), stroke: T.gold, 'stroke-width': '1.2', fill: 'none', 'stroke-dasharray': '3,3', opacity: '0.85' }));
    if (Number.isFinite(idx[N - 1])) svg.appendChild(svgEl('circle', { cx: w, cy: py(idx[N - 1], minI, maxI).toFixed(1), r: '3', fill: T.gold }));

    // 各指標折線（只在有快照的日期有點，其餘 null）
    active.forEach((m, mi) => {
      const color = T.series[TREND_METRICS.findIndex((tm) => tm.key === m.key) % T.series.length];
      const vals = allDates.map((d) => { const s = snapByDate.get(d); return s ? m.get(s) : null; });
      const filtered = vals.filter((v) => Number.isFinite(v));
      if (!filtered.length) return;
      const mn = Math.min(...filtered), mx = Math.max(...filtered);

      // 折線路徑（null 點斷開，連接相鄰快照點）
      let linePath = '';
      let seg = '';
      vals.forEach((v, i) => {
        if (!Number.isFinite(v)) { if (seg) { linePath += seg + ' '; seg = ''; } return; }
        seg += `${seg ? 'L' : 'M'}${px(i).toFixed(1)},${py(v, mn, mx).toFixed(1)} `;
      });
      if (seg) linePath += seg;

      if (mi === 0 && linePath.trim()) {
        // 第一條線加底部填色
        const firstPt = vals.findIndex((v) => Number.isFinite(v));
        const lastPt = vals.length - 1 - [...vals].reverse().findIndex((v) => Number.isFinite(v));
        svg.appendChild(svgEl('path', {
          d: `${linePath.trim()} L${px(lastPt).toFixed(1)},${h} L${px(firstPt).toFixed(1)},${h} Z`,
          fill: 'url(#sfA-lvmFill)',
        }));
      }
      if (linePath.trim()) svg.appendChild(svgEl('path', { d: linePath.trim(), stroke: color, 'stroke-width': '1.8', fill: 'none' }));

      // 快照日期上的點
      vals.forEach((v, i) => {
        if (!Number.isFinite(v)) return;
        svg.appendChild(svgEl('circle', { cx: px(i).toFixed(1), cy: py(v, mn, mx).toFixed(1), r: '3', fill: color }));
      });
    });

    container.appendChild(svg);

    // X 軸：取 4 個均勻分佈的日期
    const axis = $('sf-leverage-axis');
    if (axis) {
      const idxs = N <= 4
        ? allDates.map((_, i) => i)
        : [0, Math.floor(N / 3), Math.floor((2 * N) / 3), N - 1];
      axis.innerHTML = idxs.map((i) => `<span>${esc(String(allDates[i]).slice(5))}</span>`).join('');
    }

    // 左 Y 軸：大盤刻度（金色）
    const yLeft = $('sf-leverage-yaxis-left');
    if (yLeft) {
      if (filteredIdx.length >= 2) {
        const fmt = (v) => Math.round(v).toLocaleString('zh-TW');
        yLeft.innerHTML = [maxI, (minI + maxI) / 2, minI].map((v) => `<span>${fmt(v)}</span>`).join('');
      } else {
        yLeft.innerHTML = '';
      }
    }

    // 右 Y 軸：第一個 active 指標刻度
    const yRight = $('sf-leverage-yaxis-right');
    if (yRight) {
      if (active.length) {
        const m0 = active[0];
        const rVals = sorted.map((s) => m0.get(s)).filter((v) => Number.isFinite(v));
        if (rVals.length >= 2) {
          const rmn = Math.min(...rVals), rmx = Math.max(...rVals);
          yRight.innerHTML = [rmx, (rmn + rmx) / 2, rmn].map((v) => `<span>${esc(m0.fmt(v))}</span>`).join('');
        } else {
          yRight.innerHTML = '';
        }
      } else {
        yRight.innerHTML = '';
      }
    }

    // 圖例
    const legend = $('sf-leverage-legend');
    if (legend) {
      const metricItems = active.map((m) => {
        const color = T.series[TREND_METRICS.findIndex((tm) => tm.key === m.key) % T.series.length];
        const vals = sorted.map((s) => m.get(s)).filter((v) => Number.isFinite(v));
        const last = vals.length ? vals[vals.length - 1] : null;
        return `<span><span style="color:${color};">━</span> ${esc(m.label)} ${last == null ? '—' : esc(m.fmt(last))}</span>`;
      });
      const lastIdx = filteredIdx.length ? filteredIdx[filteredIdx.length - 1] : null;
      const idxItem = `<span><span style="color:${T.gold};">┄</span> 加權指數 ${lastIdx == null ? '—' : Math.round(lastIdx).toLocaleString('zh-TW')}</span>`;
      legend.innerHTML = [...metricItems, idxItem].join('');
    }
  }

  // ===========================================================
  // 計算 helper：依 metricKey 切換的部位/族群分配
  // ===========================================================

  function positionAllocation(summary, metricKey) {
    const list = (summary || currentSummary || computeSummary()).details || [];
    const map = new Map();
    list.forEach((c) => {
      const value = metricValueOf(c, metricKey);
      if (!value) return;
      const sym = c.product.underlying_symbol || c.product.product_code || c.product.product_id;
      const prev = map.get(sym) || {
        symbol: sym,
        name: c.product.underlying_short_name || c.product.underlying_name || c.product.product_name,
        productName: c.product.product_name,
        value: 0,
      };
      prev.value += value;
      map.set(sym, prev);
    });
    return Array.from(map.values()).sort((a, b) => b.value - a.value);
  }

  function sectorPerformanceMap() {
    const sortedSnaps = snapshots.slice().sort((a, b) => a.date.localeCompare(b.date));
    if (sortedSnaps.length < 2) return {};
    const last = sortedSnaps[sortedSnaps.length - 1];
    const prev = sortedSnaps[sortedSnaps.length - 2];

    // 建立 productId → 昨日 unrealizedPnl 查詢表
    const prevPnlMap = new Map();
    (prev.positionMetrics || []).forEach((m) => {
      if (m && m.productId != null) prevPnlMap.set(m.productId, num(m.unrealizedPnl) ?? 0);
    });

    const sectorPnlChange = new Map();
    const sectorExposure  = new Map();
    (last.positionMetrics || []).forEach((m) => {
      if (!m || !m.underlyingSymbol) return;
      const topic = pickPrimaryTopic(m.underlyingSymbol);
      const lastPnl = num(m.unrealizedPnl);
      const prevPnl = prevPnlMap.has(m.productId) ? prevPnlMap.get(m.productId) : null;
      if (lastPnl != null && prevPnl != null) {
        sectorPnlChange.set(topic, (sectorPnlChange.get(topic) || 0) + (lastPnl - prevPnl));
      }
      sectorExposure.set(topic, (sectorExposure.get(topic) || 0) + Math.abs(num(m.grossExposure) || 0));
    });

    const out = {};
    sectorPnlChange.forEach((pnlChange, topic) => {
      const exposure = sectorExposure.get(topic) || 0;
      out[topic] = exposure ? (pnlChange / exposure) * 100 : 0;
    });
    return out;
  }

  function sectorAllocation(summary, metricKey, withPerf) {
    const list = (summary || currentSummary || computeSummary()).details || [];
    const map = new Map();
    list.forEach((c) => {
      const sym = c.product.underlying_symbol;
      if (!sym) return;
      const topic = pickPrimaryTopic(sym);
      const value = metricValueOf(c, metricKey);
      map.set(topic, (map.get(topic) || 0) + value);
    });
    const perfMap = withPerf ? sectorPerformanceMap() : {};
    const palette = T.series;
    return Array.from(map.entries())
      .filter(([, v]) => v > 0)
      .map(([label, value], i) => ({
        label,
        value,
        color: palette[i % palette.length],
        perf: Number.isFinite(perfMap[label]) ? perfMap[label] : 0,
      }))
      .sort((a, b) => b.value - a.value);
  }

  // ===========================================================
  // KPI Rail / Header / Stats / Liquid 渲染
  // ===========================================================

  const kpiCards = [
    { id: 'equity', label: '帳戶權益', short: 'EQUITY', color: T.navy, accessor: (s) => s.accountEquity, format: (v) => Number.isFinite(v) ? Math.round(v).toLocaleString('zh-TW') : '—' },
    { id: 'gross', label: '總曝險', short: 'GROSS', color: T.up, accessor: (s) => s.grossExposure, format: (v) => Math.round(v || 0).toLocaleString('zh-TW') },
    { id: 'net', label: '淨曝險', short: 'NET', color: T.up, accessor: (s) => s.netExposure, format: (v) => Math.round(v || 0).toLocaleString('zh-TW') },
    { id: 'margin', label: '總保證金', short: 'MARGIN', color: T.gold, accessor: (s) => s.totalMargin, format: (v) => Math.round(v || 0).toLocaleString('zh-TW') },
    { id: 'pnl', label: '未實現損益', short: 'P&L', color: T.up, accessor: (s) => s.unrealizedPnl, format: (v) => Number.isFinite(v) ? fmtMoneySigned(v) : '—' },
  ];

  function renderKpiRail(summary, sorted) {
    const rail = $('sf-kpi-rail');
    if (!rail) return;
    if (!rail.dataset.built) {
      rail.innerHTML = kpiCards.map((card) => `
        <div class="sf-kpi-card" data-kpi="${card.id}">
          <span class="sf-kpi-card__sweep" style="background: linear-gradient(90deg, transparent, ${card.color}, transparent);"></span>
          <div class="sf-kpi-card__head">
            <span class="sf-kpi-card__label">${esc(card.label)}</span>
            <span class="sf-kpi-card__delta sf-kpi-card__delta--muted" data-delta>—</span>
          </div>
          <div class="sf-kpi-card__value" data-value>—</div>
          <div class="sf-kpi-card__spark" data-spark></div>
        </div>
      `).join('');
      rail.dataset.built = '1';
    }
    kpiCards.forEach((card) => {
      const cardEl = rail.querySelector(`[data-kpi="${card.id}"]`);
      if (!cardEl) return;
      const valueEl = cardEl.querySelector('[data-value]');
      const deltaEl = cardEl.querySelector('[data-delta]');
      const sparkEl = cardEl.querySelector('[data-spark]');
      const value = num(card.accessor(summary));
      const series = sorted.map((s) => num(card.accessor(Object.assign({ accountEquity: s.accountEquity }, s.summary))));
      const validSeries = series.filter((v) => Number.isFinite(v));
      const previous = validSeries.length >= 2 ? validSeries[validSeries.length - 2] : (validSeries.length === 1 ? validSeries[0] : null);
      const startVal = Number.isFinite(cardEl._lastValue) ? cardEl._lastValue : (Number.isFinite(value) ? 0 : 0);
      animateNumber(valueEl, startVal, Number.isFinite(value) ? value : 0, { formatter: card.format });
      cardEl._lastValue = Number.isFinite(value) ? value : 0;
      if (card.id === 'pnl') {
        valueEl.classList.toggle('sf-kpi-card__value--up', Number.isFinite(value) && value > 0);
        valueEl.classList.toggle('sf-kpi-card__value--down', Number.isFinite(value) && value < 0);
      }
      if (Number.isFinite(value) && Number.isFinite(previous) && previous !== 0) {
        const deltaPct = ((value - previous) / Math.abs(previous)) * 100;
        const dir = deltaPct > 0 ? 'up' : deltaPct < 0 ? 'down' : 'muted';
        deltaEl.className = `sf-kpi-card__delta sf-kpi-card__delta--${dir}`;
        deltaEl.innerHTML = `<span class="sf-kpi-card__delta-arrow"></span>${dir === 'up' ? '+' : dir === 'down' ? '−' : ''}${Math.abs(deltaPct).toFixed(2)}%`;
      } else {
        deltaEl.className = 'sf-kpi-card__delta sf-kpi-card__delta--muted';
        deltaEl.textContent = '—';
      }
      drawSparkline(sparkEl, validSeries.slice(-12), card.color);
    });
  }

  function renderPortfolioHeader(summary) {
    const sub = $('sf-portfolio-summary');
    if (sub) {
      const equityText = Number.isFinite(num(summary.accountEquity))
        ? `帳戶權益 NT$ ${Math.round(summary.accountEquity).toLocaleString('zh-TW')}`
        : '尚未填入帳戶權益';
      sub.textContent = `股票期貨 · 即時試算 · ${summary.positionCount || 0} 檔持倉 · ${equityText}`;
    }
    const live = $('sf-portfolio-live');
    if (live) {
      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const txt = `LIVE · ${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
      live.textContent = txt;
    }
    document.querySelectorAll('.sf-portfolio-metric button[data-metric]').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.metric === portfolioMetric);
    });
    const meta = METRIC_LABELS[portfolioMetric] || METRIC_LABELS.notional;
    const flowChip = $('sf-flow-metric-chip');
    if (flowChip) {
      flowChip.textContent = `依 ${meta.label}`;
      flowChip.style.color = meta.color;
    }
    const flowSub = $('sf-flow-metric-sub');
    if (flowSub) flowSub.textContent = `SECTOR · ${meta.short}`;
    const donutChip = $('sf-donut-metric-chip');
    if (donutChip) {
      donutChip.textContent = `依 ${meta.label}`;
      donutChip.style.color = meta.color;
    }
    const treeChip = $('sf-tree-metric-chip');
    if (treeChip) {
      treeChip.textContent = `面積：${meta.label}`;
      treeChip.style.color = meta.color;
    }
  }

  // VaR(1d, 95%) 估算
  // - 若 snapshots 有變動：用實測 sigma × 1.65（measured）
  // - 否則：以 2% 日波動率假設做 parametric 估算（fallback）
  // 回傳 { value, mode: 'measured' | 'parametric' | null }
  function estimateVaR(summary) {
    const gross = Math.abs(num(summary.grossExposure) || 0);
    const sortedSnaps = snapshots.slice().sort((a, b) => a.date.localeCompare(b.date)).slice(-20);
    const grossSeries = sortedSnaps.map((s) => num(s.summary.grossExposure)).filter((v) => Number.isFinite(v));
    if (grossSeries.length >= 5) {
      const mean = grossSeries.reduce((s, v) => s + v, 0) / grossSeries.length;
      const variance = grossSeries.reduce((s, v) => s + (v - mean) ** 2, 0) / grossSeries.length;
      const sigma = Math.sqrt(variance);
      // 將快照間波動轉成「曝險百分比變動」，再乘當前曝險，避免常數曝險時 sigma=0
      const meanAbs = Math.abs(mean) || gross || 1;
      const pctSigma = sigma / meanAbs;
      if (pctSigma > 0.001 && gross > 0) {
        return { value: 1.65 * pctSigma * gross, mode: 'measured' };
      }
    }
    if (gross > 0) {
      // Parametric fallback：假設台股期貨 1 日 σ ≈ 2%
      return { value: 1.65 * 0.02 * gross, mode: 'parametric' };
    }
    return { value: 0, mode: null };
  }

  function renderFlowStats(summary) {
    const long = num(summary.totalLong) || 0;
    const short = num(summary.totalShort) || 0;
    const total = long + short;
    const lsEl = $('sf-stats-ls');
    if (lsEl) {
      if (!total) lsEl.textContent = '—';
      else lsEl.innerHTML = `<span style="color: var(--sfA-up);">${((long / total) * 100).toFixed(0)}%</span> / <span style="color: var(--sfA-down);">${((short / total) * 100).toFixed(0)}%</span>`;
    }
    const varEl = $('sf-stats-var');
    if (varEl) {
      const v = estimateVaR(summary);
      if (v.mode == null) {
        varEl.textContent = '尚未持倉';
      } else if (v.mode === 'parametric') {
        varEl.innerHTML = `NT$ ${fmtCompact(v.value)} <small style="font-size: 0.8em; color: var(--sfA-muted); font-weight: 400;">（估算 σ=2%）</small>`;
      } else {
        varEl.innerHTML = `NT$ ${fmtCompact(v.value)} <small style="font-size: 0.8em; color: var(--sfA-muted); font-weight: 400;">（實測）</small>`;
      }
    }
    const pnlEl = $('sf-stats-pnl');
    if (pnlEl) {
      pnlEl.innerHTML = summary.unrealizedPnl == null
        ? '<span style="color: var(--sfA-muted);">—</span>'
        : `<span style="color: ${summary.unrealizedPnl >= 0 ? 'var(--sfA-up)' : 'var(--sfA-down)'};">${fmtMoneySigned(summary.unrealizedPnl)}</span>`;
    }
  }

  function renderLiquidBars(summary) {
    const wrap = $('sf-liquid-list');
    if (!wrap) return;
    const equity = num(summary.accountEquity);
    const margin = num(summary.totalMargin) || 0;
    const marginPct = equity ? Math.min(1, margin / equity) : 0;
    const availPct = equity ? Math.max(0, 1 - marginPct) : 0;
    const v = estimateVaR(summary);
    const varEstimate = v.value;
    const riskPct = equity ? Math.min(1, varEstimate / equity) : 0;
    let riskLabel;
    if (!equity) riskLabel = '請先填帳戶權益';
    else if (v.mode == null) riskLabel = '尚未持倉';
    else if (v.mode === 'parametric') riskLabel = `${(riskPct * 100).toFixed(1)}% · ${fmtCompact(varEstimate)}（估算 σ=2%）`;
    else riskLabel = `${(riskPct * 100).toFixed(1)}% · ${fmtCompact(varEstimate)}（實測）`;
    wrap.innerHTML = '';
    const items = [
      { holder: 'sf-liquid-margin', pct: marginPct, color: T.gold, label: '保證金占用', value: equity ? `${(marginPct * 100).toFixed(0)}% · ${fmtCompact(margin)}` : `${fmtCompact(margin)}` },
      { holder: 'sf-liquid-avail', pct: availPct, color: T.navy, label: '可用資金', value: equity ? `${(availPct * 100).toFixed(0)}% · ${fmtCompact(equity - margin)}` : '請先填帳戶權益' },
      { holder: 'sf-liquid-risk', pct: riskPct, color: T.up, label: '風險係數 (VaR/權益)', value: riskLabel },
    ];
    items.forEach((it) => {
      const slot = document.createElement('div');
      slot.id = it.holder;
      wrap.appendChild(slot);
      drawLiquidBar(slot, it.pct, it.color, it.label, it.value);
    });
    const callEl = $('sf-margin-call');
    const callWrap = $('sf-margin-call-wrap');
    if (callEl && callWrap) {
      if (!equity || !margin) {
        callEl.textContent = '—';
        callWrap.classList.remove('sf-liquid-foot__item--ok', 'sf-liquid-foot__item--warn');
      } else {
        const distance = Math.max(0, 1 - marginPct);
        const ok = distance > 0.3;
        callEl.textContent = ok ? `安全 · 距離 ${(distance * 100).toFixed(0)}%` : `警戒 · 距離 ${(distance * 100).toFixed(0)}%`;
        callWrap.classList.toggle('sf-liquid-foot__item--ok', ok);
        callWrap.classList.toggle('sf-liquid-foot__item--warn', !ok);
      }
    }
    const addRoom = $('sf-add-room');
    if (addRoom) {
      addRoom.textContent = equity ? `NT$ ${fmtCompact(Math.max(0, equity - margin))}` : '—';
    }
  }

  function renderDonutLegend(items, metricKey, donutHandle) {
    const legend = $('sf-donut-legend');
    if (!legend) return;
    const total = items.reduce((s, d) => s + d.value, 0);
    const fmt = metricFormatter(metricKey);
    legend.innerHTML = items.map((d, i) => `
      <div class="sf-donut__legend-row" data-arc-idx="${i}" style="cursor: pointer;">
        <span class="sf-donut__legend-chip" style="background: ${d.color};"></span>
        <span title="${esc(d.label)}">${esc(d.label)} <strong>${total ? ((d.value / total) * 100).toFixed(1) : '0.0'}%</strong></span>
        <em>${fmt(d.value)}</em>
      </div>
    `).join('') || '<div class="sf-portfolio-empty">尚無持倉</div>';
    const countChip = $('sf-donut-count');
    if (countChip) countChip.textContent = `${items.length} 檔`;
    if (donutHandle) {
      legend.querySelectorAll('.sf-donut__legend-row[data-arc-idx]').forEach((row) => {
        const idx = Number(row.dataset.arcIdx);
        row.addEventListener('mouseenter', () => donutHandle.activate(idx));
        row.addEventListener('mouseleave', () => donutHandle.deactivate());
        row.addEventListener('focus', () => donutHandle.activate(idx));
        row.addEventListener('blur', () => donutHandle.deactivate());
      });
    }
  }

  function renderPortfolio() {
    if (!document.querySelector('[data-body="portfolio"]')) return;
    const summary = currentSummary || computeSummary();
    const sorted = snapshots.slice().sort((a, b) => a.date.localeCompare(b.date));
    renderPortfolioHeader(summary);
    renderKpiRail(summary, sorted);
    bindTrendToggles();
    drawLeverageTrend($('sf-leverage-trend'), sorted);
    drawGauge($('sf-gauge-equity'), summary.equityLeverage || 0, 5, T.navy);
    drawGauge($('sf-gauge-margin'), summary.marginLeverage || 0, 15, T.gold);
    const flow = sectorAllocation(summary, portfolioMetric);
    drawFlowBar($('sf-flowbar'), flow);
    const flowLegend = $('sf-flow-legend');
    if (flowLegend) {
      const fmt = metricFormatter(portfolioMetric);
      flowLegend.innerHTML = flow.length
        ? flow.map((f) => `<span class="sf-flow-legend__item"><span class="sf-flow-legend__chip" style="background:${f.color};"></span>${esc(f.label)} · ${fmt(f.value)}</span>`).join('')
        : '<span class="sf-flow-legend__item" style="color: var(--sfA-muted);">尚未持倉</span>';
    }
    renderFlowStats(summary);
    const allocation = positionAllocation(summary, portfolioMetric)
      .map((d, i) => ({ label: `${d.symbol} ${d.name || d.productName || ''}`.trim(), value: d.value, color: T.series[i % T.series.length] }));
    const donutHandle = drawDonut($('sf-donut'), allocation, {
      formatter: metricFormatter(portfolioMetric),
      totalLabel: `總計 · ${METRIC_LABELS[portfolioMetric].label}`,
    });
    renderDonutLegend(allocation, portfolioMetric, donutHandle);
    renderLiquidBars(summary);
    drawTreemap($('sf-treemap'), sectorAllocation(summary, portfolioMetric, true));
    renderSnapshotTable();
  }

  function bindTrendToggles() {
    const container = $('sf-trend-toggles');
    if (!container) return;
    container.innerHTML = TREND_METRICS.map((m) =>
      `<button class="sf-trend-toggle${activeTrendMetrics.has(m.key) ? ' active' : ''}" data-trend="${esc(m.key)}">${esc(m.label)}</button>`
    ).join('');
    container.querySelectorAll('[data-trend]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const k = btn.dataset.trend;
        if (activeTrendMetrics.has(k)) {
          if (activeTrendMetrics.size > 1) activeTrendMetrics.delete(k);
        } else {
          activeTrendMetrics.add(k);
        }
        try { localStorage.setItem(trendMetricKey, JSON.stringify([...activeTrendMetrics])); } catch { /* ignore */ }
        container.querySelectorAll('[data-trend]').forEach((b) =>
          b.classList.toggle('active', activeTrendMetrics.has(b.dataset.trend))
        );
        const sorted = snapshots.slice().sort((a, b) => a.date.localeCompare(b.date));
        drawLeverageTrend($('sf-leverage-trend'), sorted);
      });
    });
  }

  function bindPortfolioMetric() {
    document.querySelectorAll('.sf-portfolio-metric button[data-metric]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const next = btn.dataset.metric;
        if (!next || !METRIC_LABELS[next] || next === portfolioMetric) return;
        portfolioMetric = next;
        try { localStorage.setItem(portfolioMetricKey, portfolioMetric); } catch { /* ignore */ }
        renderPortfolio();
      });
    });
  }

  function compareValue(row, key) {
    const value = row[key];
    if (typeof value === 'string') return value;
    const n = num(value);
    return n == null ? -Infinity : n;
  }

  function passesRankFilters(row) {
    const q = $('sf-rank-search').value.trim().toLowerCase();
    if (q && !(row.search_key || '').includes(q)) return false;
    const type = $('sf-rank-type').value;
    if (type && row.category !== type) return false;
    const volumeMin = num($('sf-volume-min').value);
    if (volumeMin != null && (num(row.volume) || 0) < volumeMin) return false;
    const oiMin = num($('sf-oi-min').value);
    if (oiMin != null && (num(row.open_interest) || 0) < oiMin) return false;
    const marginMax = num($('sf-margin-max').value);
    if (marginMax != null && (num(row.initial_margin) || Infinity) > marginMax) return false;
    const levMin = num($('sf-leverage-min').value);
    if (levMin != null && (num(row.leverage) || 0) < levMin) return false;
    const field = $('sf-filter-field').value;
    const op = $('sf-filter-op').value;
    const filterValue = $('sf-filter-value').value.trim();
    if (field && filterValue) {
      const raw = row[field];
      if (op === 'contains') {
        if (!String(raw == null ? '' : raw).toLowerCase().includes(filterValue.toLowerCase())) return false;
      } else {
        const left = num(raw);
        const right = num(filterValue);
        if (left == null || right == null) return false;
        if (op === 'eq' && left !== right) return false;
        if (op === 'gte' && left < right) return false;
        if (op === 'lte' && left > right) return false;
      }
    }
    return true;
  }

  function renderRanking() {
    const tbody = document.querySelector('#sf-ranking-table tbody');
    if (!tbody) return;
    const filtered = rankingProducts.filter(passesRankFilters).sort((a, b) => {
      const av = compareValue(a, rankSort.key);
      const bv = compareValue(b, rankSort.key);
      if (typeof av === 'string' || typeof bv === 'string') return String(av).localeCompare(String(bv), 'zh-Hant') * rankSort.dir;
      return (av - bv) * rankSort.dir;
    });
    $('sf-rank-count').textContent = `${filtered.length} 筆`;
    tbody.innerHTML = filtered.map((row) => `
      <tr>
        <td><strong>${esc(row.product_name)}</strong><small>${esc(row.contract_month || '')} ${esc(row.type_label || '')}</small></td>
        <td>${price(row.future_price)}</td>
        <td>${signed(row.change, (n) => `${n >= 0 ? '+' : ''}${price(n)}`)}</td>
        <td>${signed(row.change_pct, pct)}</td>
        <td>${money(row.volume)}</td>
        <td>${money(row.avg_volume_20d)}${row.avg_volume_days && row.avg_volume_days < 20 ? `<small>${row.avg_volume_days}日</small>` : ''}</td>
        <td>${pct(row.amplitude)}</td>
        <td>${money(row.open_interest)}</td>
        <td${row.open_interest_change == null ? ' title="歷史快照需 ≥2 個交易日才能計算"' : ''}>${signed(row.open_interest_change, money)}</td>
        <td><strong>${esc(row.underlying_symbol)}</strong><small>${esc(row.underlying_short_name || '')}</small></td>
        <td>${price(row.spot_price)}</td>
        <td>${signed(row.basis, (n) => `${n >= 0 ? '+' : ''}${price(n)}`)}</td>
        <td>${money(row.initial_margin)}</td>
        <td>${money(row.contract_multiplier)}</td>
        <td><strong>${leverage(row.leverage)}</strong></td>
      </tr>
    `).join('') || '<tr><td colspan="15" class="muted">沒有符合條件的商品</td></tr>';
    document.querySelectorAll('#sf-ranking-table th[data-sort]').forEach((th) => {
      th.classList.toggle('active', th.dataset.sort === rankSort.key);
      th.dataset.dir = th.dataset.sort === rankSort.key ? (rankSort.dir === -1 ? 'desc' : 'asc') : '';
    });
  }

  function downloadText(filename, text, type) {
    const blob = new Blob([text], { type: type || 'text/plain;charset=utf-8' });
    downloadBlob(filename, blob);
  }

  function downloadBlob(filename, blob) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function exportJson() {
    const data = {
      version: 2,
      exportedAt: new Date().toISOString(),
      accountEquity: num($('sf-account-equity') && $('sf-account-equity').value),
      positions,
      snapshots,
      productsAsOf: payload.as_of || '',
    };
    downloadText(`stock-futures-backup-${todayIso()}.json`, JSON.stringify(data, null, 2), 'application/json;charset=utf-8');
    setStatus('完整 JSON 已匯出');
  }

  function snapshotOverviewRow(snap) {
    return {
      '日期': snap.date,
      '帳戶權益': snap.accountEquity,
      '總多方曝險': snap.summary.totalLong,
      '總空方曝險': snap.summary.totalShort,
      '總曝險': snap.summary.grossExposure,
      '淨曝險': snap.summary.netExposure,
      '總保證金': snap.summary.totalMargin,
      '保證金使用率': snap.summary.marginUsage,
      '保證金槓桿': snap.summary.marginLeverage,
      '權益槓桿': snap.summary.equityLeverage,
      '1% 損益': snap.summary.onePctPnl,
      '未實現損益': snap.summary.unrealizedPnl,
      '損益%': snap.summary.unrealizedPnlPct,
      '加權指數': snap.marketIndices && snap.marketIndices.taiex,
      '櫃買指數': snap.marketIndices && snap.marketIndices.tpex,
    };
  }

  function metricForPosition(snap, pos, idx) {
    const metrics = Array.isArray(snap.positionMetrics) ? snap.positionMetrics : [];
    return metrics[idx] || metrics.find((item) => item.productId === pos.productId) || {};
  }

  function snapshotPositionRows(snap) {
    return (snap.positions || []).map((pos, idx) => {
      const metric = metricForPosition(snap, pos, idx);
      const product = byId.get(pos.productId) || {};
      return {
        '日期': snap.date,
        '商品': metric.productName || product.product_name || '',
        '商品代碼': metric.productId || pos.productId || product.product_id || product.product_code || '',
        '方向': (metric.direction || pos.direction) === 'short' ? '賣出(空)' : '買進(多)',
        '目標曝險': pos.targetExposure,
        '手動口數': pos.manualLots,
        '使用口數': metric.lots,
        '期貨市價': metric.futurePrice,
        '持倉價格': pos.holdingPrice,
        '未實現損益': metric.unrealizedPnl,
        '損益%': metric.unrealizedPnlPct,
        '契約乘數': metric.contractMultiplier,
        '單口保證金': metric.initialMargin,
        '總保證金': metric.totalMargin,
        '名目曝險': metric.grossExposure,
        '淨曝險': metric.netExposure,
        '成交量': product.volume,
        '未平倉 OI': product.open_interest,
        '標的代號': metric.underlyingSymbol || product.underlying_symbol || '',
        '標的名稱': metric.underlyingName || product.underlying_short_name || product.underlying_name || '',
        '備註': pos.note || '',
      };
    });
  }

  function exportXlsx() {
    if (!snapshots.length) {
      setStatus('沒有快照可匯出，請先儲存快照');
      return;
    }
    if (!window.StockFuturesXlsx) {
      setStatus('XLSX 工具尚未載入');
      return;
    }
    const sorted = snapshots.slice().sort((a, b) => a.date.localeCompare(b.date));
    const overviewHeaders = ['日期', '帳戶權益', '總多方曝險', '總空方曝險', '總曝險', '淨曝險', '總保證金', '保證金使用率', '保證金槓桿', '權益槓桿', '1% 損益', '未實現損益', '損益%', '加權指數', '櫃買指數'];
    const detailHeaders = ['日期', '商品', '商品代碼', '方向', '目標曝險', '手動口數', '使用口數', '期貨市價', '持倉價格', '未實現損益', '損益%', '契約乘數', '單口保證金', '總保證金', '名目曝險', '淨曝險', '成交量', '未平倉 OI', '標的代號', '標的名稱', '備註'];
    const blob = window.StockFuturesXlsx.writeWorkbook([
      { name: '歷史總覽', headers: overviewHeaders, rows: sorted.map(snapshotOverviewRow) },
      { name: '每日持倉明細', headers: detailHeaders, rows: sorted.flatMap(snapshotPositionRows) },
    ]);
    downloadBlob(`stock-futures-history-${todayIso()}.xlsx`, blob);
    setStatus('Excel 歷史明細 XLSX 已匯出');
  }

  function dateText(value) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      const ms = Date.UTC(1899, 11, 30) + Math.round(value) * 86400000;
      const d = new Date(ms);
      return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
    }
    return String(value == null ? '' : value).trim().slice(0, 10);
  }

  function findProductId(code, symbol, name) {
    const c = String(code || '').trim();
    if (c && byId.has(c)) return c;
    const found = products.find((row) => {
      if (c && (row.product_id === c || row.product_code === c)) return true;
      if (symbol && row.underlying_symbol === String(symbol).trim() && (!name || String(row.product_name || '').includes(String(name).trim()))) return true;
      return false;
    });
    return found ? found.product_id : c;
  }

  function directionFromText(value) {
    const text = String(value || '').toLowerCase();
    return text.includes('short') || text.includes('賣') || text.includes('空') ? 'short' : 'long';
  }

  function overviewSnapshotFromRow(row) {
    const date = dateText(row['日期'] || row.date);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
    return normalizeSnapshot({
      date,
      source: 'xlsx',
      savedAt: new Date().toISOString(),
      accountEquity: importNum(row['帳戶權益']),
      summary: {
        totalLong: importNum(row['總多方曝險']),
        totalShort: importNum(row['總空方曝險']),
        grossExposure: importNum(row['總曝險']),
        netExposure: importNum(row['淨曝險']),
        totalMargin: importNum(row['總保證金']),
        marginUsage: importNum(row['保證金使用率']),
        marginLeverage: importNum(row['保證金槓桿']),
        equityLeverage: importNum(row['權益槓桿']),
        onePctPnl: importNum(row['1% 損益'] || row['1%損益']),
        positionCount: 0,
        unrealizedPnl: importNum(row['未實現損益']),
        unrealizedPnlPct: importNum(row['損益%']),
      },
      positions: [],
      positionMetrics: [],
      marketIndices: {
        date,
        taiex: importNum(row['加權指數']),
        tpex: importNum(row['櫃買指數']),
      },
    });
  }

  function detailFromRow(row, idx) {
    const date = dateText(row['日期'] || row.date);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
    const productId = findProductId(row['商品代碼'], row['標的代號'], row['商品']);
    if (!productId) return null;
    const product = byId.get(productId) || {};
    const direction = directionFromText(row['方向']);
    const usedLots = lots(row['使用口數']);
    const futurePrice = num(row['期貨市價']);
    const multiplier = num(row['契約乘數']);
    const initialMargin = num(row['單口保證金']);
    const totalMargin = num(row['總保證金']) ?? ((usedLots || 0) * (initialMargin || 0));
    const grossExposure = num(row['名目曝險']) ?? ((usedLots || 0) * (futurePrice || 0) * (multiplier || 0));
    const netExposure = num(row['淨曝險']) ?? (direction === 'short' ? -grossExposure : grossExposure);
    const holdingPrice = num(row['持倉價格']);
    const unrealizedPnl = num(row['未實現損益']) ?? (
      holdingPrice == null || futurePrice == null || !usedLots
        ? null
        : (futurePrice - holdingPrice) * (multiplier || 0) * usedLots * (direction === 'short' ? -1 : 1)
    );
    const costBasisAbs = (holdingPrice == null || !usedLots) ? null : Math.abs(holdingPrice * (multiplier || 0) * usedLots);
    const unrealizedPnlPct = importNum(row['損益%']) ?? (
      unrealizedPnl == null || !costBasisAbs ? null : unrealizedPnl / costBasisAbs
    );
    return {
      date,
      position: normalizePosition({
        id: `${date}-${productId}-${idx}`,
        productId,
        direction,
        targetExposure: num(row['目標曝險']),
        manualLots: lots(row['手動口數']),
        holdingPrice,
        note: row['備註'] || '',
      }),
      metric: {
        productId,
        productName: row['商品'] || product.product_name || '',
        underlyingSymbol: row['標的代號'] || product.underlying_symbol || '',
        underlyingName: row['標的名稱'] || product.underlying_short_name || product.underlying_name || '',
        direction,
        lots: usedLots,
        futurePrice,
        initialMargin,
        contractMultiplier: multiplier,
        grossExposure,
        netExposure,
        totalMargin,
        holdingPrice,
        unrealizedPnl,
        unrealizedPnlPct,
      },
    };
  }

  function fillSummaryFromMetrics(snapshot) {
    if (!snapshot.positionMetrics.length || snapshot.summary.grossExposure) return snapshot;
    let totalLong = 0;
    let totalShort = 0;
    let totalMargin = 0;
    let net = 0;
    let unrealizedPnl = 0;
    let costBasis = 0;
    let pnlCount = 0;
    snapshot.positionMetrics.forEach((metric) => {
      const exposure = num(metric.netExposure) || 0;
      if (exposure >= 0) totalLong += exposure;
      else totalShort += Math.abs(exposure);
      totalMargin += num(metric.totalMargin) || 0;
      net += exposure;
      const pnl = num(metric.unrealizedPnl);
      if (pnl != null) {
        unrealizedPnl += pnl;
        pnlCount += 1;
        const cost = num(metric.holdingPrice);
        const mult = num(metric.contractMultiplier) || 0;
        const lt = num(metric.lots) || 0;
        if (cost != null && mult && lt) costBasis += Math.abs(cost * mult * lt);
      }
    });
    const gross = totalLong + totalShort;
    snapshot.summary.totalLong = totalLong;
    snapshot.summary.totalShort = totalShort;
    snapshot.summary.grossExposure = gross;
    snapshot.summary.netExposure = net;
    snapshot.summary.totalMargin = totalMargin;
    snapshot.summary.marginUsage = snapshot.accountEquity && totalMargin ? totalMargin / snapshot.accountEquity : snapshot.summary.marginUsage;
    snapshot.summary.marginLeverage = totalMargin ? gross / totalMargin : snapshot.summary.marginLeverage;
    snapshot.summary.equityLeverage = snapshot.accountEquity ? gross / snapshot.accountEquity : snapshot.summary.equityLeverage;
    snapshot.summary.onePctPnl = net * 0.01;
    if (pnlCount && snapshot.summary.unrealizedPnl == null) {
      snapshot.summary.unrealizedPnl = unrealizedPnl;
      snapshot.summary.unrealizedPnlPct = costBasis ? unrealizedPnl / costBasis : null;
    }
    return snapshot;
  }

  async function importXlsx(buffer) {
    if (!window.StockFuturesXlsx) throw new Error('XLSX 工具尚未載入');
    const sheets = await window.StockFuturesXlsx.readWorkbook(buffer);
    const overviewRows = sheets['歷史總覽'] || [];
    const detailRows = sheets['每日持倉明細'] || [];
    const map = new Map();
    overviewRows.forEach((row) => {
      const snap = overviewSnapshotFromRow(row);
      if (snap) map.set(snap.date, snap);
    });
    detailRows.map(detailFromRow).filter(Boolean).forEach((item) => {
      const snap = map.get(item.date) || normalizeSnapshot({
        date: item.date,
        source: 'xlsx',
        savedAt: new Date().toISOString(),
        positions: [],
        positionMetrics: [],
        summary: {},
        marketIndices: { date: item.date },
      });
      snap.positions.push(item.position);
      snap.positionMetrics.push(item.metric);
      snap.summary.positionCount = snap.positions.length;
      map.set(item.date, snap);
    });
    const imported = Array.from(map.values()).map(fillSummaryFromMetrics);
    const result = await applyImportedSnapshots(imported, 'XLSX');
    if (result.cancelled) {
      setStatus('已取消匯入');
      return;
    }
    renderPortfolio();
    setStatus(`XLSX 已匯入 ${imported.length} 筆快照，含 ${detailRows.length} 筆持倉明細（${result.modeLabel}）`);
  }

  function mergeSnapshots(importedSnapshots) {
    const map = new Map(snapshots.map((snap) => [snap.date, snap]));
    importedSnapshots.map(normalizeSnapshot).forEach((snap) => map.set(snap.date, snap));
    snapshots = Array.from(map.values()).sort((a, b) => a.date.localeCompare(b.date));
    saveSnapshots();
  }

  function replaceSnapshots(importedSnapshots) {
    snapshots = importedSnapshots.map(normalizeSnapshot).sort((a, b) => a.date.localeCompare(b.date));
    saveSnapshots();
  }

  // 統一的匯入入口：偵測衝突 → 詢問模式 → 應用
  // result: { cancelled: bool, mode: 'replace'|'merge', modeLabel: '完整覆蓋'|'合併保留' }
  async function applyImportedSnapshots(importedSnaps, sourceTag) {
    const importDates = new Set(importedSnaps.map((s) => s.date));
    const residualDates = snapshots.map((s) => s.date).filter((d) => !importDates.has(d));
    if (residualDates.length === 0) {
      // 無衝突：直接合併（沒差別）
      mergeSnapshots(importedSnaps);
      return { cancelled: false, mode: 'merge', modeLabel: '合併' };
    }
    const choice = await showImportConflictDialog({
      sourceTag,
      importCount: importedSnaps.length,
      importDates: Array.from(importDates).sort(),
      residualDates: residualDates.sort(),
    });
    if (choice === 'cancel') return { cancelled: true };
    if (choice === 'replace') {
      replaceSnapshots(importedSnaps);
      return { cancelled: false, mode: 'replace', modeLabel: '完整覆蓋' };
    }
    mergeSnapshots(importedSnaps);
    return { cancelled: false, mode: 'merge', modeLabel: '合併保留' };
  }

  function showImportConflictDialog({ sourceTag, importCount, importDates, residualDates }) {
    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.className = 'sf-modal-overlay';
      const importRange = importDates.length
        ? `${importDates[0]} ~ ${importDates[importDates.length - 1]}`
        : '（空）';
      const residualPreview = residualDates.slice(0, 5).join('、') + (residualDates.length > 5 ? ` 等 ${residualDates.length} 筆` : '');
      overlay.innerHTML = `
        <div class="sf-modal" role="dialog" aria-modal="true">
          <h3 class="sf-modal__title">匯入${esc(sourceTag)}：偵測到衝突</h3>
          <div class="sf-modal__body">
            <p>本次匯入包含 <strong>${importCount}</strong> 筆快照（${esc(importRange)}）。</p>
            <p>本機目前還有 <strong>${residualDates.length}</strong> 筆快照不在這次匯入範圍：</p>
            <p class="sf-modal__residual">${esc(residualPreview)}</p>
            <p class="sf-modal__hint">你想怎麼處理？</p>
          </div>
          <div class="sf-modal__actions">
            <button type="button" class="sf-text-btn" data-choice="cancel">取消匯入</button>
            <button type="button" class="sf-text-btn" data-choice="merge">合併保留<small>（保留現有 + 加入匯入）</small></button>
            <button type="button" class="sf-add-btn" data-choice="replace">完整覆蓋<small>（清空現有，只留匯入內容）</small></button>
          </div>
        </div>
      `;
      document.body.appendChild(overlay);
      const close = (choice) => {
        document.body.removeChild(overlay);
        resolve(choice);
      };
      overlay.querySelectorAll('[data-choice]').forEach((btn) => {
        btn.addEventListener('click', () => close(btn.dataset.choice));
      });
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close('cancel');
      });
      const onKey = (e) => {
        if (e.key === 'Escape') {
          document.removeEventListener('keydown', onKey);
          close('cancel');
        }
      };
      document.addEventListener('keydown', onKey);
    });
  }

  async function importJson(text) {
    const data = JSON.parse(text);
    let posReplaced = false;
    if (Array.isArray(data.positions)) {
      positions = data.positions.map(normalizePosition).filter((pos) => byId.has(pos.productId));
      savePositions();
      posReplaced = true;
    }
    let snapResult = null;
    if (Array.isArray(data.snapshots)) {
      const imported = data.snapshots.map((snap) => Object.assign({}, snap, { source: snap.source || 'json' }));
      snapResult = await applyImportedSnapshots(imported, 'JSON');
      if (snapResult.cancelled) {
        setStatus('已取消快照匯入（部位仍以匯入為準）');
        if (posReplaced) renderPositions();
        return;
      }
    }
    if (data.accountEquity != null && $('sf-account-equity')) {
      $('sf-account-equity').value = data.accountEquity;
      localStorage.setItem(equityKey, String(data.accountEquity));
    }
    renderPositions();
    renderPortfolio();
    const tag = snapResult ? `（快照 ${snapResult.modeLabel}）` : '';
    setStatus(`完整 JSON 已匯入${tag}`);
  }

  function handleImport(file) {
    if (!file) return;
    const lowerName = file.name.toLowerCase();
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        if (lowerName.endsWith('.xlsx')) await importXlsx(reader.result);
        else {
          const text = String(reader.result || '');
          importJson(text);
        }
      } catch (err) {
        setStatus(`匯入失敗：${err.message || err}`);
      }
    };
    if (lowerName.endsWith('.xlsx')) reader.readAsArrayBuffer(file);
    else reader.readAsText(file, 'utf-8');
  }

  tabs.forEach((btn) => btn.addEventListener('click', () => {
    tabs.forEach((t) => t.classList.remove('active'));
    btn.classList.add('active');
    bodies.forEach((body) => { body.hidden = body.dataset.body !== btn.dataset.tab; });
    if (btn.dataset.tab === 'portfolio') renderPortfolio();
  }));

  if ($('sf-account-equity')) {
    $('sf-account-equity').value = localStorage.getItem(equityKey) || '';
    $('sf-account-equity').addEventListener('input', () => {
      localStorage.setItem(equityKey, $('sf-account-equity').value);
      // 不重建表格（避免 caret 重置）— 只刷新 KPI + portfolio
      refreshSummaryKpis();
      const portfolioBody = document.querySelector('[data-body="portfolio"]');
      if (portfolioBody && !portfolioBody.hidden) renderPortfolio();
    });
  }
  if ($('sf-backfill-date')) $('sf-backfill-date').max = todayIso();
  if ($('sf-product-query')) {
    $('sf-product-query').addEventListener('input', renderMatches);
    $('sf-product-query').addEventListener('focus', renderMatches);
  }
  if ($('sf-add-position')) $('sf-add-position').addEventListener('click', addPosition);
  if ($('sf-clear-positions')) $('sf-clear-positions').addEventListener('click', () => {
    positions = [];
    savePositions();
    renderPositions();
    setStatus('目前部位已清空');
  });
  if ($('sf-save-today')) $('sf-save-today').addEventListener('click', () => saveSnapshotForDate(todayIso(), 'manual'));
  if ($('sf-save-backfill')) $('sf-save-backfill').addEventListener('click', () => saveSnapshotForDate($('sf-backfill-date').value, 'manual'));
  if ($('sf-open-historic-price')) $('sf-open-historic-price').addEventListener('click', openHistoricPanel);
  if ($('sf-historic-cancel')) $('sf-historic-cancel').addEventListener('click', closeHistoricPanel);
  if ($('sf-historic-save')) $('sf-historic-save').addEventListener('click', saveHistoricSnapshot);
  if ($('sf-historic-correct-btn')) $('sf-historic-correct-btn').addEventListener('click', showHistoricCorrectModal);
  if ($('sf-clear-snapshots-btn')) {
    let clearPending = false;
    let clearTimer = null;
    $('sf-clear-snapshots-btn').addEventListener('click', () => {
      if (!snapshots.length) return;
      if (!clearPending) {
        clearPending = true;
        $('sf-clear-snapshots-btn').textContent = '確定清空？再按一次確認';
        $('sf-clear-snapshots-btn').style.background = '#dc2626';
        $('sf-clear-snapshots-btn').style.color = '#fff';
        clearTimer = setTimeout(() => {
          clearPending = false;
          $('sf-clear-snapshots-btn').textContent = '清空快照';
          $('sf-clear-snapshots-btn').style.background = '';
          $('sf-clear-snapshots-btn').style.color = '';
        }, 3000);
      } else {
        clearTimeout(clearTimer);
        snapshots = [];
        saveSnapshots();
        renderPortfolio();
      }
    });
  }
  if ($('sf-export-json')) $('sf-export-json').addEventListener('click', exportJson);
  if ($('sf-export-xlsx')) $('sf-export-xlsx').addEventListener('click', exportXlsx);
  if ($('sf-import-trigger')) $('sf-import-trigger').addEventListener('click', () => $('sf-import-file').click());
  if ($('sf-import-file')) $('sf-import-file').addEventListener('change', (event) => {
    handleImport(event.target.files && event.target.files[0]);
    event.target.value = '';
  });

  ['sf-rank-search', 'sf-rank-type', 'sf-volume-min', 'sf-oi-min', 'sf-margin-max', 'sf-leverage-min', 'sf-filter-field', 'sf-filter-op', 'sf-filter-value'].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', renderRanking);
  });
  if ($('sf-rank-sort')) $('sf-rank-sort').addEventListener('change', () => {
    rankSort = { key: $('sf-rank-sort').value, dir: -1 };
    renderRanking();
  });
  document.querySelectorAll('#sf-ranking-table th[data-sort]').forEach((th) => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      rankSort = { key, dir: rankSort.key === key ? rankSort.dir * -1 : -1 };
      renderRanking();
    });
  });

  bindPortfolioMetric();
  renderMatches();
  renderPositions();
  renderRanking();
  renderPortfolio();
})();
