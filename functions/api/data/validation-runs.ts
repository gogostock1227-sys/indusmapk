// /api/data/validation-runs
//   GET → 列 validation_runs/ 目錄下的檔案 + 讀取 _approved.json
//   POST { run_id, applied: bool, comment? } → 修改 _approved.json
//
// validation_runs/ 是驗證腳本產出的審計紀錄目錄。每次跑驗證會產生
// validation_runs/<timestamp>.json，admin 在後台可瀏覽 + 標記 approve/reject。
// 結果寫進 validation_runs/_approved.json：{ run_id: { applied, by, at, comment } }
import type { RequestCtx } from "../../lib/types";
import { requireDataPerm, jsonOk, jsonError } from "../../lib/auth-guard";
import { getFile, putFile } from "../../lib/github";
import { logAudit, getClientIp } from "../../lib/audit";

const APPROVED_FILE = "validation_runs/_approved.json";

interface ApprovedMap {
  [run_id: string]: {
    applied: boolean;
    by: string;
    at: string;
    comment?: string;
  };
}

export const onRequestGet = async (ctx: RequestCtx) => {
  const guard = requireDataPerm(ctx.data.user, "validation_runs");
  if (guard) return guard;

  // 讀 _approved.json（可能不存在）
  let approved: ApprovedMap = {};
  let sha: string | null = null;
  try {
    const file = await getFile(ctx.env, APPROVED_FILE);
    if (file) {
      approved = JSON.parse(file.content);
      sha = file.sha;
    }
  } catch (e: any) {
    return jsonError(`讀取 _approved.json 失敗：${e.message}`, 502);
  }

  // 列目錄是低頻操作，用 GitHub Trees API
  // GET /repos/{owner}/{repo}/contents/validation_runs
  try {
    const res = await fetch(
      `https://api.github.com/repos/${ctx.env.GITHUB_REPO}/contents/validation_runs`,
      {
        headers: {
          Authorization: `Bearer ${ctx.env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "indusmapk-admin/1.0",
        },
      },
    );
    if (res.status === 404) return jsonOk({ runs: [], approved, sha });
    if (!res.ok) return jsonError(`列目錄失敗：${res.status}`, 502);
    const items = (await res.json()) as Array<{
      name: string; path: string; type: string; size: number;
    }>;
    const runs = items
      .filter(i => i.type === "file" && i.name.endsWith(".json") && !i.name.startsWith("_"))
      .map(i => ({
        run_id: i.name.replace(/\.json$/, ""),
        path: i.path,
        size: i.size,
        approved_state: approved[i.name.replace(/\.json$/, "")] ?? null,
      }))
      .sort((a, b) => b.run_id.localeCompare(a.run_id)); // 最新在前
    return jsonOk({ runs, approved, sha });
  } catch (e: any) {
    return jsonError(`列目錄失敗：${e.message}`, 502);
  }
};

export const onRequestPost = async (ctx: RequestCtx) => {
  const caller = ctx.data.user;
  const guard = requireDataPerm(caller, "validation_runs");
  if (guard) return guard;
  if (!caller) return jsonError("unauthorized", 401);

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  const runId = String(body?.run_id ?? "").trim();
  const applied = !!body?.applied;
  const comment = body?.comment ? String(body.comment) : undefined;

  if (!runId) return jsonError("body.run_id 必填", 400);

  // 讀現有 approved → patch → 寫回
  let approved: ApprovedMap = {};
  try {
    const file = await getFile(ctx.env, APPROVED_FILE);
    if (file) approved = JSON.parse(file.content);
  } catch (e: any) {
    return jsonError(`讀取 _approved.json 失敗：${e.message}`, 502);
  }

  approved[runId] = {
    applied,
    by: caller.email,
    at: new Date().toISOString(),
    ...(comment ? { comment } : {}),
  };

  const content = JSON.stringify(approved, null, 2) + "\n";
  const verb = applied ? "approved" : "rejected";
  const message = `validation: ${verb} ${runId} by ${caller.email}`
    + (comment ? `\n\n${comment}` : "");

  try {
    const result = await putFile(ctx.env, APPROVED_FILE, content, message, caller.email);
    await logAudit(ctx.env, {
      user: caller,
      action: "data_edit",
      target: `validation_runs/${runId}`,
      diff_summary: `${verb}${comment ? " - " + comment : ""}`,
      ip: getClientIp(ctx.request),
    });
    return jsonOk({ ok: true, run_id: runId, applied, commit: result.commitSha });
  } catch (e: any) {
    if (e.conflict) return jsonError("資料已被他人改動，請重新載入後再試。", 409);
    return jsonError(`儲存失敗：${e.message}`, 502);
  }
};
