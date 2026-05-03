// GET /api/finmind/financials?ticker=2330&type=income&start=2024-01-01
// finmind 財報代理。
//   type=income     → TaiwanStockFinancialStatements (損益表)
//   type=balance    → TaiwanStockBalanceSheet         (資產負債)
//   type=cashflow   → TaiwanStockCashFlowsStatement   (現金流量)
import type { RequestCtx } from "../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../lib/auth-guard";

const FINMIND_BASE = "https://api.finmindtrade.com/api/v4/data";

const TYPE_TO_DATASET: Record<string, string> = {
  income:   "TaiwanStockFinancialStatements",
  balance:  "TaiwanStockBalanceSheet",
  cashflow: "TaiwanStockCashFlowsStatement",
};

export const onRequestGet = async (ctx: RequestCtx) => {
  const guard = requireRole(ctx.data.user, "admin");
  if (guard) return guard;

  if (!ctx.env.FINMIND_TOKEN) {
    return jsonError("尚未設定 FINMIND_TOKEN", 503);
  }

  const url = new URL(ctx.request.url);
  const ticker = url.searchParams.get("ticker")?.trim();
  const type = url.searchParams.get("type")?.trim() || "income";
  const start = url.searchParams.get("start")?.trim()
                || new Date(Date.now() - 730 * 86400000).toISOString().slice(0, 10); // 預設兩年
  if (!ticker) return jsonError("ticker 必填", 400);
  const dataset = TYPE_TO_DATASET[type];
  if (!dataset) return jsonError(`type 必須是 ${Object.keys(TYPE_TO_DATASET).join("/")}`, 400);

  const params = new URLSearchParams({
    dataset,
    data_id: ticker,
    start_date: start,
    token: ctx.env.FINMIND_TOKEN,
  });

  try {
    const res = await fetch(`${FINMIND_BASE}?${params}`);
    if (!res.ok) return jsonError(`finmind 回應 ${res.status}：${await res.text()}`, 502);
    const data = await res.json() as { status: number; msg: string; data?: any[] };
    if (data.status !== 200) return jsonError(`finmind 錯誤：${data.msg}`, 502);
    return jsonOk({
      ticker,
      type,
      dataset,
      rows_returned: (data.data ?? []).length,
      data: data.data ?? [],
    });
  } catch (e: any) {
    return jsonError(`finmind 呼叫失敗：${e.message}`, 502);
  }
};
