// Cloudflare Turnstile 驗證
import type { Env } from "./types";

interface TurnstileResponse {
  success: boolean;
  "error-codes"?: string[];
  challenge_ts?: string;
  hostname?: string;
  action?: string;
  cdata?: string;
}

export async function verifyTurnstile(
  env: Env,
  token: string,
  remoteIp?: string,
): Promise<{ success: boolean; errorCodes?: string[] }> {
  if (!token) return { success: false, errorCodes: ["missing-token"] };
  const form = new FormData();
  form.append("secret", env.TURNSTILE_SECRET);
  form.append("response", token);
  if (remoteIp) form.append("remoteip", remoteIp);

  const res = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST",
    body: form,
  });
  if (!res.ok) return { success: false, errorCodes: [`http-${res.status}`] };
  const data = (await res.json()) as TurnstileResponse;
  return { success: data.success, errorCodes: data["error-codes"] };
}
