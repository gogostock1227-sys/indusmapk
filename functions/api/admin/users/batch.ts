// PATCH /api/admin/users/batch — 批量修改用戶
//
// payload: {
//   ids: number[],
//   action: "set_role" | "extend" | "set_status",
//   value: any,                 // 依 action 而異
// }
//
// action 種類：
//   - "set_role"   value: { role: "member"|"premium"|"admin", role_expires_at?: ISO|null }
//   - "extend"     value: { days: number }   // 0 / -1 = 永久
//   - "set_status" value: { status: "active"|"suspended" }
//
// 回傳：{ updated: number, skipped: [{id, reason}], errors: [{id, error}] }
//
// 防呆規則沿用單筆 PUT（[id].ts）：
//   - admin 只能改 member ↔ premium，碰到 admin/super_admin 列入 skipped
//   - 不允許把最後一個 super_admin 降權
//   - 改成 member 時自動清空 role_expires_at + data_permissions
//   - 一次 batch 寫一筆 audit log
import type { RequestCtx } from "../../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../../lib/auth-guard";
import { getUserById } from "../../../lib/d1";
import { logAudit, getClientIp } from "../../../lib/audit";

type Action = "set_role" | "extend" | "set_status";

interface SkipEntry { id: number; reason: string; }
interface ErrorEntry { id: number; error: string; }

