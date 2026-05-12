import { SearchRequest, SearchResponse } from "./types";

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
