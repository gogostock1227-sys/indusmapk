// D1 helper：用戶 / access rules CRUD
import type { Env, User, Role, DataPermissions } from "./types";

function rowToUser(row: any): User {
  return {
    id: row.id,
    google_id: row.google_id,
    email: row.email,
    name: row.name ?? null,
    picture: row.picture ?? null,
    role: row.role as Role,
    role_expires_at: row.role_expires_at ?? null,
    data_permissions: row.data_permissions
      ? (JSON.parse(row.data_permissions) as DataPermissions)
      : null,
    notes: row.notes ?? null,
    created_at: row.created_at,
    last_login_at: row.last_login_at ?? null,
    status: row.status as "active" | "suspended",
  };
}

export async function getUserById(env: Env, id: number): Promise<User | null> {
  const row = await env.DB.prepare("SELECT * FROM users WHERE id = ?").bind(id).first();
  return row ? rowToUser(row) : null;
}

export async function getUserByGoogleId(env: Env, googleId: string): Promise<User | null> {
  const row = await env.DB.prepare("SELECT * FROM users WHERE google_id = ?")
    .bind(googleId)
    .first();
  return row ? rowToUser(row) : null;
}

export async function getUserByEmail(env: Env, email: string): Promise<User | null> {
  const row = await env.DB.prepare("SELECT * FROM users WHERE email = ?").bind(email).first();
  return row ? rowToUser(row) : null;
}

export interface UpsertGoogleUser {
  google_id: string;
  email: string;
  name: string | null;
  picture: string | null;
}

export async function upsertGoogleUser(env: Env, info: UpsertGoogleUser): Promise<User> {
  // 1) 已綁定的 Google 帳號 → 更新 last_login_at + 名字/頭像（用戶可能改 Google 顯示名）
  const existing = await getUserByGoogleId(env, info.google_id);
  if (existing) {
    await env.DB.prepare(
      `UPDATE users
       SET last_login_at = CURRENT_TIMESTAMP,
           name = ?,
           picture = ?
       WHERE id = ?`,
    ).bind(info.name, info.picture, existing.id).run();
    const fresh = await getUserById(env, existing.id);
    return fresh!;
  }

  // 2) Email 已存在但 google_id 是 'PENDING_*' placeholder
  //    （bootstrap super_admin 首次登入 — 多個帳號各用 PENDING_1 / PENDING_2 區分）
  const byEmail = await getUserByEmail(env, info.email);
  if (byEmail && byEmail.google_id.startsWith("PENDING")) {
    await env.DB.prepare(
      `UPDATE users
       SET google_id = ?, name = ?, picture = ?, last_login_at = CURRENT_TIMESTAMP
       WHERE id = ?`,
    ).bind(info.google_id, info.name, info.picture, byEmail.id).run();
    const fresh = await getUserById(env, byEmail.id);
    return fresh!;
  }

  // 3) 全新用戶 → INSERT role='member'
  const result = await env.DB.prepare(
    `INSERT INTO users (google_id, email, name, picture, role, last_login_at)
     VALUES (?, ?, ?, ?, 'member', CURRENT_TIMESTAMP)`,
  ).bind(info.google_id, info.email, info.name, info.picture).run();

  const insertedId = result.meta.last_row_id;
  const fresh = await getUserById(env, insertedId);
  if (!fresh) throw new Error("Insert succeeded but fetch failed");
  return fresh;
}

/**
 * 過期 role 自動降級。
 * 若 role 是 admin / premium 且 role_expires_at < now → 降為 member。
 * 回傳更新後的 user（如果沒過期則回原 user）。
 */
export async function downgradeIfExpired(env: Env, user: User): Promise<User> {
  if (!user.role_expires_at) return user;
  if (user.role !== "admin" && user.role !== "premium") return user;

  const expiresMs = Date.parse(user.role_expires_at);
  if (isNaN(expiresMs) || expiresMs > Date.now()) return user;

  await env.DB.prepare(
    `UPDATE users
     SET role = 'member', role_expires_at = NULL, data_permissions = NULL
     WHERE id = ?`,
  ).bind(user.id).run();

  return { ...user, role: "member", role_expires_at: null, data_permissions: null };
}

// ─── access_rules ───────────────────────────────────────────────────────

export interface AccessRule {
  id: number;
  path_pattern: string;
  required_role: Role;
  comment: string | null;
  created_by: number | null;
  created_at: string;
  active: number;
}

export async function findMatchingRule(env: Env, path: string): Promise<AccessRule | null> {
  // SQLite GLOB：path_pattern 是 GLOB 模式，path 是要比對的字串。
  //
  // 雙向歸一化：Cloudflare Pages 服務同一個頁面有兩個 URL 變體：
  //   • /foo.html  （直接帶 .html）
  //   • /foo       （pretty URL，內部 rewrite 服務 /foo.html）
  // middleware 看到的 path 取決於用戶輸入哪個變體。為了避免規則寫
  // /foo.html 但用戶訪問 /foo 不被擋，這裡同時試兩個變體：
  //   • 原 path
  //   • 若 path 沒有 .html 後綴且不是目錄 → path + ".html"
  //   • 若 path 有 .html 後綴 → 也試去掉 .html 的版本（反方向歸一化）
  const variants: string[] = [path];
  if (path && !path.endsWith("/")) {
    if (path.endsWith(".html")) {
      variants.push(path.slice(0, -5));
    } else {
      variants.push(path + ".html");
    }
  }
  const placeholders = variants.map(() => "? GLOB path_pattern").join(" OR ");
  const row = await env.DB.prepare(
    `SELECT * FROM access_rules
     WHERE active = 1 AND (${placeholders})
     ORDER BY length(path_pattern) DESC, id DESC
     LIMIT 1`,
  ).bind(...variants).first();
  return row ? (row as unknown as AccessRule) : null;
}

export async function listAccessRules(env: Env): Promise<AccessRule[]> {
  const rs = await env.DB.prepare(
    `SELECT * FROM access_rules ORDER BY active DESC, length(path_pattern) DESC, id DESC`,
  ).all();
  return (rs.results ?? []) as unknown as AccessRule[];
}
