export interface Experiment {
  name: string;
  dataset: string;
  start_time: string;
  run_count: number | null;
  scores: Record<string, number>;
}

export interface AgentTrial {
  nct_id: string;
  title: string;
  url: string;
  conditions: string[];
  similarity: number;
}

export interface RetrievalResult {
  query: string;
  count: number;
  top: { nct_id: string; title: string; similarity: number }[];
}

export type AgentEvent =
  | { type: "clarification"; questions: string[] }
  | { type: "sub_questions"; sub_questions: string[] }
  | { type: "retrieval"; round: number; results: RetrievalResult[]; total_unique: number }
  | { type: "analysis"; iteration: number; decision: "refine" | "answer"; reasoning: string; new_queries: string[] }
  | { type: "answer"; answer: string; trials: AgentTrial[] }
  | { type: "done" }
  | { type: "error"; detail: string };

export interface ExperimentsResponse {
  langsmith_configured: boolean;
  running: boolean;
  last_error: string | null;
  experiments: Experiment[];
}
