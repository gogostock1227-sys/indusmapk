// GET /api/admin/users/audit — 列 audit_log
// 支援 query：?action=role_change&user_id=42&limit=100&offset=0
import type { RequestCtx } from "../../../lib/types";
import { requireRole, jsonOk } from "../../../lib/auth-guard";

export const onRequestGet = async (ctx: RequestCtx) => {
  const guard = requireRole(ctx.data.user, "admin");
  if (guard) return guard;

  const url = new URL(ctx.request.url);
  const action = url.searchParams.get("action") ?? "";
  const userId = url.searchParams.get("user_id") ?? "";
  const limit = Math.min(parseInt(url.searchParams.get("limit") ?? "100", 10) || 100, 500);
  const offset = parseInt(url.searchParams.get("offset") ?? "0", 10) || 0;

  const wheres: string[] = [];
  const binds: unknown[] = [];

  if (action) {
    wheres.push("action = ?");
    binds.push(action);
  }
  if (userId) {
    const u = parseInt(userId, 10);
    if (!isNaN(u)) {
      wheres.push("user_id = ?");
      binds.push(u);
    }
  }

  const where = wheres.length ? "WHERE " + wheres.join(" AND ") : "";
  const sql = `SELECT id, user_id, user_email, action, target, diff_summary, ip, created_at
               FROM audit_log ${where}
               ORDER BY created_at DESC, id DESC
               LIMIT ? OFFSET ?`;
  binds.push(limit, offset);

  const rs = await ctx.env.DB.prepare(sql).bind(...binds).all();
  return jsonOk({
    entries: rs.results ?? [],
    limit,
    offset,
  });
};
