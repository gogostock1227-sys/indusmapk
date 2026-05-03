// POST /api/ai/suggest-position
// body: { ticker, name?, business_summary, current_segment?, current_position? }
// 回: { suggested_position, suggested_segment, confidence, reasoning, raw }
//
// 比 suggest-classification 更精準聚焦在「供應鏈位階」單一維度。適合 admin
// 在已知 industry_segment 後微調 supply_chain_position 用。
import type { RequestCtx } from "../../lib/types";
import { requireRole, jsonOk, jsonError } from "../../lib/auth-guard";
import { callAnthropic, extractText, tryParseJson, cacheStats } from "../../lib/anthropic";

const POSITION_TAXONOMY = `供應鏈位階白名單：
- IP            (IP 矽智財：智原、力旺、創意 — 提供電路設計授權)
- IC_DESIGN     (IC 設計：聯發科、瑞昱、聯詠 — 純設計，不做晶圓)
- FOUNDRY       (晶圓代工：台積電、聯電、世界先進)
- OSAT_ADV      (先進封裝：日月光投控、矽品 — CoWoS / SoIC / FOPLP)
- OSAT          (傳統封測：京元電、超豐)
- SUBSTRATE     (IC 載板：欣興、南電、景碩 — ABF / BT 載板)
- PCB           (PCB / HDI：健鼎、定穎、台光電)
- EMS           (代工製造：鴻海、和碩 — Tier 1 ODM/EMS)
- ODM           (品牌代設計：廣達、英業達 — 含設計能力)
- BRAND         (品牌：華碩、宏碁 — 自有品牌)
- DISTRIBUTOR   (通路：大聯大、文曄 — 半導體通路)
- OTHER         (其他/不適用)`;

const SYSTEM_INSTRUCTION = `你是台股供應鏈位階分類專家。給定個股業務描述，判斷它在供應鏈中的位階。

${POSITION_TAXONOMY}

輸出（valid JSON，不要 markdown 包裝）：
{
  "suggested_position": "上述白名單之一",
  "suggested_segment": "AI_SEMI / ELEC_COMP / NETCOM / 等",
  "confidence": 0.0-1.0,
  "reasoning": "判斷依據（引用業務描述具體文字）"
}`;

export const onRequestPost = async (ctx: RequestCtx) => {
  const guard = requireRole(ctx.data.user, "admin");
  if (guard) return guard;

  let body: any;
  try { body = await ctx.request.json(); }
  catch { return jsonError("invalid json", 400); }

  const ticker = String(body?.ticker ?? "").trim();
  const name = String(body?.name ?? "").trim();
  const summary = String(body?.business_summary ?? "").trim();
  const curSeg = String(body?.current_segment ?? "").trim();
  const curPos = String(body?.current_position ?? "").trim();

  if (!ticker) return jsonError("ticker 必填", 400);
  if (!summary) return jsonError("business_summary 必填", 400);

  try {
    const resp = await callAnthropic(ctx.env, {
      max_tokens: 800,
      temperature: 0.2,
      system: [
        { type: "text", text: SYSTEM_INSTRUCTION, cache_control: { type: "ephemeral" } },
      ],
      messages: [{
        role: "user",
        content: `個股：${ticker} ${name}
目前段：${curSeg || "（未指定）"}
目前位階：${curPos || "（未指定）"}

業務描述：
${summary}

請判斷供應鏈位階。`,
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
