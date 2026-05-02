// 全站 middleware：JWT 驗證 + role 過期降級 + access rules 路徑攔截
//
// 觸發範圍：Cloudflare Pages Functions middleware 對「所有」請求觸發
// （包括靜態 .html / .css / .js / 圖片），透過 ctx.next() 繼續到靜態服務。

import type { Env, RequestCtx } from "./lib/types";
import { ROLE_RANK } from "./lib/types";
import { verifyJwt, readSessionCookie, buildSessionCookie, signJwt } from "./lib/jwt";
import { getUserById, downgradeIfExpired, findMatchingRule } from "./lib/d1";

// 不需要 access rules 檢查的路徑（靜態資源 / API 自管 / 系統頁）
const STATIC_EXT = /\.(css|js|mjs|map|png|jpe?g|gif|svg|webp|avif|ico|woff2?|ttf|otf|eot|json|txt|xml|webmanifest)$/i;

const PUBLIC_PATHS = new Set<string>([
  "/paywall.html",
  "/admin/login.html",         // 登入頁本身要可訪問
  "/favicon.ico",
  "/robots.txt",
]);

function isApiPath(pathname: string): boolean {
  return pathname.startsWith("/api/");
}

function isStaticAsset(pathname: string): boolean {
  return STATIC_EXT.test(pathname);
}

export const onRequest = async (ctx: RequestCtx) => {
  const env = ctx.env as Env;
  const url = new URL(ctx.request.url);
  const path = url.pathname;

  // 1. 解析 JWT，注入 user / role 到 ctx.data
  let user = null;
  const token = readSessionCookie(ctx.request);
  let needRefreshCookie = false;
  let refreshedToken: string | null = null;

  if (token) {
    const payload = await verifyJwt(token, env.JWT_SECRET);
    if (payload) {
      const fresh = await getUserById(env, payload.uid);
      if (fresh && fresh.status === "active") {
        // 過期降級
        const after = await downgradeIfExpired(env, fresh);
        user = after;

        // 若 role 在 D1 跟 JWT 不一致（過期降級或 super_admin 改了），
        // 重新簽 JWT 寫回 cookie
        if (after.role !== payload.role || after.role_expires_at !== payload.role_exp) {
          needRefreshCookie = true;
          refreshedToken = await signJwt(
            {
              uid: after.id,
              email: after.email,
              role: after.role,
              role_exp: after.role_expires_at,
            },
            env.JWT_SECRET,
          );
        }
      }
    }
  }

  ctx.data = {
    user,
    role: user?.role ?? "guest",
  };

  // 2. API 與 admin 自管 — 不做頁面 access rules 檢查（個別 endpoint 自己驗）
  //    但 ctx.next() 後 endpoint 內可以讀 ctx.data.user
  if (isApiPath(path) || isStaticAsset(path)) {
    const res = await ctx.next();
    if (needRefreshCookie && refreshedToken) {
      const newRes = new Response(res.body, res);
      newRes.headers.append("Set-Cookie", buildSessionCookie(refreshedToken));
      return newRes;
    }
    return res;
  }

  // 3. /admin/* 路徑：要求 admin+ 才能進（除了 login.html）
  if (path.startsWith("/admin/") && path !== "/admin/login.html") {
    const userRank = ROLE_RANK[ctx.data.role];
    if (userRank < ROLE_RANK.admin) {
      // 未登入 → 跳到 login；已登入但 role 不足 → 跳 paywall（提示要 admin 權限）
      if (!user) {
        return Response.redirect(
          `${url.origin}/admin/login.html?next=${encodeURIComponent(path)}`,
          302,
        );
      }
      return Response.redirect(
        `${url.origin}/paywall.html?from=${encodeURIComponent(path)}&need=admin`,
        302,
      );
    }
  }

  // 4. 公開路徑放行
  if (PUBLIC_PATHS.has(path)) {
    return passthrough(ctx, needRefreshCookie, refreshedToken);
  }

  // 5. 查 access_rules
  try {
    const rule = await findMatchingRule(env, path);
    if (rule) {
      const userRank = ROLE_RANK[ctx.data.role];
      const reqRank = ROLE_RANK[rule.required_role];
      if (userRank < reqRank) {
        return Response.redirect(
          `${url.origin}/paywall.html?from=${encodeURIComponent(path)}&need=${rule.required_role}`,
          302,
        );
      }
    }
  } catch {
    // D1 查詢失敗時不擋，避免規則表壞掉導致整站不能用（fail-open for read）
  }

  return passthrough(ctx, needRefreshCookie, refreshedToken);
};

async function passthrough(
  ctx: RequestCtx,
  needRefresh: boolean,
  refreshedToken: string | null,
): Promise<Response> {
  const res = await ctx.next();
  if (needRefresh && refreshedToken) {
    const newRes = new Response(res.body, res);
    newRes.headers.append("Set-Cookie", buildSessionCookie(refreshedToken));
    return newRes;
  }
  return res;
}
