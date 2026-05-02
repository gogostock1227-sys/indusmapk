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
      { key: "data-publish", label: "發布", href: "/admin/data/publish.html" },
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

  return {
    fetchJson, flash, fmtDate, fmtDateOnly, expiryStatus,
    me, bustMeCache, renderSidebar, tag,
    ROLE_LABEL, DATA_CATEGORIES, DATA_CATEGORY_LABEL,
  };
})();
