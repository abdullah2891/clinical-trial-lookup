import { AgentEvent, ExperimentsResponse, SearchRequest, SearchResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_URL ?? "";

// ── Demo password ───────────────────────────────────────────────────────────────
const PW_KEY = "demo_pw";

export const getPassword = (): string => localStorage.getItem(PW_KEY) ?? "";
export const setPassword = (p: string): void => localStorage.setItem(PW_KEY, p);
export const clearPassword = (): void => localStorage.removeItem(PW_KEY);

let onAuthError: () => void = () => {};
export const setAuthErrorHandler = (fn: () => void): void => { onAuthError = fn; };

const authHeaders = (): Record<string, string> => ({ "X-Demo-Password": getPassword() });

function check401(status: number): void {
  if (status === 401) {
    clearPassword();
    onAuthError();
  }
}

export async function login(password: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!resp.ok) {
    throw new Error(resp.status === 401 ? "Incorrect password" : `Login failed (${resp.status})`);
  }
  setPassword(password);
}

export async function searchTrials(request: SearchRequest): Promise<SearchResponse> {
  const resp = await fetch(`${API_BASE}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(request),
  });

  if (!resp.ok) {
    check401(resp.status);
    const text = await resp.text();
    throw new Error(`Search failed (${resp.status}): ${text}`);
  }

  return resp.json() as Promise<SearchResponse>;
}

export async function fetchExperiments(): Promise<ExperimentsResponse> {
  const resp = await fetch(`${API_BASE}/experiments`, { headers: authHeaders() });
  if (!resp.ok) {
    check401(resp.status);
    throw new Error(`Failed to load experiments (${resp.status})`);
  }
  return resp.json() as Promise<ExperimentsResponse>;
}

export async function streamAgentSearch(
  question: string,
  onEvent: (event: AgentEvent) => void,
  clarifications = "",
): Promise<void> {
  const resp = await fetch(`${API_BASE}/agent/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ question, clarifications }),
  });
  if (!resp.ok || !resp.body) {
    check401(resp.status);
    throw new Error(`Agent search failed (${resp.status})`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()) as AgentEvent);
      } catch {
        // skip malformed frame
      }
    }
  }
}

export type EvalSuite = "screener" | "agent" | "guardrail";

export async function runExperiment(suite: EvalSuite = "screener"): Promise<void> {
  const resp = await fetch(`${API_BASE}/experiments/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ suite }),
  });
  if (!resp.ok) {
    check401(resp.status);
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail ?? `Failed to start experiment (${resp.status})`);
  }
}
