export interface ScreeningResult {
  nct_id: string;
  title: string;
  eligible: boolean;
  confidence: number;
  reason: string;
  key_criteria_met: string[];
  key_criteria_failed: string[];
  url: string;
  latency_ms: number;
}

export interface SearchResponse {
  query_id: string;
  normalized_condition: string;
  candidates_retrieved: number;
  results: ScreeningResult[];
  latency_ms: number;
}

export interface SearchRequest {
  symptoms: string;
  max_results: number;
  status_filter: string;
}
