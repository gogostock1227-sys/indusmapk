// /api/admin/users/:id/tags
//   PUT — 設定該用戶的標籤集合（覆蓋式）  body: { tag_ids: number[] }
//
// 用「整批覆蓋」模式而非個別 add/remove，前端編輯 modal 改完一次送過來：
//   1) DELETE FROM user_tags WHERE user_id = ?
//   2) INSERT INTO user_tags ... (每個新 tag_id)
// 簡化前端 + 避免 race，且這個操作頻次低、用戶/標籤量都不大
import type { RequestCtx } from "../../../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../../../lib/auth-guard";
import { getUserById } from "../../../../lib/d1";
import { logAudit, getClientIp } from "../../../../lib/audit";

interface Params { id: string; }

export const onRequestPut = async (ctx: RequestCtx<Params>) => {
  const caller = ctx.data.user;
  const guard = requireRole(caller, "admin");
  if (guard) return guard;
  if (!caller) return jsonError("unauthorized", 401);

  const userId = parseInt(ctx.params.id, 10);
  if (isNaN(userId)) return jsonError("invalid user id", 400);

  const target = await getUserById(ctx.env, userId);
  if (!target) return jsonError("user not found", 404);

  // admin 不能改 admin/super_admin 的標籤
  const isSuper = caller.role === "super_admin";
  if (!isSuper && (target.role === "admin" || target.role === "super_admin")) {
    return jsonError("admin cannot modify admin/super_admin tags", 403);
  }

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  if (!Array.isArray(body?.tag_ids)) return jsonError("tag_ids must be an array", 400);
  const tagIds = body.tag_ids.map((x: any) => parseInt(x, 10)).filter((n: number) => !isNaN(n));

  // 取舊 tags（for audit diff）
  const oldRs = await ctx.env.DB.prepare(
    `SELECT t.name FROM user_tags ut JOIN tags t ON ut.tag_id = t.id WHERE ut.user_id = ?`,
  ).bind(userId).all<{ name: string }>();
  const oldNames = (oldRs.results ?? []).map(r => r.name).sort();

  // 驗證 tag_ids 都存在
  if (tagIds.length > 0) {
    const placeholders = tagIds.map(() => "?").join(",");
    const valid = await ctx.env.DB.prepare(
      `SELECT id FROM tags WHERE id IN (${placeholders})`,
    ).bind(...tagIds).all<{ id: number }>();
    if ((valid.results ?? []).length !== tagIds.length) {
      return jsonError("some tag_ids do not exist", 400);
    }
  }

  // 覆蓋式 sync：先 DELETE 全清，再 INSERT 新集合
  await ctx.env.DB.prepare(`DELETE FROM user_tags WHERE user_id = ?`).bind(userId).run();
  if (tagIds.length > 0) {
    // 用 batch INSERT 提高效率（D1 prepared statement batch）
    const stmts = tagIds.map(tagId =>
      ctx.env.DB.prepare(
        `INSERT INTO user_tags (user_id, tag_id, assigned_by) VALUES (?, ?, ?)`,
      ).bind(userId, tagId, caller.id),
    );
    await ctx.env.DB.batch(stmts);
  }

  // 取新 tags（for audit diff + 回傳）
  const newRs = await ctx.env.DB.prepare(
    `SELECT t.id, t.name, t.color FROM user_tags ut JOIN tags t ON ut.tag_id = t.id WHERE ut.user_id = ? ORDER BY t.name`,
  ).bind(userId).all<{ id: number; name: string; color: string }>();
  const newTags = newRs.results ?? [];
  const newNames = newTags.map(r => r.name).sort();

  // diff
  const added = newNames.filter(n => !oldNames.includes(n));
  const removed = oldNames.filter(n => !newNames.includes(n));
  const diffParts: string[] = [];
  if (added.length) diffParts.push(`+[${added.join(",")}]`);
  if (removed.length) diffParts.push(`-[${removed.join(",")}]`);

  if (diffParts.length === 0) {
    return jsonOk({ ok: true, no_change: true, tags: newTags });
  }

  await logAudit(ctx.env, {
    user: caller,
    action: "data_edit",
    target: `users/${userId} (${target.email})`,
    diff_summary: `tags ${diffParts.join(" ")}`,
    ip: getClientIp(ctx.request),
  });

  return jsonOk({ ok: true, tags: newTags });
};
