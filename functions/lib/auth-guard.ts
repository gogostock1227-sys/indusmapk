// Role 與 data_permission gate
import { ROLE_RANK, type Role, type User, type DataPermissions } from "./types";

/**
 * 檢查 user 的 role 是否 >= minRole。
 * 回傳 null = 通過；回傳 Response = 已生成 401/403 拒絕回應。
 */
export function requireRole(user: User | null, minRole: Role): Response | null {
  const userRank = user ? ROLE_RANK[user.role] : ROLE_RANK.guest;
  if (userRank < ROLE_RANK[minRole]) {
    if (!user) {
      return new Response(JSON.stringify({ error: "unauthorized", code: "AUTH_REQUIRED" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(
      JSON.stringify({
        error: "forbidden",
        code: "ROLE_INSUFFICIENT",
        required: minRole,
        actual: user.role,
      }),
      { status: 403, headers: { "Content-Type": "application/json" } },
    );
  }
  return null;
}

/**
 * admin 級別的細粒度資料權限檢查。
 * super_admin 永遠通過。
 * admin 必須在 data_permissions[category] === true 才通過。
 */
export function requireDataPerm(
  user: User | null,
  category: keyof DataPermissions,
): Response | null {
  if (!user) {
    return new Response(JSON.stringify({ error: "unauthorized", code: "AUTH_REQUIRED" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }
  if (user.role === "super_admin") return null;
  if (user.role !== "admin") {
    return new Response(
      JSON.stringify({ error: "forbidden", code: "ROLE_INSUFFICIENT", required: "admin" }),
      { status: 403, headers: { "Content-Type": "application/json" } },
    );
  }
  const perm = user.data_permissions?.[category] === true;
  if (!perm) {
    return new Response(
      JSON.stringify({
        error: "forbidden",
        code: "DATA_PERM_DENIED",
        category,
      }),
      { status: 403, headers: { "Content-Type": "application/json" } },
    );
  }
  return null;
}

export function jsonError(
  message: string,
  status = 400,
  extra: Record<string, unknown> = {},
): Response {
  return new Response(JSON.stringify({ error: message, ...extra }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function jsonOk(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
