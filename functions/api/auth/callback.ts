// GET /api/auth/callback — Google OAuth 回調：換 token、拿 userinfo、upsert D1、簽 JWT、set cookie
import type { Env, RequestCtx } from "../../lib/types";
import { upsertGoogleUser } from "../../lib/d1";
import { signJwt, buildSessionCookie } from "../../lib/jwt";
import { logAudit, getClientIp } from "../../lib/audit";

const STATE_COOKIE = "oauth_state";

function readCookie(request: Request, name: string): string | null {
  const raw = request.headers.get("cookie");
  if (!raw) return null;
  for (const part of raw.split(/;\s*/)) {
    const eq = part.indexOf("=");
    if (eq < 0) continue;
    if (part.slice(0, eq) === name) return part.slice(eq + 1);
  }
  return null;
}

interface GoogleTokenResponse {
  access_token: string;
  id_token?: string;
  expires_in?: number;
  scope?: string;
  token_type?: string;
}

interface GoogleUserInfo {
  sub: string;
  email: string;
  name?: string;
  picture?: string;
  email_verified?: boolean;
}

export const onRequestGet = async (ctx: RequestCtx) => {
  const env = ctx.env as Env;
  const url = new URL(ctx.request.url);
  const code = url.searchParams.get("code");
  const stateFromQuery = url.searchParams.get("state");

  if (!code || !stateFromQuery) {
    return errorRedirect("missing-code");
  }

  // 驗 state
  const stateCookie = readCookie(ctx.request, STATE_COOKIE);
  if (!stateCookie) return errorRedirect("state-missing");
  const [stateInCookie, nextEncoded = ""] = stateCookie.split("|");
  if (stateInCookie !== stateFromQuery) return errorRedirect("state-mismatch");
  const next = nextEncoded ? decodeURIComponent(nextEncoded) : "/";

  // 換 access_token
  const tokenRes = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      code,
      client_id: env.GOOGLE_CLIENT_ID,
      client_secret: env.GOOGLE_CLIENT_SECRET,
      redirect_uri: `${env.APP_BASE_URL}/api/auth/callback`,
      grant_type: "authorization_code",
    }),
  });
  if (!tokenRes.ok) return errorRedirect(`token-exchange-${tokenRes.status}`);
  const tokens = (await tokenRes.json()) as GoogleTokenResponse;

  // 拿 userinfo
  const userRes = await fetch("https://www.googleapis.com/oauth2/v3/userinfo", {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
  });
  if (!userRes.ok) return errorRedirect(`userinfo-${userRes.status}`);
  const info = (await userRes.json()) as GoogleUserInfo;

  if (!info.email) return errorRedirect("no-email");

  // upsert D1
  const user = await upsertGoogleUser(env, {
    google_id: info.sub,
    email: info.email,
    name: info.name ?? null,
    picture: info.picture ?? null,
  });

  if (user.status === "suspended") {
    return errorRedirect("suspended");
  }

  // audit log
  await logAudit(env, {
    user,
    action: "login",
    ip: getClientIp(ctx.request),
  });

  // 簽 JWT
  const token = await signJwt(
    {
      uid: user.id,
      email: user.email,
      role: user.role,
      role_exp: user.role_expires_at,
    },
    env.JWT_SECRET,
  );

  return new Response(null, {
    status: 302,
    headers: new Headers([
      ["Location", next],
      ["Set-Cookie", buildSessionCookie(token)],
      // 清掉 oauth_state cookie（用過即丟）
      ["Set-Cookie", `${STATE_COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`],
    ]),
  });
};

function errorRedirect(reason: string): Response {
  return new Response(null, {
    status: 302,
    headers: { Location: `/admin/login.html?error=${encodeURIComponent(reason)}` },
  });
}
