// GET /api/finlab/financials?ticker=2330&type=income
// 同 quote.ts 的 caveat：finlab REST 非公開穩定，建議用 finmind 替代
import type { RequestCtx } from "../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../lib/auth-guard";

const FINLAB_DATA_ENDPOINT = "https://asia-east2-fdata-299302.cloudfunctions.net/data_v4";

const TYPE_TO_BLOB: Record<string, string> = {
  income:    "fundamental_features:營業收入",
  balance:   "fundamental_features:總資產",
  cashflow:  "fundamental_features:營業活動之現金流量",
};

export const onRequestGet = async (ctx: RequestCtx) => {
  const guard = requireRole(ctx.data.user, "admin");
  if (guard) return guard;

  if (!ctx.env.FINLAB_TOKEN) {
    return jsonError("尚未設定 FINLAB_TOKEN", 503);
  }

  const url = new URL(ctx.request.url);
  const ticker = url.searchParams.get("ticker")?.trim();
  const type = url.searchParams.get("type")?.trim() || "income";
  if (!ticker) return jsonError("ticker 必填", 400);
  const blob = TYPE_TO_BLOB[type];
  if (!blob) return jsonError(`type 必須是 ${Object.keys(TYPE_TO_BLOB).join("/")}`, 400);

  try {
    const res = await fetch(FINLAB_DATA_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_token: ctx.env.FINLAB_TOKEN,
        bucket_name: "finlab_tw_stock_item",
        blob_name: blob,
        ticker,
      }),
    });
    if (!res.ok) {
      return jsonError(`finlab 回應 ${res.status}：${await res.text()}`, 502);
    }
    return new Response(await res.text(), {
      headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
    });
  } catch (e: any) {
    return jsonError(`finlab 呼叫失敗：${e.message}`, 502);
  }
};
