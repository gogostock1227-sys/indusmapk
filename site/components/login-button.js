/**
 * 主站右上角登入入口 / 會員中心浮動 panel。
 *
 * 用法：base.html 已注入 <div id="indusmapk-auth"></div> + 引入此 script。
 *
 * 行為：
 *   - 在 /admin/* 路徑下不注入（admin 自己有 sidebar 顯示用戶資訊）
 *   - 未登入：顯示「用 Google 登入」按鈕（藍色實心）
 *   - 已登入：顯示「頭像 + 角色徽章 ▾」，點擊展開浮動會員中心：
 *       - 頭像 / 顯示名稱 / email
 *       - 會員等級（中文）
 *       - 使用期限（永久 / YYYY-MM-DD / 紅色警告 N 天後到期）
 *       - 狀態
 *       - 進入後台（admin+ 限）
 *       - 登出
 */
(function () {
  "use strict";

  // admin 路徑跳過（admin 後台已有 sidebar 顯示 user 資訊）
  if (location.pathname.startsWith("/admin/")) return;

  const ROLE_LABELS = {
    member: "免費會員",
    premium: "進階用戶",
    admin: "管理員",
    super_admin: "超級管理員",
  };

  function el(tag, attrs, ...children) {
    const e = document.createElement(tag);
    if (attrs) {
      for (const k in attrs) {
        if (k === "onclick") e.addEventListener("click", attrs[k]);
        else if (k === "style" && typeof attrs[k] === "object") Object.assign(e.style, attrs[k]);
        else e.setAttribute(k, attrs[k]);
      }
    }
    for (const c of children) {
      if (c == null) continue;
      e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return e;
  }

  function injectStyle() {
    if (document.getElementById("indusmapk-auth-style")) return;
    const css = `
      .auth-area, #indusmapk-auth {
        position: relative; display: flex; align-items: center;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", "Source Sans 3", sans-serif;
        font-size: 14px; margin-left: 0.75rem;
      }
      #indusmapk-auth .login-btn {
        background: #3b82f6; color: #fff; border: 0;
        padding: 0.45rem 1rem; border-radius: 8px;
        font-size: 13px; font-weight: 500; cursor: pointer;
        display: inline-flex; align-items: center; gap: 0.4rem;
        transition: background 0.15s;
      }
      #indusmapk-auth .login-btn:hover { background: #2563eb; }
      #indusmapk-auth .login-btn svg { width: 14px; height: 14px; }

      #indusmapk-auth .avatar-trigger {
        display: flex; align-items: center; gap: 0.5rem;
        cursor: pointer; padding: 0.25rem 0.6rem 0.25rem 0.3rem;
        background: #fff; border: 1px solid #e5e7eb; border-radius: 999px;
        transition: border-color 0.15s, box-shadow 0.15s;
      }
      #indusmapk-auth .avatar-trigger:hover {
        border-color: #cbd5e1; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
      }
      #indusmapk-auth .avatar {
        width: 26px; height: 26px; border-radius: 50%; object-fit: cover;
      }
      #indusmapk-auth .role-tag {
        font-size: 11px; padding: 0.1rem 0.5rem; border-radius: 999px;
        font-weight: 500; line-height: 1.4;
      }
      #indusmapk-auth .role-tag.r-member      { background: #f1f5f9; color: #64748b; }
      #indusmapk-auth .role-tag.r-premium     { background: #f3e8ff; color: #9333ea; }
      #indusmapk-auth .role-tag.r-admin       { background: #fee2e2; color: #dc2626; }
      #indusmapk-auth .role-tag.r-super_admin { background: #fef3c7; color: #d97706; }
      #indusmapk-auth .caret { color: #94a3b8; font-size: 11px; margin-left: 2px; }

      #indusmapk-auth .panel {
        position: absolute; right: 0; top: calc(100% + 8px);
        min-width: 280px; max-width: calc(100vw - 16px);
        background: #fff;
        border: 1px solid #e5e7eb; border-radius: 10px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.08);
        padding: 0; z-index: 9999; display: none;
        overflow: hidden;
        box-sizing: border-box;
      }
      #indusmapk-auth .panel.open { display: block; }
      #indusmapk-auth .panel-head {
        display: flex; gap: 0.75rem; align-items: center;
        padding: 1rem; border-bottom: 1px solid #f1f5f9;
        min-width: 0;
      }
      #indusmapk-auth .panel-head > div { min-width: 0; flex: 1; }
      #indusmapk-auth .panel-head img { width: 42px; height: 42px; border-radius: 50%; flex: none; }
      #indusmapk-auth .panel-name {
        font-weight: 600; color: #0f172a; font-size: 14px;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      #indusmapk-auth .panel-email {
        color: #64748b; font-size: 12px;
        max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      #indusmapk-auth .panel-info {
        padding: 0.75rem 1rem; font-size: 13px;
      }
      #indusmapk-auth .info-row {
        display: flex; justify-content: space-between; align-items: center;
        padding: 0.4rem 0;
      }
      #indusmapk-auth .info-label { color: #64748b; }
      #indusmapk-auth .info-value { color: #0f172a; font-weight: 500; }
      #indusmapk-auth .info-value.warn { color: #dc2626; }
      #indusmapk-auth .info-value.gold { color: #d97706; }
      #indusmapk-auth .panel-actions {
        border-top: 1px solid #f1f5f9; padding: 0.4rem 0;
      }
      #indusmapk-auth .menu-item {
        display: block; padding: 0.6rem 1rem; color: #0f172a;
        text-decoration: none; font-size: 13px;
        transition: background 0.1s;
      }
      #indusmapk-auth .menu-item:hover { background: #f8fafc; text-decoration: none; }
      #indusmapk-auth .menu-item.danger { color: #dc2626; }

      /* 手機版：dropdown 改用 fixed 鎖右上角，避免被父層裁切或位移 */
      @media (max-width: 480px) {
        #indusmapk-auth .panel {
          position: fixed;
          top: 60px;
          right: 8px;
          left: auto;
          min-width: 0;
          width: calc(100vw - 16px);
          max-width: 320px;
        }
      }

      /* 到期警告 modal — 視窗正中央顯示，半透明 overlay 加強引導 */
      #indusmapk-expiry-overlay {
        position: fixed; inset: 0; z-index: 10000;
        background: rgba(15, 23, 42, 0.55);
        display: grid; place-items: center;
        padding: 1rem;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", sans-serif;
        animation: indusmapk-fade-in 0.2s ease-out;
        backdrop-filter: blur(2px);
      }
      @keyframes indusmapk-fade-in {
        from { opacity: 0; }
        to   { opacity: 1; }
      }
      #indusmapk-expiry-modal {
        background: #fff; border-radius: 14px;
        padding: 2rem 2.25rem 1.5rem;
        max-width: 440px; width: 100%;
        text-align: center;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        animation: indusmapk-pop-in 0.25s cubic-bezier(.34,1.56,.64,1);
      }
      @keyframes indusmapk-pop-in {
        from { opacity: 0; transform: scale(0.85); }
        to   { opacity: 1; transform: scale(1); }
      }
      #indusmapk-expiry-modal .icon {
        font-size: 3rem; line-height: 1; margin-bottom: 0.75rem;
      }
      #indusmapk-expiry-modal .title {
        font-size: 1.25rem; font-weight: 700; color: #0f172a;
        margin: 0 0 0.5rem;
      }
      #indusmapk-expiry-modal .title.warn   { color: #92400e; }
      #indusmapk-expiry-modal .title.danger { color: #991b1b; }
      #indusmapk-expiry-modal .days-big {
        display: inline-block; padding: 0 0.4rem;
        font-size: 1.6rem; font-weight: 800;
      }
      #indusmapk-expiry-modal .sub {
        color: #475569; font-size: 14px; line-height: 1.6;
        margin: 0.75rem 0 1.25rem;
      }
      #indusmapk-expiry-modal .role-pill {
        display: inline-block; background: #f1f5f9; color: #334155;
        padding: 0.15rem 0.65rem; border-radius: 999px;
        font-size: 12px; font-weight: 500;
      }
      #indusmapk-expiry-modal .actions {
        display: flex; gap: 0.6rem; justify-content: center;
        flex-wrap: wrap; margin-top: 0.75rem;
      }
      #indusmapk-expiry-modal .extend-btn {
        background: #3b82f6; color: #fff; border: 0;
        padding: 0.65rem 1.4rem; border-radius: 8px;
        font-size: 14px; font-weight: 500; cursor: pointer;
        text-decoration: none;
      }
      #indusmapk-expiry-modal .extend-btn:hover { background: #2563eb; }
      #indusmapk-expiry-modal .close-btn {
        background: transparent; color: #64748b; border: 1px solid #cbd5e1;
        padding: 0.65rem 1.4rem; border-radius: 8px;
        font-size: 14px; font-weight: 500; cursor: pointer;
      }
      #indusmapk-expiry-modal .close-btn:hover { background: #f8fafc; }
      #indusmapk-expiry-overlay .danger-tint { background: rgba(127, 29, 29, 0.55); }
    `;
    const style = document.createElement("style");
    style.id = "indusmapk-auth-style";
    style.textContent = css;
    document.head.appendChild(style);
  }

  // ── 渲染：未登入 ─────────────────────────────────────────────
  function renderGuest(root) {
    root.innerHTML = "";
    const btn = el("button", { class: "login-btn", title: "用 Google 帳號登入" });
    btn.innerHTML = `
      <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path fill="#fff" d="M21.6 12.2c0-.6-.1-1.1-.2-1.6H12v3.3h5.4c-.2 1-.9 2-2 2.6l3.2 2.5c1.9-1.7 3-4.3 3-6.8z"/>
        <path fill="#fff" d="M12 22c2.7 0 4.9-.9 6.5-2.4l-3.2-2.5c-.9.6-2 1-3.4 1-2.6 0-4.8-1.7-5.6-4.1L3 16.6C4.7 19.8 8.1 22 12 22z" opacity="0.8"/>
        <path fill="#fff" d="M6.4 13.9c-.2-.6-.3-1.2-.3-1.9s.1-1.3.3-1.9L3 7.4C2.4 8.8 2 10.4 2 12s.4 3.2 1 4.6l3.4-2.7z" opacity="0.6"/>
        <path fill="#fff" d="M12 5.5c1.5 0 2.8.5 3.8 1.5l2.8-2.8C16.9 2.6 14.7 1.7 12 1.7c-3.9 0-7.3 2.2-9 5.7l3.4 2.7c.8-2.4 3-4.1 5.6-4.1z" opacity="0.4"/>
      </svg>
      <span>用 Google 登入</span>
    `;
    btn.addEventListener("click", () => {
      const next = location.pathname + location.search;
      location.href = `/admin/login.html?next=${encodeURIComponent(next)}`;
    });
    root.appendChild(btn);
  }

  // ── 渲染：已登入（含浮動會員中心 panel） ──────────────────────
  function expiryDisplay(iso) {
    if (!iso) return { text: "永久", className: "gold" };
    const ms = Date.parse(iso);
    if (isNaN(ms)) return { text: iso, className: "" };
    const now = Date.now();
    const days = Math.floor((ms - now) / 86400000);
    if (days < 0) return { text: "已過期", className: "warn" };
    if (days < 7) return { text: `${days} 天後到期`, className: "warn" };
    const d = new Date(ms);
    const pad = n => String(n).padStart(2, "0");
    return { text: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`, className: "" };
  }

  function renderUser(root, me) {
    root.innerHTML = "";
    const roleClass = `r-${me.role}`;
    const roleLabel = ROLE_LABELS[me.role] || me.role;
    const exp = expiryDisplay(me.role_expires_at);

    const trigger = el("div", { class: "avatar-trigger" });
    trigger.innerHTML = `
      <img class="avatar" src="${me.picture || ""}" alt="" referrerpolicy="no-referrer">
      <span class="role-tag ${roleClass}">${roleLabel}</span>
      <span class="caret">▾</span>
    `;

    const panel = el("div", { class: "panel" });
    const isAdminPlus = me.role === "admin" || me.role === "super_admin";
    panel.innerHTML = `
      <div class="panel-head">
        <img src="${me.picture || ""}" alt="" referrerpolicy="no-referrer">
        <div>
          <div class="panel-name">${me.name || me.email.split("@")[0]}</div>
          <div class="panel-email" title="${me.email}">${me.email}</div>
        </div>
      </div>
      <div class="panel-info">
        <div class="info-row">
          <span class="info-label">會員等級</span>
          <span class="info-value"><span class="role-tag ${roleClass}">${roleLabel}</span></span>
        </div>
        <div class="info-row">
          <span class="info-label">使用期限</span>
          <span class="info-value ${exp.className}">${exp.text}</span>
        </div>
        <div class="info-row">
          <span class="info-label">狀態</span>
          <span class="info-value">${me.role === "member" ? "等待升級權限" : "✓ 啟用"}</span>
        </div>
      </div>
      <div class="panel-actions">
        ${isAdminPlus ? `<a class="menu-item" href="/admin/">進入後台</a>` : ""}
        <a class="menu-item danger" href="/api/auth/logout">登出</a>
      </div>
    `;

    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      panel.classList.toggle("open");
    });
    document.addEventListener("click", () => panel.classList.remove("open"));

    root.appendChild(trigger);
    root.appendChild(panel);
  }

  // ── 入口 ───────────────────────────────────────────────────
  function init() {
    let root = document.getElementById("indusmapk-auth");
    if (!root) {
      // 沒有預設容器 → fixed 在右上角作 fallback
      root = el("div", {
        id: "indusmapk-auth",
        style: { position: "fixed", top: "12px", right: "16px", zIndex: 9999 },
      });
      document.body.appendChild(root);
    }
    injectStyle();

    fetch("/api/auth/me", { credentials: "same-origin" })
      .then(r => r.json())
      .then(me => {
        if (me.authenticated) {
          renderUser(root, me);
          showExpiryWarning(me);
        } else {
          renderGuest(root);
        }
      })
      .catch(() => renderGuest(root));
  }

  // ── 到期警告 banner（5 天內快過期才顯示） ──────────────────────
  function showExpiryWarning(me) {
    // super_admin 永久不需要警告
    if (me.role === "super_admin") return;
    // member / guest 沒到期日概念
    if (!me.role_expires_at) return;

    const ms = Date.parse(me.role_expires_at);
    if (isNaN(ms)) return;
    const now = Date.now();
    const days = Math.ceil((ms - now) / 86400000);

    // 已過期：middleware 會自動降為 member 並重發 cookie，這裡不警告
    if (days <= 0) return;
    // 大於 5 天：暫不打擾
    if (days > 5) return;

    if (document.getElementById("indusmapk-expiry-overlay")) return; // 已存在不重複插入

    const isDanger = days <= 2;
    const roleText = ROLE_LABELS[me.role] || me.role;
    const overlay = el("div", {
      id: "indusmapk-expiry-overlay",
      class: isDanger ? "danger-tint" : "",
    });
    overlay.innerHTML = `
      <div id="indusmapk-expiry-modal" role="dialog" aria-modal="true">
        <div class="icon">${isDanger ? "⚠️" : "⏰"}</div>
        <h3 class="title ${isDanger ? "danger" : "warn"}">
          你的權限<span class="days-big">${days}</span>天後到期
        </h3>
        <div class="sub">
          <span class="role-pill">${roleText}</span>
          <br><br>
          ${isDanger
            ? "⚠ 即將失效，請盡快聯絡管理員延長使用期限。"
            : "請聯絡管理員協助續期，避免影響你的使用權限。"}
        </div>
        <div class="actions">
          <button class="close-btn" id="indusmapk-close-modal">我知道了</button>
          <a class="extend-btn" id="indusmapk-extend-btn">聯絡管理員續期</a>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    document.getElementById("indusmapk-extend-btn").addEventListener("click", (e) => {
      e.preventDefault();
      const subject = `申請延長${roleText}權限`;
      const body = `Hi，\n\n我是 ${me.email}，目前是「${roleText}」，將於 ${days} 天後到期。\n` +
                   `麻煩協助延長使用期限，謝謝！\n\n（自動發送自 indusmapk.com）`;
      location.href = `mailto:gogostock1227@gmail.com?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
      overlay.remove();
    });
    document.getElementById("indusmapk-close-modal").addEventListener("click", () => {
      overlay.remove();
    });
    // 點 overlay 空白處也可關閉（modal 本身吃掉 click 不冒泡）
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
    document.getElementById("indusmapk-expiry-modal").addEventListener("click", (e) => e.stopPropagation());
    // ESC 鍵關閉
    const escHandler = (e) => { if (e.key === "Escape") { overlay.remove(); document.removeEventListener("keydown", escHandler); } };
    document.addEventListener("keydown", escHandler);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
