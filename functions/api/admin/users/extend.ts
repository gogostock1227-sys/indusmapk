// POST /api/admin/users/extend
// body: { id: number, days: number }   (days 也可以是 -1 表示設成永久；0 表示移除到期日；負值 = 過期)
//
// admin 可以延長 premium / member 的到期日
// super_admin 可以延長任何 role
import type { RequestCtx } from "../../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../../lib/auth-guard";
import { getUserById } from "../../../lib/d1";
import { logAudit, getClientIp } from "../../../lib/audit";

export const onRequestPost = async (ctx: RequestCtx) => {
  const caller = ctx.data.user;
  const guard = requireRole(caller, "admin");
  if (guard) return guard;
  if (!caller) return jsonError("unauthorized", 401);

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  const id = parseInt(body?.id, 10);
  const daysRaw = body?.days;
  if (isNaN(id)) return jsonError("invalid id", 400);
  if (typeof daysRaw !== "number") return jsonError("days must be a number", 400);

  const target = await getUserById(ctx.env, id);
  if (!target) return jsonError("not found", 404);

  const isSuper = caller.role === "super_admin";
  if (!isSuper && (target.role === "admin" || target.role === "super_admin")) {
    return jsonError("admin cannot extend admin/super_admin", 403);
  }

  // days = 0 → 設成永久（NULL）
  // days = -1 → 同上（語意清晰）
  // days > 0 → 從現在開始延長 N 天（不是從現有 expires_at 累加，避免歷史殘留）
  // days < 0 (但 >= -2) → 設為永久；否則直接設為 days 天前的時間（強制過期）
  let newExpiresAt: string | null;
  if (daysRaw === 0 || daysRaw === -1) {
    newExpiresAt = null;
  } else {
    const ms = Date.now() + daysRaw * 86400000;
    newExpiresAt = new Date(ms).toISOString();
  }

  await ctx.env.DB.prepare(
    `UPDATE users SET role_expires_at = ? WHERE id = ?`,
  ).bind(newExpiresAt, target.id).run();

  await logAudit(ctx.env, {
    user: caller,
    action: "extend_expiry",
    target: `users/${target.id} (${target.email})`,
    diff_summary: `role_expires_at: ${target.role_expires_at ?? "null"} → ${newExpiresAt ?? "null"} (days=${daysRaw})`,
    ip: getClientIp(ctx.request),
  });

  const fresh = await getUserById(ctx.env, target.id);
  return jsonOk(fresh);
};
