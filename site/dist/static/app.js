// ═══════════════════════════════════════════
//   族群寶 - 搜尋 autocomplete + 互動
//   支援多個搜尋框（header global-search + 首頁 hero-search）
// ═══════════════════════════════════════════

(function() {
  const pairs = [
    ['global-search', 'search-dropdown'],
    ['hero-search',   'hero-search-dropdown'],
  ].map(([i, d]) => [document.getElementById(i), document.getElementById(d)])
   .filter(([i, d]) => i && d);
  if (!pairs.length) return;

  let SEARCH_DATA = [];

  function waitForData(cb, tries) {
    tries = tries || 0;
    if (window.SEARCH_DATA && Array.isArray(window.SEARCH_DATA)) {
      SEARCH_DATA = window.SEARCH_DATA;
      SEARCH_DATA.forEach(it => { it._k = (it.keywords || it.label).toLowerCase(); });
      cb();
    } else if (tries < 50) {
      setTimeout(() => waitForData(cb, tries + 1), 80);
    } else {
      console.warn('SEARCH_DATA 載入逾時');
    }
  }

  function setupSearch(input, dropdown) {
    let activeIdx = -1;
    let currentResults = [];

    function filter(q) {
      if (!q) return [];
      q = q.toLowerCase().trim();
      const tokens = q.split(/\s+/).filter(Boolean);
      return SEARCH_DATA.filter(it =>
        tokens.every(t => it._k.includes(t))
      ).slice(0, 20);
    }

    function render(results) {
      currentResults = results;
      activeIdx = -1;
      if (!results.length) {
        dropdown.innerHTML = '<div class="search-item muted first">找不到相符結果</div>';
        dropdown.hidden = false;
        return;
      }
      const topics = results.filter(r => r.type === 'topic');
      const companies = results.filter(r => r.type === 'company');
      const parts = [];
      if (topics.length) {
        parts.push('<div class="search-section-title">題材 / 族群</div>');
        topics.forEach((t) => {
          parts.push(`<a class="search-item" data-href="${window.STATIC_PREFIX}${t.href}" data-idx="${results.indexOf(t)}">
            <strong>${t.label}</strong><small>${t.sub || ''}</small></a>`);
        });
      }
      if (companies.length) {
        parts.push('<div class="search-section-title">公司 / 個股</div>');
        companies.forEach((c) => {
          parts.push(`<a class="search-item" data-href="${window.STATIC_PREFIX}${c.href}" data-idx="${results.indexOf(c)}">
            <strong>${c.label}</strong><small>${c.sub || ''}</small></a>`);
        });
      }
      dropdown.innerHTML = parts.join('');
      dropdown.hidden = false;

      dropdown.querySelectorAll('.search-item').forEach(el => {
        el.addEventListener('mousedown', (e) => {
          e.preventDefault();
          if (el.dataset.href) window.location.href = el.dataset.href;
        });
        el.addEventListener('mouseenter', () => {
          dropdown.querySelectorAll('.search-item').forEach(x => x.classList.remove('active'));
          el.classList.add('active');
          activeIdx = parseInt(el.dataset.idx || -1, 10);
        });
      });
    }

    let debounce;
    input.addEventListener('input', () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => {
        render(filter(input.value));
      }, 80);
    });

    input.addEventListener('focus', () => {
      if (input.value) render(filter(input.value));
    });

    document.addEventListener('click', (e) => {
      if (!e.target.closest('.search-box') && !e.target.closest('.hero-search-box')) {
        dropdown.hidden = true;
      }
    });

    input.addEventListener('keydown', (e) => {
      if (!currentResults.length) return;
      const items = Array.from(dropdown.querySelectorAll('.search-item[data-href]'));
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        activeIdx = Math.min(activeIdx + 1, items.length - 1);
        items.forEach(x => x.classList.remove('active'));
        if (items[activeIdx]) items[activeIdx].classList.add('active');
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        activeIdx = Math.max(activeIdx - 1, 0);
        items.forEach(x => x.classList.remove('active'));
        if (items[activeIdx]) items[activeIdx].classList.add('active');
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (items[activeIdx]) window.location.href = items[activeIdx].dataset.href;
        else if (items[0]) window.location.href = items[0].dataset.href;
      } else if (e.key === 'Escape') {
        dropdown.hidden = true;
        input.blur();
      }
    });
  }

  waitForData(() => {
    pairs.forEach(([i, d]) => setupSearch(i, d));
  });

  // 快捷鍵 '/' 聚焦到第一個可用搜尋框（優先 hero）
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
      e.preventDefault();
      const first = document.getElementById('hero-search') || document.getElementById('global-search');
      if (first) first.focus();
    }
  });

  // Nav dropdown（position:fixed 繞過 overflow 截斷，JS 計算座標）
  document.querySelectorAll('.nav-dropdown').forEach(wrapper => {
    const menu = wrapper.querySelector('.nav-dropdown-menu');
    if (!menu) return;
    let timer;
    function showMenu() {
      clearTimeout(timer);
      const r = wrapper.getBoundingClientRect();
      menu.style.top = (r.bottom + 2) + 'px';
      menu.style.left = r.left + 'px';
      menu.style.display = 'block';
    }
    wrapper.addEventListener('mouseenter', showMenu);
    wrapper.addEventListener('mouseleave', () => { timer = setTimeout(() => { menu.style.display = ''; }, 120); });
    menu.addEventListener('mouseenter', () => clearTimeout(timer));
    menu.addEventListener('mouseleave', () => { timer = setTimeout(() => { menu.style.display = ''; }, 120); });
  });
})();

/* ───── 網站更新公告 + 新手導覽 loader ─────
 * 動態注入 driver.js / onboarding 相關資源，避免每個獨立 template 都要改 head/body。
 * 跳過 admin 後台路徑（沿用 login-button.js 同款 guard）。
 */
(function loadOnboarding() {
  if (location.pathname.startsWith("/admin/")) return;
  const prefix = window.STATIC_PREFIX || "";
  const head = document.head;
  // cache-bust：每小時換一次 query，避免改完不生效
  const v = new Date().toISOString().slice(0, 13).replace(/[-T]/g, "");

  function injectLink(href) {
    if (document.querySelector('link[href="' + href + '"]')) return;
    const l = document.createElement("link");
    l.rel = "stylesheet";
    l.href = href;
    head.appendChild(l);
  }
  function injectScript(src, onload) {
    if (document.querySelector('script[src="' + src + '"]')) {
      if (onload) onload();
      return;
    }
    const s = document.createElement("script");
    s.src = src;
    s.defer = true;
    if (onload) s.addEventListener("load", onload);
    head.appendChild(s);
  }

  injectLink(prefix + "static/onboarding.css?v=" + v);
  injectLink("https://cdn.jsdelivr.net/npm/driver.js@1.3.1/dist/driver.css");
  injectScript("https://cdn.jsdelivr.net/npm/driver.js@1.3.1/dist/driver.js.iife.js", function () {
    injectScript(prefix + "static/onboarding.js?v=" + v);
  });
})();
