// Audit log 寫入工具
import type { Env, User } from "./types";

export type AuditAction =
  | "login"
  | "logout"
  | "data_edit"
  | "build_trigger"
  | "role_change"
  | "data_perm_change"
  | "access_rule_change"
  | "extend_expiry"
  | "suspend"
  | "unsuspend";

export interface AuditEntry {
  user: User;
  action: AuditAction;
  target?: string;
  diff_summary?: string;
  ip?: string;
}

export async function logAudit(env: Env, entry: AuditEntry): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO audit_log (user_id, user_email, action, target, diff_summary, ip)
     VALUES (?, ?, ?, ?, ?, ?)`,
  )
    .bind(
      entry.user.id,
      entry.user.email,
      entry.action,
      entry.target ?? null,
      entry.diff_summary ?? null,
      entry.ip ?? null,
    )
    .run();
}

export function getClientIp(request: Request): string | undefined {
  return (
    request.headers.get("cf-connecting-ip") ||
    request.headers.get("x-forwarded-for")?.split(",")[0].trim() ||
    undefined
  );
}
