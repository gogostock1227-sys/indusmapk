// GET /api/auth/me — 回當前登入用戶的資訊（前端 UI 渲染用）
import type { RequestCtx } from "../../lib/types";
import { jsonOk } from "../../lib/auth-guard";

export const onRequestGet = async (ctx: RequestCtx) => {
  const user = ctx.data.user;
  if (!user) {
    return jsonOk({ authenticated: false, role: "guest" });
  }
  return jsonOk({
    authenticated: true,
    uid: user.id,
    email: user.email,
    name: user.name,
    picture: user.picture,
    role: user.role,
    role_expires_at: user.role_expires_at,
    data_permissions: user.data_permissions,
  });
};
