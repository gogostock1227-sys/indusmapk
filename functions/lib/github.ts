// GitHub Contents API wrapper：讀寫 repo 檔案 + 觸發 workflow_dispatch
import type { Env } from "./types";

const API = "https://api.github.com";
const UA = "indusmapk-admin/1.0";

interface ContentsResponse {
  content: string;        // base64
  sha: string;
  encoding: "base64";
  path: string;
}

function b64encode(s: string): string {
  // unicode-safe base64：先 utf-8 編碼再 btoa
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

function b64decode(s: string): string {
  const bin = atob(s.replace(/\n/g, ""));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

async function gh(env: Env, path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": UA,
      ...(init.headers || {}),
    },
  });
  return res;
}

export interface GhFile {
  content: string;        // 解碼後的明文
  sha: string;
}

export async function getFile(env: Env, filePath: string): Promise<GhFile | null> {
  const res = await gh(env, `/repos/${env.GITHUB_REPO}/contents/${filePath}`);
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`GitHub getFile ${filePath} failed: ${res.status} ${await res.text()}`);
  }
  const data = (await res.json()) as ContentsResponse;
  return {
    content: b64decode(data.content),
    sha: data.sha,
  };
}

export interface PutFileOptions {
  branch?: string;        // 預設 main
}

/**
 * 寫檔到 GitHub。內建 409 sha 衝突重試一次。
 * 若兩次都失敗，throw 帶有 conflict=true 的錯誤讓 caller 提示用戶。
 */
export async function putFile(
  env: Env,
  filePath: string,
  content: string,
  commitMessage: string,
  authorEmail: string,
  opts: PutFileOptions = {},
): Promise<{ commitSha: string }> {
  for (let attempt = 0; attempt < 2; attempt++) {
    const existing = await getFile(env, filePath);
    const body: Record<string, unknown> = {
      message: commitMessage,
      content: b64encode(content),
      author: {
        name: authorEmail.split("@")[0] || authorEmail,
        email: authorEmail,
      },
      committer: {
        name: "indusmapk-admin",
        email: "noreply@indusmapk.com",
      },
    };
    if (existing) body.sha = existing.sha;
    if (opts.branch) body.branch = opts.branch;

    const res = await gh(env, `/repos/${env.GITHUB_REPO}/contents/${filePath}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });

    if (res.ok) {
      const data = (await res.json()) as { commit: { sha: string } };
      return { commitSha: data.commit.sha };
    }

    // 409 = sha conflict，重試一次
    if (res.status === 409 && attempt === 0) continue;

    const errText = await res.text();
    const err = new Error(
      `GitHub putFile ${filePath} failed: ${res.status} ${errText}`,
    ) as Error & { conflict?: boolean };
    if (res.status === 409) err.conflict = true;
    throw err;
  }
  throw new Error("unreachable");
}

export async function triggerWorkflow(
  env: Env,
  workflowFile: string,
  inputs: Record<string, string> = {},
  ref = "main",
): Promise<void> {
  const res = await gh(
    env,
    `/repos/${env.GITHUB_REPO}/actions/workflows/${workflowFile}/dispatches`,
    {
      method: "POST",
      body: JSON.stringify({ ref, inputs }),
    },
  );
  if (!res.ok) {
    throw new Error(
      `GitHub triggerWorkflow ${workflowFile} failed: ${res.status} ${await res.text()}`,
    );
  }
}

export interface WorkflowRun {
  id: number;
  name: string;
  status: string;          // queued / in_progress / completed
  conclusion: string | null;
  html_url: string;
  created_at: string;
  updated_at: string;
}

export async function listRecentRuns(
  env: Env,
  workflowFile: string,
  perPage = 5,
): Promise<WorkflowRun[]> {
  const res = await gh(
    env,
    `/repos/${env.GITHUB_REPO}/actions/workflows/${workflowFile}/runs?per_page=${perPage}`,
  );
  if (!res.ok) throw new Error(`listRecentRuns failed: ${res.status}`);
  const data = (await res.json()) as { workflow_runs: WorkflowRun[] };
  return data.workflow_runs;
}
