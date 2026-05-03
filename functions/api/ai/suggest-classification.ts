// POST /api/ai/suggest-classification
// body: {
//   ticker:           "2330",
//   name?:            "台積電",
//   business_summary: "...",
//   twse_industry?:   "半導體業",
//   current_groups?:  ["輝達概念股", ...]   // 已有的歸屬，給 AI 參考
// }
// 回: {
//   recommended_groups: [{name, confidence, reasoning}],
//   suggested_segment: "AI_SEMI",
//   suggested_position: "FOUNDRY",
//   raw: <Claude 原文>,
//   cache_stats: {...}
// }
//
// 設計：候選族群清單（從 GitHub data/concept_groups.json 取所有 keys，~989 族群名）
// 放 system 段 + cache_control，每次呼叫只重算 user 段，省 token 80%+。
import type { RequestCtx } from "../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../lib/auth-guard";
import { callAnthropic, extractText, tryParseJson, cacheStats } from "../../lib/anthropic";
import { getFile } from "../../lib/github";

const SYSTEM_INSTRUCTION = `你是台股族群分類專家。

任務：給定一支個股的名稱、TWSE 產業、業務描述，從候選族群清單中推薦最合適的歸屬，並建議產業段（industry_segment）與供應鏈位階（supply_chain_position）。

輸出格式（必須是 valid JSON，不要解釋、不要 markdown 包裝）：
{
  "recommended_groups": [
    { "name": "族群名（必須來自候選清單）", "confidence": 0.0-1.0, "reasoning": "為什麼歸這個族群（引用 business_summary 具體文字）" }
  ],
  "suggested_segment": "AI_SEMI / ELEC_COMP / NETCOM / IC_DESIGN / FOUNDRY / OSAT_ADV / SUBSTRATE / PCB / THERMAL / POWER / OPTICAL / NETWORK / CONNECTOR / PASSIVE / AUTO / DEFENSE / CONSUMER / DISPLAY / SHIPPING / FINANCE / TRADITIONAL / BIOTECH / EVENT / SIC_GAN / NICHE / POLICY / CHANNEL / CLOUD / SPORTS / ENERGY / CHEMICAL / BUILDING / MEDIA / OTHER",
  "suggested_position": "IP / IC_DESIGN / FOUNDRY / OSAT_ADV / OSAT / SUBSTRATE / PCB / EMS / ODM / BRAND / DISTRIBUTOR / OTHER",
  "notes": "整體判斷簡述（< 80 字）"
}

規則：
- recommended_groups 至多 5 個，按 confidence 降序排列
- confidence < 0.7 表示信心不足，admin UI 會以紅色標示
- 推薦理由必須引用 business_summary 內具體文字片段（用引號）
- 如果 candidates 沒有合適族群，recommended_groups 可為空陣列`;

export const onRequestPost = async (ctx: RequestCtx) => {
  const guard = requireRole(ctx.data.user, "admin");
  if (guard) return guard;

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  const ticker = String(body?.ticker ?? "").trim();
  const name = String(body?.name ?? "").trim();
  const summary = String(body?.business_summary ?? "").trim();
  const twseInd = String(body?.twse_industry ?? "").trim();
  const current = Array.isArray(body?.current_groups) ? body.current_groups : [];

  if (!ticker) return jsonError("ticker 必填", 400);
  if (!summary) return jsonError("business_summary 必填", 400);

  // 從 GitHub 讀候選族群清單（concept_groups.json 的 keys）
  let candidates: string[] = [];
  try {
    const file = await getFile(ctx.env, "data/concept_groups.json");
    if (file) {
      const cg = JSON.parse(file.content);
      candidates = Object.keys(cg);
    }
  } catch { /* 候選清單抓不到時降級為空，AI 直接判斷 */ }

  const candidatesText = candidates.length > 0
    ? candidates.join("、")
    : "（候選清單未提供，請依 business_summary 直接命名族群）";

  try {
    const resp = await callAnthropic(ctx.env, {
      max_tokens: 1500,
      temperature: 0.3,
      system: [
        {
          type: "text",
          text: SYSTEM_INSTRUCTION + "\n\n候選族群清單（共 " + candidates.length + " 個）：\n" + candidatesText,
          cache_control: { type: "ephemeral" },
        },
      ],
      messages: [{
        role: "user",
        content: [{
          type: "text",
          text: `個股：${ticker} ${name}
TWSE 產業：${twseInd || "（未提供）"}
目前歸屬族群：${current.length > 0 ? current.join("、") : "（無）"}

業務描述：
${summary}

請依規則輸出 JSON。`,
        }],
      }],
    });

    const raw = extractText(resp);
    const parsed = tryParseJson(raw);
    if (!parsed) {
      return jsonOk({ raw, parse_failed: true, cache_stats: cacheStats(resp) });
    }
    return jsonOk({ ...parsed, raw, cache_stats: cacheStats(resp) });
  } catch (e: any) {
    return jsonError(`AI 推薦失敗：${e.message}`, 502);
  }
};
