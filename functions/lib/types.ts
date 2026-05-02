// 共用型別定義

export type Role = "guest" | "member" | "premium" | "admin" | "super_admin";

export const ROLE_RANK: Record<Role, number> = {
  guest: 0,
  member: 1,
  premium: 2,
  admin: 3,
  super_admin: 4,
};

export interface DataPermissions {
  concept_groups?: boolean;
  stock_profiles?: boolean;
  master_patch?: boolean;
  industry_meta?: boolean;
  validation_runs?: boolean;
}

export interface User {
  id: number;
  google_id: string;
  email: string;
  name: string | null;
  picture: string | null;
  role: Role;
  role_expires_at: string | null;
  data_permissions: DataPermissions | null;
  notes: string | null;
  created_at: string;
  last_login_at: string | null;
  status: "active" | "suspended";
}

export interface JwtPayload {
  uid: number;
  email: string;
  role: Role;
  role_exp: string | null;
  iat: number;
  exp: number;
}

export interface Env {
  DB: D1Database;
  GOOGLE_CLIENT_ID: string;
  GOOGLE_CLIENT_SECRET: string;
  JWT_SECRET: string;
  GITHUB_TOKEN: string;
  GITHUB_REPO: string;            // "owner/repo"
  TURNSTILE_SECRET: string;
  TURNSTILE_SITE_KEY: string;
  APP_BASE_URL: string;           // "https://indusmapk.com"
  FINLAB_TOKEN?: string;
  ANTHROPIC_API_KEY?: string;
}

// Pages Function context with our user injected by _middleware
export interface AuthedContext {
  user: User | null;              // null = guest
  role: Role;                     // 永遠有值（未登入 = "guest"）
}

// 把 ctx.data 強制成我們知道的形狀
export type RequestCtx<P = unknown> = EventContext<Env, string, AuthedContext> & {
  params: P;
};
