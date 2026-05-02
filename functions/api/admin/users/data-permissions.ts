// PUT /api/admin/users/data-permissions
// body: { id: number, permissions: { concept_groups?: bool, stock_profiles?: bool, ... } }
//
// 僅 super_admin 可呼叫。改 admin role 用戶的 data_permissions JSON。
// target.role 必須是 'admin'，否則 400。
import type { RequestCtx, DataPermissions } from "../../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../../lib/auth-guard";
import { getUserById } from "../../../lib/d1";
import { logAudit, getClientIp } from "../../../lib/audit";

const VALID_KEYS: (keyof DataPermissions)[] = [
  "concept_groups",
  "stock_profiles",
  "master_patch",
  "industry_meta",
  "validation_runs",
];

export const onRequestPut = async (ctx: RequestCtx) => {
  const caller = ctx.data.user;
  const guard = requireRole(caller, "super_admin");
  if (guard) return guard;
  if (!caller) return jsonError("unauthorized", 401);

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  const id = parseInt(body?.id, 10);
  const incoming = body?.permissions;
  if (isNaN(id)) return jsonError("invalid id", 400);
  if (!incoming || typeof incoming !== "object") return jsonError("permissions must be object", 400);

  const target = await getUserById(ctx.env, id);
  if (!target) return jsonError("not found", 404);
  if (target.role !== "admin") {
    return jsonError("data_permissions only applies to role='admin'", 400);
  }

  // sanitize：只接受白名單 key、值強制 boolean
  const cleaned: DataPermissions = {};
  for (const k of VALID_KEYS) {
    if (k in incoming) cleaned[k] = !!incoming[k];
  }

  const json = JSON.stringify(cleaned);
  await ctx.env.DB.prepare(
    `UPDATE users SET data_permissions = ? WHERE id = ?`,
  ).bind(json, target.id).run();

  await logAudit(ctx.env, {
    user: caller,
    action: "data_perm_change",
    target: `users/${target.id} (${target.email})`,
    diff_summary: `before=${JSON.stringify(target.data_permissions ?? {})} after=${json}`,
    ip: getClientIp(ctx.request),
  });

  const fresh = await getUserById(ctx.env, target.id);
  return jsonOk(fresh);
};
