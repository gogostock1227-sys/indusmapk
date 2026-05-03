// 一次性 debug endpoint — 確認 Cloudflare Pages env vars 是否實際送進 Function runtime
// 安全設計：
//   - 需要帶 ?key=indusmapk-debug-2026 才能訪問（簡單防爬蟲）
//   - 永遠不回傳 secret 實際值，只回 set/length/prefix metadata
//   - 用完即刪（debug 完成後 commit 移除）
import type { Env } from "../../lib/types";

const DEBUG_KEY = "indusmapk-debug-2026";

interface Ctx {
  env: Env;
  request: Request;
  data: Record<string, unknown>;
}

export const onRequestGet = async (ctx: Ctx) => {
  const url = new URL(ctx.request.url);
  if (url.searchParams.get("key") !== DEBUG_KEY) {
    return new Response("forbidden", { status: 403 });
  }
  const env = ctx.env;
  const meta = (v: string | undefined) => ({
    set: !!v,
    length: (v ?? "").length,
    prefix: (v ?? "").slice(0, 12),
  });
  const body = {
    plain_text_vars: {
      GOOGLE_CLIENT_ID: meta(env.GOOGLE_CLIENT_ID),
      TURNSTILE_SITE_KEY: env.TURNSTILE_SITE_KEY ?? "(undefined)",
      GITHUB_REPO: env.GITHUB_REPO ?? "(undefined)",
      APP_BASE_URL: env.APP_BASE_URL ?? "(undefined)",
    },
    secrets_metadata_only: {
      GOOGLE_CLIENT_SECRET: meta(env.GOOGLE_CLIENT_SECRET),
      JWT_SECRET: meta(env.JWT_SECRET),
      TURNSTILE_SECRET: meta(env.TURNSTILE_SECRET),
      GITHUB_TOKEN: meta(env.GITHUB_TOKEN),
    },
    bindings: {
      DB_bound: !!env.DB,
    },
  };
  return new Response(JSON.stringify(body, null, 2), {
    headers: { "Content-Type": "application/json" },
  });
};
