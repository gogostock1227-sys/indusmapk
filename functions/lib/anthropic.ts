// Anthropic Claude API helper（用 Web Crypto / fetch，零依賴）
//
// 預設 model: claude-sonnet-4-6（當前主流，平衡速度/品質）
// 預設帶 prompt caching（cache_control: ephemeral） — 候選清單 + 規則放 system 段，
// 連續呼叫同一系統 prompt 5 分鐘內 cache hit。
//
// 用法：
//   const resp = await callAnthropic(env, {
//     system: [{ type: "text", text: BIG_RULES, cache_control: { type: "ephemeral" } }],
//     messages: [{ role: "user", content: "..." }],
//   });
//   const text = extractText(resp);
//   const json = tryParseJson(text);
import type { Env } from "./types";

export interface ContentBlock {
  type: "text";
  text: string;
  cache_control?: { type: "ephemeral" };
}

export interface MessagesParams {
  model?: string;
  system?: string | ContentBlock[];
  messages: Array<{
    role: "user" | "assistant";
    content: string | ContentBlock[];
  }>;
  max_tokens?: number;
  temperature?: number;
}

export interface MessagesResponse {
  id: string;
  type: "message";
  role: "assistant";
  content: Array<{ type: string; text?: string }>;
  model: string;
  stop_reason: string;
  usage: {
    input_tokens: number;
    output_tokens: number;
    cache_creation_input_tokens?: number;
    cache_read_input_tokens?: number;
  };
}

export async function callAnthropic(env: Env, params: MessagesParams): Promise<MessagesResponse> {
  if (!env.ANTHROPIC_API_KEY) {
    throw new Error("ANTHROPIC_API_KEY 未設定（請到 Cloudflare Dashboard → Pages → Settings → Variables → Secrets 加上）");
  }
  const body: Record<string, unknown> = {
    model: params.model ?? "claude-sonnet-4-6",
    max_tokens: params.max_tokens ?? 1024,
    messages: params.messages,
  };
  if (params.system !== undefined) body.system = params.system;
  if (params.temperature !== undefined) body.temperature = params.temperature;

  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`Anthropic API ${res.status}: ${await res.text()}`);
  }
  return await res.json() as MessagesResponse;
}

export function extractText(resp: MessagesResponse): string {
  return resp.content.filter(b => b.type === "text" && b.text).map(b => b.text!).join("\n");
}

export function tryParseJson(text: string): any {
  // 處理 ```json ... ``` fence 包裝
  const fenced = text.match(/```(?:json)?\s*\n?([\s\S]+?)```/);
  const clean = fenced ? fenced[1] : text;
  try { return JSON.parse(clean.trim()); }
  catch { return null; }
}

export function cacheStats(resp: MessagesResponse) {
  return {
    input: resp.usage.input_tokens,
    output: resp.usage.output_tokens,
    cache_create: resp.usage.cache_creation_input_tokens ?? 0,
    cache_read: resp.usage.cache_read_input_tokens ?? 0,
  };
}
