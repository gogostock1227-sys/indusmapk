// PUT /api/admin/access-rules/:id — 更新規則（super_admin only）
// DELETE /api/admin/access-rules/:id — 軟刪除（active=0）（super_admin only）
import type { RequestCtx, Role } from "../../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../../lib/auth-guard";
import { logAudit, getClientIp } from "../../../lib/audit";

interface Params { id: string; }

const VALID_ROLES: Role[] = ["guest", "member", "premium", "admin"];

export const onRequestPut = async (ctx: RequestCtx<Params>) => {
  const caller = ctx.data.user;
  const guard = requireRole(caller, "super_admin");
  if (guard) return guard;
  if (!caller) return jsonError("unauthorized", 401);

  const id = parseInt(ctx.params.id, 10);
  if (isNaN(id)) return jsonError("invalid id", 400);

  const before = await ctx.env.DB.prepare(`SELECT * FROM access_rules WHERE id = ?`).bind(id).first();
  if (!before) return jsonError("not found", 404);

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  const sets: string[] = [];
  const binds: unknown[] = [];
  const diffs: string[] = [];

  if (body.path_pattern !== undefined) {
    const v = String(body.path_pattern).trim();
    if (!v) return jsonError("path_pattern cannot be empty", 400);
    sets.push("path_pattern = ?"); binds.push(v);
    if (v !== (before as any).path_pattern) diffs.push(`pattern: ${(before as any).path_pattern} → ${v}`);
  }
  if (body.required_role !== undefined) {
    if (!VALID_ROLES.includes(body.required_role)) {
      return jsonError(`required_role must be one of ${VALID_ROLES.join(",")}`, 400);
    }
    sets.push("required_role = ?"); binds.push(body.required_role);
    if (body.required_role !== (before as any).required_role) {
      diffs.push(`role: ${(before as any).required_role} → ${body.required_role}`);
    }
  }
  if (body.comment !== undefined) {
    sets.push("comment = ?"); binds.push(body.comment ?? null);
  }
  if (body.active !== undefined) {
    sets.push("active = ?"); binds.push(body.active ? 1 : 0);
    if (!!body.active !== !!((before as any).active)) {
      diffs.push(`active: ${(before as any).active} → ${body.active ? 1 : 0}`);
    }
  }

  if (sets.length === 0) return jsonOk({ ok: true, no_change: true });

  binds.push(id);
  await ctx.env.DB.prepare(`UPDATE access_rules SET ${sets.join(", ")} WHERE id = ?`)
    .bind(...binds).run();

  await logAudit(ctx.env, {
    user: caller,
    action: "access_rule_change",
    target: `access_rules/${id}`,
    diff_summary: diffs.length ? diffs.join("; ") : "comment updated",
    ip: getClientIp(ctx.request),
  });

  const fresh = await ctx.env.DB.prepare(`SELECT * FROM access_rules WHERE id = ?`).bind(id).first();
  return jsonOk(fresh);
};

export const onRequestDelete = async (ctx: RequestCtx<Params>) => {
  const caller = ctx.data.user;
  const guard = requireRole(caller, "super_admin");
  if (guard) return guard;
  if (!caller) return jsonError("unauthorized", 401);

  const id = parseInt(ctx.params.id, 10);
  if (isNaN(id)) return jsonError("invalid id", 400);

  // 軟刪除 (active = 0)，保留審計紀錄
  await ctx.env.DB.prepare(`UPDATE access_rules SET active = 0 WHERE id = ?`).bind(id).run();

  await logAudit(ctx.env, {
    user: caller,
    action: "access_rule_change",
    target: `access_rules/${id}`,
    diff_summary: "deactivated (soft delete)",
    ip: getClientIp(ctx.request),
  });

  return jsonOk({ ok: true, id });
};
