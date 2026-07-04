import { ExperimentsResponse, SearchRequest, SearchResponse } from "./types";

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

export async function runExperiment(): Promise<void> {
  const resp = await fetch(`${API_BASE}/experiments/run`, { method: "POST" });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail ?? `Failed to start experiment (${resp.status})`);
  }
}