export const onRequestPatch = async (ctx: RequestCtx) => {
  const caller = ctx.data.user;
  const guard = requireRole(caller, "admin");
  if (guard) return guard;
  if (!caller) return jsonError("unauthorized", 401);

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  const ids = Array.isArray(body?.ids)
    ? body.ids.map((x: any) => parseInt(x, 10)).filter((n: number) => !isNaN(n))
    : [];
  const action: Action = body?.action;
  const value = body?.value ?? {};

  if (ids.length === 0) return jsonError("ids required", 400);
  if (ids.length > 200) return jsonError("max 200 users per batch", 400);
  if (!["set_role", "extend", "set_status"].includes(action)) {
    return jsonError("invalid action", 400);
  }

  const isSuper = caller.role === "super_admin";

  // ─── 預先驗證 action 內容 ──────────────────────────────────────
  if (action === "set_role") {
    const role = value?.role;
    if (!["member", "premium", "admin"].includes(role)) {
      return jsonError("set_role: invalid role (member/premium/admin only)", 400);
    }
    // admin 只能升降 member ↔ premium
    if (!isSuper && !["member", "premium"].includes(role)) {
      return jsonError("admin can only set role to member/premium", 403);
    }
  } else if (action === "extend") {
    if (typeof value?.days !== "number") {
      return jsonError("extend: days must be a number", 400);
    }
  } else if (action === "set_status") {
    if (!["active", "suspended"].includes(value?.status)) {
      return jsonError("set_status: invalid status", 400);
    }
  }

  // ─── 預先 query super_admin 數量（為了「最後一個 super_admin 降權」防呆）
  const cntSuper = await ctx.env.DB.prepare(
    `SELECT COUNT(*) as c FROM users WHERE role = 'super_admin'`,
  ).first<{ c: number }>();
  const totalSuperAdmins = cntSuper?.c ?? 0;

  const skipped: SkipEntry[] = [];
  const errors: ErrorEntry[] = [];
  let updated = 0;

  // ─── 逐個 fetch + validate + UPDATE ────────────────────────────
  // 注：D1 沒有 multi-statement transaction，在 Workers 中只能一筆一筆來。
  //     以「先讀全部 target → batch 一次 audit log」確保審計完整。
  const targets = await Promise.all(ids.map((id) => getUserById(ctx.env, id)));

  // 計算這個 batch 中要降權的 super_admin 數，預判保護線
  let demotionsOfSuper = 0;
  if (action === "set_role" && value?.role && value.role !== "super_admin") {
    for (const t of targets) {
      if (t && t.role === "super_admin") demotionsOfSuper++;
    }
  }

  for (let i = 0; i < ids.length; i++) {
    const id = ids[i];
    const target = targets[i];

    if (!target) { skipped.push({ id, reason: "not_found" }); continue; }

    // admin 不能動 admin / super_admin
    if (!isSuper && (target.role === "admin" || target.role === "super_admin")) {
      skipped.push({ id, reason: "admin_cannot_modify_admin_or_super" });
      continue;
    }

    try {
      if (action === "set_role") {
        const role = value.role;
        const role_expires_at = value.role_expires_at ?? null;

        // 不能把人升為 super_admin（系統限定）
        if (role === "super_admin") {
          skipped.push({ id, reason: "cannot_promote_to_super_admin" });
          continue;
        }

        // 不能把最後一個 super_admin 降權
        if (target.role === "super_admin" && role !== "super_admin") {
          if (totalSuperAdmins - demotionsOfSuper < 1) {
            skipped.push({ id, reason: "cannot_demote_last_super_admin" });
            continue;
          }
        }

        if (role === target.role && role_expires_at === target.role_expires_at) {
          skipped.push({ id, reason: "no_change" });
          continue;
        }

        const sets: string[] = ["role = ?"];
        const binds: unknown[] = [role];
        if (role === "member") {
          sets.push("data_permissions = NULL");
          sets.push("role_expires_at = NULL");
        } else {
          sets.push("role_expires_at = ?");
          binds.push(role_expires_at || null);
        }
        binds.push(target.id);

        await ctx.env.DB.prepare(`UPDATE users SET ${sets.join(", ")} WHERE id = ?`)
          .bind(...binds).run();
        updated++;
      } else if (action === "extend") {
        const days = value.days;
        let newExpiresAt: string | null;
        if (days === 0 || days === -1) {
          newExpiresAt = null;
        } else {
          newExpiresAt = new Date(Date.now() + days * 86400000).toISOString();
        }
        await ctx.env.DB.prepare(
          `UPDATE users SET role_expires_at = ? WHERE id = ?`,
        ).bind(newExpiresAt, target.id).run();
        updated++;
      } else if (action === "set_status") {
        const status = value.status;

        // admin 不能停權任何 admin/super_admin
        if (!isSuper && status === "suspended"
            && (target.role === "admin" || target.role === "super_admin")) {
          skipped.push({ id, reason: "admin_cannot_suspend_admin_or_super" });
          continue;
        }
        if (status === target.status) {
          skipped.push({ id, reason: "no_change" });
          continue;
        }

        await ctx.env.DB.prepare(
          `UPDATE users SET status = ? WHERE id = ?`,
        ).bind(status, target.id).run();
        updated++;
      }
    } catch (e: any) {
      errors.push({ id, error: e?.message || "update failed" });
    }
  }

  // ─── 寫一筆批量 audit log ──────────────────────────────────────
  let auditAction: "role_change" | "extend_expiry" | "suspend" | "unsuspend" = "role_change";
  let summary = "";
  if (action === "set_role") {
    auditAction = "role_change";
    summary = `batch set_role: role=${value.role}, ids=${ids.length} (updated=${updated}, skipped=${skipped.length})`;
  } else if (action === "extend") {
    auditAction = "extend_expiry";
    summary = `batch extend: days=${value.days}, ids=${ids.length} (updated=${updated}, skipped=${skipped.length})`;
  } else if (action === "set_status") {
    auditAction = value.status === "suspended" ? "suspend" : "unsuspend";
    summary = `batch set_status: status=${value.status}, ids=${ids.length} (updated=${updated}, skipped=${skipped.length})`;
  }

  await logAudit(ctx.env, {
    user: caller,
    action: auditAction,
    target: `users (batch x${ids.length})`,
    diff_summary: summary,
    ip: getClientIp(ctx.request),
  });

  return jsonOk({ updated, skipped, errors });
};
