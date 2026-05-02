// GET /api/admin/users — 列表（admin / super_admin 都能看）
// 支援 query：?q=email_or_name&role=member|premium|admin&status=active|suspended&expiring=7
import type { RequestCtx } from "../../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../../lib/auth-guard";

export const onRequestGet = async (ctx: RequestCtx) => {
  const guard = requireRole(ctx.data.user, "admin");
  if (guard) return guard;

  const url = new URL(ctx.request.url);
  const q = url.searchParams.get("q")?.trim() ?? "";
  const role = url.searchParams.get("role")?.trim() ?? "";
  const status = url.searchParams.get("status")?.trim() ?? "";
  const expiring = url.searchParams.get("expiring");

  const wheres: string[] = [];
  const binds: unknown[] = [];

  if (q) {
    wheres.push("(email LIKE ? OR name LIKE ?)");
    binds.push(`%${q}%`, `%${q}%`);
  }
  if (role && ["member", "premium", "admin", "super_admin"].includes(role)) {
    wheres.push("role = ?");
    binds.push(role);
  }
  if (status && ["active", "suspended"].includes(status)) {
    wheres.push("status = ?");
    binds.push(status);
  }
  if (expiring) {
    const days = parseInt(expiring, 10);
    if (!isNaN(days) && days > 0) {
      wheres.push("role_expires_at IS NOT NULL AND role_expires_at <= datetime('now', ? )");
      binds.push(`+${days} days`);
    }
  }

  const where = wheres.length ? "WHERE " + wheres.join(" AND ") : "";
  const sql = `SELECT id, email, name, picture, role, role_expires_at, data_permissions, notes,
                      created_at, last_login_at, status
               FROM users ${where}
               ORDER BY
                 CASE role
                   WHEN 'super_admin' THEN 0
                   WHEN 'admin' THEN 1
                   WHEN 'premium' THEN 2
                   ELSE 3
                 END,
                 last_login_at DESC NULLS LAST,
                 id DESC
               LIMIT 500`;

  const rs = await ctx.env.DB.prepare(sql).bind(...binds).all();
  const users = (rs.results ?? []).map((r: any) => ({
    ...r,
    data_permissions: r.data_permissions ? JSON.parse(r.data_permissions) : null,
  }));

  return jsonOk({ users, total: users.length });
};
