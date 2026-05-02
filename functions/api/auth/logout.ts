// GET /api/auth/logout — 清 session cookie，回首頁
import type { RequestCtx } from "../../lib/types";
import { clearSessionCookie } from "../../lib/jwt";
import { logAudit, getClientIp } from "../../lib/audit";

export const onRequestGet = async (ctx: RequestCtx) => {
  const user = ctx.data.user;
  if (user) {
    await logAudit(ctx.env, {
      user,
      action: "logout",
      ip: getClientIp(ctx.request),
    });
  }
  return new Response(null, {
    status: 302,
    headers: {
      Location: "/",
      "Set-Cookie": clearSessionCookie(),
    },
  });
};
