import React from "react";
import { SearchResponse } from "../types";

interface Props {
  response: SearchResponse;
}

export default function ResultsMeta({ response }: Props) {
  const latencySec = (response.latency_ms / 1000).toFixed(1);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-1">
      <div>
        <p className="text-sm font-semibold text-slate-800">
          Trials you may be eligible for —{" "}
          <span className="text-brand-600">{response.normalized_condition || "your condition"}</span>
        </p>
        <p className="text-xs text-slate-500 mt-0.5">
          {response.candidates_retrieved} candidates screened · {response.results.length} likely eligible
        </p>
      </div>

      <div className="flex items-center gap-1.5 text-xs text-slate-400 bg-slate-100 px-3 py-1.5 rounded-full">
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        {latencySec}s
      </div>
    </div>
  );
}
