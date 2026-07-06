import { AgentEvent, ExperimentsResponse, SearchRequest, SearchResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_URL ?? "";

export async function searchTrials(request: SearchRequest): Promise<SearchResponse> {
  const resp = await fetch(`${API_BASE}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Search failed (${resp.status}): ${text}`);
  }

  return resp.json() as Promise<SearchResponse>;
}

export async function fetchExperiments(): Promise<ExperimentsResponse> {
  const resp = await fetch(`${API_BASE}/experiments`);
  if (!resp.ok) {
    throw new Error(`Failed to load experiments (${resp.status})`);
  }
  return resp.json() as Promise<ExperimentsResponse>;
}

export async function streamAgentSearch(
  question: string,
  onEvent: (event: AgentEvent) => void,
): Promise<void> {
  const resp = await fetch(`${API_BASE}/agent/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!resp.ok || !resp.body) {
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

export async function runExperiment(): Promise<void> {
  const resp = await fetch(`${API_BASE}/experiments/run`, { method: "POST" });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail ?? `Failed to start experiment (${resp.status})`);
  }
}
