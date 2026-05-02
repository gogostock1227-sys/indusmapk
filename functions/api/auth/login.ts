// GET /api/auth/login — 驗 Turnstile，跳轉到 Google OAuth consent screen
import type { Env, RequestCtx } from "../../lib/types";
import { verifyTurnstile } from "../../lib/turnstile";
import { getClientIp } from "../../lib/audit";

const STATE_COOKIE = "oauth_state";

function randomState(): string {
  const buf = new Uint8Array(16);
  crypto.getRandomValues(buf);
  return Array.from(buf, (b) => b.toString(16).padStart(2, "0")).join("");
}

export const onRequestGet = async (ctx: RequestCtx) => {
  const env = ctx.env as Env;
  const url = new URL(ctx.request.url);
  const turnstileToken = url.searchParams.get("ts") || "";
  const next = url.searchParams.get("next") || "/";

  const verify = await verifyTurnstile(env, turnstileToken, getClientIp(ctx.request));
  if (!verify.success) {
    return new Response(
      JSON.stringify({ error: "turnstile-failed", codes: verify.errorCodes }),
      { status: 403, headers: { "Content-Type": "application/json" } },
    );
  }

  const state = randomState();
  const params = new URLSearchParams({
    client_id: env.GOOGLE_CLIENT_ID,
    redirect_uri: `${env.APP_BASE_URL}/api/auth/callback`,
    response_type: "code",
    scope: "openid email profile",
    state,
    access_type: "online",
    prompt: "select_account",
  });
  // 把 next 也藏進 state cookie（用 | 分隔）以便 callback 知道要回哪
  const stateValue = `${state}|${encodeURIComponent(next)}`;

  return new Response(null, {
    status: 302,
    headers: {
      Location: `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`,
      "Set-Cookie": [
        `${STATE_COOKIE}=${stateValue}`,
        "Path=/",
        "HttpOnly",
        "Secure",
        "SameSite=Lax",
        "Max-Age=600",
      ].join("; "),
    },
  });
};
