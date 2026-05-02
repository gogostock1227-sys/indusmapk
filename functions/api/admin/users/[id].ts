// PUT /api/admin/users/:id — 編輯用戶（role / role_expires_at / notes / status）
//
// 規則：
//   - admin 只能改 member ↔ premium 的 role + expires + notes
//   - admin 不能改其他 admin / super_admin（target.role >= admin → 拒絕）
//   - super_admin 能改任何用戶（除了把自己降權，且系統不允許 super_admin → super_admin 的橫向）
//   - 任何人都不能把 user 升為 super_admin（系統設計限定，super_admin 只能透過 SQL bootstrap）
//   - 防止最後一個 super_admin 被降權
//
// GET /api/admin/users/:id — 看單一用戶詳細
import type { RequestCtx } from "../../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../../lib/auth-guard";
import { getUserById } from "../../../lib/d1";
import { logAudit, getClientIp } from "../../../lib/audit";

interface Params { id: string; }

export const onRequestGet = async (ctx: RequestCtx<Params>) => {
  const guard = requireRole(ctx.data.user, "admin");
  if (guard) return guard;

  const id = parseInt(ctx.params.id, 10);
  if (isNaN(id)) return jsonError("invalid id", 400);

  const target = await getUserById(ctx.env, id);
  if (!target) return jsonError("not found", 404);

  return jsonOk(target);
};

export const onRequestPut = async (ctx: RequestCtx<Params>) => {
  const caller = ctx.data.user;
  const guard = requireRole(caller, "admin");
  if (guard) return guard;
  if (!caller) return jsonError("unauthorized", 401); // 滿足 TS

  const id = parseInt(ctx.params.id, 10);
  if (isNaN(id)) return jsonError("invalid id", 400);

  const target = await getUserById(ctx.env, id);
  if (!target) return jsonError("not found", 404);

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  const { role, role_expires_at, notes, status } = body;
  const isSuper = caller.role === "super_admin";

  // 1. admin 不能動 admin / super_admin
  if (!isSuper && (target.role === "admin" || target.role === "super_admin")) {
    return jsonError("admin cannot modify admin/super_admin", 403);
  }

  // 2. 任何人都不能把人升為 super_admin（系統限定）
  if (role === "super_admin" && target.role !== "super_admin") {
    return jsonError("promotion to super_admin not allowed via API", 403);
  }

  // 3. 不能把 super_admin 降權（除非還有其他 super_admin）
  if (target.role === "super_admin" && role && role !== "super_admin") {
    const cnt = await ctx.env.DB.prepare(
      `SELECT COUNT(*) as c FROM users WHERE role = 'super_admin' AND id != ?`,
    ).bind(target.id).first<{ c: number }>();
    if (!cnt || cnt.c === 0) {
      return jsonError("cannot demote the last super_admin", 400);
    }
  }

  // 4. admin 改 role 的範圍限定為 member / premium
  if (!isSuper && role && !["member", "premium"].includes(role)) {
    return jsonError("admin can only set role to member/premium", 403);
  }

  // 5. admin 不能停權任何 admin/super_admin
  if (!isSuper && status === "suspended"
      && (target.role === "admin" || target.role === "super_admin")) {
    return jsonError("admin cannot suspend admin/super_admin", 403);
  }

  // ─── 組 UPDATE ───
  const sets: string[] = [];
  const binds: unknown[] = [];
  const diffs: string[] = [];

  if (role !== undefined && role !== target.role) {
    sets.push("role = ?");
    binds.push(role);
    diffs.push(`role: ${target.role} → ${role}`);
    // 改 role 為 member 時清掉 data_permissions / role_expires_at
    if (role === "member") {
      sets.push("data_permissions = NULL");
      sets.push("role_expires_at = NULL");
    }
  }
  if (role_expires_at !== undefined && role_expires_at !== target.role_expires_at) {
    sets.push("role_expires_at = ?");
    binds.push(role_expires_at || null);
    diffs.push(`role_expires_at: ${target.role_expires_at ?? "null"} → ${role_expires_at ?? "null"}`);
  }
  if (notes !== undefined) {
    sets.push("notes = ?");
    binds.push(notes);
    if (notes !== target.notes) diffs.push("notes updated");
  }
  if (status !== undefined && ["active", "suspended"].includes(status) && status !== target.status) {
    sets.push("status = ?");
    binds.push(status);
    diffs.push(`status: ${target.status} → ${status}`);
  }

  if (sets.length === 0) return jsonOk({ ok: true, no_change: true });

  binds.push(target.id);
  await ctx.env.DB.prepare(`UPDATE users SET ${sets.join(", ")} WHERE id = ?`)
    .bind(...binds).run();

  await logAudit(ctx.env, {
    user: caller,
    action: status === "suspended" ? "suspend"
          : status === "active" && target.status === "suspended" ? "unsuspend"
          : "role_change",
    target: `users/${target.id} (${target.email})`,
    diff_summary: diffs.join("; "),
    ip: getClientIp(ctx.request),
  });

  const fresh = await getUserById(ctx.env, target.id);
  return jsonOk(fresh);
};

export const onRequestDelete = async (ctx: RequestCtx<Params>) => {
  // 不開放實質 DELETE，只能用 status='suspended' 軟刪除
  return jsonError("hard delete disabled, use PUT with status='suspended'", 405);
};
