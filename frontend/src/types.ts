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

export interface Experiment {
  name: string;
  start_time: string;
  run_count: number | null;
  accuracy: number | null;
  confidence_abs_error: number | null;
}

export interface ExperimentsResponse {
  langsmith_configured: boolean;
  running: boolean;
  last_error: string | null;
  experiments: Experiment[];
}
