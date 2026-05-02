// /api/data/stock-profiles
//   GET ?ticker=2330  → 單股 profile + sha
//   GET             → 所有 ticker 列表（精簡：只回 ticker + name + segment）
//   PUT body { ticker, profile, summary? } → 改單股、寫回整檔
//
// stock_profiles.json ~1MB 1900+ 股，整檔下載到 admin UI 太重。
// 設計：admin UI 只取 list 顯示 → 點某股拉單股詳細 → 改完只送單股 patch，
// 後端讀整檔、改單股、寫回整檔（一次 GitHub commit）。
import type { RequestCtx } from "../../lib/types";
import { requireDataPerm, jsonOk, jsonError } from "../../lib/auth-guard";
import { getFile, putFile } from "../../lib/github";
import { logAudit, getClientIp } from "../../lib/audit";

const FILE_PATH = "concept_taxonomy/stock_profiles.json";

export const onRequestGet = async (ctx: RequestCtx) => {
  const guard = requireDataPerm(ctx.data.user, "stock_profiles");
  if (guard) return guard;

  const url = new URL(ctx.request.url);
  const ticker = url.searchParams.get("ticker")?.trim();

  try {
    const file = await getFile(ctx.env, FILE_PATH);
    if (!file) return jsonError("stock_profiles.json 不存在", 404);
    const data = JSON.parse(file.content);

    if (ticker) {
      // 單股查詢
      const profile = data[ticker];
      if (!profile) return jsonError(`找不到 ticker=${ticker}`, 404);
      return jsonOk({ ticker, profile, sha: file.sha });
    }

    // 列表模式：只回精簡欄位
    const list = Object.entries(data).map(([t, p]: [string, any]) => ({
      ticker: t,
      name: p?.name ?? null,
      industry_segment: p?.industry_segment ?? null,
      supply_chain_position: p?.supply_chain_position ?? null,
      core_themes: Array.isArray(p?.core_themes) ? p.core_themes.length : 0,
      human_reviewed: !!p?.human_reviewed,
    }));
    return jsonOk({ list, total: list.length, sha: file.sha });
  } catch (e: any) {
    return jsonError(`讀取失敗：${e.message}`, 502);
  }
};

export const onRequestPut = async (ctx: RequestCtx) => {
  const caller = ctx.data.user;
  const guard = requireDataPerm(caller, "stock_profiles");
  if (guard) return guard;
  if (!caller) return jsonError("unauthorized", 401);

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  const ticker = String(body?.ticker ?? "").trim();
  const incoming = body?.profile;
  const summary = String(body?.summary ?? "").trim();

  if (!ticker) return jsonError("body.ticker 必填", 400);
  if (!incoming || typeof incoming !== "object" || Array.isArray(incoming)) {
    return jsonError("body.profile 必須是物件", 400);
  }

  // 讀整檔 → patch 單股 → 寫回
  let file;
  try { file = await getFile(ctx.env, FILE_PATH); }
  catch (e: any) { return jsonError(`讀取失敗：${e.message}`, 502); }
  if (!file) return jsonError("stock_profiles.json 不存在", 404);

  const data = JSON.parse(file.content);
  const before = data[ticker] || null;
  data[ticker] = { ...incoming, ticker, last_validated: new Date().toISOString() };

  const content = JSON.stringify(data, null, 2) + "\n";
  const action = before ? "編輯" : "新增";
  const message = `data: ${action} stock_profile ${ticker} by ${caller.email}`
    + (summary ? `\n\n${summary}` : "");

  try {
    const result = await putFile(ctx.env, FILE_PATH, content, message, caller.email);
    await logAudit(ctx.env, {
      user: caller,
      action: "data_edit",
      target: `${FILE_PATH}#${ticker}`,
      diff_summary: summary || `${action} ${ticker}`,
      ip: getClientIp(ctx.request),
    });
    return jsonOk({ ok: true, commit: result.commitSha, ticker });
  } catch (e: any) {
    if (e.conflict) {
      return jsonError("資料已被他人改動，請重新載入後再儲存。", 409);
    }
    return jsonError(`儲存失敗：${e.message}`, 502);
  }
};
