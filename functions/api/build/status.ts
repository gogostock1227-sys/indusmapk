// GET /api/build/status
// 列最近 5 次 build run 狀態（admin 後台 publish 頁顯示）
import type { RequestCtx } from "../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../lib/auth-guard";
import { listRecentRuns } from "../../lib/github";

const WORKFLOW_FILE = "build-and-deploy.yml";

export const onRequestGet = async (ctx: RequestCtx) => {
  const guard = requireRole(ctx.data.user, "admin");
  if (guard) return guard;

  try {
    const runs = await listRecentRuns(ctx.env, WORKFLOW_FILE, 5);
    return jsonOk({
      runs: runs.map(r => ({
        id: r.id,
        name: r.name,
        status: r.status,             // queued / in_progress / completed
        conclusion: r.conclusion,     // success / failure / cancelled / null
        url: r.html_url,
        created_at: r.created_at,
        updated_at: r.updated_at,
      })),
    });
  } catch (e: any) {
    return jsonError(`查詢 build 狀態失敗：${e.message}`, 502);
  }
};
