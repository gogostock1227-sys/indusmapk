/**
 * 族群寶 — 網站更新公告 Modal + 新手導覽教學
 *
 * 行為：
 *   - 只在首頁觸發（避免在中間頁面被打擾）
 *   - 每天首訪 OR 有新版本時，自動彈出「網站更新」modal
 *   - 首次造訪用戶，關閉 modal 後自動啟動 driver.js 導覽
 *   - 用戶可勾選「不再顯示此通知」永久 opt-out
 *   - 老用戶可從 modal 內「重看導覽」按鈕手動觸發（非首頁會自動跳轉）
 *
 * Storage Keys：
 *   - idmk_lastSeen       : "{version}|{YYYY-MM-DD}" — 上次看公告的版本與日期
 *   - idmk_tourCompleted  : "1" — 已完成過導覽
 *   - idmk_dismissForever : "1" — 用戶選擇永久不再顯示公告
 *
 * 跳過條件：admin 後台路徑（沿用 login-button.js 同款 guard）
 */
(function () {
  "use strict";

  // admin 後台跳過
  if (location.pathname.startsWith("/admin/")) return;

  const STORAGE_KEY = "idmk_lastSeen";
  const TOUR_KEY = "idmk_tourCompleted";
  const DISMISS_KEY = "idmk_dismissForever";
  const CHANGELOG_URL = (window.STATIC_PREFIX || "") + "data/changelog.json";

  let changelogData = null;

  // ───── localStorage 安全包裝（隱私模式可能 throw）─────
  function safeGet(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }
  function safeSet(key, val) {
    try { localStorage.setItem(key, val); } catch (e) { /* swallow */ }
  }
  function safeRemove(key) {
    try { localStorage.removeItem(key); } catch (e) { /* swallow */ }
  }

  // ───── 是否在首頁？（modal/tour 只在首頁跑） ─────
  function isHomePage() {
    const path = location.pathname.replace(/\/+$/, "");
    return path === "" || path.endsWith("/index.html") || path === "/index.html";
  }

  // ───── 1. 載入 changelog.json ─────
  fetch(CHANGELOG_URL, { cache: "no-cache" })
    .then(r => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(data => {
      changelogData = data;
      decideTrigger();
    })
    .catch(err => console.warn("[onboarding] changelog 載入失敗", err));

  // ───── 2. 決定觸發策略 ─────
  function decideTrigger() {
    // 非首頁完全不打擾
    if (!isHomePage()) return;

    // 從其他頁面點「重看導覽」跳回，自動啟動
    if (location.search.includes("retour=1")) {
      // 清掉 URL 參數避免重整時重複觸發
      try {
        const url = new URL(location.href);
        url.searchParams.delete("retour");
        history.replaceState({}, "", url.toString());
      } catch (e) { /* 舊瀏覽器忽略 */ }
      setTimeout(startTour, 800);
      return;
    }

    // 用戶已勾選「不再顯示」，完全 opt-out
    if (safeGet(DISMISS_KEY) === "1") return;

    const today = new Date().toISOString().slice(0, 10);
    const seenRaw = safeGet(STORAGE_KEY) || "|";
    const [seenVer, seenDate] = seenRaw.split("|");
    const latestVer = changelogData.latestVersion;

    const isNewVersion = seenVer !== latestVer;
    const isNewDay = seenDate !== today;

    if (isNewVersion || isNewDay) {
      showChangelogModal();
    } else if (!safeGet(TOUR_KEY)) {
      // 沒彈 modal 但還沒走過導覽（罕見），延遲跑
      setTimeout(startTour, 800);
    }
  }

  // ───── 3. 渲染 modal ─────
  function ensureModalRoot() {
    let root = document.getElementById("idmk-changelog-modal");
    if (!root) {
      root = document.createElement("div");
      root.id = "idmk-changelog-modal";
      root.hidden = true;
      document.body.appendChild(root);
    }
    return root;
  }

  function showChangelogModal() {
    const root = ensureModalRoot();
    if (!root || !changelogData) return;

    const w = changelogData.welcome || {};
    const versions = changelogData.versions || [];
    const latestVer = changelogData.latestVersion || (versions[0] && versions[0].version) || "";
    const latestDate = (versions[0] && versions[0].date) || "";

    const linksHtml = (w.links || []).map(l =>
      `<a href="${escapeAttr(l.url)}" target="_blank" rel="noopener">${escapeHtml(l.label)}</a>`
    ).join(" · ");

    const versionsHtml = versions.map(v => {
      const items = (v.changes || []).map(c =>
        `<li><span class="idmk-cl-tag idmk-cl-tag-${tagClass(c.type)}">${escapeHtml(c.type)}</span>${escapeHtml(c.text)}</li>`
      ).join("");
      return `
        <div class="idmk-cl-version">
          <div class="idmk-cl-ver-head">
            <span class="idmk-cl-ver-num">v${escapeHtml(v.version)}</span>
            <span class="idmk-cl-ver-date">${escapeHtml(v.date || "")}</span>
          </div>
          <ul class="idmk-cl-ver-list">${items}</ul>
        </div>`;
    }).join("");

    root.innerHTML = `
      <div class="idmk-cl-overlay" data-idmk-close></div>
      <article class="idmk-cl-card" role="dialog" aria-labelledby="idmk-cl-title">
        <header class="idmk-cl-head">
          <span class="idmk-cl-eyebrow">WHAT'S NEW · 更新公告</span>
          <h2 id="idmk-cl-title" class="idmk-cl-title">${escapeHtml(w.title || "歡迎使用族群寶")}</h2>
          <p class="idmk-cl-subtitle">最新版本 <strong>v${escapeHtml(latestVer)}</strong>${latestDate ? ` · ${escapeHtml(latestDate)}` : ""}</p>
        </header>

        <div class="idmk-cl-body">
          <div class="idmk-cl-welcome">
            ${(w.lines || []).map(line => `<p>${escapeHtml(line)}</p>`).join("")}
          </div>

          ${linksHtml ? `<div class="idmk-cl-meta">🔗 ${linksHtml}</div>` : ""}
          ${w.addToHomeTip ? `<p class="idmk-cl-tip">${escapeHtml(w.addToHomeTip)}</p>` : ""}

          <p class="idmk-cl-section-label">Release Notes</p>
          ${versionsHtml}
        </div>

        <footer class="idmk-cl-actions">
          <label class="idmk-cl-dismiss">
            <input type="checkbox" id="idmk-cl-dismiss-cb">
            <span>不再顯示此通知</span>
          </label>
          <div class="idmk-cl-actions-btns">
            <button type="button" class="idmk-cl-btn-secondary" data-idmk-retour>重看導覽</button>
            <button type="button" class="idmk-cl-btn-primary" data-idmk-close>開始使用</button>
          </div>
        </footer>
      </article>
    `;
    root.hidden = false;
    document.body.style.overflow = "hidden";

    // 綁事件
    root.querySelectorAll("[data-idmk-close]").forEach(el => {
      el.addEventListener("click", closeChangelogModal);
    });
    root.querySelectorAll("[data-idmk-retour]").forEach(el => {
      el.addEventListener("click", retour);
    });
    document.addEventListener("keydown", onEsc);
  }

  function onEsc(e) {
    if (e.key === "Escape") closeChangelogModal();
  }

  // ───── 4. 關閉 modal — 寫 storage + 條件啟動導覽 ─────
  function closeChangelogModal() {
    const today = new Date().toISOString().slice(0, 10);
    const dismissCb = document.getElementById("idmk-cl-dismiss-cb");
    const dismissForever = !!(dismissCb && dismissCb.checked);

    if (changelogData) {
      safeSet(STORAGE_KEY, `${changelogData.latestVersion}|${today}`);
    }
    if (dismissForever) {
      safeSet(DISMISS_KEY, "1");
    }

    const root = document.getElementById("idmk-changelog-modal");
    if (root) {
      root.hidden = true;
      root.innerHTML = "";
    }
    document.body.style.overflow = "";
    document.removeEventListener("keydown", onEsc);

    // 首次訪問用戶，關閉 modal 後自動啟動導覽
    if (!safeGet(TOUR_KEY)) {
      setTimeout(startTour, 400);
    }
  }

  // ───── 5. 啟動 driver.js 導覽（6 步詳細版）─────
  function startTour() {
    const driver = (window.driver && window.driver.js && window.driver.js.driver) || null;
    if (typeof driver !== "function") {
      console.warn("[onboarding] driver.js 未載入，跳過導覽");
      return;
    }

    const allSteps = [
      {
        selector: ".logo",
        title: "歡迎使用族群寶 🎉",
        description: "台股題材族群深度資料庫 — 1968 檔上市櫃個股 + 989 個題材族群 + 每日籌碼簡報，每天下午 5 點前更新。先帶你認識六大區塊。"
      },
      {
        selector: "#hero-search",
        title: "① 搜尋你關心的個股或題材",
        description: "輸入股票代號（2330）、公司名（台積電）、題材關鍵字（CPO、AI 伺服器、輝達概念股），直接定位所屬族群、相關個股與近期表現。"
      },
      {
        selector: ".hero-search-quick",
        title: "② 今日熱門題材",
        description: "每天搜尋關鍵字熱度，自動刷新。不確定看什麼，從這裡點 chip 直接抓今日市場焦點。"
      },
      {
        selector: "#daily-chip-report",
        title: "③ 每日籌碼一張表",
        description: "VIX 波動率、外資/投信/自營商三大法人買賣超、外資期貨未平倉、融資融券餘額 — 盤後 5 點前自動更新，一頁掌握資金站位。"
      },
      {
        selector: ".primary-nav",
        title: "④ 核心分析模組",
        description: "產業地圖（族群熱力圖）｜漲停分析｜股期儀表板（269 檔個股期貨自建組合）｜AI 分析｜RS 評分｜題材對比 — 從不同切角拆解台股。"
      },
      {
        selector: "#indusmapk-auth",
        title: "⑤ 登入解鎖會員功能",
        description: "Google 一鍵登入後可使用個股 Memo 筆記、查看會員等級與使用期限。右上角浮動按鈕點開即可。"
      },
      {
        selector: ".search-box",
        title: "⑥ 全域搜尋（Header）",
        description: "任何頁面右上角都有這個搜尋框，不必回首頁。覺得順手歡迎分享給朋友 🙌"
      }
    ];

    // 過濾不存在的元素，避免 driver.js 卡住
    const steps = allSteps
      .filter(s => document.querySelector(s.selector))
      .map(s => ({
        element: s.selector,
        popover: { title: s.title, description: s.description }
      }));

    if (steps.length === 0) {
      console.warn("[onboarding] 沒有可用 selector，跳過導覽");
      return;
    }

    const driverObj = driver({
      showProgress: true,
      allowClose: true,
      nextBtnText: "下一步 →",
      prevBtnText: "← 上一步",
      doneBtnText: "完成 ✓",
      progressText: "Step {{current}} of {{total}}",
      steps: steps,
      onDestroyed: () => safeSet(TOUR_KEY, "1")
    });
    driverObj.drive();
  }

  // ───── 6. 重看導覽（非首頁自動跳回首頁觸發）─────
  function retour() {
    if (isHomePage()) {
      // 在首頁直接跑
      closeChangelogModal();
      setTimeout(startTour, 250);
    } else {
      // 跳回首頁加 ?retour=1，由 decideTrigger 接力啟動
      const home = (window.STATIC_PREFIX || "") + "index.html?retour=1";
      location.href = home;
    }
  }

  // 暴露 API（讓 footer 等其他地方可呼叫）
  window.idmkRetour = retour;
  window.idmkOpenChangelog = showChangelogModal;
  window.idmkResetOnboarding = function () {
    // debug helper：清掉所有 onboarding storage，下次訪問如同新用戶
    safeRemove(STORAGE_KEY);
    safeRemove(TOUR_KEY);
    safeRemove(DISMISS_KEY);
    console.log("[onboarding] storage cleared. reload to see modal/tour again.");
  };

  // ───── 工具函式 ─────
  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function escapeAttr(s) { return escapeHtml(s); }
  function tagClass(type) {
    const t = String(type || "");
    if (t.includes("新增")) return "add";
    if (t.includes("優化") || t.includes("改善")) return "improve";
    if (t.includes("修復") || t.includes("bug")) return "fix";
    return "default";
  }
})();
