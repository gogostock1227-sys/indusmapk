// /api/data/industry-meta
//   GET → data/industry_meta.json（族群文案、CAGR、市場規模、indicators 等）
//   PUT → 整檔覆蓋
import type { RequestCtx } from "../../lib/types";
import { requireDataPerm, jsonOk, jsonError } from "../../lib/auth-guard";
import { getFile, putFile } from "../../lib/github";
import { logAudit, getClientIp } from "../../lib/audit";

const FILE_PATH = "data/industry_meta.json";

export const onRequestGet = async (ctx: RequestCtx) => {
  const guard = requireDataPerm(ctx.data.user, "industry_meta");
  if (guard) return guard;
  try {
    const file = await getFile(ctx.env, FILE_PATH);
    if (!file) return jsonError("industry_meta.json 不存在", 404);
    const data = JSON.parse(file.content);
    return jsonOk({ data, sha: file.sha, group_count: Object.keys(data).length });
  } catch (e: any) {
    return jsonError(`讀取失敗：${e.message}`, 502);
  }
};

export const onRequestPut = async (ctx: RequestCtx) => {
  const caller = ctx.data.user;
  const guard = requireDataPerm(caller, "industry_meta");
  if (guard) return guard;
  if (!caller) return jsonError("unauthorized", 401);

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  const data = body?.data;
  const summary = String(body?.summary ?? "").trim();

  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return jsonError("body.data 必須是物件", 400);
  }

  const content = JSON.stringify(data, null, 2) + "\n";
  const message = `data: 編輯 industry_meta (${Object.keys(data).length} 族群) by ${caller.email}`
    + (summary ? `\n\n${summary}` : "");

  try {
    const result = await putFile(ctx.env, FILE_PATH, content, message, caller.email);
    await logAudit(ctx.env, {
      user: caller,
      action: "data_edit",
      target: FILE_PATH,
      diff_summary: summary || `${Object.keys(data).length} 族群`,
      ip: getClientIp(ctx.request),
    });
    return jsonOk({ ok: true, commit: result.commitSha });
  } catch (e: any) {
    if (e.conflict) return jsonError("資料已被他人改動，請重新載入後再儲存。", 409);
    return jsonError(`儲存失敗：${e.message}`, 502);
  }
};
