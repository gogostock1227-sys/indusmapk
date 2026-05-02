// /api/data/concept-groups
//   GET: admin+ (data_perm.concept_groups) → 回整個 data/concept_groups.json
//   PUT: 整檔覆蓋，body { data: {...}, summary?: string }
//
// 後端 GitHub Contents API commit 帶 admin email 作為 author，
// commit message 含 admin email + diff summary，audit log 同步寫入 D1。
import type { RequestCtx } from "../../lib/types";
import { requireDataPerm, jsonOk, jsonError } from "../../lib/auth-guard";
import { getFile, putFile } from "../../lib/github";
import { logAudit, getClientIp } from "../../lib/audit";

const FILE_PATH = "data/concept_groups.json";

export const onRequestGet = async (ctx: RequestCtx) => {
  const guard = requireDataPerm(ctx.data.user, "concept_groups");
  if (guard) return guard;

  try {
    const file = await getFile(ctx.env, FILE_PATH);
    if (!file) return jsonError("data/concept_groups.json 不存在", 404);
    const data = JSON.parse(file.content);
    return jsonOk({ data, sha: file.sha, group_count: Object.keys(data).length });
  } catch (e: any) {
    return jsonError(`讀取失敗：${e.message}`, 502);
  }
};

export const onRequestPut = async (ctx: RequestCtx) => {
  const caller = ctx.data.user;
  const guard = requireDataPerm(caller, "concept_groups");
  if (guard) return guard;
  if (!caller) return jsonError("unauthorized", 401);

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  const data = body?.data;
  const summary = String(body?.summary ?? "").trim();

  // schema 驗證：dict<group_name, ticker[]>
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return jsonError("body.data 必須是 {族群: [tickers...]} 物件", 400);
  }
  for (const [k, v] of Object.entries(data)) {
    if (!Array.isArray(v)) {
      return jsonError(`族群「${k}」的值必須是陣列`, 400);
    }
    for (const ticker of v) {
      if (typeof ticker !== "string") {
        return jsonError(`族群「${k}」內含非字串 ticker`, 400);
      }
    }
  }

  // 與 build_site.py / migrate 工具產出格式對齊：indent=2 + 末尾 \n
  const content = JSON.stringify(data, null, 2) + "\n";
  const groupCount = Object.keys(data).length;
  const tickerCount = Object.values(data).reduce(
    (sum: number, arr: any) => sum + (Array.isArray(arr) ? arr.length : 0),
    0,
  );
  const message = `data: 編輯 concept_groups (${groupCount} 族群 / ${tickerCount} ticker) by ${caller.email}`
    + (summary ? `\n\n${summary}` : "");

  try {
    const result = await putFile(ctx.env, FILE_PATH, content, message, caller.email);
    await logAudit(ctx.env, {
      user: caller,
      action: "data_edit",
      target: FILE_PATH,
      diff_summary: summary || `${groupCount} 族群 / ${tickerCount} ticker`,
      ip: getClientIp(ctx.request),
    });
    return jsonOk({ ok: true, commit: result.commitSha, group_count: groupCount });
  } catch (e: any) {
    if (e.conflict) {
      return jsonError("資料已被他人改動，請重新載入後再儲存。", 409);
    }
    return jsonError(`儲存失敗：${e.message}`, 502);
  }
};
