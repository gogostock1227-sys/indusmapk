// /api/admin/tags/:id
//   PATCH  — 更新標籤  body: { name?, color?, description? }
//   DELETE — 刪除標籤（CASCADE 清掉所有 user_tags 關聯）
import type { RequestCtx } from "../../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../../lib/auth-guard";
import { logAudit, getClientIp } from "../../../lib/audit";

interface Params { id: string; }

const VALID_COLORS = ["cyan", "magenta", "violet", "emerald", "amber", "rose", "sky", "lime"];

export const onRequestPatch = async (ctx: RequestCtx<Params>) => {
  const caller = ctx.data.user;
  const guard = requireRole(caller, "admin");
  if (guard) return guard;
  if (!caller) return jsonError("unauthorized", 401);

  const id = parseInt(ctx.params.id, 10);
  if (isNaN(id)) return jsonError("invalid id", 400);

  const target = await ctx.env.DB.prepare(
    `SELECT id, name, color, description FROM tags WHERE id = ?`,
  ).bind(id).first<{ id: number; name: string; color: string; description: string | null }>();
  if (!target) return jsonError("tag not found", 404);

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  const sets: string[] = [];
  const binds: unknown[] = [];
  const diffs: string[] = [];

  if (body.name !== undefined) {
    const name = String(body.name).trim();
    if (!name) return jsonError("name cannot be empty", 400);
    if (name.length > 50) return jsonError("name too long (max 50)", 400);
    if (name !== target.name) {
      // 防 name 衝突
      const exist = await ctx.env.DB.prepare(
        `SELECT id FROM tags WHERE name = ? AND id != ?`,
      ).bind(name, id).first();
      if (exist) return jsonError(`tag "${name}" already exists`, 409);
      sets.push("name = ?");
      binds.push(name);
      diffs.push(`name: ${target.name} → ${name}`);
    }
  }

  if (body.color !== undefined) {
    const color = String(body.color).trim();
    if (!VALID_COLORS.includes(color)) {
      return jsonError(`invalid color (must be one of: ${VALID_COLORS.join(", ")})`, 400);
    }
    if (color !== target.color) {
      sets.push("color = ?");
      binds.push(color);
      diffs.push(`color: ${target.color} → ${color}`);
    }
  }

  if (body.description !== undefined) {
    const description = body.description ? String(body.description).trim() : null;
    sets.push("description = ?");
    binds.push(description);
    if (description !== target.description) diffs.push("description updated");
  }

  if (sets.length === 0) return jsonOk({ ok: true, no_change: true });

  binds.push(id);
  await ctx.env.DB.prepare(`UPDATE tags SET ${sets.join(", ")} WHERE id = ?`).bind(...binds).run();

  await logAudit(ctx.env, {
    user: caller,
    action: "data_edit",
    target: `tags/${id} (${target.name})`,
    diff_summary: diffs.join("; "),
    ip: getClientIp(ctx.request),
  });

  const fresh = await ctx.env.DB.prepare(
    `SELECT id, name, color, description, created_at FROM tags WHERE id = ?`,
  ).bind(id).first();
  return jsonOk(fresh);
};

export const onRequestDelete = async (ctx: RequestCtx<Params>) => {
  const caller = ctx.data.user;
  const guard = requireRole(caller, "admin");
  if (guard) return guard;
  if (!caller) return jsonError("unauthorized", 401);

  const id = parseInt(ctx.params.id, 10);
  if (isNaN(id)) return jsonError("invalid id", 400);

  const target = await ctx.env.DB.prepare(
    `SELECT id, name FROM tags WHERE id = ?`,
  ).bind(id).first<{ id: number; name: string }>();
  if (!target) return jsonError("tag not found", 404);

  // CASCADE：DELETE FROM tags 會連帶清 user_tags（FK ON DELETE CASCADE）
  const cnt = await ctx.env.DB.prepare(
    `SELECT COUNT(*) as c FROM user_tags WHERE tag_id = ?`,
  ).bind(id).first<{ c: number }>();
  const affectedUsers = cnt?.c ?? 0;

  await ctx.env.DB.prepare(`DELETE FROM tags WHERE id = ?`).bind(id).run();

  await logAudit(ctx.env, {
    user: caller,
    action: "data_edit",
    target: `tags/${id} (${target.name})`,
    diff_summary: `delete tag (affected ${affectedUsers} users)`,
    ip: getClientIp(ctx.request),
  });

  return jsonOk({ ok: true, deleted_id: id, affected_users: affectedUsers });
};
