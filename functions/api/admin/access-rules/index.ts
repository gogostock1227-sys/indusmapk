// GET /api/admin/access-rules — 列規則（admin+ 都能看）
// POST /api/admin/access-rules — 新增規則（super_admin only）
import type { RequestCtx, Role } from "../../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../../lib/auth-guard";
import { listAccessRules } from "../../../lib/d1";
import { logAudit, getClientIp } from "../../../lib/audit";

const VALID_ROLES: Role[] = ["guest", "member", "premium", "admin"];

export const onRequestGet = async (ctx: RequestCtx) => {
  const guard = requireRole(ctx.data.user, "admin");
  if (guard) return guard;
  const rules = await listAccessRules(ctx.env);
  return jsonOk({ rules });
};

export const onRequestPost = async (ctx: RequestCtx) => {
  const caller = ctx.data.user;
  const guard = requireRole(caller, "super_admin");
  if (guard) return guard;
  if (!caller) return jsonError("unauthorized", 401);

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  const path_pattern = String(body?.path_pattern ?? "").trim();
  const required_role = String(body?.required_role ?? "").trim();
  const comment = body?.comment ? String(body.comment) : null;

  if (!path_pattern) return jsonError("path_pattern required", 400);
  if (!VALID_ROLES.includes(required_role as Role)) {
    return jsonError(`required_role must be one of ${VALID_ROLES.join(",")}`, 400);
  }

  const result = await ctx.env.DB.prepare(
    `INSERT INTO access_rules (path_pattern, required_role, comment, created_by, active)
     VALUES (?, ?, ?, ?, 1)`,
  ).bind(path_pattern, required_role, comment, caller.id).run();

  const id = result.meta.last_row_id;
  const fresh = await ctx.env.DB.prepare(`SELECT * FROM access_rules WHERE id = ?`)
    .bind(id).first();

  await logAudit(ctx.env, {
    user: caller,
    action: "access_rule_change",
    target: `access_rules/${id}`,
    diff_summary: `created: ${path_pattern} → ${required_role}`,
    ip: getClientIp(ctx.request),
  });

  return jsonOk(fresh, 201);
};
