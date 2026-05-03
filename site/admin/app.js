// admin SPA 共用工具
window.IM = (function () {
  const ROLE_LABEL = {
    member: "免費會員",
    premium: "進階用戶",
    admin: "管理員",
    super_admin: "超級管理員",
  };
  const DATA_CATEGORY_LABEL = {
    concept_groups: "族群定義",
    stock_profiles: "個股 profile",
    master_patch: "族群規則",
    industry_meta: "產業說明",
    validation_runs: "驗證審核",
  };
  const DATA_CATEGORIES = Object.keys(DATA_CATEGORY_LABEL);

  async function fetchJson(url, opts = {}) {
    const res = await fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      ...opts,
    });
    let body;
    try { body = await res.json(); } catch { body = null; }
    if (!res.ok) {
      const err = new Error(body?.error || `HTTP ${res.status}`);
      err.status = res.status;
      err.payload = body;
      throw err;
    }
    return body;
  }

  function flash(message, type = "info") {
    const div = document.createElement("div");
    div.className = `flash flash-${type}`;
    div.textContent = message;
    document.body.appendChild(div);
    setTimeout(() => div.remove(), 4000);
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function fmtDateOnly(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  }

  function expiryStatus(iso) {
    if (!iso) return { label: "永久", className: "" };
    const ms = Date.parse(iso);
    const now = Date.now();
    if (isNaN(ms)) return { label: iso, className: "" };
    const diff = ms - now;
    if (diff < 0) return { label: `已過期 ${fmtDate(iso)}`, className: "tag-expired" };
    const days = Math.floor(diff / 86400000);
    if (days < 7) return { label: `${days} 天後過期`, className: "tag-expiring" };
    return { label: `${fmtDateOnly(iso)} 過期`, className: "" };
  }

  // 取當前用戶（cached for 30 秒）
  let _meCache = null;
  let _meTs = 0;
  async function me() {
    if (_meCache && Date.now() - _meTs < 30000) return _meCache;
    _meCache = await fetchJson("/api/auth/me");
    _meTs = Date.now();
    return _meCache;
  }

  function bustMeCache() { _meCache = null; _meTs = 0; }

  // 渲染 sidebar，依據 role 隱藏不該看到的項
  async function renderSidebar(activeKey) {
    const me_ = await me();
    if (!me_.authenticated || (me_.role !== "admin" && me_.role !== "super_admin")) {
      // 中途 role 被降權 — 強制送回 login
      location.href = "/admin/login.html";
      return;
    }

    const isSuper = me_.role === "super_admin";
    const items = [
      { key: "dashboard", label: "Dashboard", href: "/admin/" },
      { sectionTitle: "用戶管理" },
      { key: "users", label: "用戶列表", href: "/admin/users.html" },
      { key: "access-rules", label: "進階內容規則", href: "/admin/access-rules.html", superOnly: true },
      { key: "audit", label: "操作紀錄", href: "/admin/audit.html" },
      { sectionTitle: "資料維運" },
      { key: "data-groups", label: "族群定義", href: "/admin/data/groups.html" },
      { key: "data-stock", label: "個股 profile", href: "/admin/data/stock.html" },
      { key: "data-industries", label: "產業文案", href: "/admin/data/industries.html" },
      { key: "data-master-patch", label: "Master Patch", href: "/admin/data/master-patch.html" },
      { key: "data-validation", label: "驗證審核", href: "/admin/data/validation.html" },
      { key: "data-ai-tools", label: "✨ AI 工具", href: "/admin/data/ai-tools.html" },
      { key: "data-publish", label: "🚀 發布", href: "/admin/data/publish.html" },
    ];

    const html = items.map(it => {
      if (it.sectionTitle) return `<div class="section-title">${it.sectionTitle}</div>`;
      if (it.superOnly && !isSuper) return "";
      const cls = it.key === activeKey ? "active" : "";
      return `<a href="${it.href}" class="${cls}">${it.label}</a>`;
    }).join("");

    const meHtml = `
      <div class="me">
        <img src="${me_.picture || ""}" alt="">
        <div class="info">
          <div class="email">${me_.email}</div>
          <div class="role">${ROLE_LABEL[me_.role] || me_.role}</div>
        </div>
        <a href="/api/auth/logout" class="btn-ghost btn-sm" title="登出">⎋</a>
      </div>`;

    document.querySelector(".sidebar").innerHTML = `
      <h2>indusmapk</h2>
      <nav>${html}</nav>
      ${meHtml}
    `;
  }

  function tag(role) {
    return `<span class="tag tag-${role}">${ROLE_LABEL[role] || role}</span>`;
  }

  // ─── AI prompt 複製 modal（C 方案：用 Claude Code Max quota，不打 API）─────
  function copyPromptModal({ title, intro, prompt, claudeUrl }) {
    claudeUrl = claudeUrl || "https://claude.ai/new";
    document.getElementById("indusmapk-prompt-modal-overlay")?.remove();
    if (!document.getElementById("indusmapk-prompt-modal-style")) {
      const style = document.createElement("style");
      style.id = "indusmapk-prompt-modal-style";
      style.textContent = `
        #indusmapk-prompt-modal-overlay {
          position: fixed; inset: 0; z-index: 11000;
          background: rgba(15,23,42,0.65);
          display: grid; place-items: center; padding: 1rem;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", sans-serif;
          animation: imp-fade 0.15s ease-out;
        }
        @keyframes imp-fade { from { opacity: 0 } to { opacity: 1 } }
        #indusmapk-prompt-modal {
          background: var(--panel, #1e293b); color: var(--text, #f1f5f9);
          border: 1px solid var(--border, #334155);
          border-radius: 12px; padding: 1.5rem;
          max-width: 720px; width: 100%; max-height: 90vh;
          display: flex; flex-direction: column; gap: 0.85rem;
          box-shadow: 0 20px 60px rgba(0,0,0,0.5);
        }
        #indusmapk-prompt-modal h3 { margin: 0; font-size: 1.1rem; }
        #indusmapk-prompt-modal .intro { color: var(--muted, #94a3b8); font-size: 13px; margin: 0; }
        #indusmapk-prompt-modal textarea {
          flex: 1; width: 100%; min-height: 280px;
          background: var(--bg, #0f172a); color: var(--text, #f1f5f9);
          border: 1px solid var(--border, #334155); border-radius: 8px;
          padding: 0.75rem; font-family: ui-monospace, SF Mono, Menlo, monospace;
          font-size: 12px; line-height: 1.5; resize: vertical;
        }
        #indusmapk-prompt-modal .actions {
          display: flex; gap: 0.5rem; justify-content: flex-end; flex-wrap: wrap;
        }
        #indusmapk-prompt-modal button, #indusmapk-prompt-modal a {
          padding: 0.55rem 1.1rem; border-radius: 8px; border: 0;
          font-size: 13px; font-weight: 500; cursor: pointer; text-decoration: none;
          font-family: inherit; display: inline-flex; align-items: center; gap: 0.4rem;
        }
        #indusmapk-prompt-modal .btn-copy { background: #a855f7; color: #fff; }
        #indusmapk-prompt-modal .btn-copy:hover { background: #9333ea; }
        #indusmapk-prompt-modal .btn-claude { background: #d97706; color: #fff; }
        #indusmapk-prompt-modal .btn-claude:hover { background: #b45309; }
        #indusmapk-prompt-modal .btn-close {
          background: transparent; color: var(--muted, #94a3b8);
          border: 1px solid var(--border, #334155);
        }
        #indusmapk-prompt-modal .stats { color: var(--muted, #94a3b8); font-size: 11px; }
      `;
      document.head.appendChild(style);
    }
    const overlay = document.createElement("div");
    overlay.id = "indusmapk-prompt-modal-overlay";
    overlay.innerHTML = `
      <div id="indusmapk-prompt-modal" role="dialog" aria-modal="true">
        <h3>✨ ${title || "AI prompt"}</h3>
        ${intro ? `<p class="intro">${intro}</p>` : ""}
        <textarea id="imp-prompt-text" spellcheck="false" readonly></textarea>
        <div class="stats" id="imp-stats">— 字符</div>
        <div class="actions">
          <button class="btn-close" id="imp-close">關閉</button>
          <button class="btn-copy" id="imp-copy">📋 複製到剪貼板</button>
          <a class="btn-claude" id="imp-open-claude" target="_blank" href="${claudeUrl}">↗ 打開 Claude Code</a>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    const ta = document.getElementById("imp-prompt-text");
    ta.value = prompt;
    document.getElementById("imp-stats").textContent =
      `${prompt.length.toLocaleString()} 字符 · 約 ${Math.ceil(prompt.length / 4).toLocaleString()} tokens（估）`;
    document.getElementById("imp-close").addEventListener("click", () => overlay.remove());
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
    document.addEventListener("keydown", function escH(e) {
      if (e.key === "Escape") { overlay.remove(); document.removeEventListener("keydown", escH); }
    });
    document.getElementById("imp-copy").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(prompt);
        flash("已複製到剪貼板，貼到 Claude Code 對話即可", "success");
      } catch (e) {
        ta.removeAttribute("readonly");
        ta.select();
        document.execCommand("copy");
        ta.setAttribute("readonly", "");
        flash("已複製（fallback 模式）", "success");
      }
    });
  }

  return {
    fetchJson, flash, fmtDate, fmtDateOnly, expiryStatus,
    me, bustMeCache, renderSidebar, tag,
    copyPromptModal,
    ROLE_LABEL, DATA_CATEGORIES, DATA_CATEGORY_LABEL,
  };
})();
