// /api/admin/tags
//   GET   — 列出所有標籤（附用戶數）
//   POST  — 新建標籤  body: { name, color?, description? }
import type { RequestCtx } from "../../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../../lib/auth-guard";
import { logAudit, getClientIp } from "../../../lib/audit";

const VALID_COLORS = ["cyan", "magenta", "violet", "emerald", "amber", "rose", "sky", "lime"];

export const onRequestGet = async (ctx: RequestCtx) => {
  const guard = requireRole(ctx.data.user, "admin");
  if (guard) return guard;

  const rs = await ctx.env.DB.prepare(
    `SELECT t.id, t.name, t.color, t.description, t.created_at,
            (SELECT COUNT(*) FROM user_tags ut WHERE ut.tag_id = t.id) AS user_count
     FROM tags t
     ORDER BY t.name COLLATE NOCASE ASC`,
  ).all();

  return jsonOk({ tags: rs.results ?? [] });
};

export const onRequestPost = async (ctx: RequestCtx) => {
  const caller = ctx.data.user;
  const guard = requireRole(caller, "admin");
  if (guard) return guard;
  if (!caller) return jsonError("unauthorized", 401);

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  const name = String(body?.name ?? "").trim();
  const color = String(body?.color ?? "cyan").trim();
  const description = body?.description ? String(body.description).trim() : null;

  if (!name) return jsonError("name required", 400);
  if (name.length > 50) return jsonError("name too long (max 50)", 400);
  if (!VALID_COLORS.includes(color)) {
    return jsonError(`invalid color (must be one of: ${VALID_COLORS.join(", ")})`, 400);
  }

  // 檢查 name 是否已存在
  const existing = await ctx.env.DB.prepare(
    `SELECT id FROM tags WHERE name = ?`,
  ).bind(name).first<{ id: number }>();
  if (existing) return jsonError(`tag "${name}" already exists`, 409);

  const result = await ctx.env.DB.prepare(
    `INSERT INTO tags (name, color, description, created_by) VALUES (?, ?, ?, ?)`,
  ).bind(name, color, description, caller.id).run();

  await logAudit(ctx.env, {
    user: caller,
    action: "data_edit",
    target: `tags/${result.meta.last_row_id}`,
    diff_summary: `create tag: ${name} (${color})`,
    ip: getClientIp(ctx.request),
  });

  const fresh = await ctx.env.DB.prepare(
    `SELECT id, name, color, description, created_at FROM tags WHERE id = ?`,
  ).bind(result.meta.last_row_id).first();

  return jsonOk(fresh);
};
