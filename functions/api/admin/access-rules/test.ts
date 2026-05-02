// POST /api/admin/access-rules/test
// body: { path: "/some/path.html" }
// 回傳該路徑會命中哪條規則（用來測試 pattern）
import type { RequestCtx } from "../../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../../lib/auth-guard";
import { findMatchingRule } from "../../../lib/d1";

export const onRequestPost = async (ctx: RequestCtx) => {
  const guard = requireRole(ctx.data.user, "super_admin");
  if (guard) return guard;

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  const path = String(body?.path ?? "").trim();
  if (!path) return jsonError("path required", 400);

  const rule = await findMatchingRule(ctx.env, path);
  return jsonOk({
    path,
    matched: !!rule,
    rule,
    effective_role: rule?.required_role ?? "guest",
    note: rule
      ? `路徑 ${path} 命中規則 #${rule.id} (pattern=${rule.path_pattern})，需要 ${rule.required_role} 才能訪問。`
      : `路徑 ${path} 沒有命中任何 active 規則，所有人都能訪問（guest 級）。`,
  });
};
