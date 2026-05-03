// POST /api/ai/analyze-industry
// body: { group: "AI伺服器", tickers?: ["2330", "2382"], context?: "..." }
// 回: { summary, drivers, risks, key_players, outlook, raw }
//
// 給 admin 編輯族群文案 (industry_meta) 時用 AI 輔助生成介紹。
// 餵：族群名 + 主要成分股 ticker + 額外 context（市場新聞等）
// 回：可直接複製到 industry_meta.json 的結構化欄位。
import type { RequestCtx } from "../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../lib/auth-guard";
import { callAnthropic, extractText, tryParseJson, cacheStats } from "../../lib/anthropic";

const SYSTEM_INSTRUCTION = `你是台股產業分析師，給定一個族群名稱與成分股，產出可直接放進 industry_meta.json 的結構化分析。

輸出（valid JSON，不要 markdown 包裝）：
{
  "summary": "100-150 字族群介紹（事件驅動 / 技術趨勢 / 主要受惠對象）",
  "drivers": ["驅動因素 1", "驅動因素 2", "驅動因素 3"],
  "risks": ["風險 1", "風險 2"],
  "key_players": ["關鍵公司 1（為什麼）", "關鍵公司 2（為什麼）"],
  "outlook": "未來 1-2 年展望（50-80 字）",
  "indicators": [
    { "label": "事件 / 技術", "value": "具體名詞" },
    { "label": "市場規模", "value": "USD XXB" },
    { "label": "CAGR", "value": "XX%" },
    { "label": "毛利水準", "value": "XX-XX%" }
  ]
}

規則：
- 內容須對齊台灣產業實際情況（不要套用美國案例）
- 引用具體公司名 / 技術名 / 客戶名
- 數字若無確定來源用區間（如「20-30%」）並標 (估)
- 不要憑空製造 ticker，只用提供的成分股`;

export const onRequestPost = async (ctx: RequestCtx) => {
  const guard = requireRole(ctx.data.user, "admin");
  if (guard) return guard;

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  const group = String(body?.group ?? "").trim();
  const tickers = Array.isArray(body?.tickers) ? body.tickers : [];
  const context = String(body?.context ?? "").trim();

  if (!group) return jsonError("group 必填", 400);

  try {
    const resp = await callAnthropic(ctx.env, {
      max_tokens: 2000,
      temperature: 0.4,
      system: [
        { type: "text", text: SYSTEM_INSTRUCTION, cache_control: { type: "ephemeral" } },
      ],
      messages: [{
        role: "user",
        content: `族群名：${group}
成分股 ticker：${tickers.length > 0 ? tickers.join(", ") : "（未提供）"}
${context ? `\n補充 context：\n${context}` : ""}

請依規則輸出 JSON 分析。`,
      }],
    });

    const raw = extractText(resp);
    const parsed = tryParseJson(raw);
    if (!parsed) {
      return jsonOk({ raw, parse_failed: true, cache_stats: cacheStats(resp) });
    }
    return jsonOk({ group, ...parsed, raw, cache_stats: cacheStats(resp) });
  } catch (e: any) {
    return jsonError(`AI 分析失敗：${e.message}`, 502);
  }
};
