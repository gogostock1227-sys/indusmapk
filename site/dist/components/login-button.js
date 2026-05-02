/**
 * 右上角登入按鈕／頭像 menu。
 * 用法：在現有公開頁面任意位置加 <div id="indusmapk-auth"></div>，並引入此 script。
 *
 *   <script src="/components/login-button.js" defer></script>
 *
 * 自動 fetch /api/auth/me，依 role 渲染不同 UI：
 *   - guest：「用 Google 登入」按鈕
 *   - member：頭像 + 「等待升級」標籤 + 登出
 *   - premium：頭像 + 「進階用戶」標籤 + 登出
 *   - admin / super_admin：頭像 + 角色標籤 + 「進入後台」連結 + 登出
 */
(function () {
  "use strict";

  const ROOT_ID = "indusmapk-auth";

  function el(tag, attrs, ...children) {
    const e = document.createElement(tag);
    if (attrs) for (const k in attrs) {
      if (k === "style" && typeof attrs[k] === "object") {
        Object.assign(e.style, attrs[k]);
      } else if (k === "onclick") {
        e.addEventListener("click", attrs[k]);
      } else {
        e.setAttribute(k, attrs[k]);
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
      #${ROOT_ID} { position: relative; display: inline-block; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", sans-serif; font-size: 14px; }
      #${ROOT_ID} .login-btn {
        background: #3b82f6; color: #fff; border: 0; padding: 0.45rem 0.9rem;
        border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500;
      }
      #${ROOT_ID} .login-btn:hover { opacity: 0.9; }
      #${ROOT_ID} .avatar-trigger {
        display: flex; align-items: center; gap: 0.5rem; cursor: pointer;
        background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
        border-radius: 999px; padding: 0.25rem 0.75rem 0.25rem 0.25rem;
      }
      #${ROOT_ID} .avatar-trigger:hover { background: rgba(255,255,255,0.1); }
      #${ROOT_ID} .avatar { width: 28px; height: 28px; border-radius: 50%; }
      #${ROOT_ID} .role-tag {
        font-size: 11px; padding: 0.1rem 0.45rem; border-radius: 999px;
        background: rgba(245,158,11,0.15); color: #f59e0b;
        font-weight: 500;
      }
      #${ROOT_ID} .role-tag.role-admin, #${ROOT_ID} .role-tag.role-super_admin { background: rgba(239,68,68,0.15); color: #ef4444; }
      #${ROOT_ID} .role-tag.role-premium { background: rgba(168,85,247,0.15); color: #a855f7; }
      #${ROOT_ID} .role-tag.role-member { background: rgba(148,163,184,0.15); color: #94a3b8; }
      #${ROOT_ID} .menu {
        position: absolute; right: 0; top: calc(100% + 6px); min-width: 220px;
        background: #1e293b; border: 1px solid #334155; border-radius: 8px;
        padding: 0.5rem; display: none; z-index: 9999;
        box-shadow: 0 10px 30px rgba(0,0,0,0.4);
      }
      #${ROOT_ID} .menu.open { display: block; }
      #${ROOT_ID} .menu-item {
        display: block; padding: 0.5rem 0.75rem; color: #f1f5f9;
        text-decoration: none; border-radius: 4px; font-size: 13px;
      }
      #${ROOT_ID} .menu-item:hover { background: rgba(255,255,255,0.05); }
      #${ROOT_ID} .menu-divider { border-top: 1px solid #334155; margin: 0.4rem 0; }
      #${ROOT_ID} .menu-info { padding: 0.5rem 0.75rem; color: #94a3b8; font-size: 12px; }
      #${ROOT_ID} .upgrade-hint {
        margin-top: 0.4rem; padding: 0.5rem 0.75rem;
        background: rgba(245,158,11,0.08); border-radius: 4px;
        font-size: 12px; color: #fbbf24;
      }
    `;
    const style = document.createElement("style");
    style.id = "indusmapk-auth-style";
    style.textContent = css;
    document.head.appendChild(style);
  }

  function renderGuest(root) {
    root.innerHTML = "";
    const btn = el("button", { class: "login-btn" }, "用 Google 登入");
    btn.addEventListener("click", () => {
      const next = location.pathname + location.search;
      location.href = `/admin/login.html?next=${encodeURIComponent(next)}`;
    });
    root.appendChild(btn);
  }

  const ROLE_LABEL = {
    member: "免費會員",
    premium: "進階用戶",
    admin: "管理員",
    super_admin: "超級管理員",
  };

  function renderUser(root, me) {
    root.innerHTML = "";
    const avatar = el("img", {
      class: "avatar",
      src: me.picture || "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><circle cx='12' cy='8' r='4' fill='%23999'/><path d='M4 22c0-4.4 3.6-8 8-8s8 3.6 8 8' fill='%23999'/></svg>",
      alt: me.name || me.email,
    });
    const tag = el("span", { class: `role-tag role-${me.role}` }, ROLE_LABEL[me.role] || me.role);
    const trigger = el("div", { class: "avatar-trigger" }, avatar, tag);

    const menu = el("div", { class: "menu" });
    menu.appendChild(el("div", { class: "menu-info" }, me.email));

    if (me.role === "member") {
      menu.appendChild(el("div", { class: "upgrade-hint" }, "等待管理員升級權限"));
    }
    if (me.role === "admin" || me.role === "super_admin") {
      menu.appendChild(el("div", { class: "menu-divider" }));
      menu.appendChild(el("a", { class: "menu-item", href: "/admin/" }, "進入後台"));
    }
    menu.appendChild(el("div", { class: "menu-divider" }));
    menu.appendChild(el("a", { class: "menu-item", href: "/api/auth/logout" }, "登出"));

    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      menu.classList.toggle("open");
    });
    document.addEventListener("click", () => menu.classList.remove("open"));

    root.appendChild(trigger);
    root.appendChild(menu);
  }

  function init() {
    let root = document.getElementById(ROOT_ID);
    if (!root) {
      // 沒有預設容器 → 自動 fixed 在右上角
      root = el("div", { id: ROOT_ID, style: { position: "fixed", top: "12px", right: "16px", zIndex: 9999 } });
      document.body.appendChild(root);
    }
    injectStyle();

    fetch("/api/auth/me", { credentials: "same-origin" })
      .then((r) => r.json())
      .then((me) => {
        if (me.authenticated) renderUser(root, me);
        else renderGuest(root);
      })
      .catch(() => renderGuest(root));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
