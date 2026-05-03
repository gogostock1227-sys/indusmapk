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
  // partial 模式：指定單一 fetch_*.py 腳本（whitelist 檢查在 workflow 端）
  const scriptRaw = String(body?.script ?? "").trim();
  // 防止任意命令注入：script 只能是純小寫字母 + 底線開頭 fetch_
  const script = /^fetch_[a-z_]+$/.test(scriptRaw) ? scriptRaw : "";

  try {
    await triggerWorkflow(ctx.env, WORKFLOW_FILE, {
      reason,
      skip_finlab: skipFinlab,
      script,
    });
  } catch (e: any) {
    return jsonError(`GitHub Actions trigger 失敗：${e.message}`, 502);
  }

  await logAudit(ctx.env, {
    user: caller,
    action: "build_trigger",
    target: WORKFLOW_FILE,
    diff_summary: script
      ? `${reason} (partial: ${script})`
      : `${reason} (skip_finlab=${skipFinlab})`,
    ip: getClientIp(ctx.request),
  });

  let mode: string, eta: string;
  if (script) {
    mode = `partial: ${script}`;
    eta = "4-7 分鐘";
  } else if (skipFinlab === "true") {
    mode = "純 render";
    eta = "1-2 分鐘";
  } else {
    mode = "抓 finlab + render";
    eta = "5-8 分鐘";
  }

  return jsonOk({
    ok: true,
    message: `已觸發 GitHub Actions（${mode}），約 ${eta} 後網站會自動更新。`,
    reason,
    skip_finlab: skipFinlab,
    script,
  });
};
