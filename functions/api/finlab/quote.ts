// GET /api/finlab/quote?ticker=2330
//
// finlab 即時報價代理。FINLAB_TOKEN 從 CF env 讀，用戶不需自帶 token。
//
// ⚠ finlab.tw 主要服務是 Python SDK（finlab.data.get(...)），
//   公開 REST endpoint 文件較少。此 proxy 嘗試呼叫 finlab 的 cloud function
//   data endpoint。若 endpoint 不對或 token 格式不一致，回 502 + 詳細錯誤。
//   建議搭配 finmind 代理（功能重疊但 REST 公開穩定）。
import type { RequestCtx } from "../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../lib/auth-guard";

// finlab 內部 data endpoint（從社群 reverse engineering 來的，可能變動）
const FINLAB_DATA_ENDPOINT = "https://asia-east2-fdata-299302.cloudfunctions.net/data_v4";

export const onRequestGet = async (ctx: RequestCtx) => {
  const guard = requireRole(ctx.data.user, "admin");
  if (guard) return guard;

  if (!ctx.env.FINLAB_TOKEN) {
    return jsonError("尚未設定 FINLAB_TOKEN（請到 Cloudflare Dashboard → Pages → Settings → Variables → Secrets 加上）", 503);
  }

  const url = new URL(ctx.request.url);
  const ticker = url.searchParams.get("ticker")?.trim();
  if (!ticker) return jsonError("ticker 必填", 400);

  try {
    const res = await fetch(FINLAB_DATA_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_token: ctx.env.FINLAB_TOKEN,
        bucket_name: "finlab_tw_stock_item",
        blob_name: "price:close",
        ticker,
      }),
    });
    if (!res.ok) {
      return jsonError(`finlab 回應 ${res.status}：${await res.text()}`, 502);
    }
    const raw = await res.text();
    // 嘗試解析（finlab 可能回 parquet binary 或 json，這裡只 echo raw）
    return new Response(raw, {
      headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
    });
  } catch (e: any) {
    return jsonError(`finlab 呼叫失敗：${e.message}（endpoint 可能變動，建議改用 /api/finmind/quote）`, 502);
  }
};
