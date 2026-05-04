// GET /api/admin/users — 列表（admin / super_admin 都能看）
// 支援 query：
//   ?q=email_or_name
//   &role=member|premium|admin
//   &status=active|suspended
//   &expiring=7
//   &tag=<tag_id>            ← 新增：只列出有該標籤的用戶
import type { RequestCtx } from "../../../lib/types";
import { requireRole, jsonOk } from "../../../lib/auth-guard";

export const onRequestGet = async (ctx: RequestCtx) => {
  const guard = requireRole(ctx.data.user, "admin");
  if (guard) return guard;

  const url = new URL(ctx.request.url);
  const q = url.searchParams.get("q")?.trim() ?? "";
  const role = url.searchParams.get("role")?.trim() ?? "";
  const status = url.searchParams.get("status")?.trim() ?? "";
  const expiring = url.searchParams.get("expiring");
  const tagId = url.searchParams.get("tag");

  const wheres: string[] = [];
  const binds: unknown[] = [];

  if (q) {
    wheres.push("(u.email LIKE ? OR u.name LIKE ?)");
    binds.push(`%${q}%`, `%${q}%`);
  }
  if (role && ["member", "premium", "admin", "super_admin"].includes(role)) {
    wheres.push("u.role = ?");
    binds.push(role);
  }
  if (status && ["active", "suspended"].includes(status)) {
    wheres.push("u.status = ?");
    binds.push(status);
  }
  if (expiring) {
    const days = parseInt(expiring, 10);
    if (!isNaN(days) && days > 0) {
      wheres.push("u.role_expires_at IS NOT NULL AND u.role_expires_at <= datetime('now', ? )");
      binds.push(`+${days} days`);
    }
  }
  // tagId 只有在 user_tags 表存在時才能用（防 migration 未跑）
  let useTagFilter = false;
  if (tagId) {
    const tid = parseInt(tagId, 10);
    if (!isNaN(tid)) {
      try {
        // 預檢 user_tags 表是否存在
        await ctx.env.DB.prepare(`SELECT 1 FROM user_tags LIMIT 1`).first();
        wheres.push("EXISTS (SELECT 1 FROM user_tags ut WHERE ut.user_id = u.id AND ut.tag_id = ?)");
        binds.push(tid);
        useTagFilter = true;
      } catch {
        // 表不存在 → 忽略 tag filter（return 全列表，等 migration 跑完才生效）
      }
    }
  }

  const where = wheres.length ? "WHERE " + wheres.join(" AND ") : "";
  const sql = `SELECT u.id, u.email, u.name, u.picture, u.role, u.role_expires_at,
                      u.data_permissions, u.notes, u.created_at, u.last_login_at, u.status
               FROM users u ${where}
               ORDER BY
                 CASE u.role
                   WHEN 'super_admin' THEN 0
                   WHEN 'admin' THEN 1
                   WHEN 'premium' THEN 2
                   ELSE 3
                 END,
                 u.last_login_at DESC NULLS LAST,
                 u.id DESC
               LIMIT 500`;

  const rs = await ctx.env.DB.prepare(sql).bind(...binds).all();
  const users = (rs.results ?? []).map((r: any) => ({
    ...r,
    data_permissions: r.data_permissions ? JSON.parse(r.data_permissions) : null,
    tags: [] as Array<{ id: number; name: string; color: string }>,
  }));

  // 一次撈所有相關 user 的 tags（避免 N+1）
  // 防呆：user_tags / tags 表可能還沒被 migration 0002 建立 → try/catch 優雅降級
  if (users.length > 0) {
    try {
      const ids = users.map((u: any) => u.id);
      const placeholders = ids.map(() => "?").join(",");
      const tagsRs = await ctx.env.DB.prepare(
        `SELECT ut.user_id, t.id, t.name, t.color
         FROM user_tags ut
         JOIN tags t ON ut.tag_id = t.id
         WHERE ut.user_id IN (${placeholders})
         ORDER BY t.name COLLATE NOCASE`,
      ).bind(...ids).all<{ user_id: number; id: number; name: string; color: string }>();

      const byUser = new Map<number, Array<{ id: number; name: string; color: string }>>();
      for (const row of tagsRs.results ?? []) {
        if (!byUser.has(row.user_id)) byUser.set(row.user_id, []);
        byUser.get(row.user_id)!.push({ id: row.id, name: row.name, color: row.color });
      }
      for (const u of users) {
        (u as any).tags = byUser.get((u as any).id) ?? [];
      }
    } catch (e) {
      // user_tags 表還沒建立（migration 0002 未跑）→ 全部回傳空 tags 陣列即可
      // 主功能（用戶列表 / 統計卡 / 批量操作）不受影響
    }
  }

  return jsonOk({ users, total: users.length });
};
