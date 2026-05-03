// POST /api/build/trigger
// admin 點「發布」按鈕 → 觸發 GitHub Actions build-and-deploy workflow_dispatch
// body: { reason?: string }
import type { RequestCtx } from "../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../lib/auth-guard";
import { triggerWorkflow } from "../../lib/github";
import { logAudit, getClientIp } from "../../lib/audit";

const WORKFLOW_FILE = "build-and-deploy.yml";

export const onRequestPost = async (ctx: RequestCtx) => {
  const caller = ctx.data.user;
  const guard = requireRole(caller, "admin");
  if (guard) return guard;
  if (!caller) return jsonError("unauthorized", 401);

  let body: any = {};
  try { body = await ctx.request.json(); } catch { /* empty body 也可 */ }

  const reason = String(body?.reason ?? "").trim()
                 || `${caller.email} 觸發手動 rebuild`;
  // skip_finlab=true → 用 cache 純 render（1-2 分鐘）
  // skip_finlab=false → 抓 finlab 增量資料 + 重 render（5-8 分鐘）
  const skipFinlab = body?.skip_finlab === true ? "true" : "false";

  try {
    await triggerWorkflow(ctx.env, WORKFLOW_FILE, {
      reason,
      skip_finlab: skipFinlab,
    });
  } catch (e: any) {
    return jsonError(`GitHub Actions trigger 失敗：${e.message}`, 502);
  }

  await logAudit(ctx.env, {
    user: caller,
    action: "build_trigger",
    target: WORKFLOW_FILE,
    diff_summary: `${reason} (skip_finlab=${skipFinlab})`,
    ip: getClientIp(ctx.request),
  });

  const eta = skipFinlab === "true" ? "1-2 分鐘" : "5-8 分鐘";
  return jsonOk({
    ok: true,
    message: `已觸發 GitHub Actions（${skipFinlab === "true" ? "純 render" : "抓 finlab + render"}），約 ${eta} 後網站會自動更新。`,
    reason,
    skip_finlab: skipFinlab,
  });
};
