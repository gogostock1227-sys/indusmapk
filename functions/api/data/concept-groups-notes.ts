// /api/data/concept-groups-notes
//   GET: 回 data/concept_groups_notes.json（每筆 ticker 的 inline 註解 sidecar）
//   PUT: 整檔覆蓋
//
// 此 sidecar 與 concept_groups.json 對應：{group: {ticker: note}}。
// 編輯 ticker 時若該 ticker 有 audit 註解（ground_truth、命中字數位置等），admin UI
// 應同步維護 notes 內的對應條目。共用 data_perm.concept_groups 權限。
import type { RequestCtx } from "../../lib/types";
import { requireDataPerm, jsonOk, jsonError } from "../../lib/auth-guard";
import { getFile, putFile } from "../../lib/github";
import { logAudit, getClientIp } from "../../lib/audit";

const FILE_PATH = "data/concept_groups_notes.json";

export const onRequestGet = async (ctx: RequestCtx) => {
  const guard = requireDataPerm(ctx.data.user, "concept_groups");
  if (guard) return guard;

  try {
    const file = await getFile(ctx.env, FILE_PATH);
    if (!file) return jsonOk({ data: {}, sha: null }); // notes sidecar 可能還不存在
    const data = JSON.parse(file.content);
    return jsonOk({ data, sha: file.sha });
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

  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return jsonError("body.data 必須是 {族群: {ticker: 註解}} 物件", 400);
  }

  const content = JSON.stringify(data, null, 2) + "\n";
  const message = `data: 編輯 concept_groups_notes by ${caller.email}`
    + (summary ? `\n\n${summary}` : "");

  try {
    const result = await putFile(ctx.env, FILE_PATH, content, message, caller.email);
    await logAudit(ctx.env, {
      user: caller,
      action: "data_edit",
      target: FILE_PATH,
      diff_summary: summary || "更新 inline 註解",
      ip: getClientIp(ctx.request),
    });
    return jsonOk({ ok: true, commit: result.commitSha });
  } catch (e: any) {
    if (e.conflict) {
      return jsonError("資料已被他人改動，請重新載入後再儲存。", 409);
    }
    return jsonError(`儲存失敗：${e.message}`, 502);
  }
};
