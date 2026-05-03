// GET /api/finmind/quote?ticker=2330&days=30
// finmind 個股日 K 代理（公開 REST API + token）
//
// finmind API 文件：https://finmindtrade.com/analysis/#/data/api
// dataset: TaiwanStockPrice → {date, stock_id, open, max, min, close, Trading_Volume, ...}
import type { RequestCtx } from "../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../lib/auth-guard";

const FINMIND_BASE = "https://api.finmindtrade.com/api/v4/data";

export const onRequestGet = async (ctx: RequestCtx) => {
  const guard = requireRole(ctx.data.user, "admin");
  if (guard) return guard;

  if (!ctx.env.FINMIND_TOKEN) {
    return jsonError("尚未設定 FINMIND_TOKEN（請到 Cloudflare Dashboard → Pages → Settings → Variables → Secrets 加上）", 503);
  }

  const url = new URL(ctx.request.url);
  const ticker = url.searchParams.get("ticker")?.trim();
  const days = Math.min(parseInt(url.searchParams.get("days") || "30", 10) || 30, 365);
  if (!ticker) return jsonError("ticker 必填", 400);

  const startDate = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);
  const params = new URLSearchParams({
    dataset: "TaiwanStockPrice",
    data_id: ticker,
    start_date: startDate,
    token: ctx.env.FINMIND_TOKEN,
  });

  try {
    const res = await fetch(`${FINMIND_BASE}?${params}`);
    if (!res.ok) return jsonError(`finmind 回應 ${res.status}：${await res.text()}`, 502);
    const data = await res.json() as { status: number; msg: string; data?: any[] };
    if (data.status !== 200) return jsonError(`finmind 錯誤：${data.msg}`, 502);
    const rows = data.data ?? [];
    const latest = rows[rows.length - 1] ?? null;
    return jsonOk({
      ticker,
      days_returned: rows.length,
      latest,
      history: rows,
    });
  } catch (e: any) {
    return jsonError(`finmind 呼叫失敗：${e.message}`, 502);
  }
};
